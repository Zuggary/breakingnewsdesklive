(function () {
  'use strict';
  var B = window.BND, $ = function (id) { return document.getElementById(id); };
  var state = { events: [], world: [], f: { type: 'all', region: 'all', day: false }, sel: null, globe: false, rot: [-40, 20], pts: [] };
  var cv = $('map'), ctx = cv.getContext('2d');
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
  function get(u) { return fetch(u, { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error(u); return r.json(); }); }

  /* ---------- filters ---------- */
  function buildFilters() {
    var box = $('filters'); box.textContent = '';
    var types = ['all'].concat(Object.keys(B.TYPES).filter(function (t) { return state.events.some(function (e) { return e.type === t; }); }));
    var sel = el('select', 'chip'); sel.setAttribute('aria-label', 'Event type');
    types.forEach(function (t) { var o = el('option', '', t === 'all' ? 'All types' : B.TYPES[t].label); o.value = t; sel.appendChild(o); });
    sel.onchange = function () { state.f.type = sel.value; render(); };
    var regs = ['all'].concat(Array.from(new Set(state.events.map(function (e) { return e.region; }))).sort());
    var rs = el('select', 'chip'); rs.setAttribute('aria-label', 'Region');
    regs.forEach(function (r) { var o = el('option', '', r === 'all' ? 'All regions' : r); o.value = r; rs.appendChild(o); });
    rs.onchange = function () { state.f.region = rs.value; render(); };
    var d = el('button', 'chip', 'Last 24 hours'); d.setAttribute('aria-pressed', 'false');
    d.onclick = function () { state.f.day = !state.f.day; d.setAttribute('aria-pressed', String(state.f.day)); render(); };
    box.appendChild(sel); box.appendChild(rs); box.appendChild(d);
  }

  /* ---------- list ---------- */
  function render() {
    var now = Date.now();
    var evs = B.filterEvents(state.events, state.f, now);
    var ol = $('list'); ol.textContent = '';
    $('count').textContent = evs.length + ' of ' + state.events.length + ' events shown';
    if (!evs.length) ol.appendChild(el('li', 'empty', 'No events match these filters.'));
    evs.slice(0, 60).forEach(function (e, i) {
      var li = el('li', 'card' + (state.sel === e.id ? ' sel' : '')); li.style.setProperty('--c', B.SEV[e.severity] || '#93a1b5'); li.id = 'ev-' + e.id;
      var h = el('button', 'head'); h.type = 'button'; h.setAttribute('aria-expanded', String(state.sel === e.id));
      h.appendChild(el('span', 'rank', String(i + 1)));
      h.appendChild(el('span', 'title', e.title));
      var b = el('span', 'badge', e.severity); h.appendChild(b);
      h.appendChild(el('span', 'place', (B.TYPES[e.type] || B.TYPES.other).label + ' · ' + e.place));
      h.appendChild(el('span', 'when', B.ago(e.time, now)));
      h.onclick = function () { state.sel = state.sel === e.id ? null : e.id; render(); draw(); };
      li.appendChild(h);
      if (state.sel === e.id) {
        var m = el('div', 'more');
        m.appendChild(el('p', '', e.summary));
        var u = B.safeUrl(e.source_url), s = el('p', 'src');
        s.appendChild(document.createTextNode('Source: ' + e.source + '. Event time: ' + e.time.replace('T', ' ').replace('Z', ' UTC') + '. '));
        if (u) { var a = el('a', '', 'Open the official page'); a.href = u; a.rel = 'noopener'; s.appendChild(a); }
        m.appendChild(s);
        m.appendChild(el('p', 'warn', 'Check official sources. This site is automated and may be wrong or late.'));
        li.appendChild(m);
      }
      ol.appendChild(li);
    });
    draw();
  }

  /* ---------- map ---------- */
  var RAD = Math.PI / 180;
  function project(lon, lat, W, H) {
    if (!state.globe) { var k = Math.min(W / 360, H / 180); return { x: (W - 360 * k) / 2 + (lon + 180) * k, y: (H - 180 * k) / 2 + (90 - lat) * k, v: true }; }
    var l0 = state.rot[0] * RAD, p0 = state.rot[1] * RAD, l = lon * RAD, p = lat * RAD, R = Math.min(W, H) * 0.46;
    var cosc = Math.sin(p0) * Math.sin(p) + Math.cos(p0) * Math.cos(p) * Math.cos(l - l0);
    return { x: W / 2 + R * Math.cos(p) * Math.sin(l - l0), y: H / 2 - R * (Math.cos(p0) * Math.sin(p) - Math.sin(p0) * Math.cos(p) * Math.cos(l - l0)), v: cosc > 0 };
  }
  function size() {
    var g = state.globe, w = cv.clientWidth || 600, d = window.devicePixelRatio || 1; var W = Math.round(w * d), H = g ? W : Math.round((cv.clientHeight || w / 2) * d);
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    $('mapbox').className = 'mapbox' + (g ? ' globe' : '');
    return [W, H];
  }
  function draw() {
    var s = size(), W = s[0], H = s[1], dpr = W / (cv.clientWidth || W);
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#0a1018'; ctx.fillRect(0, 0, W, H);
    if (state.globe) {
      var R = Math.min(W, H) * 0.46; ctx.beginPath(); ctx.arc(W / 2, H / 2, R, 0, 7); ctx.fillStyle = '#0d1826'; ctx.fill(); ctx.strokeStyle = '#243044'; ctx.stroke();
    }
    ctx.fillStyle = '#182436'; ctx.strokeStyle = '#2a3b55'; ctx.lineWidth = 1 * dpr;
    state.world.forEach(function (poly) {
      var ring = poly[0], started = false, lx = null;
      ctx.beginPath();
      for (var i = 0; i < ring.length; i++) {
        var p = project(ring[i][0], ring[i][1], W, H);
        if (!p.v) { started = false; continue; }
        if (!state.globe && lx !== null && Math.abs(p.x - lx) > W / 2) started = false;
        if (!started) { ctx.moveTo(p.x, p.y); started = true; } else ctx.lineTo(p.x, p.y);
        lx = p.x;
      }
      ctx.fill(); ctx.stroke();
    });
    var now = Date.now(), evs = B.filterEvents(state.events, state.f, now).slice(0, 60);
    state.pts = [];
    evs.slice().reverse().forEach(function (e) {
      if (e.lat == null) return;
      var p = project(e.lon, e.lat, W, H); if (!p.v) return;
      var col = B.SEV[e.severity] || '#93a1b5', r = (3 + e.score / 14) * dpr, on = state.sel === e.id;
      ctx.beginPath(); ctx.arc(p.x, p.y, r * 1.9, 0, 7); ctx.fillStyle = col + '33'; ctx.fill();
      ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 7); ctx.fillStyle = col; ctx.fill();
      ctx.lineWidth = (on ? 3 : 1) * dpr; ctx.strokeStyle = on ? '#ffb020' : '#0b0f14'; ctx.stroke();
      var rk = evs.indexOf(e);
      if (rk < 10) { ctx.fillStyle = '#0b0f14'; ctx.font = 'bold ' + Math.round(r * 1.2) + 'px ui-monospace,monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(String(rk + 1), p.x, p.y + dpr * 0.5); }
      state.pts.push({ id: e.id, x: p.x / dpr, y: p.y / dpr, r: Math.max(r / dpr * 1.9, 12) });
    });
  }
  function hit(ev) {
    var b = cv.getBoundingClientRect(), x = ev.clientX - b.left, y = ev.clientY - b.top, best = null, bd = 1e9;
    state.pts.forEach(function (p) { var d = Math.hypot(p.x - x, p.y - y); if (d < p.r && d < bd) { bd = d; best = p; } });
    return best;
  }
  var drag = null;
  cv.addEventListener('pointerdown', function (e) { drag = { x: e.clientX, y: e.clientY, rot: state.rot.slice(), moved: false }; });
  window.addEventListener('pointermove', function (e) {
    if (!drag || !state.globe) return;
    var dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
    state.rot = [drag.rot[0] - dx * 0.4, Math.max(-80, Math.min(80, drag.rot[1] + dy * 0.4))]; draw();
  });
  window.addEventListener('pointerup', function (e) {
    if (drag && !drag.moved) {
      var h = hit(e); if (h) { state.sel = h.id; render(); var n = $('ev-' + h.id); if (n) n.scrollIntoView({ block: 'nearest', behavior: reduce ? 'auto' : 'smooth' }); }
    }
    drag = null;
  });
  $('proj').onclick = function () { state.globe = !state.globe; this.setAttribute('aria-pressed', String(state.globe)); this.textContent = state.globe ? 'Flat map' : 'Globe view'; draw(); };
  $('reset').onclick = function () { state.rot = [-40, 20]; state.sel = null; render(); };
  window.addEventListener('resize', draw);

  function legend() {
    var lg = $('legend'); lg.textContent = '';
    ['extreme', 'severe', 'moderate', 'minor'].forEach(function (t) {
      var s = el('span'); var i = el('i'); i.style.background = B.SEV[t]; s.appendChild(i); s.appendChild(document.createTextNode(t)); lg.appendChild(s);
    });
    lg.appendChild(el('span', '', 'Numbers match the top 10 in the list.'));
  }

  Promise.all([get('data/events.json'), get('data/world.json')]).then(function (r) {
    state.events = r[0].events; state.world = r[1];
    var age = (Date.now() - Date.parse(r[0].generated)) / 60000;
    $('updated').textContent = 'Data built ' + B.ago(r[0].generated) + '. Refreshes about every 10 minutes.';
    $('dot').className = 'dot' + (age > 45 ? ' stale' : '');
    if (age > 45) $('updated').textContent += ' Warning: this data is older than 45 minutes.';
    buildFilters(); legend(); render();
  }).catch(function () {
    $('count').textContent = 'Data could not be loaded. Try again in a minute.';
  });
})();
