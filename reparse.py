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
        novo = detalhes.datas_do_texto(
            ins["texto"], int((ev.get("inicio") or "2026")[:4]), ev.get("inicio"))
        if not novo:
            continue

        # preserva o que não é data (sorteados vive fora daqui)
        novo.setdefault("temSorteio", ins.get("temSorteio", False))
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
