/* Breaking News Desk service worker: offline support, same-origin files only. */
(function () {
  "use strict";
  var CACHE = "bnd-offline-v2";
  var FILES = ["./", "./", "/about", "/privacy", "/data", "/corrections", "./tokens.css", "/tv", "/event",
               "./style.css", "./fonts/public-sans-latin-wght-normal.woff2", "./fonts/barlow-condensed-700.woff2", "./app.js", "./lib.js", "./favicon.svg",
               "./data/events.json", "./data/sources.json", "./data/world.json"];
  function path(rel) { return new URL(rel, self.registration.scope).pathname; }
  var PATHS = {};
  FILES.forEach(function (f) { PATHS[path(f)] = true; });

  self.addEventListener("install", function (e) {
    e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(FILES.map(path)); }).then(function () { return self.skipWaiting(); }));
  });
  self.addEventListener("activate", function (e) {
    e.waitUntil(caches.keys().then(function (ks) {
      return Promise.all(ks.map(function (k) { return k === CACHE ? null : caches.delete(k); }));
    }).then(function () { return self.clients.claim(); }));
  });
  self.addEventListener("fetch", function (e) {
    var req = e.request;
    if (req.method !== "GET") return;
    var url = new URL(req.url);
    if (url.origin !== self.location.origin) return;          // never touch other sites
    var key = url.pathname;
    if (!PATHS[key]) return;                                    // only our own listed files
    e.respondWith(caches.open(CACHE).then(function (cache) {
      var net = fetch(req).then(function (r) { if (r && r.ok && r.type === "basic") cache.put(key, r.clone()); return r; });
      var slow = new Promise(function (res) { setTimeout(res, 4000); }).then(function () { return cache.match(key).then(function (c) { return c || net; }); });
      return Promise.race([net, slow]).catch(function () { return cache.match(key).then(function (c) { return c || Response.error(); }); });
    }));
  });
})();
