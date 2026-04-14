// Lumeway Service Worker — enables PWA install on Android / desktop
const CACHE_NAME = 'lumeway-v1';

// Install — cache shell assets
self.addEventListener('install', function(e) {
  self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(names) {
      return Promise.all(
        names.filter(function(n) { return n !== CACHE_NAME; })
             .map(function(n) { return caches.delete(n); })
      );
    })
  );
  self.clients.claim();
});

// Fetch — network-first, fallback to cache
self.addEventListener('fetch', function(e) {
  // Skip non-GET and API requests
  if (e.request.method !== 'GET' || e.request.url.includes('/api/')) return;

  e.respondWith(
    fetch(e.request)
      .then(function(response) {
        // Cache successful responses
        if (response.ok) {
          var clone = response.clone();
          caches.open(CACHE_NAME).then(function(cache) {
            cache.put(e.request, clone);
          });
        }
        return response;
      })
      .catch(function() {
        return caches.match(e.request);
      })
  );
});
