const CACHE_NAME = 'studymate-v1.2';
const ASSETS_TO_CACHE = [
  '',
  'index.html',
  'manifest.json'
];

// ===== INSTALL — I-save lahat sa Cache =====
self.addEventListener('install', event => {
  console.log('✅ Installing Service Worker...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('📦 Caching assets...');
        return cache.addAll(ASSETS_TO_CACHE);
      })
      .then(() => self.skipWaiting())
  );
});

// ===== ACTIVATE — Burahin ang lumang cache =====
self.addEventListener('activate', event => {
  console.log('✅ Activating Service Worker...');
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.filter(name => name !== CACHE_NAME)
          .map(name => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// ===== FETCH — Kung walang internet, gamitin ang Cache =====
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(cachedResponse => {
        // Kung nasa cache na — ibigay agad
        if (cachedResponse) {
          return cachedResponse;
        }
        // Kung wala — kunin sa internet
        return fetch(event.request)
          .then(response => {
            // I-save sa cache para sa susunod
            return caches.open(CACHE_NAME)
              .then(cache => {
                cache.put(event.request, response.clone());
                return response;
              });
          })
          .catch(() => {
            // Walang internet at wala sa cache — fallback
            console.log('⚠️ Offline — cannot fetch:', event.request.url);
          });
      })
  );
});
