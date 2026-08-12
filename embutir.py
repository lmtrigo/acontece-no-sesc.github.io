#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Injeta os dados coletados dentro de prototipo.html.

O protótipo é um arquivo único (é assim que ele vira link compartilhável), então
os dados entram embutidos, entre os marcadores:

    /* DADOS:INICIO */ ... /* DADOS:FIM */

Uso:
    python embutir.py                          # dados/eventos.json -> prototipo.html
    python embutir.py --max 800                # limita o volume embutido
"""

import argparse
import json
import os
import re
from datetime import date

import regras

MARCADOR = re.compile(
    r"/\* DADOS:INICIO \*/.*?/\* DADOS:FIM \*/",
    re.DOTALL,
)

# Campos que o app realmente lê. Tudo o que não estiver aqui fica de fora do
# arquivo publicado — o eventos.json completo continua no disco.
CAMPOS = ("id", "tit", "sub", "uni", "reg", "cat", "subcat", "publico",
          "projeto", "gratis", "pago", "online", "esgotado", "ingressosWeb",
          "temporada", "hora", "inicio", "fim", "link", "dias",
          # segunda passada (detalhes.py)
          "precos", "sessoes", "vendaOnline", "vendaPresencial", "vendaOnlineFim",
          "urlCompra", "maxPorPessoa", "classificacao", "endereco", "geo",
          "inscricao", "sorteados")
# `desc` fica de fora de propósito: 2,5 mil textos pesariam no download de
# todo mundo para serem lidos um de cada vez. O app busca por evento, em
# dados/desc/<id>.json, e descarta ao fechar.
#
# Exceção: o arquivo único (prévia por link) não tem servidor ao lado, então
# lá a busca falha e o evento fica sem descrição. `--com-descricao` embute
# mesmo assim, para quando a prévia é o que vai ser mostrado.


def enxugar(ev, limite_sub=170, com_desc=False):
    """Mantém só o necessário e corta o complemento longo.

    O complemento é texto do portal; guardamos um resumo curto e mandamos
    o leitor para a página oficial pelo link.
    """
    out = {}
    if com_desc and ev.get("desc"):
        out["desc"] = ev["desc"]
    for c in CAMPOS:
        v = ev.get(c)
        if v is None or v == "" or v is False:
            continue
        if c == "sub" and isinstance(v, str) and len(v) > limite_sub:
            v = v[:limite_sub].rsplit(" ", 1)[0] + "…"
        out[c] = v
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dados", default=os.path.join("dados", "eventos.json"))
    p.add_argument("--html", default="prototipo.html")
    p.add_argument("--max", type=int, default=0, help="0 = todos")
    p.add_argument("--sem-projeto", action="store_true",
                   help="remove os eventos que pertencem a um projeto "
                        "(por padrão eles ficam e viram filtro no app)")
    p.add_argument("--manter", nargs="*", default=[],
                   help="projetos a preservar mesmo com a remoção ligada, "
                        'ex: --manter "Palco Giratório" "Agosto Indígena"')
    p.add_argument("--com-descricao", action="store_true",
                   help="embute as descrições no arquivo único (a prévia por "
                        "link não tem servidor para buscá-las sob demanda)")
    p.add_argument("--horizonte", type=int, default=60,
                   help="dias à frente para a regra de retenção")
    p.add_argument("--sem-retencao", action="store_true",
                   help="mantém tudo o que foi coletado, sem aplicar a regra")
    p.add_argument("--sem-excecao-sorteio", action="store_true",
                   help="remove também os eventos de projeto que têm sorteio "
                        "(por padrão eles ficam, senão a aba Meus Sorteios "
                        "perde quase todo o Turismo Social)")
    args = p.parse_args()

    with open(args.dados, encoding="utf-8") as f:
        d = json.load(f)

    eventos = d["eventos"]

    if not args.sem_retencao:
        hoje = max(date.today().isoformat(), d["janela"]["de"])
        eventos = regras.aplicar(eventos, hoje, args.horizonte)

    # Eventos de projeto são temporadas e programas recorrentes que repetem a
    # mesma atividade dezenas de vezes; fora da agenda, a lista fica navegável.
    if args.sem_projeto:
        manter = set(args.manter)

        def tem_sorteio(e):
            if e.get("sorteados"):
                return True
            i = e.get("inscricao") or {}
            return bool(i.get("temSorteio"))

        def fica(e):
            if not e.get("projeto"):
                return True
            if e["projeto"] in manter:
                return True
            # exceção: sem isso, "Turismo Social" quase some e a conferência
            # automática de sorteio fica sem base para comparar
            return tem_sorteio(e) and not args.sem_excecao_sorteio

        antes = len(eventos)
        eventos = [e for e in eventos if fica(e)]
        resgatados = sum(1 for e in eventos if e.get("projeto"))
        print("Removidos %d eventos de projeto · %d preservados (sorteio ou --manter)"
              % (antes - len(eventos), resgatados))
    if args.max and len(eventos) > args.max:
        # mantém a proporção entre regiões em vez de cortar o fim da lista
        por_reg = {}
        for e in eventos:
            por_reg.setdefault(e["reg"], []).append(e)
        total = len(eventos)
        escolhidos = []
        for reg, lista in por_reg.items():
            cota = max(1, round(args.max * len(lista) / total))
            escolhidos.extend(lista[:cota])
        eventos = escolhidos[:args.max]
        print("Reduzido para %d eventos (proporcional por região)" % len(eventos))

    pacote = {
        "fonte": d.get("fonte"),
        "geradoEm": d.get("geradoEm"),
        "janela": d.get("janela"),
        "unidades": d.get("unidades"),
        "eventos": [enxugar(e, com_desc=args.com_descricao) for e in eventos],
    }

    js = "/* DADOS:INICIO */\n  var DADOS = " + json.dumps(
        pacote, ensure_ascii=False, separators=(",", ":")) + ";\n  /* DADOS:FIM */"

    with open(args.html, encoding="utf-8") as f:
        html = f.read()

    if not MARCADOR.search(html):
        raise SystemExit("Marcadores /* DADOS:INICIO */ … /* DADOS:FIM */ "
                         "não encontrados em " + args.html)

    novo = MARCADOR.sub(lambda _: js, html, count=1)

    with open(args.html, "w", encoding="utf-8", newline="\n") as f:
        f.write(novo)

    ocorr = sum(len(e.get("dias", [])) for e in pacote["eventos"])
    print("Embutidos %d eventos · %d ocorrências · HTML com %.0f KB"
          % (len(pacote["eventos"]), ocorr, os.path.getsize(args.html) / 1024))


if __name__ == "__main__":
    main()
