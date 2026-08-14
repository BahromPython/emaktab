const CACHE = 'emaktab-v5';
const OFFLINE_URL = '/offline.html';

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll([OFFLINE_URL, '/manifest.json']))
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => e.waitUntil(clients.claim()));

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request).catch(() =>
      caches.match(OFFLINE_URL).then(r => r || new Response('Offline', {status: 503}))
    )
  );
});

self.addEventListener('push', e => {
  let data = {title:'📚 eMaktab', body:'Имрӯз дарс бихон!'};
  try { if(e.data) data = e.data.json(); } catch(err){}
  e.waitUntil(self.registration.showNotification(data.title||'📚 eMaktab',{
    body: data.body||'Имрӯз дарс бихон!',
    icon: '/favicon.ico',
    data: {url: data.url||'/eMaktab_lms_v2.html'}
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.matchAll({type:'window'}).then(list => {
    for(const c of list) if(c.url.includes('eMaktab')&&'focus'in c) return c.focus();
    return clients.openWindow(e.notification.data?.url||'/eMaktab_lms_v2.html');
  }));
});
