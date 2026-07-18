/**
 * Math3D Service Worker — PWA 离线支持
 *
 * 缓存策略：
 * - App Shell (/, /src/*, /assets/*): Cache First
 * - API (/api/*): Network First
 * - Lesson 页面 (/lessons/*): Cache First（离线可回看课件）
 */

const CACHE_VERSION = "math3d-v1";
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const LESSON_CACHE = `${CACHE_VERSION}-lessons`;
const API_CACHE = `${CACHE_VERSION}-api`;

// 安装：预缓存 App Shell
const APP_SHELL = [
  "/",
  "/index.html",
  "/manifest.json",
  "/icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(APP_SHELL);
    }).then(() => {
      return self.skipWaiting();
    })
  );
});

// 激活：清理旧缓存
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key.startsWith("math3d-") && key !== STATIC_CACHE && key !== LESSON_CACHE && key !== API_CACHE)
          .map((key) => caches.delete(key))
      );
    }).then(() => {
      return self.clients.claim();
    })
  );
});

// 请求拦截
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 跳过非 GET 请求
  if (request.method !== "GET") return;

  // 跳过 Chrome 扩展等非 http/https 请求
  if (!url.protocol.startsWith("http")) return;

  // API 请求：Network First（拿最新数据）
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirst(request, API_CACHE));
    return;
  }

  // 课件页面 /static/lessons/：Cache First（离线可用）
  if (url.pathname.startsWith("/static/lessons/") || url.pathname.includes("/view")) {
    event.respondWith(cacheFirst(request, LESSON_CACHE));
    return;
  }

  // 上传的图片：Network First
  if (url.pathname.startsWith("/static/uploads/")) {
    event.respondWith(networkFirst(request, "math3d-images"));
    return;
  }

  // 第三方 CDN (Three.js, KaTeX)：Cache First
  if (url.hostname.includes("unpkg.com") || url.hostname.includes("cdn.jsdelivr.net")) {
    event.respondWith(cacheFirst(request, `${CACHE_VERSION}-cdn`));
    return;
  }

  // 其余静态资源：Cache First
  event.respondWith(cacheFirst(request, STATIC_CACHE));
});

// ======== 缓存策略 ========

/** Cache First：优先用缓存（快速 + 离线），没命中才走网络并缓存。 */
async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (e) {
    // 离线 + 无缓存 → 返回友好页面
    if (request.destination === "document") {
      return caches.match("/");
    }
    throw e;
  }
}

/** Network First：优先用网络（最新数据），失败才用缓存。 */
async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (e) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw e;
  }
}
