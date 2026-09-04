// Minimal service worker. This app is data-driven and needs a live
// connection to the Streamlit server, so this deliberately does NOT
// cache pages for offline use — it only exists so browsers treat the
// app as "installable" (Add to Home Screen / Install app).

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Pass every request straight through to the network.
  event.respondWith(fetch(event.request));
});
