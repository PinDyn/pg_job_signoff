/* PG Job Signoff service worker — Phase 2 PWA */
const CACHE = "pg-signoff-v2";
const PRECACHE = [
  "/signoff",
  "/assets/pg_job_signoff/css/signoff.css",
  "/assets/pg_job_signoff/js/signoff_page.js",
  "/assets/pg_job_signoff/icons/icon-192.svg",
  "/assets/pg_job_signoff/icons/icon-512.svg",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Never cache API mutate calls
  if (req.method !== "GET") {
    return;
  }

  // Network-first for signoff API reads
  if (url.pathname.indexOf("/api/method/pg_job_signoff") === 0) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // Cache-first for app shell assets
  if (
    url.pathname.indexOf("/assets/pg_job_signoff/") === 0 ||
    url.pathname === "/signoff" ||
    url.pathname === "/manifest.webmanifest"
  ) {
    event.respondWith(
      caches.match(req).then((cached) => {
        const network = fetch(req)
          .then((res) => {
            const copy = res.clone();
            caches.open(CACHE).then((cache) => cache.put(req, copy));
            return res;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
  }
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});
