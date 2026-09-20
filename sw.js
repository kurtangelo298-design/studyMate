const CACHE_NAME = 'studymate-ph-v3';
const ASSETS = [
  './',
  './index.html',
  './manifest.json'
];

// ✅ I-INSTALL at i-save ang lahat sa cache
self.addEventListener('install', event => {
  console.log('[StudyMate SW] Installing version:', CACHE_NAME);
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      console.log('[StudyMate SW] Caching files...');
      return cache.addAll(ASSETS);
    }).then(() => {
      console.log('[StudyMate SW] ✅ All files cached!');
      return self.skipWaiting(); // Agad gamitin ang bagong bersyon
    })
  );
});

// ✅ KUNIN — May internet → i-update; Walang internet → gamitin ang cache
self.addEventListener('fetch', event => {
  event.respondWith(
    fetch(event.request)
      .then(response => {
        // May internet — i-refresh ang cache
        return caches.open(CACHE_NAME).then(cache => {
          cache.put(event.request, response.clone());
          return response;
        });
      })
      .catch(() => {
        // Walang internet — ibigay ang nakatago
        return caches.match(event.request).then(cached => {
          if (cached) return cached;
          console.log('[StudyMate SW] ⚠️ Not cached:', event.request.url);
        });
      })
  );
});

// ✅ I-UPDATE — Burahin ang lumang cache
self.addEventListener('activate', event => {
  console.log('[StudyMate SW] Activating new version...');
  event.waitUntil(
    caches.keys().then(names => {
      return Promise.all(
        names.filter(name => name !== CACHE_NAME)
             .map(name => {
               console.log('[StudyMate SW] Deleting old cache:', name);
               return caches.delete(name);
             })
      );
    }).then(() => self.clients.claim())
  );
});
