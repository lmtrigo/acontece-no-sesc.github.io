# -*- coding: utf-8 -*-
"""Confere os extratores contra páginas reais."""
import json
import detalhes

CASOS = [
    ("rachel-reis", "https://www.sescsp.org.br/programacao/rachel-reis-jundiai/", "2026-08-14"),
    ("historia-natureza", "https://www.sescsp.org.br/programacao/historia-e-natureza-na-regiao-serrana-do-rj-petropolis-e-teresopolis/", "2026-09-05"),
    ("paisagens-serra", "https://www.sescsp.org.br/programacao/paisagens-da-serra-fluminense-2/", "2026-08-12"),
    ("ecos-independencia", "https://www.sescsp.org.br/programacao/ecos-da-independencia/", "2026-09-12"),
    ("chao-caipira", "https://www.sescsp.org.br/programacao/chao-caipira-11/", "2026-08-16"),
]

for nome, url, dia in CASOS:
    pg = detalhes.buscar(url)
    if not pg:
        print("==", nome, "FALHOU\n")
        continue
    print("==", nome)
    print("  acesso :", json.dumps(detalhes.da_pagina(pg, 2026, dia), ensure_ascii=False)[:340])
    d = detalhes.extrair_descricao(pg)
    print("  desc   :", (d[:200] + "…") if d else "(nenhuma)")
    print()
