const CACHE_NAME = 'fongfood-cache-v2'; // Đổi tên cache để luôn làm mới

self.addEventListener('install', (event) => {
    self.skipWaiting(); // Ép service worker mới hoạt động ngay lập tức
});

self.addEventListener('activate', (event) => {
    // Xóa sạch các bộ nhớ đệm (cache) cũ rích
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});

self.addEventListener('fetch', (event) => {
    // CHIẾN THUẬT: NETWORK FIRST (ƯU TIÊN MẠNG) CHO GIAO DIỆN HTML
    if (event.request.mode === 'navigate' || event.request.headers.get('accept').includes('text/html')) {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    // Nếu có mạng -> Tải code mới nhất và lưu một bản dự phòng
                    return caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, response.clone());
                        return response;
                    });
                })
                .catch(() => {
                    // Nếu MẤT MẠNG -> Mới lôi bản dự phòng ra dùng
                    return caches.match(event.request);
                })
        );
    } else {
        // Đối với hình ảnh, CSS, JS thì có thể lấy từ Cache cho nhanh
        event.respondWith(
            caches.match(event.request).then((response) => {
                return response || fetch(event.request);
            })
        );
    }
});