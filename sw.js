/*
 * Service worker — cache-first app shell, offline-first. Everything this app
 * needs is static files + IndexedDB; there's no API to fall back to the network
 * for, so cache-first (falling back to network only on a cache miss) is enough.
 *
 * Bump CACHE_NAME on every deploy that changes any precached file — that's what
 * forces old clients to fetch fresh copies instead of serving stale cached ones
 * forever.
 */

const CACHE_NAME = "liftlog-v1";

const APP_SHELL = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./css/style.css",
  "./js/engine.js",
  "./js/library.js",
  "./js/storage.js",
  "./js/app.js",
  "./icons/icon-192.png",
  "./icons/icon-192-maskable.png",
  "./icons/icon-512.png",
  "./icons/icon-512-maskable.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        // Cache a copy of anything same-origin we successfully fetch, so it's
        // available offline next time too (e.g. a page reload that pulls in a
        // file not in the original precache list).
        if (response.ok && new URL(event.request.url).origin === self.location.origin) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return response;
      }).catch(() => cached);
    })
  );
});
