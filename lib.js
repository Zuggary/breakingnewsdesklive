/* Pure helpers, shared by the page and the Node tests. */
(function (root) {
  var TYPES = {
    earthquake: { label: 'Earthquake', color: '#ff9340' },
    weather: { label: 'Weather', color: '#5cb3ff' },
    storm: { label: 'Cyclone', color: '#b48cff' },
    flood: { label: 'Flood', color: '#3fd0d0' },
    wildfire: { label: 'Wildfire', color: '#ff5c5c' },
    volcano: { label: 'Volcano', color: '#f2d04b' },
    transport: { label: 'Air travel', color: '#6fd6a8' },
    statement: { label: 'Official statement', color: '#7fa6ff' },
    headline: { label: 'Outlet headlines', color: '#c8b8a0' },
    notice: { label: 'Official notice', color: '#9fb4d9' },
    recall: { label: 'Recall', color: '#e6c14a' },
    cyber: { label: 'Cyber', color: '#ff5fd0' },
    outage: { label: 'Outage', color: '#ff7ab8' },
    smoke: { label: 'Smoke', color: '#b0a090' },
    tsunami: { label: 'Tsunami', color: '#27c2ff' },
    space: { label: 'Space weather', color: '#d58cff' },
    drought: { label: 'Drought', color: '#c9a06b' },
    other: { label: 'Other', color: '#93a1b5' }
  };
  var GROUPS = { hazards: ['Hazards', ['earthquake', 'weather', 'storm', 'flood', 'wildfire', 'volcano', 'drought', 'tsunami', 'smoke']],
    transport: ['Transport', ['transport']], outages: ['Outages and cyber', ['outage', 'cyber']], recalls: ['Recalls and safety', ['recall']],
    world: ['World events', ['statement', 'headline']],
    notices: ['Official notices', ['notice']], space: ['Space', ['space', 'launch']] };
  var SEV = { extreme: '#ff5c5c', severe: '#ff9340', moderate: '#f2d04b', minor: '#93a1b5' };
  function ago(iso, now) {
    var m = Math.max(1, Math.round(((now || Date.now()) - Date.parse(iso)) / 60000));
    if (m < 60) return m + 'm ago';
    var h = Math.round(m / 60);
    if (h < 48) return h + 'h ago';
    return Math.round(h / 24) + 'd ago';
  }
  function filterEvents(events, f, now) {
    now = now || Date.now();
    return events.filter(function (e) {
      if (f.type && f.type !== 'all') {
        if (f.type.indexOf('g:') === 0) { if (GROUPS[f.type.slice(2)][1].indexOf(e.type) < 0) return false; }
        else if (e.type !== f.type) return false;
      }
      if (f.region && f.region !== 'all' && e.region !== f.region) return false;
      var hrs = f.hours || (f.day ? 24 : 0);
      if (hrs && now - Date.parse(e.time) > hrs * 36e5) return false;
      return true;
    });
  }
  function safeUrl(u) { return /^https:\/\/[^\s]+$/.test(u || '') ? u : null; }
  var ILLUS = { earthquake: ['earthquake-1', 'earthquake-2', 'earthquake-3'], storm: ['storm-1', 'storm-2', 'storm-3'], wildfire: ['wildfire-4', 'wildfire-5', 'wildfire-6'],
    smoke: ['wildfire-4', 'wildfire-5', 'wildfire-6'], flood: ['flood-1', 'flood-2', 'flood-3'], volcano: ['volcano-1', 'volcano-2', 'volcano-3'], outage: ['outage-2', 'outage-3', 'outage-5', 'outage-6'],
    cyber: ['outage-2', 'outage-3', 'outage-5', 'outage-6'], transport: ['flight-1', 'flight-2', 'flight-3'], recall: ['recall-1', 'recall-2', 'recall-3'], space: ['space-2', 'space-3'] };
  function illustrationFor(e) {
    var list = ILLUS[e.type]; if (!list) return null;
    var h = 0, s = e.id || ''; for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return 'assets/illustrations/' + list[h % list.length] + '.webp';
  }
  function renderIllustration(src) {
    var d = document, f = d.createElement('figure'); f.className = 'ctx-fig illus';
    var wrap = d.createElement('div'); wrap.className = 'illus-wrap';
    var im = d.createElement('img'); im.loading = 'lazy'; im.src = src; im.width = 320; im.alt = 'Illustration of the kind of event. It is not a photo of this event.'; wrap.appendChild(im);
    var tag = d.createElement('span'); tag.className = 'illus-tag'; tag.textContent = 'Illustration'; wrap.appendChild(tag); f.appendChild(wrap);
    var fc = d.createElement('figcaption'); fc.className = 'src'; fc.textContent = 'Illustration made for this site. It does not show the actual scene.'; f.appendChild(fc);
    return f;
  }
  function renderContext(c, e) {
    var d = document, box = d.createElement('div'); box.className = 'ctx';
    function el(t, cls, x) { var n = d.createElement(t); if (cls) n.className = cls; if (x != null) n.textContent = x; return n; }
    function link(href, text) { var a = el('a', '', text); a.href = safeUrl(href) || '#'; a.rel = 'noopener'; return a; }
    box.appendChild(el('h3', '', 'Context'));
    if (c.summary) {
      var p = el('p', 'ctx-text', c.summary.text); box.appendChild(p);
      var cr = el('p', 'src'); cr.appendChild(d.createTextNode('Text from Wikipedia: ')); cr.appendChild(link(c.summary.url, c.summary.title));
      cr.appendChild(d.createTextNode(' (')); cr.appendChild(link(c.summary.history_url, 'authors'));
      cr.appendChild(d.createTextNode('), licence ')); cr.appendChild(link('https://creativecommons.org/licenses/by-sa/4.0/', c.summary.licence)); cr.appendChild(d.createTextNode('. Not our words.'));
      box.appendChild(cr);
    }
    if (c.image) {
      var f = el('figure', 'ctx-fig'); var im = d.createElement('img'); im.loading = 'lazy'; im.alt = 'Photo related to ' + (c.summary ? c.summary.title : 'this item'); im.src = safeUrl(c.image.src) || ''; im.width = 320; f.appendChild(im);
      var fc = el('figcaption', 'src'); fc.appendChild(d.createTextNode('Photo: ' + c.image.author + ', ' + c.image.license + '. ')); fc.appendChild(link(c.image.credit_url, 'File page on Wikimedia Commons')); f.appendChild(fc); box.appendChild(f);
    }
    if (c.satellite) {
      var f2 = el('figure', 'ctx-fig'); var im2 = d.createElement('img'); im2.loading = 'lazy'; im2.alt = 'Satellite view of the wider area'; im2.src = safeUrl(c.satellite.src) || ''; im2.width = 320; f2.appendChild(im2);
      var fc2 = el('figcaption', 'src'); fc2.appendChild(d.createTextNode(c.satellite.note + ' Credit: ')); fc2.appendChild(link(c.satellite.credit_url, c.satellite.credit)); f2.appendChild(fc2); box.appendChild(f2);
    }
    if (!c.image && e) { var il = illustrationFor(e); if (il) box.appendChild(renderIllustration(il)); }
    return box;
  }
  var api = { ILLUS: ILLUS, illustrationFor: illustrationFor, renderContext: renderContext, GROUPS: GROUPS, TYPES: TYPES, SEV: SEV, ago: ago, filterEvents: filterEvents, safeUrl: safeUrl };
  if (typeof module !== 'undefined') module.exports = api; else root.BND = api;
})(this);
