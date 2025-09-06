self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

// Minimal pass-through; we don't cache aggressively in MVP
self.addEventListener('fetch', (event) => {
  return;
});


