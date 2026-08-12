#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monta a pasta `web/` — o site hospedável, instalável como PWA e que se
atualiza sozinho.

Diferença para o `embutir.py`:
    embutir.py  → um arquivo só, dados embutidos, vira link compartilhável
                  do Claude. Nunca se atualiza.
    publicar.py → app + dados/eventos.json separados + manifest + service
                  worker. O app busca o JSON a cada abertura, então basta o
                  robô regravar o JSON para todo mundo receber.

Gera:
    web/index.html            o app (cópia do prototipo com manifest e SW)
    web/dados/eventos.json    a base servida ao vivo
    web/manifest.webmanifest  nome, cores e ícones da instalação
    web/sw.js                 casca em cache, dados pela rede
    web/icon-192.png, icon-512.png, icon-maskable.png

Uso:
    python publicar.py
    python publicar.py --base /agenda-sesc/     # subpasta do GitHub Pages
"""

import argparse
import json
import os
import re
import shutil
import struct
import zlib

NOME = "Agenda Sesc SP"
NOME_CURTO = "Agenda Sesc"
DESC = "Agregador não oficial da programação do Sesc São Paulo."
TEMA = "#15171A"
FUNDO = "#F2F2F0"


# ----------------------------------------------------------------- ícones
def png(caminho, tamanho, maskable=False):
    """Escreve um PNG sem dependências: fundo tinta e uma marca de agenda."""
    fundo = (0x15, 0x17, 0x1A)
    tinta = (0xF2, 0xF2, 0xF0)
    acento = (0xC2, 0x57, 0x1E)

    s = tamanho
    # área segura menor quando maskable (o sistema recorta as bordas)
    m = int(s * (0.28 if maskable else 0.18))
    topo = int(s * 0.10)

    linhas = bytearray()
    for y in range(s):
        linhas.append(0)  # filtro None
        for x in range(s):
            c = fundo
            dentro = m <= x < s - m and m <= y < s - m
            if dentro:
                borda = max(2, s // 64)
                na_borda = (x < m + borda or x >= s - m - borda or
                            y < m + borda or y >= s - m - borda)
                faixa = y < m + borda + topo
                if faixa:
                    c = acento
                elif na_borda:
                    c = tinta
                else:
                    # três "linhas de programação"
                    passo = (s - 2 * m - topo) // 4
                    rel = y - (m + borda + topo)
                    if passo > 0 and rel % passo < max(2, passo // 5) and rel > 0:
                        if m + borda * 3 <= x < s - m - borda * 3:
                            c = tinta
            linhas.extend(c)

    def chunk(tipo, dados):
        c = struct.pack(">I", len(dados)) + tipo + dados
        return c + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    with open(caminho, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", s, s, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(linhas), 9)))
        f.write(chunk(b"IEND", b""))


# ----------------------------------------------------------------- textos
def manifest(base):
    return json.dumps({
        "name": NOME,
        "short_name": NOME_CURTO,
        "description": DESC,
        "start_url": base,
        "scope": base,
        "display": "standalone",
        "orientation": "portrait",
        "background_color": FUNDO,
        "theme_color": TEMA,
        "lang": "pt-BR",
        "icons": [
            {"src": base + "icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": base + "icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": base + "icon-maskable.png", "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
        ],
    }, ensure_ascii=False, indent=2)


SW = """/* Service worker do Agenda Sesc SP.
   Casca: cache primeiro (abre offline e instantâneo).
   Dados: rede primeiro, cache como reserva (sempre o mais novo que houver). */
const VERSAO = 'agenda-sesc-%(versao)s';
const CASCA = [%(casca)s];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSAO).then((c) => c.addAll(CASCA)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== VERSAO).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.endsWith('eventos.json')) {
    e.respondWith(
      fetch(req)
        .then((r) => {
          const copia = r.clone();
          caches.open(VERSAO).then((c) => c.put(req, copia));
          return r;
        })
        .catch(() => caches.match(req, { ignoreSearch: true }))
    );
    return;
  }

  e.respondWith(
    caches.match(req, { ignoreSearch: true }).then((hit) => hit || fetch(req))
  );
});
"""


CABECA = """<link rel="manifest" href="%(base)smanifest.webmanifest">
<meta name="theme-color" content="%(tema)s">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="%(curto)s">
<link rel="apple-touch-icon" href="%(base)sicon-192.png">
<meta name="description" content="%(desc)s">
"""

REGISTRO = """
<script>
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('%(base)ssw.js').catch(function () {});
  });
}
</script>
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--html", default="prototipo.html")
    p.add_argument("--dados", default=os.path.join("dados", "eventos.json"))
    p.add_argument("--saida", default="web")
    p.add_argument("--base", default="./",
                   help="caminho onde o app vai morar; use /repo/ no GitHub Pages")
    args = p.parse_args()

    base = args.base if args.base.endswith("/") else args.base + "/"

    os.makedirs(os.path.join(args.saida, "dados"), exist_ok=True)

    with open(args.html, encoding="utf-8") as f:
        html = f.read()

    # o embutido continua ali como reserva offline; o JSON servido é que manda
    cab = CABECA % {"base": base, "tema": TEMA, "curto": NOME_CURTO, "desc": DESC}
    html = re.sub(r"(<title>.*?</title>)", lambda m: m.group(1) + "\n" + cab, html, count=1)
    html += REGISTRO % {"base": base}

    with open(os.path.join(args.saida, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(html)

    shutil.copyfile(args.dados, os.path.join(args.saida, "dados", "eventos.json"))

    with open(os.path.join(args.saida, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        f.write(manifest(base))

    png(os.path.join(args.saida, "icon-192.png"), 192)
    png(os.path.join(args.saida, "icon-512.png"), 512)
    png(os.path.join(args.saida, "icon-maskable.png"), 512, maskable=True)

    with open(args.dados, encoding="utf-8") as f:
        d = json.load(f)
    versao = (d.get("geradoEm") or "0").replace(":", "").replace("-", "").replace("T", "")

    casca = ", ".join("'%s%s'" % (base, n) for n in
                      ["", "index.html", "manifest.webmanifest",
                       "icon-192.png", "icon-512.png"])
    with open(os.path.join(args.saida, "sw.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write(SW % {"versao": versao, "casca": casca})

    # o GitHub Pages ignora pastas com _ e roda Jekyll sem isso
    open(os.path.join(args.saida, ".nojekyll"), "w").close()

    tam = sum(os.path.getsize(os.path.join(dp, n))
              for dp, _, ns in os.walk(args.saida) for n in ns)
    print("web/ pronto · %d eventos · %.0f KB no total · base %s"
          % (len(d["eventos"]), tam / 1024, base))
    print("Teste local:  python -m http.server 8000 --directory web")


if __name__ == "__main__":
    main()
