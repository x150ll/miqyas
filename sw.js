/* MIQYAS service worker — v1.7.3 */
const V = "miqyas-v1.7.3";
const CORE = [
  "./", "./index.html", "./manifest.json",
  "./icon-192.png", "./icon-512.png", "./icon-maskable.png",
  "./apple-touch-icon.png", "./og.png"
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(V).then(c => c.addAll(CORE)).catch(() => {})
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== V).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", e => {
  if (e.data && e.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // Navigations: network-first, offline fallback to cached shell
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then(res => {
          const copy = res.clone();
          caches.open(V).then(c => c.put("./index.html", copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match("./index.html"))
    );
    return;
  }

  // Google Fonts: stale-while-revalidate
  if (url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com") {
    e.respondWith(
      caches.open(V).then(async c => {
        const hit = await c.match(req);
        const net = fetch(req).then(res => {
          if (res && res.status === 200) c.put(req, res.clone());
          return res;
        }).catch(() => hit);
        return hit || net;
      })
    );
    return;
  }

  // Live calibration params: always try network first
  if (url.origin === location.origin && url.pathname.endsWith("params.json")) {
    e.respondWith(
      fetch(req).then(res => {
        if (res && res.status === 200) {
          const copy = res.clone();
          caches.open(V).then(c => c.put(req, copy)).catch(() => {});
        }
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }

  // Same-origin assets: cache-first
  if (url.origin === location.origin) {
    e.respondWith(
      caches.match(req).then(hit =>
        hit ||
        fetch(req).then(res => {
          if (res && res.status === 200) {
            const copy = res.clone();
            caches.open(V).then(c => c.put(req, copy)).catch(() => {});
          }
          return res;
        })
      )
    );
  }
});
