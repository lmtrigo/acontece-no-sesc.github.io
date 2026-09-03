# -*- coding: utf-8 -*-
"""Diagnóstico manual dos extratores contra páginas reais — NÃO é teste.

Chamava-se `teste_detalhes.py` e não tinha uma asserção sequer: buscava cinco
páginas na rede, imprimia o resultado e terminava com sucesso acontecesse o
que acontecesse. Um arquivo com "teste" no nome que nunca falha é pior do que
nenhum, porque dá a impressão de que alguém está olhando.

Serve para inspecionar a olho o que o extrator devolve de uma página nova, ou
depois de mexer num padrão. As verificações que falham de verdade, e que
rodam na CI sem tocar na rede, estão em `teste_extratores.py`.

    python diagnostico_detalhes.py
"""
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
