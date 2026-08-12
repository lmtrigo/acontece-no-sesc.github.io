# -*- coding: utf-8 -*-
"""Regra de retenção — o que entra no app.

O corte deixou de ser pela data do evento e passou a ser pela **data de
entrada**: o que importa para quem usa é conseguir vaga, e a inscrição de um
passeio de novembro abre em agosto. Um recorte por data de evento perderia
exatamente esse caso.

Fica no app quem satisfaz uma destas condições:

  1. a inscrição ou a venda ABRE dentro do horizonte (padrão: 60 dias);
  2. a inscrição ou a venda está ABERTA agora;
  3. o evento acontece dentro do horizonte e não exige inscrição nem compra.

Sai do app o que já encerrou e o que só acontece (e só abre) muito adiante.
"""

from datetime import date, timedelta

DIAS_SEM_PRAZO = 3       # mesma presunção do app quando a página não publica


def _dia(v):
    return v[:10] if isinstance(v, str) and len(v) >= 10 else None


def fim_inscricao(ev):
    """Encerramento real ou presumido (abertura + 3 dias)."""
    i = ev.get("inscricao") or {}
    if not i.get("inscricao"):
        return None
    if i.get("inscricaoFim"):
        return _dia(i["inscricaoFim"])
    ini = _dia(i["inscricao"])
    if not ini:
        return None
    return (date.fromisoformat(ini) + timedelta(days=DIAS_SEM_PRAZO)).isoformat()


def barreira_fechada(ev, hoje):
    """Há evidência de que já não dá para entrar.

    Só conta como fechada o que tem DATA. Um bloco de inscrição em prosa
    ("inscrições no local", "lista de espera") não diz nada sobre prazo, e
    tratá-lo como fechado apagaria centenas de atividades que estão de pé.
    """
    if ev.get("esgotado"):
        return True
    f = fim_inscricao(ev)
    if f and f < hoje:
        return True
    fim_venda = _dia(ev.get("vendaOnlineFim"))
    if fim_venda and fim_venda < hoje:
        return True
    return False


def aberta_agora(ev, hoje):
    i = ev.get("inscricao") or {}
    ini_insc = _dia(i.get("inscricao"))
    if ini_insc and ini_insc <= hoje:
        f = fim_inscricao(ev)
        if f and f >= hoje:
            return True
    venda = _dia(ev.get("vendaOnline")) or _dia(ev.get("vendaPresencial"))
    if venda and venda <= hoje and not barreira_fechada(ev, hoje):
        return True
    return False


SO_COM_INSCRICAO = ("Turismo Social",)


def manter(ev, hoje, horizonte):
    """`hoje` e `horizonte` são strings YYYY-MM-DD."""
    i = ev.get("inscricao") or {}

    # Passeio sem data de inscrição publicada não é oferta: ou já passou da
    # fase (caso dos que só têm o resultado do sorteio na página) ou não dá
    # para saber como entrar. Mostrar isso só gera expectativa vazia.
    if ev.get("cat") in SO_COM_INSCRICAO and not i.get("inscricao"):
        return False

    aberturas = [d for d in (_dia(i.get("inscricao")),
                             _dia(ev.get("vendaOnline")),
                             _dia(ev.get("vendaPresencial"))) if d]

    # 1. a entrada abre dentro do horizonte
    if any(hoje <= d <= horizonte for d in aberturas):
        return True

    # 2. a entrada já está aberta
    if aberta_agora(ev, hoje):
        return True

    # 3. acontece no horizonte e nada indica que a entrada fechou
    if not barreira_fechada(ev, hoje):
        for d in ev.get("dias") or []:
            if hoje <= d <= horizonte:
                return True

    return False


def indice_sorteios(eventos):
    """Passeios sorteáveis, mesmo os que a retenção descarta.

    Quem já se inscreveu num sorteio precisa registrar o código depois que a
    inscrição fechou — que é exatamente quando o evento sai da agenda. Sem
    este índice, o formulário não reconhece o link.
    """
    out = []
    for e in eventos:
        i = e.get("inscricao") or {}
        if not (i.get("temSorteio") or e.get("sorteados")):
            continue
        if not e.get("link"):
            continue
        out.append({
            "id": e["id"],
            "tit": e["tit"],
            "uni": e.get("uni"),
            "cat": e.get("cat"),
            "link": e["link"],
            "precos": e.get("precos"),
            "sorteio": i.get("sorteio"),
            "inscricao": i.get("inscricao"),
            "inscricaoFim": i.get("inscricaoFim"),
            "sorteados": e.get("sorteados"),
        })
    out.sort(key=lambda x: x["tit"])
    return out


def aplicar(eventos, hoje, dias=60, verboso=True):
    horizonte = (date.fromisoformat(hoje) + timedelta(days=dias)).isoformat()
    fica = [e for e in eventos if manter(e, hoje, horizonte)]
    if verboso:
        print("Retenção (%s a %s): %d de %d eventos"
              % (hoje, horizonte, len(fica), len(eventos)))
    return fica
