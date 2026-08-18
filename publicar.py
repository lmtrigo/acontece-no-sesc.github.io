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
from datetime import date, timedelta

import coletor
import regras

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
def esc_ics(s):
    return (str(s or "").replace("\\", "\\\\").replace(",", "\\,")
            .replace(";", "\\;").replace("\n", "\\n"))


def _ics(linhas):
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0",
                        "PRODID:-//Agenda Sesc SP (nao oficial)//PT-BR",
                        "CALSCALE:GREGORIAN"] + linhas + ["END:VCALENDAR"])


def _stamp(quando, hora_padrao="09:00"):
    p = str(quando).split("T")
    hm = (p[1][:5] if len(p) > 1 and p[1] else hora_padrao).replace(":", "")
    return p[0].replace("-", "") + "T" + hm + "00"


def ics_evento(ev):
    """O compromisso do evento. Viagem contínua vira um intervalo só."""
    local = esc_ics("Sesc " + (ev.get("uni") or "") +
                    (" — " + ev["endereco"] if ev.get("endereco") else ""))
    desc = esc_ics(((ev.get("sub") + " — ") if ev.get("sub") else "") + (ev.get("link") or ""))
    tit = esc_ics(ev.get("tit"))
    dias = ev.get("dias") or []

    if ev.get("continuo") and len(dias) > 1:
        fim = (date.fromisoformat(dias[-1]) + timedelta(days=1)).isoformat()
        return _ics(["BEGIN:VEVENT", "UID:%s-viagem@agenda-sesc" % ev["id"],
                     "DTSTART;VALUE=DATE:" + dias[0].replace("-", ""),
                     "DTEND;VALUE=DATE:" + fim.replace("-", ""),
                     "SUMMARY:" + tit, "LOCATION:" + local, "DESCRIPTION:" + desc,
                     "BEGIN:VALARM", "TRIGGER:-P1D", "ACTION:DISPLAY",
                     "DESCRIPTION:" + esc_ics("Amanhã: " + (ev.get("tit") or "")),
                     "END:VALARM", "END:VEVENT"])

    pontos = ([s["quando"] for s in ev["sessoes"]] if ev.get("sessoes")
              else [d + "T" + (ev.get("hora") or "09:00") for d in dias])
    corpo = []
    for i, q in enumerate(pontos):
        corpo += ["BEGIN:VEVENT", "UID:%s-%d@agenda-sesc" % (ev["id"], i),
                  "DTSTART:" + _stamp(q), "SUMMARY:" + tit,
                  "LOCATION:" + local, "DESCRIPTION:" + desc,
                  "BEGIN:VALARM", "TRIGGER:-PT2H", "ACTION:DISPLAY",
                  "DESCRIPTION:" + tit, "END:VALARM", "END:VEVENT"]
    return _ics(corpo) if corpo else None


TETO_POR_DATA = 8   # acima disso é curso semanal; não vale 20 arquivos


def ics_uma_data(ev, quando):
    """Uma sessão só, para quem escolheu a data no app."""
    local = esc_ics("Sesc " + (ev.get("uni") or "") +
                    (" — " + ev["endereco"] if ev.get("endereco") else ""))
    desc = esc_ics(((ev.get("sub") + " — ") if ev.get("sub") else "") + (ev.get("link") or ""))
    return _ics(["BEGIN:VEVENT",
                 "UID:%s-%s@agenda-sesc" % (ev["id"], _stamp(quando)),
                 "DTSTART:" + _stamp(quando), "SUMMARY:" + esc_ics(ev.get("tit")),
                 "LOCATION:" + local, "DESCRIPTION:" + desc,
                 "BEGIN:VALARM", "TRIGGER:-PT2H", "ACTION:DISPLAY",
                 "DESCRIPTION:" + esc_ics(ev.get("tit")), "END:VALARM", "END:VEVENT"])


def datas_de(ev):
    """Instantes das sessões, na mesma ordem que o app mostra."""
    if ev.get("sessoes"):
        return [s["quando"] for s in ev["sessoes"]]
    return [d + "T" + (ev.get("hora") or "09:00") for d in (ev.get("dias") or [])]


def ics_inscricao(ev):
    """Só a abertura da inscrição — um compromisso, como pedido."""
    i = ev.get("inscricao") or {}
    quando = i.get("inscricao") or ev.get("vendaOnline") or ev.get("vendaPresencial")
    if not quando:
        return None
    extra = []
    if i.get("inscricaoFim"):
        extra.append("Encerra em " + i["inscricaoFim"][:10])
    if i.get("sorteio"):
        extra.append("Sorteio em " + i["sorteio"][:10])
    return _ics(["BEGIN:VEVENT", "UID:%s-insc@agenda-sesc" % ev["id"],
                 "DTSTART:" + _stamp(quando, "10:00"),
                 "SUMMARY:" + esc_ics("Abrem as inscrições: " + (ev.get("tit") or "")),
                 "LOCATION:" + esc_ics("Sesc " + (ev.get("uni") or "")),
                 "DESCRIPTION:" + esc_ics(". ".join(extra + [ev.get("link") or ""])),
                 "BEGIN:VALARM", "TRIGGER:-PT1H", "ACTION:DISPLAY",
                 "DESCRIPTION:" + esc_ics("Inscrições abrem em 1h"),
                 "END:VALARM", "END:VEVENT"])


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

  // Um .ics só abre o app de calendario se chegar como text/calendar.
  // Nem todo host declara esse tipo (o http.server do Python manda
  // application/octet-stream), entao o proprio worker corrige o cabecalho.
  if (url.pathname.endsWith('.ics')) {
    e.respondWith(
      fetch(req).then((r) => r.blob().then((b) => new Response(b, {
        status: r.status,
        headers: {
          'Content-Type': 'text/calendar; charset=utf-8',
          'Content-Disposition': 'inline'
        }
      })))
    );
    return;
  }

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
    p.add_argument("--horizonte", type=int, default=60,
                   help="dias à frente para a regra de retenção")
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

    # eventos.json sem descrição; cada descrição vira um arquivo próprio,
    # buscado só quando alguém abre aquele evento
    with open(args.dados, encoding="utf-8") as f:
        bruto = json.load(f)

    hoje = max(coletor.agora_br().date().isoformat(), bruto["janela"]["de"])
    bruto["sorteaveis"] = regras.indice_sorteios(bruto["eventos"])
    bruto["eventos"] = regras.aplicar(bruto["eventos"], hoje, args.horizonte)

    dir_desc = os.path.join(args.saida, "dados", "desc")
    if os.path.isdir(dir_desc):
        shutil.rmtree(dir_desc)
    os.makedirs(dir_desc, exist_ok=True)

    n_desc = 0
    magro = dict(bruto)
    magro["eventos"] = []
    for ev in bruto["eventos"]:
        d = ev.pop("desc", None)
        if d:
            with open(os.path.join(dir_desc, "%s.json" % ev["id"]), "w", encoding="utf-8") as f:
                json.dump({"desc": d}, f, ensure_ascii=False, separators=(",", ":"))
            n_desc += 1
        magro["eventos"].append(ev)

    with open(os.path.join(args.saida, "dados", "eventos.json"), "w", encoding="utf-8") as f:
        json.dump(magro, f, ensure_ascii=False, separators=(",", ":"))
    print("%d descrições em arquivos separados" % n_desc)

    # Arquivos .ics servidos por URL real. É isto que abre o app de
    # calendário no celular: um blob: não tem endereço que o sistema
    # reconheça, então o navegador sempre o trata como download.
    dir_ics = os.path.join(args.saida, "dados", "ics")
    if os.path.isdir(dir_ics):
        shutil.rmtree(dir_ics)
    os.makedirs(dir_ics, exist_ok=True)

    def grava(nome, conteudo):
        with open(os.path.join(dir_ics, nome), "w", encoding="utf-8", newline="") as f:
            f.write(conteudo)

    n_ics = n_ins = n_dia = 0
    for ev in magro["eventos"]:
        conteudo = ics_evento(ev)
        if conteudo:
            grava("%s.ics" % ev["id"], conteudo)
            n_ics += 1

        conteudo = ics_inscricao(ev)
        if conteudo:
            grava("%s-insc.ics" % ev["id"], conteudo)
            n_ins += 1

        # um arquivo por sessão, para quem escolhe a data no app
        datas = datas_de(ev)
        if not ev.get("continuo") and 1 < len(datas) <= TETO_POR_DATA:
            for q in datas:
                grava("%s-%s.ics" % (ev["id"], q[:10].replace("-", "")),
                      ics_uma_data(ev, q))
                n_dia += 1
            ev["icsd"] = 1        # o app só linka o que existe

    print("%d .ics de evento · %d por sessão · %d de inscrição" % (n_ics, n_dia, n_ins))

    # regrava o eventos.json com a marca icsd
    with open(os.path.join(args.saida, "dados", "eventos.json"), "w", encoding="utf-8") as f:
        json.dump(magro, f, ensure_ascii=False, separators=(",", ":"))

    with open(os.path.join(args.saida, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        f.write(manifest(base))

    png(os.path.join(args.saida, "icon-192.png"), 192)
    png(os.path.join(args.saida, "icon-512.png"), 512)
    png(os.path.join(args.saida, "icon-maskable.png"), 512, maskable=True)

    d = magro
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
