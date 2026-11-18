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
    aviation: { label: 'Aviation weather', color: '#8fd0ff' },
    security: { label: 'Security news', color: '#c8b8a0' },
    smoke: { label: 'Smoke', color: '#b0a090' },
    tsunami: { label: 'Tsunami', color: '#27c2ff' },
    space: { label: 'Space weather', color: '#d58cff' },
    drought: { label: 'Drought', color: '#c9a06b' },
    other: { label: 'Other', color: '#93a1b5' }
  };
  var GROUPS = { hazards: ['Hazards', ['earthquake', 'weather', 'storm', 'flood', 'wildfire', 'volcano', 'drought', 'tsunami', 'smoke']],
    transport: ['Transport', ['transport', 'aviation']], outages: ['Outages and cyber', ['outage', 'cyber']], recalls: ['Recalls and safety', ['recall']],
    world: ['World events', ['statement', 'headline']],
    notices: ['Official notices', ['notice']], security: ['Security news', ['security']], space: ['Space', ['space', 'launch']] };
  var SEV = { extreme: '#ff5c5c', severe: '#ff6a3d', moderate: '#f3cb45', minor: '#93a1b5' };
  function ago(iso, now) {
    var m = Math.max(1, Math.round(((now || Date.now()) - Date.parse(iso)) / 60000));
    if (m < 60) return m + 'm ago';
    var h = Math.round(m / 60);
    if (h < 48) return h + 'h ago';
    return Math.round(h / 24) + 'd ago';
  }
  function eventAge(event, generated, now) {
    var build = Date.parse(generated), first = new Date(event.first_seen);
    if (event.first_seen && Math.abs(build - Date.parse(event.time)) <= 9e5 && build - first > 9e5) {
      var hour = first.getHours();
      return 'since ' + (hour % 12 || 12) + ':' + String(first.getMinutes()).padStart(2, '0') + (hour < 12 ? ' am' : ' pm');
    }
    return ago(event.time, now);
  }
  var SEVRANK = { extreme: 0, severe: 1, moderate: 2, minor: 3 };
  function filterEvents(events, f, now) {
    now = now || Date.now();
    var hrs = f.hours == null ? (f.day ? 24 : 72) : f.hours;
    function age(e) { return now - Date.parse(e.updated || e.time); }
    function tier(e) { return e.severity === 'extreme' ? 0 : age(e) > 864e5 ? 2 : 1; }
    return events.filter(function (e) {
      if (f.type && f.type !== 'all') {
        if (f.type.indexOf('g:') === 0) { if (GROUPS[f.type.slice(2)][1].indexOf(e.type) < 0) return false; }
        else if (e.type !== f.type) return false;
      }
      if (f.region && f.region !== 'all' && e.region !== f.region) return false;
      if (f.sev && SEVRANK[f.sev] != null && (SEVRANK[e.severity] == null ? 9 : SEVRANK[e.severity]) > SEVRANK[f.sev]) return false;
      if (hrs && age(e) > hrs * 36e5 && !((f.hours == null || f.hours === 72) && e.severity === 'extreme')) return false; // the default list never ages out an extreme event
      return true;
    }).sort(function (a, b) {
      return tier(a) - tier(b);
    });
  }
  function withoutLead(events, lead) {
    if (!lead || (!lead.id && !lead.headline)) return events;
    return events.filter(function (e) { return lead.id ? e.id !== lead.id : e.title !== lead.headline; });
  }
  function groupEvents(events) {
    var groups = new Map();
    events.forEach(function (event) {
      var key = JSON.stringify([event.type, event.title, event.severity, event.place]);
      if (!groups.has(key)) groups.set(key, { ev: event, members: [] });
      groups.get(key).members.push(event);
    });
    return Array.from(groups.values());
  }
  function safeUrl(u) { return /^https:\/\/[^\s]+$/.test(u || '') ? u : null; }
  function sourceLink(url, text, rel) {
    var href = safeUrl(url), node = document.createElement(href ? 'a' : 'span');
    node.textContent = text;
    if (href) {
      node.href = href;
      node.rel = rel || 'noopener';
    }
    return node;
  }
  var ILLUS = { earthquake: ['earthquake-1', 'earthquake-2', 'earthquake-3'], storm: ['storm-1', 'storm-2', 'storm-3'], wildfire: ['wildfire-4', 'wildfire-5', 'wildfire-6'],
    smoke: ['wildfire-4', 'wildfire-5', 'wildfire-6'], flood: ['flood-1', 'flood-2', 'flood-3'], volcano: ['volcano-1', 'volcano-2', 'volcano-3'], outage: ['outage-2', 'outage-3', 'outage-5', 'outage-6'],
    cyber: ['outage-2', 'outage-3', 'outage-5', 'outage-6'], transport: ['flight-1', 'flight-2', 'flight-3'], recall: ['recall-1', 'recall-3'], space: ['space-2', 'space-3'] };
  function illustrationFor(e) {
    var list = ILLUS[e.type]; if (!list) return null;
    var h = 0, s = e.id || ''; for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return 'assets/illustrations/' + list[h % list.length] + '.webp';
  }
  function renderIllustration(src) {
    var d = document, f = d.createElement('figure'); f.className = 'ctx-fig illus';
    var wrap = d.createElement('div'); wrap.className = 'illus-wrap';
    var im = d.createElement('img'); im.loading = 'lazy'; im.decoding = 'async'; im.src = src; im.width = 320; im.height = 180; im.alt = 'Illustration of the kind of event. It is not a photo of this event.'; wrap.appendChild(im);
    var tag = d.createElement('span'); tag.className = 'illus-tag'; tag.textContent = 'Illustration'; wrap.appendChild(tag); f.appendChild(wrap);
    var fc = d.createElement('figcaption'); fc.className = 'src'; fc.textContent = 'Illustration made for this site. It does not show the actual scene.'; f.appendChild(fc);
    return f;
  }
  function renderContext(c, e, heading) {
    var d = document, box = d.createElement('div'); box.className = 'ctx';
    function el(t, cls, x) { var n = d.createElement(t); if (cls) n.className = cls; if (x != null) n.textContent = x; return n; }
    box.appendChild(el(heading || 'h3', '', 'Context'));
    if (c.summary) {
      var p = el('p', 'ctx-text', c.summary.text); box.appendChild(p);
      var cr = el('p', 'src'); cr.appendChild(d.createTextNode('Text from Wikipedia: ')); cr.appendChild(sourceLink(c.summary.url, c.summary.title));
      cr.appendChild(d.createTextNode(' (')); cr.appendChild(sourceLink(c.summary.history_url, 'authors'));
      cr.appendChild(d.createTextNode('), licence ')); cr.appendChild(sourceLink('https://creativecommons.org/licenses/by-sa/4.0/', c.summary.licence)); cr.appendChild(d.createTextNode('. Not our words.'));
      box.appendChild(cr);
    }
    var photo = c.image && safeUrl(c.image.src);
    if (photo) {
      var f = el('figure', 'ctx-fig'); var im = d.createElement('img'); im.loading = 'lazy'; im.decoding = 'async'; im.alt = 'Photo related to ' + (c.summary ? c.summary.title : 'this item'); im.src = photo; im.width = 320; f.appendChild(im);
      var fc = el('figcaption', 'src'); fc.appendChild(d.createTextNode('Photo: ' + c.image.author + ', ' + c.image.license + '. ')); fc.appendChild(sourceLink(c.image.credit_url, 'File page on Wikimedia Commons')); f.appendChild(fc); box.appendChild(f);
    }
    if (c.satellite && safeUrl(c.satellite.src)) {
      var f2 = el('figure', 'ctx-fig'); var im2 = d.createElement('img'); im2.loading = 'lazy'; im2.decoding = 'async'; im2.alt = 'Satellite view of the wider area'; im2.src = c.satellite.src; im2.width = 320; f2.appendChild(im2);
      var fc2 = el('figcaption', 'src'); fc2.appendChild(d.createTextNode(c.satellite.note + ' Credit: ')); fc2.appendChild(sourceLink(c.satellite.credit_url, c.satellite.credit)); f2.appendChild(fc2); box.appendChild(f2);
    }
    if (!photo && e) { var il = illustrationFor(e); if (il) box.appendChild(renderIllustration(il)); }
    return box;
  }
  var STOCK_TYPE = { earthquake: 'earthquake', wildfire: 'wildfire', smoke: 'wildfire', storm: 'storm', flood: 'flood', tsunami: 'flood', volcano: 'volcano', outage: 'outage', cyber: 'cyber', recall: 'recall', space: 'space', drought: 'heat' };
  function stockTag(e) {
    if (!e) return null;
    if (e.type === 'weather') {
      var t = (e.title || '').toLowerCase();
      if (/heat|hot|fire weather|red flag/.test(t)) return 'heat';
      if (/winter|blizzard|snow|freez|frost|ice|cold|chill/.test(t)) return 'winter';
      if (/flood/.test(t)) return 'flood';
      if (/hurricane|cyclone|tropical|storm|wind|gale|tornado/.test(t)) return 'storm';
      return null;
    }
    return STOCK_TYPE[e.type] || null;
  }
  function pickStock(manifest, tag, key) {
    var items = (manifest && manifest.items || []).filter(function (i) { return i.tag === tag; });
    if (!items.length) return null;
    var n = 0; String(key || '').split('').forEach(function (c) { n = (n + c.charCodeAt(0)) % 9973; });
    return items[n % items.length];
  }
  function stockPicture(item, sizes, eager) {
    var d = document, pic = d.createElement('picture');
    ['avif', 'webp'].forEach(function (ext) {
      var s = d.createElement('source'); s.type = 'image/' + ext;
      s.srcset = [375, 768, 1440].map(function (w) { return 'assets/stock/web/' + item.id + '-' + w + '.' + ext + ' ' + w + 'w'; }).join(', ');
      s.sizes = sizes || '100vw'; pic.appendChild(s);
    });
    var im = d.createElement('img'); im.src = 'assets/stock/web/' + item.id + '-768.jpg'; im.alt = item.alt; im.width = 1440; im.height = 810;
    im.decoding = 'async'; if (!eager) im.loading = 'lazy'; pic.appendChild(im);
    return pic;
  }
  var api = { sourceLink: sourceLink, stockTag: stockTag, pickStock: pickStock, stockPicture: stockPicture, ILLUS: ILLUS, illustrationFor: illustrationFor, renderContext: renderContext, GROUPS: GROUPS, TYPES: TYPES, SEV: SEV, ago: ago, eventAge: eventAge, filterEvents: filterEvents, withoutLead: withoutLead, groupEvents: groupEvents, safeUrl: safeUrl };
  if (typeof module !== 'undefined') module.exports = api; else root.BND = api;
})(this);
