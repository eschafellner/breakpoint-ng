/* Only public assets and the anonymous emergency page belong in Cache Storage. */
const CACHE_VERSION = 'breakpoint-v2';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const OFFLINE_CACHE = `${CACHE_VERSION}-offline`;
const PRECACHE_URLS = [
  '/static/css/styles.css', '/static/js/pwa.js',
  '/static/icons/icon-192x192.png', '/static/icons/icon-512x512.png',
  '/static/icons/icon-maskable-512x512.png', '/static/icons/apple-touch-icon.png',
  '/static/icons/icon.svg', '/static/icons/favicon-32x32.png'
];

async function refreshOfflinePage() {
  try {
    const response = await fetch('/offline/', { credentials: 'omit', cache: 'no-store' });
    if (response.ok && !response.redirected && response.headers.get('X-Breakpoint-Offline') === 'public') {
      const cache = await caches.open(OFFLINE_CACHE);
      await cache.put('/offline/', response);
    }
  } catch (_) {
    // Keep the last known public emergency information during a network outage.
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(STATIC_CACHE);
    await cache.addAll(PRECACHE_URLS);
    await refreshOfflinePage();
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) =>
      key.startsWith('breakpoint-') && key !== STATIC_CACHE && key !== OFFLINE_CACHE
    ).map((key) => caches.delete(key)));
    await refreshOfflinePage();
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  if (event.data?.type === 'REFRESH_OFFLINE') event.waitUntil(refreshOfflinePage());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    event.waitUntil(refreshOfflinePage());
    event.respondWith(fetch(request).catch(async () => {
      const cache = await caches.open(OFFLINE_CACHE);
      return (await cache.match('/offline/')) || new Response(
        'Offline – Bitte prüfe deine Internetverbindung.',
        { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } }
      );
    }));
    return;
  }

  if (url.pathname.startsWith('/static/')) {
    const update = (async () => {
      const cache = await caches.open(STATIC_CACHE);
      const response = await fetch(request);
      const control = response.headers.get('Cache-Control') || '';
      const type = response.headers.get('Content-Type') || '';
      if (response.ok && !response.redirected && !/private|no-store/i.test(control) && !type.includes('text/html')) {
        await cache.put(request, response.clone());
      }
      return response;
    })();
    event.waitUntil(update.catch(() => {}));
    event.respondWith((async () => {
      const cache = await caches.open(STATIC_CACHE);
      const cached = await cache.match(request);
      return cached || update;
    })());
  }
  // Authenticated pages, protected media, APIs, and manifest use the network.
});
