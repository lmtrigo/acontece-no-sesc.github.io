#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reprocessa as datas de inscrição/sorteio já coletadas, sem rede.

O `detalhes.py` guarda o trecho original em `inscricao.texto`. Sempre que o
extrator de datas melhorar, dá para reaplicá-lo sobre esse texto em segundos,
em vez de rebaixar mil páginas.

Uso:
    python reparse.py
    python reparse.py --mostrar 15      # imprime antes/depois
"""

import argparse
import json
import os
from datetime import datetime

import coletor
import detalhes

# O que `detalhes.datas_do_texto` sabe produzir — e portanto o que ele tem
# autoridade para substituir. Qualquer outra chave de `inscricao` veio de
# outro extrator e precisa sobreviver à releitura.
CHAVES_DE_DATA = ("texto", "inscricao", "inscricaoFim", "sorteio", "sorteioFim",
                  "pagamento", "pagamentoFim", "temSorteio")


def reler(ins, ano, dia_ref):
    """Relê as datas de `ins` sobre o texto guardado, preservando o resto.

    A versão anterior trocava o bloco `inscricao` inteiro pelo que o extrator
    de datas devolvia, e enumerava o que preservar. A enumeração citava
    `sorteados` — que de fato vive no topo do evento, não aqui — e esquecia
    `regras`, as janelas recorrentes de credencial da §4.7 do HANDOFF. Elas
    são extraídas do HTML por `detalhes.regras_de_inscricao` e morriam um
    passo depois, no mesmo workflow, sem contador nenhum acusar.

    Ficava invisível por acaso: os eventos com `regras` não têm
    `inscricao.texto`, então o laço os pula antes de chegar aqui. Bastava uma
    página trazer as duas coisas para a regra sumir.

    Agora é lista positiva: só o que a releitura sabe produzir é substituído.
    Devolve None quando não há o que reler.
    """
    novo = detalhes.datas_do_texto(ins["texto"], ano, dia_ref)
    if not novo:
        return None
    saida = dict(ins)
    for chave in CHAVES_DE_DATA:
        saida.pop(chave, None)
    saida.update(novo)
    saida.setdefault("temSorteio", False)
    return saida


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dados", default=os.path.join("dados", "eventos.json"))
    p.add_argument("--mostrar", type=int, default=8)
    args = p.parse_args()

    with open(args.dados, encoding="utf-8") as f:
        d = json.load(f)

    mudou = 0
    limpas = 0
    amostras = []

    for ev in d["eventos"]:
        # a limpeza da descrição também roda sobre o texto já guardado
        if ev.get("desc"):
            nova = detalhes.limpar_servico(ev["desc"])
            if nova != ev["desc"]:
                if len(nova) >= 60:
                    ev["desc"] = nova
                else:
                    ev.pop("desc", None)
                limpas += 1

        ins = ev.get("inscricao")
        if not ins or not ins.get("texto"):
            continue

        antes = {k: ins.get(k) for k in
                 ("inscricao", "inscricaoFim", "sorteio", "pagamento", "pagamentoFim")}
        novo = reler(ins, int((ev.get("inicio") or "2026")[:4]),
                     ev.get("fim") or ev.get("inicio"))
        if novo is None:
            continue
        ev["inscricao"] = novo

        depois = {k: novo.get(k) for k in antes}
        if antes != depois:
            mudou += 1
            if len(amostras) < args.mostrar:
                amostras.append((ev["tit"], ins["texto"][:120], antes, depois))

    de = datetime.strptime(d["janela"]["de"], "%Y-%m-%d").date()
    ate = datetime.strptime(d["janela"]["ate"], "%Y-%m-%d").date()
    viagens = coletor.expandir_viagens(d["eventos"], de, ate)

    with open(args.dados, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))

    print("Reprocessados %d eventos · %d com datas alteradas · %d descrições limpas\n"
          % (sum(1 for e in d["eventos"] if e.get("inscricao")), mudou, limpas))
    for tit, txt, a, b in amostras:
        print("• %s" % tit)
        print("  texto : %s…" % txt)
        print("  antes : %s" % {k: v for k, v in a.items() if v})
        print("  depois: %s\n" % {k: v for k, v in b.items() if v})


if __name__ == "__main__":
    main()
