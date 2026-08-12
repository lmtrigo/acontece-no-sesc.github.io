/* Service worker do Agenda Sesc SP.
   Casca: cache primeiro (abre offline e instantâneo).
   Dados: rede primeiro, cache como reserva (sempre o mais novo que houver). */
const VERSAO = 'agenda-sesc-20260812072457';
const CASCA = ['./', './index.html', './manifest.webmanifest', './icon-192.png', './icon-512.png'];

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
