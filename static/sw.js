// Активируем SW сразу, без перезагрузки страницы
self.addEventListener('install', e => {
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    e.waitUntil(clients.claim());
});

// Клик по уведомлению открывает чат
self.addEventListener('notificationclick', e => {
    e.notification.close();
    e.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => {
            if (cs.length > 0) return cs[0].focus();
            return clients.openWindow('/');
        })
    );
});
