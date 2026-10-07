// Execute the actual worker against an isolated Cache/Fetch implementation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const listeners = {};
const stores = new Map();
let network = async () => new Response('Notfallkontakt alt', {
  headers: {'X-Breakpoint-Offline': 'public', 'Content-Type': 'text/html'}
});
const key = request => typeof request === 'string' ? request : request.url;
const cacheApi = {
  async open(name) {
    if (!stores.has(name)) stores.set(name, new Map());
    const store = stores.get(name);
    return {
      async addAll(urls) { for (const url of urls) store.set(url, new Response('asset')); },
      async put(request, response) { store.set(key(request), response.clone()); },
      async match(request) { return store.get(key(request))?.clone(); }
    };
  },
  async keys() { return [...stores.keys()]; },
  async delete(name) { return stores.delete(name); }
};
vm.runInNewContext(fs.readFileSync('static/js/sw.js', 'utf8'), {
  self: {location: {origin: 'https://club.test'}, addEventListener: (type, handler) => {listeners[type] = handler;},
    skipWaiting: async () => {}, clients: {claim: async () => {}}},
  caches: cacheApi, fetch: (...args) => network(...args), URL, Response
});
async function lifecycle(type, extra = {}) {
  const pending = [];
  listeners[type]({...extra, waitUntil: promise => pending.push(promise)});
  await Promise.all(pending);
}
async function request(path, options = {}) {
  const pending = [];
  let response;
  listeners.fetch({request: {url: new URL(path, 'https://club.test').href, method: 'GET', mode: 'cors', ...options},
    waitUntil: promise => pending.push(promise), respondWith: promise => {response = promise;}});
  const result = response ? await response : undefined;
  await Promise.all(pending);
  return result;
}
(async () => {
  stores.set('breakpoint-v1', new Map([['/accounts/profile/', new Response('private account')]]));
  stores.set('unrelated-application', new Map());
  await lifecycle('install');
  await lifecycle('activate');
  assert(!stores.has('breakpoint-v1'), 'Activation must purge legacy authenticated HTML');
  assert(stores.has('unrelated-application'), 'Do not delete another application cache');
  const offlineStore = stores.get('breakpoint-v2-offline');
  const assets = stores.get('breakpoint-v2-static');
  const privatePath = 'https://club.test/accounts/profile/';
  const cachedCount = assets.size;
  network = async (request, options) => {
    if (request === '/offline/') {
      assert.equal(options.credentials, 'omit');
      assert.equal(options.cache, 'no-store');
      return new Response('Notfallkontakt neu', {headers: {'X-Breakpoint-Offline': 'public'}});
    }
    return new Response('Secret financial and personal data', {headers: {'Cache-Control': 'private, no-store', 'Content-Type': 'text/html'}});
  };
  const online = await request('/accounts/profile/', {mode: 'navigate'});
  assert.equal(await online.text(), 'Secret financial and personal data');
  assert.equal(assets.size, cachedCount);
  assert(!assets.has(privatePath) && !offlineStore.has(privatePath));
  assert.equal(await offlineStore.get('/offline/').clone().text(), 'Notfallkontakt neu');
  network = async () => {throw new Error('offline');};
  assert.equal(await (await request('/accounts/profile/', {mode: 'navigate'})).text(), 'Notfallkontakt neu');
  assert.equal(await (await request('/admin/', {mode: 'navigate'})).text(), 'Notfallkontakt neu');
  for (const [url, options] of [['/accounts/login/', {method: 'POST'}], ['/media/private.pdf', {}], ['https://other.test/static/x.js', {}], ['/api/private/', {}]]) {
    assert.equal(await request(url, options), undefined, 'Private/non-GET/cross-origin requests must not be intercepted');
  }
  const staticPath = 'https://club.test/static/test.css';
  network = async () => new Response('css', {headers: {'Content-Type': 'text/css'}});
  assert.equal(await (await request('/static/test.css')).text(), 'css');
  assert(assets.has(staticPath));
  network = async () => {throw new Error('offline');};
  assert.equal(await (await request('/static/test.css')).text(), 'css');
  network = async () => new Response('private', {headers: {'Cache-Control': 'private', 'Content-Type': 'text/css'}});
  await request('/static/private.css');
  assert(!assets.has('https://club.test/static/private.css'));
  network = async () => new Response('login HTML', {headers: {'Content-Type': 'text/html'}});
  await request('/static/login.css');
  assert(!assets.has('https://club.test/static/login.css'));
  await lifecycle('message', {data: {type: 'REFRESH_OFFLINE'}});
  assert.equal(await offlineStore.get('/offline/').clone().text(), 'Notfallkontakt neu', 'Unmarked HTML must not replace the emergency page');
  offlineStore.clear();
  network = async () => {throw new Error('offline');};
  assert.equal((await request('/accounts/profile/', {mode: 'navigate'})).status, 503);
  console.log('Service worker: privacy, upgrade purge, asset caching, emergency refresh and offline fallback passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
