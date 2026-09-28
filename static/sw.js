// Service Worker для уведомлений на Android и ПК
self.addEventListener('notificationclick', e => {
    e.notification.close();
    e.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(cs => {
            if (cs.length > 0) {
                return cs[0].focus();
            }
            return clients.openWindow('/');
        })
    );
});
