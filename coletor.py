#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coletor da programação do Sesc São Paulo.

Fonte: API REST pública do portal (WordPress).
  GET /wp-json/wp/v1/unidades-atividades
      -> lista de unidades, com a região em `description` (capital|interior|litoral)
  GET /wp-json/wp/v1/atividades/filter?data_inicial=&data_final=&ppp=&page=
      -> atividades no intervalo; envelope {editorial, atividade[], total{value}}

Estratégia: uma consulta por DIA. É o único jeito de saber em quais dias cada
atividade acontece — o endpoint devolve `dataPrimeiraSessao`/`dataUltimaSessao`
do evento inteiro, não da sessão daquele dia.

Limitações conhecidas da fonte (documentadas, não contornadas aqui):
  - não há nota da crítica nem avaliação de público;
  - não há data de abertura/encerramento de inscrição nem dados de sorteio
    (isso vive na página de cada atividade, exigiria uma requisição por evento);
  - para temporadas longas, o horário de cada sessão específica não vem na
    listagem; usamos o horário da primeira sessão como representativo.

Uso:
    python coletor.py                      # 30 dias a partir de hoje
    python coletor.py --dias 14
    python coletor.py --de 2026-08-11 --ate 2026-09-10
    python coletor.py --regioes capital litoral
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# O robô roda em UTC (GitHub Actions) e quem lê está em São Paulo. Sem fixar o
# fuso, a hora da coleta aparecia três horas adiantada no app e uma execução
# de madrugada carimbava o dia seguinte. O Brasil não usa mais horário de
# verão desde 2019, então o desvio é constante.
FUSO_BR = timezone(timedelta(hours=-3))


def agora_br():
    return datetime.now(FUSO_BR)

BASE = "https://www.sescsp.org.br"
API_UNIDADES = BASE + "/wp-json/wp/v1/unidades-atividades"
API_ATIVIDADES = BASE + "/wp-json/wp/v1/atividades/filter"

PPP = 300
PAUSA = 0.35          # segundos entre requisições — o portal não é nosso
TIMEOUT = 30
TENTATIVAS = 3

UA = "agenda-sesc-prototipo/1.0 (coletor de programacao publica; uso pessoal)"

REGIOES_VALIDAS = ("capital", "interior", "litoral")


def buscar(url, tentativa=1):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        if tentativa >= TENTATIVAS:
            raise
        espera = 2 ** tentativa
        print("    ! falhou (%s), repetindo em %ds" % (e, espera), file=sys.stderr)
        time.sleep(espera)
        return buscar(url, tentativa + 1)


def carregar_unidades():
    """Devolve {nome_da_unidade: regiao}."""
    dados = buscar(API_UNIDADES)
    mapa = {}
    for u in dados:
        nome = (u.get("name") or "").strip()
        regiao = (u.get("description") or "").strip().lower()
        if nome:
            mapa[nome] = regiao if regiao in REGIOES_VALIDAS else "outra"
    return mapa


def url_geral(page):
    """Listagem sem filtro de data — a rede de segurança."""
    q = urllib.parse.urlencode({
        "tipo": "atividade", "dinamico": "true", "ppp": PPP, "page": page,
    })
    return API_ATIVIDADES + "?" + q


def url_dia(dia, page):
    q = urllib.parse.urlencode({
        "local": "", "categoria": "", "gratuito": "", "online": "",
        "publico": "", "atividade": "", "linguagem": "",
        "data_inicial": dia, "data_final": dia,
        "tipo": "atividade", "dinamico": "true",
        "ppp": PPP, "page": page,
    })
    return API_ATIVIDADES + "?" + q


def primeiro(lista, campo="name"):
    if isinstance(lista, list) and lista:
        v = lista[0]
        if isinstance(v, dict):
            return v.get(campo) or v.get("titulo") or v.get("name")
    return None


def hora_de(iso):
    if isinstance(iso, str) and "T" in iso:
        return iso.split("T")[1][:5]
    return None


def dia_de(iso):
    if isinstance(iso, str) and "T" in iso:
        return iso.split("T")[0]
    if isinstance(iso, str) and len(iso) == 10:
        return iso
    return None


def normalizar(a, unidades):
    """Achata um item da API no formato que o app consome."""
    uni = primeiro(a.get("unidade")) or "—"
    ling = a.get("tipos_linguagens") or []
    cat = sub = None
    if ling and isinstance(ling[0], dict):
        cat = ling[0].get("titulo")
        filhos = ling[0].get("children") or []
        if filhos and isinstance(filhos[0], dict):
            sub = filhos[0].get("titulo")

    gratuito = (a.get("gratuito") or "").strip()
    link = a.get("link") or ""
    if link.startswith("/"):
        link = BASE + link

    return {
        "id": a.get("id"),
        # chave da bilheteria: abre portal.sescsp.org.br/bilheteria/atividade.action
        "idJava": a.get("id_java"),
        "tit": (a.get("titulo") or "").strip(),
        "sub": (a.get("complemento") or "").strip(),
        "uni": uni,
        "reg": unidades.get(uni, "outra"),
        "cat": cat or "Outros",
        "subcat": sub,
        "publico": primeiro(a.get("publico_tag"), "titulo"),
        "projeto": primeiro(a.get("conjunto")),
        "gratis": gratuito == "Atividade gratuita",
        "pago": gratuito == "Atividade paga",
        "online": bool((a.get("online") or "").strip()),
        "esgotado": bool((a.get("esgotado") or "").strip()),
        "cancelado": bool((a.get("cancelado") or "").strip()),
        "ingressosWeb": a.get("qtdeIngressosWeb"),
        "temporada": bool((a.get("quantDatas") or "").strip()),
        "hora": hora_de(a.get("dataPrimeiraSessao")),
        "inicio": dia_de(a.get("dataPrimeiraSessao")),
        "fim": dia_de(a.get("dataUltimaSessao")),
        "link": link,
        "dias": [],
    }


CONTINUOS = ("Turismo Social",)


def expandir_viagens(lista, de, ate):
    """Preenche os dias do meio de um passeio de vários dias.

    Uma viagem de 11 a 16/8 acontece nos seis dias, mas a listagem devolve o
    evento em uns dias e não em outros — resultado: o passeio aparecia só na
    primeira data da agenda.

    Só vale para categorias contínuas por natureza. Uma exposição também tem
    início e fim distantes, mas fecha às segundas: ali os dias coletados é
    que estão certos, e preencher o intervalo seria inventar.
    """
    n = 0
    for e in lista:
        if e["cat"] not in CONTINUOS:
            continue
        ini, fim = e.get("inicio"), e.get("fim")
        if not ini or not fim or ini == fim:
            continue
        d0 = datetime.strptime(ini, "%Y-%m-%d").date()
        d1 = datetime.strptime(fim, "%Y-%m-%d").date()
        if (d1 - d0).days > 60:      # não é viagem, é engano de cadastro
            continue
        todos = []
        d = max(d0, de)
        while d <= min(d1, ate):
            todos.append(d.isoformat())
            d += timedelta(days=1)
        if not todos or len(todos) < 2:
            continue
        # marca como contínuo mesmo quando a listagem já trouxe todos os dias:
        # é a marca que faz o app tratar a viagem como um intervalo só
        if todos != e["dias"]:
            e["dias"] = todos
            n += 1
        e["continuo"] = True
    if n:
        print("Preenchido o intervalo de %d passeios de vários dias" % n)
    return n


def coletar(de, ate, regioes):
    unidades = carregar_unidades()
    print("Unidades: %d (%s)" % (
        len(unidades),
        ", ".join("%s=%d" % (r, sum(1 for v in unidades.values() if v == r))
                  for r in REGIOES_VALIDAS)))

    eventos = {}
    dia = de
    total_dias = (ate - de).days + 1
    n = 0

    while dia <= ate:
        n += 1
        iso = dia.isoformat()
        page = 1
        do_dia = 0
        while True:
            envelope = buscar(url_dia(iso, page))
            itens = envelope.get("atividade") or []
            total = (envelope.get("total") or {}).get("value", 0)

            for a in itens:
                # a API devolve buracos (null) no meio da lista
                if not isinstance(a, dict):
                    continue
                eid = a.get("id")
                if eid is None:
                    continue
                if eid not in eventos:
                    eventos[eid] = normalizar(a, unidades)
                if iso not in eventos[eid]["dias"]:
                    eventos[eid]["dias"].append(iso)
                do_dia += 1

            if page * PPP >= total or not itens:
                break
            page += 1
            time.sleep(PAUSA)

        print("  [%2d/%2d] %s  %4d sessões  (acumulado: %d eventos)"
              % (n, total_dias, iso, do_dia, len(eventos)))
        dia += timedelta(days=1)
        time.sleep(PAUSA)

    # ------------------------------------------------------------------
    # Rede de segurança: o filtro de data da API deixa eventos de fora.
    # "Ecos da Independência" (12/09) não volta na consulta de 12/09, mas
    # aparece na listagem sem filtro. Então varremos tudo e recuperamos o
    # que ficou faltando, usando as datas do próprio registro.
    # ------------------------------------------------------------------
    print("Varredura de segurança (listagem sem filtro de data)…")
    page, recuperados = 1, 0
    while True:
        envelope = buscar(url_geral(page))
        itens = envelope.get("atividade") or []
        total = (envelope.get("total") or {}).get("value", 0)

        for a in itens:
            if not isinstance(a, dict):
                continue
            eid = a.get("id")
            if eid is None or eid in eventos:
                continue
            ini = dia_de(a.get("dataPrimeiraSessao"))
            fim = dia_de(a.get("dataUltimaSessao")) or ini
            if not ini:
                continue
            if fim < de.isoformat() or ini > ate.isoformat():
                continue

            ev = normalizar(a, unidades)
            # não sabemos os dias intermediários de uma temporada; ficam a
            # primeira e a última, e detalhes.py corrige quando há bilheteria
            dias = {ini} if ini == fim else {ini, fim}
            ev["dias"] = sorted(d for d in dias if de.isoformat() <= d <= ate.isoformat())
            if not ev["dias"]:
                continue
            ev["parcial"] = ini != fim
            eventos[eid] = ev
            recuperados += 1

        if page * PPP >= total or not itens:
            break
        page += 1
        time.sleep(PAUSA)

    print("  recuperados %d eventos que o filtro de data não devolveu" % recuperados)

    lista = list(eventos.values())

    if regioes:
        antes = len(lista)
        lista = [e for e in lista if e["reg"] in regioes]
        print("Filtro de região %s: %d -> %d eventos" % (regioes, antes, len(lista)))

    # Descartado agora só o cancelado. "Outros" é o balde do que o portal não
    # categorizou — jogá-lo fora tirava da agenda atividades que existem de
    # verdade, e a única coisa que faltava nelas era o rótulo.
    antes = len(lista)
    lista = [e for e in lista if not e["cancelado"]]
    print("Descartados %d cancelados" % (antes - len(lista)))
    sem_cat = sum(1 for e in lista if e["cat"] == "Outros")
    if sem_cat:
        print("Mantidos %d eventos sem categoria (entram como \"Outros\")" % sem_cat)

    for e in lista:
        e["dias"].sort()

    expandir_viagens(lista, de, ate)

    lista.sort(key=lambda e: (e["dias"][0] if e["dias"] else "9999", e["tit"]))
    return lista, unidades


def carimbar_estreia(lista, caminho_anterior, hoje):
    """Marca em `visto` o dia em que cada evento apareceu pela primeira vez.

    Novidade só se sabe comparando com a coleta anterior, e o app não guarda
    histórico — então o carimbo viaja dentro do próprio arquivo: quem já
    estava lá conserva a data antiga, quem não estava recebe a de hoje.

    A primeira coleta com rastreio não carimba ninguém: ela só estabelece a
    linha de base e grava `rastreioDesde`. Sem isso o primeiro dia mentiria
    duas vezes — o catálogo inteiro apareceria como novo, e uma mudança de
    regra nossa (a entrada dos eventos "Outros", que a coleta antiga jogava
    fora) entraria como se o Sesc tivesse acabado de publicar 359 atividades.

    Quem já estava na base e não tem carimbo fica **sem** carimbo: é anterior
    ao rastreio e não dá para inventar uma data.

    Ressalvas conhecidas: um evento que suma da listagem por um dia e volte
    depois é carimbado de novo, e a janela que anda um dia por vez carimba a
    borda (medido: 3 eventos em 5 dias). Preferimos isso a guardar um
    histórico de ids que cresceria para sempre.

    Devolve a data em que o rastreio começou, para gravar no arquivo.
    """
    try:
        with open(caminho_anterior, encoding="utf-8") as f:
            anterior = json.load(f)
    except (OSError, ValueError):
        anterior = None

    if not anterior:
        print("Sem coleta anterior: linha de base, nenhuma novidade marcada")
        return hoje

    desde = anterior.get("rastreioDesde")
    if not desde:
        print("Primeira coleta com rastreio: linha de base com %d eventos, "
              "nenhuma novidade marcada" % len(anterior.get("eventos") or []))
        return hoje

    antigos = {}
    for e in anterior.get("eventos") or []:
        if e.get("id") is not None:
            antigos[e["id"]] = (e.get("visto") or "")[:10]

    novos = 0
    for e in lista:
        if e["id"] not in antigos:
            e["visto"] = hoje
            novos += 1
        elif antigos[e["id"]]:
            e["visto"] = antigos[e["id"]]
        # já estava lá e não tem carimbo: é anterior ao rastreio
    print("Novidades desta coleta: %d eventos que não estavam na anterior" % novos)
    return desde


def main():
    p = argparse.ArgumentParser(description="Coleta a programação do Sesc SP.")
    p.add_argument("--dias", type=int, default=30, help="janela a partir de hoje")
    p.add_argument("--de", help="data inicial YYYY-MM-DD")
    p.add_argument("--ate", help="data final YYYY-MM-DD")
    p.add_argument("--regioes", nargs="*", default=list(REGIOES_VALIDAS),
                   help="capital interior litoral")
    p.add_argument("--saida", default=os.path.join("dados", "eventos.json"))
    args = p.parse_args()

    hoje = agora_br().date()
    de = datetime.strptime(args.de, "%Y-%m-%d").date() if args.de else hoje
    ate = (datetime.strptime(args.ate, "%Y-%m-%d").date() if args.ate
           else de + timedelta(days=args.dias - 1))

    print("Coletando de %s a %s" % (de, ate))
    inicio = time.time()
    eventos, unidades = coletar(de, ate, set(args.regioes))
    rastreio = carimbar_estreia(eventos, args.saida, hoje.isoformat())

    saida = {
        "fonte": "Sesc São Paulo — portal público (wp-json)",
        "geradoEm": agora_br().isoformat(timespec="seconds"),
        # desde quando dá para dizer o que é novidade (ver carimbar_estreia)
        "rastreioDesde": rastreio,
        "janela": {"de": de.isoformat(), "ate": ate.isoformat()},
        "unidades": [{"nome": k, "regiao": v} for k, v in sorted(unidades.items())],
        "categorias": sorted({e["cat"] for e in eventos}),
        "eventos": eventos,
    }

    os.makedirs(os.path.dirname(args.saida) or ".", exist_ok=True)
    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))

    kb = os.path.getsize(args.saida) / 1024
    ocorrencias = sum(len(e["dias"]) for e in eventos)
    print("\n%d eventos · %d ocorrências · %.0f KB · %.0fs"
          % (len(eventos), ocorrencias, kb, time.time() - inicio))
    print("Escrito em %s" % args.saida)

    por_regiao = {}
    for e in eventos:
        por_regiao[e["reg"]] = por_regiao.get(e["reg"], 0) + 1
    print("Por região: " + ", ".join("%s=%d" % kv for kv in sorted(por_regiao.items())))
    por_cat = {}
    for e in eventos:
        por_cat[e["cat"]] = por_cat.get(e["cat"], 0) + 1
    print("Por categoria: " + ", ".join("%s=%d" % kv for kv in
                                        sorted(por_cat.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
