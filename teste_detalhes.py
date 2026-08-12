# -*- coding: utf-8 -*-
"""Confere o extrator contra as três páginas de exemplo."""
import json
import detalhes

CASOS = [
    ("rachel-reis-jundiai", "https://www.sescsp.org.br/programacao/rachel-reis-jundiai/", "2026-08-14"),
    ("historia-e-natureza", "https://www.sescsp.org.br/programacao/historia-e-natureza-na-regiao-serrana-do-rj-petropolis-e-teresopolis/", "2026-09-05"),
    ("paisagens-serra", "https://www.sescsp.org.br/programacao/paisagens-da-serra-fluminense-2/", "2026-08-12"),
]

for nome, url, dia in CASOS:
    pg = detalhes.buscar(url)
    if not pg:
        print("==", nome, "FALHOU")
        continue
    print("==", nome)
    print("  precos :", json.dumps(detalhes.extrair_precos(pg), ensure_ascii=False))
    print("  acesso :", json.dumps(detalhes.extrair_acesso(pg, 2026, dia), ensure_ascii=False))
    cods = detalhes.extrair_codigos(pg)
    print("  codigos:", len(cods), cods[:6])
