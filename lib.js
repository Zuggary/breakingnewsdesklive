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
  var GROUPS = {
    hazards: ['Hazards', ['earthquake', 'weather', 'storm', 'flood', 'wildfire', 'volcano', 'drought', 'tsunami', 'smoke']],
    transport: ['Transport', ['transport', 'aviation']],
    outages: ['Outages and cyber', ['outage', 'cyber']],
    recalls: ['Recalls and safety', ['recall']],
    world: ['World events', ['statement', 'headline']],
    notices: ['Official notices', ['notice']],
    security: ['Security news', ['security']],
    space: ['Space', ['space', 'launch']]
  };
  var SEV = { extreme: '#ef4444', severe: '#f2b33d', moderate: '#4cc3ff', minor: '#9fb4c8' };
  var SEV_TOKENS = {
    extreme: { bar: '#ef4444', text: '#fecaca', soft: 'rgba(239, 68, 68, 0.20)', code: 'EXT', label: 'EXTREME' },
    severe: { bar: '#f2b33d', text: '#ffd98a', soft: 'rgba(242, 179, 61, 0.16)', code: 'SEV', label: 'SEVERE' },
    moderate: { bar: '#4cc3ff', text: '#9fd3ff', soft: 'rgba(76, 195, 255, 0.16)', code: 'MOD', label: 'MODERATE' },
    minor: { bar: '#9fb4c8', text: '#b9c8d6', soft: 'rgba(185, 200, 214, 0.10)', code: 'MIN', label: 'MINOR' }
  };
  var SHORT = {
    'usgs-quakes': 'USGS',
    'nws-alerts': 'NWS',
    nhc: 'NHC',
    eonet: 'NASA',
    gdacs: 'GDACS',
    'usgs-volcano': 'USGS',
    'swpc-kp': 'NOAA SWPC',
    'spc-outlook': 'NOAA SPC',
    'hms-smoke': 'NOAA HMS',
    'atd-faa': 'FAA',
    'awc-sigmet': 'NOAA AWC',
    ms365: 'MS365',
    'openfda-food': 'FDA',
    cpsc: 'CPSC',
    'cisa-kev': 'CISA',
    'fedreg-presidential': 'FED REG',
    fcdo: 'UK FCDO',
    'eu-press': 'EU',
    'gdelt-doc': 'GDELT',
    probes: 'DESK PROBES',
    'news-lane': 'NEWS',
    curated: 'DESK',
    'tsunami-ak': 'NOAA',
    'tsunami-hi': 'NOAA',
    'status-github': 'GITHUB',
    'status-cloudflare': 'CLOUDFLARE',
    'status-openai': 'OPENAI',
    'status-atlassian': 'ATLASSIAN'
  };
  var OFFICIAL_TYPES = {
    earthquake: 1, weather: 1, volcano: 1, storm: 1, flood: 1, wildfire: 1, smoke: 1,
    tsunami: 1, space: 1, drought: 1, transport: 1, aviation: 1, recall: 1, cyber: 1, notice: 1
  };
  var NAMED_ENTITIES = {
    amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ',
    ndash: '\u2013', mdash: '\u2014', lsquo: '\u2018', rsquo: '\u2019',
    sbquo: '\u201a', ldquo: '\u201c', rdquo: '\u201d', bdquo: '\u201e',
    hellip: '\u2026', bull: '\u2022', middot: '\u00b7', laquo: '\u00ab',
    raquo: '\u00bb', deg: '\u00b0', plusmn: '\u00b1', times: '\u00d7',
    divide: '\u00f7', copy: '\u00a9', reg: '\u00ae', trade: '\u2122',
    euro: '\u20ac', pound: '\u00a3', yen: '\u00a5', cent: '\u00a2',
    sect: '\u00a7', para: '\u00b6',
    Agrave: '\u00c0', Aacute: '\u00c1', Acirc: '\u00c2', Atilde: '\u00c3', Auml: '\u00c4', Aring: '\u00c5', AElig: '\u00c6', Ccedil: '\u00c7',
    Egrave: '\u00c8', Eacute: '\u00c9', Ecirc: '\u00ca', Euml: '\u00cb', Igrave: '\u00cc', Iacute: '\u00cd', Icirc: '\u00ce', Iuml: '\u00cf',
    ETH: '\u00d0', Ntilde: '\u00d1', Ograve: '\u00d2', Oacute: '\u00d3', Ocirc: '\u00d4', Otilde: '\u00d5', Ouml: '\u00d6', Oslash: '\u00d8',
    Ugrave: '\u00d9', Uacute: '\u00da', Ucirc: '\u00db', Uuml: '\u00dc', Yacute: '\u00dd', THORN: '\u00de', szlig: '\u00df',
    agrave: '\u00e0', aacute: '\u00e1', acirc: '\u00e2', atilde: '\u00e3', auml: '\u00e4', aring: '\u00e5', aelig: '\u00e6', ccedil: '\u00e7',
    egrave: '\u00e8', eacute: '\u00e9', ecirc: '\u00ea', euml: '\u00eb', igrave: '\u00ec', iacute: '\u00ed', icirc: '\u00ee', iuml: '\u00ef',
    eth: '\u00f0', ntilde: '\u00f1', ograve: '\u00f2', oacute: '\u00f3', ocirc: '\u00f4', otilde: '\u00f5', ouml: '\u00f6', oslash: '\u00f8',
    ugrave: '\u00f9', uacute: '\u00fa', ucirc: '\u00fb', uuml: '\u00fc', yacute: '\u00fd', thorn: '\u00fe', yuml: '\u00ff'
  };
  function decodeEntities(text) {
    if (typeof text !== 'string') return '';
    var out = text;
    for (var pass = 0; pass < 3; pass++) {
      var next = out
        .replace(/&#x([0-9a-f]{1,6});?/gi, function (m, hex) {
          var cp = parseInt(hex, 16);
          return cp > 0 && cp <= 0x10ffff && !(cp >= 0xd800 && cp <= 0xdfff) ? String.fromCodePoint(cp) : m;
        })
        .replace(/&#(\d{1,7});?/g, function (m, dec) {
          var cp = parseInt(dec, 10);
          return cp > 0 && cp <= 0x10ffff && !(cp >= 0xd800 && cp <= 0xdfff) ? String.fromCodePoint(cp) : m;
        })
        .replace(/&([a-zA-Z][a-zA-Z0-9]{1,15});/g, function (m, name) {
          if (Object.prototype.hasOwnProperty.call(NAMED_ENTITIES, name)) return NAMED_ENTITIES[name];
          var low = name.toLowerCase();
          return Object.prototype.hasOwnProperty.call(NAMED_ENTITIES, low) ? NAMED_ENTITIES[low] : m;
        });
      if (next === out) break;
      out = next;
    }
    return out;
  }
  function cleanDc(text) {
    if (typeof text !== 'string') return '';
    return decodeEntities(text).replace(/\b(?:Washington,?\s+D\.?C\.?|District of Columbia)(?!\w)/gi, 'DC');
  }
  function sanitizeEvent(e) {
    if (!e || typeof e !== 'object') return e;
    var copy = Object.assign({}, e);
    ['title', 'place', 'summary', 'source', 'source_short', 'region', 'what_changed'].forEach(function (k) {
      if (typeof copy[k] === 'string') copy[k] = cleanDc(copy[k]);
    });
    if (copy.detail && typeof copy.detail === 'object') {
      var det = Object.assign({}, copy.detail);
      ['headline', 'reported_line', 'reason', 'fir', 'volcano', 'observatory', 'outlet_names', 'status', 'impact', 'measured_at', 'cleared_at', 'location_note', 'issuer', 'state'].forEach(function (k) {
        if (typeof det[k] === 'string') det[k] = cleanDc(det[k]);
      });
      if (Array.isArray(det.sources)) {
        det.sources = det.sources.map(function (s) {
          if (!s || typeof s !== 'object') return s;
          var sc = Object.assign({}, s);
          if (typeof sc.source === 'string') sc.source = cleanDc(sc.source);
          if (typeof sc.name === 'string') sc.name = cleanDc(sc.name);
          if (typeof sc.scope === 'string') sc.scope = cleanDc(sc.scope);
          if (typeof sc.intermediary === 'string') sc.intermediary = cleanDc(sc.intermediary);
          return sc;
        });
      }
      if (Array.isArray(det.responses)) {
        det.responses = det.responses.map(function (r) {
          if (!r || typeof r !== 'object') return r;
          var rc = Object.assign({}, r);
          if (typeof rc.who === 'string') rc.who = cleanDc(rc.who);
          if (typeof rc.text === 'string') rc.text = cleanDc(rc.text);
          return rc;
        });
      }
      copy.detail = det;
    }
    if (Array.isArray(copy.links)) {
      copy.links = copy.links.map(function (l) {
        if (!l || typeof l !== 'object') return l;
        var lc = Object.assign({}, l);
        if (typeof lc.label === 'string') lc.label = cleanDc(lc.label);
        if (typeof lc.title === 'string') lc.title = cleanDc(lc.title);
        return lc;
      });
    }
    if (Array.isArray(copy.history)) {
      copy.history = copy.history.map(function (h) {
        if (!h || typeof h !== 'object') return h;
        var hc = Object.assign({}, h);
        if (typeof hc.why === 'string') hc.why = cleanDc(hc.why);
        if (typeof hc.from === 'string') hc.from = cleanDc(hc.from);
        if (typeof hc.to === 'string') hc.to = cleanDc(hc.to);
        return hc;
      });
    }
    return copy;
  }
  function severityTokens(sev) {
    return SEV_TOKENS[sev] || SEV_TOKENS.minor;
  }
  function ago(iso, now) {
    var m = Math.max(1, Math.round(((now || Date.now()) - Date.parse(iso)) / 60000));
    if (m < 60) return m + 'm ago';
    var h = Math.round(m / 60);
    if (h < 48) return h + 'h ago';
    return Math.round(h / 24) + 'd ago';
  }
  function isSnapshotFresh(generated, now) {
    var build = Date.parse(generated);
    return Number.isFinite(build) && (((now || Date.now()) - build) <= 45 * 60000);
  }
  function eventAge(event, generated, now) {
    var nowMs = now || Date.now();
    var build = Date.parse(generated), first = new Date(event.first_seen);
    var withinSnap = !Number.isFinite(build) || (nowMs - build <= 45 * 60000);
    if (withinSnap && event.first_seen && Math.abs(build - Date.parse(event.time)) <= 9e5 && build - first > 9e5) {
      var hour = first.getHours(), stamp = (hour % 12 || 12) + ':' + String(first.getMinutes()).padStart(2, '0') + (hour < 12 ? ' am' : ' pm');
      var days = Math.round((new Date(build).setHours(0, 0, 0, 0) - new Date(first).setHours(0, 0, 0, 0)) / 864e5);
      if (days <= 0) return 'since ' + stamp;
      if (days === 1) return 'since yesterday ' + stamp;
      return 'since ' + first.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' + stamp;
    }
    return ago(event.time, nowMs);
  }
  function itemFreshness(event, generated, now, srcMeta) {
    var nowMs = now || Date.now();
    var ts = event && (event.updated || event.time);
    var evMs = Date.parse(ts || '');
    var ageMs = Number.isFinite(evMs) ? Math.max(0, nowMs - evMs) : Infinity;
    var snapFresh = isSnapshotFresh(generated, nowMs);
    var srcStale = Boolean(srcMeta && (srcMeta.freshness === 'stale' || srcMeta.ok === false));
    var oldItem = ageMs > 24 * 3600000;
    var rawAge = event ? eventAge(event, generated, nowMs) : '';
    return {
      stale: srcStale,
      oldItem: oldItem,
      snapFresh: snapFresh,
      badge: srcStale ? 'SOURCE STALE' : '',
      ageText: rawAge,
      rawAge: rawAge
    };
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
    return events.filter(function (e) { return lead.id ? e.id !== lead.id : !(e.title === lead.headline && e.confidence); }); // with no id, only a news row with that title is the lead
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
  function validatedCommonsImage(c) {
    var imMeta = c && c.image;
    if (!imMeta) return null;
    var src = safeUrl(imMeta.src);
    var creditUrl = safeUrl(imMeta.credit_url);
    var author = imMeta.author ? String(imMeta.author).trim() : '';
    var license = imMeta.license ? String(imMeta.license).trim() : '';
    if (!src || !author || !license || !creditUrl) return null;
    if (!/^https:\/\/commons\.wikimedia\.org\/wiki\/File:/i.test(creditUrl)) return null;
    return { src: src, author: author, license: license, credit_url: creditUrl };
  }
  function renderContext(c, e, heading) {
    c = c || {};
    var d = document, box = d.createElement('div'); box.className = 'ctx';
    function el(t, cls, x) { var n = d.createElement(t); if (cls) n.className = cls; if (x != null) n.textContent = x; return n; }
    box.appendChild(el(heading || 'h3', '', 'Context'));
    if (c.summary) {
      var p = el('p', 'ctx-text', cleanDc(c.summary.text)); box.appendChild(p);
      var cr = el('p', 'src'); cr.appendChild(d.createTextNode('Text from Wikipedia: ')); cr.appendChild(sourceLink(c.summary.url, cleanDc(c.summary.title)));
      cr.appendChild(d.createTextNode(' (')); cr.appendChild(sourceLink(c.summary.history_url, 'authors'));
      cr.appendChild(d.createTextNode('), licence ')); cr.appendChild(sourceLink('https://creativecommons.org/licenses/by-sa/4.0/', c.summary.licence)); cr.appendChild(d.createTextNode('. Not our words.'));
      box.appendChild(cr);
    }
    var validImg = validatedCommonsImage(c);
    if (validImg) {
      var f = el('figure', 'ctx-fig'); var im = d.createElement('img'); im.loading = 'lazy'; im.decoding = 'async'; im.alt = 'Photo related to ' + (c.summary ? cleanDc(c.summary.title) : 'this item'); im.src = validImg.src; im.width = 320; f.appendChild(im);
      var fc = el('figcaption', 'src'); fc.appendChild(d.createTextNode('Photo: ' + cleanDc(validImg.author) + ', ' + cleanDc(validImg.license) + '. ')); fc.appendChild(sourceLink(validImg.credit_url, 'File page on Wikimedia Commons')); f.appendChild(fc); box.appendChild(f);
    }
    if (c.satellite && safeUrl(c.satellite.src)) {
      var f2 = el('figure', 'ctx-fig'); var im2 = d.createElement('img'); im2.loading = 'lazy'; im2.decoding = 'async'; im2.alt = 'Satellite view of the wider area'; im2.src = c.satellite.src; im2.width = 320; f2.appendChild(im2);
      var fc2 = el('figcaption', 'src'); fc2.appendChild(d.createTextNode(cleanDc(c.satellite.note) + ' Credit: ')); fc2.appendChild(sourceLink(c.satellite.credit_url, cleanDc(c.satellite.credit))); f2.appendChild(fc2); box.appendChild(f2);
    }
    if (!validImg && e) { var il = illustrationFor(e); if (il) box.appendChild(renderIllustration(il)); }
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
    if (item && item.tag) pic.setAttribute('data-stock-tag', item.tag);
    ['avif', 'webp'].forEach(function (ext) {
      var s = d.createElement('source'); s.type = 'image/' + ext;
      s.srcset = [375, 768, 1440].map(function (w) { return 'assets/stock/web/' + item.id + '-' + w + '.' + ext + ' ' + w + 'w'; }).join(', ');
      s.sizes = sizes || '100vw'; pic.appendChild(s);
    });
    var im = d.createElement('img'); im.src = 'assets/stock/web/' + item.id + '-768.jpg'; im.alt = item.alt; im.width = 1440; im.height = 810;
    im.decoding = 'async'; if (!eager) im.loading = 'lazy'; pic.appendChild(im);
    return pic;
  }
  function verificationTag(e) {
    if (!e || typeof e !== 'object') {
      return { code: 'REPORTED', short: 'REPORTED', label: 'Reported', color: '#b8c7d6' };
    }
    var status = String(e.status || '');
    var conf = String(e.confidence || '');
    var d = e.detail || {};
    if (conf === 'Resolved' || d.open === false) {
      return { code: 'RESOLVED', short: 'RESOLVED', label: 'Resolved', color: '#b8c7d6' };
    }
    if (conf === 'Corrected') {
      return { code: 'CORRECTED', short: 'CORRECTED', label: 'Corrected', color: '#ffd98a' };
    }
    if (conf === 'Contested') {
      return { code: 'CONTESTED', short: 'CONTESTED', label: 'Contested', color: '#fecaca' };
    }
    if (/unverified/i.test(conf) || (e.type === 'headline' && conf !== 'Corroborated') || e.type === 'statement' ||
      ((e.source_id === 'probes' || d.lane === 'probes') && d.open !== false)) {
      return { code: 'UNVERIFIED', short: 'UNVERIFIED', label: 'Unverified lead', color: '#ffd98a' };
    }
    if (conf === 'Corroborated') {
      return { code: 'CORROBORATED', short: 'CORROBORATED', label: 'Corroborated', color: '#eef3f8' };
    }
    if (status === 'UNVERIFIED') {
      return { code: 'UNVERIFIED', short: 'UNVERIFIED', label: 'Unverified lead', color: '#ffd98a' };
    }
    if (status === 'DEVELOPING') {
      return { code: 'DEVELOPING', short: 'DEVELOPING', label: 'Developing', color: '#ffd98a' };
    }
    if (conf === 'Official single source' || OFFICIAL_TYPES[e.type] || e.source_id === 'ms365' ||
      String(e.source_id || '').indexOf('status-') === 0) {
      return { code: 'OFFICIAL SINGLE SOURCE', short: 'OFFICIAL', label: 'Official single source', color: '#a7f3d0' };
    }
    return { code: 'REPORTED', short: 'REPORTED', label: 'Reported', color: '#b8c7d6' };
  }
  function displaySource(e, opts) {
    if (!e || typeof e !== 'object') return 'Public source';
    var compact = !!(opts && opts.compact);
    var d = e.detail || {};
    if (Array.isArray(d.sources) && d.sources.length) {
      var seen = {}, names = [];
      d.sources.forEach(function (src) {
        var raw = cleanDc(String((src && (src.source || src.name)) || '').trim());
        if (raw && !seen[raw]) { seen[raw] = 1; names.push(raw); }
      });
      if (names.length) {
        if (compact) {
          if (names.length === 1) return names[0];
          return names[0] + ' +' + (names.length - 1);
        }
        return names.slice(0, 3).join(', ') + (names.length > 3 ? ' +' + (names.length - 3) : '');
      }
    }
    if (compact) {
      return cleanDc(e.source_short || SHORT[e.source_id] || e.source || 'Public source');
    }
    return cleanDc(e.source || SHORT[e.source_id] || 'Public source');
  }
  function formatCoord(lat, lon) {
    if (lat == null || lon == null || !Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    return Math.abs(lat).toFixed(1) + '\u00b0' + (lat >= 0 ? 'N' : 'S') + ' ' + Math.abs(lon).toFixed(1) + '\u00b0' + (lon >= 0 ? 'E' : 'W');
  }
  function compactFacts(e) {
    if (!e || typeof e !== 'object') return [];
    var d = e.detail || {}, facts = [];
    var coord = formatCoord(e.lat, e.lon);
    if (coord) facts.push(coord);
    if (e.type === 'earthquake') {
      if (d.magnitude != null && String(e.title || '').indexOf(String(d.magnitude)) === -1) facts.push('M ' + d.magnitude);
      if (d.depth_km != null) facts.push('Depth ' + d.depth_km + ' km');
      if (d.pager) facts.push('PAGER ' + d.pager);
    } else if (e.type === 'storm') {
      if (d.magnitude != null) facts.push(d.magnitude + ' ' + (d.unit ? String(d.unit).toLowerCase() : 'kts'));
    } else if (e.type === 'volcano') {
      if (d.alert_level) facts.push(d.alert_level + (d.color_code ? ' (' + d.color_code + ')' : ''));
    } else if (e.type === 'weather') {
      if (d.alerts != null) facts.push(d.alerts + ' active alert' + (d.alerts === 1 ? '' : 's'));
    } else if (e.type === 'space') {
      if (d.kp != null) facts.push('Kp ' + d.kp + (d.g_scale ? ', G' + d.g_scale : ''));
    } else if (e.type === 'smoke') {
      if (d.plumes != null) facts.push(d.plumes + ' plume' + (d.plumes === 1 ? '' : 's'));
    } else if (e.type === 'transport' || e.type === 'aviation') {
      if (d.reason) facts.push('Reason: ' + cleanDc(String(d.reason)));
      if (d.avg_delay_text) facts.push('Avg delay ' + d.avg_delay_text);
      else if (d.max_delay_text) facts.push('Max delay ' + d.max_delay_text);
      if (d.until) facts.push('Until ' + d.until);
    } else if (e.type === 'outage' || e.type === 'cyber') {
      if (d.measured_at) facts.push('First failing check ' + d.measured_at);
      if (d.cleared_at) facts.push('Cleared ' + d.cleared_at);
      if (d.status && !d.measured_at) facts.push('Status: ' + d.status + (d.impact ? ' (' + d.impact + ')' : ''));
    } else if (Array.isArray(d.sources) && d.sources.length) {
      facts.push(d.sources.length + ' attributed source' + (d.sources.length === 1 ? '' : 's'));
    }
    return facts;
  }
  function fmtUtc(iso) {
    var ms = Date.parse(iso);
    if (!Number.isFinite(ms)) return '';
    var dt = new Date(ms);
    return String(dt.getUTCHours()).padStart(2, '0') + ':' + String(dt.getUTCMinutes()).padStart(2, '0') + ' UTC';
  }
  function whatChangedLine(e) {
    if (!e || typeof e !== 'object') return 'No source revision recorded.';
    if (typeof e.what_changed === 'string' && e.what_changed.trim()) return cleanDc(e.what_changed.trim());
    var d = e.detail || {};
    if (Array.isArray(e.history) && e.history.length) {
      var latest = e.history.reduce(function (best, cur) {
        if (!cur || typeof cur !== 'object') return best;
        if (!best) return cur;
        return (Date.parse(cur.t || e.time) || 0) >= (Date.parse(best.t || e.time) || 0) ? cur : best;
      }, null);
      if (latest) {
        var when = fmtUtc(latest.t || e.updated || e.time);
        var oldL = latest.from, newL = latest.to;
        if (oldL && newL && oldL !== newL) {
          var levels = ['Unverified lead', 'Official single source', 'Corroborated'];
          var dir = 'changed';
          if (levels.indexOf(oldL) !== -1 && levels.indexOf(newL) !== -1) {
            dir = levels.indexOf(newL) > levels.indexOf(oldL) ? 'raised' : 'lowered';
          }
          return 'Updated ' + when + ': label ' + dir + ' from ' + oldL + ' to ' + newL;
        }
        return 'Updated ' + when + ': ' + cleanDc(String(latest.why || 'item updated'));
      }
    }
    if (e.updated && e.updated !== e.time && fmtUtc(e.updated)) {
      return 'Updated ' + fmtUtc(e.updated) + ': bulletin revised since ' + fmtUtc(e.time);
    }
    if (d.cleared_at) {
      return 'Updated: desk probes cleared at ' + cleanDc(String(d.cleared_at)) + ' after 3 healthy checks';
    }
    if (d.measured_at) {
      return 'Measured by the desk: first failing probe at ' + cleanDc(String(d.measured_at)) + ' (no service resolution statement)';
    }
    if (e.first_seen && e.time) {
      var tMs = Date.parse(e.time), fMs = Date.parse(e.first_seen);
      if (Number.isFinite(tMs) && Number.isFinite(fMs) && Math.abs(tMs - fMs) >= 60000) {
        if (tMs > fMs) return 'Updated ' + fmtUtc(e.time) + ': active source bulletin (first tracked ' + fmtUtc(e.first_seen) + ')';
        return 'Tracked since ' + fmtUtc(e.first_seen) + ': no source revision since ' + fmtUtc(e.time);
      }
    }
    var pub = fmtUtc(e.time);
    return pub ? ('No changes since first published at ' + pub + '.') : 'No source revision recorded.';
  }
  function twoLines(summary, limit) {
    var s = cleanDc(String(summary || '')).trim();
    var cap = limit || 240;
    if (!s) return '';
    var parts = s.split(/(?<=[.!?])\s+/);
    var out = parts.slice(0, 2).join(' ').trim();
    if (out.length > cap) {
      var cut = out.slice(0, cap);
      var idx = cut.lastIndexOf(' ');
      out = (idx > 0 ? cut.slice(0, idx) : cut).replace(/[,;]+$/, '') + '...';
    }
    return out;
  }
  function leadKindOf(e) {
    if (!e) return 'event';
    if (e.big) return 'big';
    var d = e.detail || {};
    if (d.lane === 'curated' || e.curated) return 'curated';
    if (d.lane === 'news') return 'news';
    return 'event';
  }
  function leadSourcesOf(e) {
    var d = e.detail || {}, out = [];
    if (d.lane === 'curated' && Array.isArray(d.sources)) {
      var urls = {};
      (e.links || []).forEach(function (l) { if (l && l.label) urls[cleanDc(l.label)] = l.url; });
      d.sources.forEach(function (s) {
        if (s && s.source) {
          var name = cleanDc(s.source);
          out.push({ name: name, intermediary: s.intermediary ? cleanDc(s.intermediary) : null, url: urls[name] || null });
        }
      });
    } else if (d.lane === 'news' && Array.isArray(e.links)) {
      e.links.slice(0, 6).forEach(function (l) {
        if (l && l.label) out.push({ name: cleanDc(l.label), intermediary: null, url: l.url || null });
      });
    } else if (e.source) {
      out.push({ name: cleanDc(e.source), intermediary: null, url: e.source_url || null });
    }
    return out;
  }
  function deriveLeadStory(events, generated) {
    if (!Array.isArray(events) || !events.length) {
      return { generated: generated || '', as_of: generated || '', lead: null, next: [] };
    }
    var ranked = [], seen = {};
    function pushMatch(pred) {
      events.forEach(function (e) {
        if (e && !seen[e.id] && pred(e)) { seen[e.id] = 1; ranked.push(e); }
      });
    }
    pushMatch(function (e) { return leadKindOf(e) === 'big'; });
    pushMatch(function (e) { return leadKindOf(e) === 'curated'; });
    pushMatch(function (e) { return leadKindOf(e) === 'news'; });
    pushMatch(function (e) { return e.type !== 'headline' && e.type !== 'statement'; });
    pushMatch(function () { return true; });
    function toStory(e) {
      var d = e.detail || {};
      return {
        id: e.id,
        kind: leadKindOf(e),
        headline: e.title,
        summary: twoLines(e.summary, 240),
        label: e.confidence || verificationTag(e).label,
        reported_line: d.reported_line || null,
        place: e.place,
        severity: e.severity,
        sources: leadSourcesOf(e),
        updated: e.time,
        ticker_ok: Boolean(e.ticker_ok)
      };
    }
    return {
      generated: generated || '',
      as_of: generated || '',
      lead: toStory(ranked[0]),
      next: ranked.slice(1, 5).map(toStory)
    };
  }
  function buildRecapItems(events, leadEvent) {
    var list = Array.isArray(events) ? events : [];
    var primary = leadEvent || list[0] || null;
    if (!primary) return { primary: null, secondary: null };
    var secondary = null;
    for (var i = 0; i < list.length; i++) {
      var e = list[i];
      if (!e || e.id === primary.id) continue;
      if (e.confidence === 'Corroborated') { secondary = e; break; }
    }
    if (!secondary) {
      for (var j = 0; j < list.length; j++) {
        var e2 = list[j];
        if (!e2 || e2.id === primary.id) continue;
        if ((e2.severity === 'extreme' || e2.severity === 'severe') && e2.type !== 'headline' && e2.type !== 'statement') {
          secondary = e2; break;
        }
      }
    }
    if (!secondary) {
      for (var k = 0; k < list.length; k++) {
        var e3 = list[k];
        if (!e3 || e3.id === primary.id) continue;
        if (e3.type !== 'headline') { secondary = e3; break; }
      }
    }
    if (!secondary) {
      for (var m = 0; m < list.length; m++) {
        if (list[m] && list[m].id !== primary.id) { secondary = list[m]; break; }
      }
    }
    return { primary: primary, secondary: secondary };
  }
  function streamFocusId(events, lead) {
    var list = Array.isArray(events) ? events : [];
    function eligible(e) { return e && e.type !== 'statement' && e.type !== 'headline'; }
    if (lead && lead.id) {
      for (var i = 0; i < list.length; i++) {
        if (list[i] && list[i].id === lead.id && eligible(list[i])) return lead.id;
      }
    }
    for (var j = 0; j < list.length; j++) {
      if (eligible(list[j])) return list[j].id;
    }
    return null;
  }
  function opsCounts(events, sourcesData, now) {
    var evs = Array.isArray(events) ? events : [];
    var hazSet = {}, trSet = {};
    GROUPS.hazards[1].forEach(function (t) { hazSet[t] = 1; });
    GROUPS.transport[1].forEach(function (t) { trSet[t] = 1; });
    var severeHazards = 0, hazardsTotal = 0, probeFailing = 0, probeItems = 0, providerOutages = 0, outagesTotal = 0, airspace = 0, faaCount = 0;
    evs.forEach(function (e) {
      if (!e) return;
      var d = e.detail || {};
      if (hazSet[e.type]) {
        hazardsTotal++;
        if (e.severity === 'extreme' || e.severity === 'severe') severeHazards++;
      }
      if (e.type === 'outage' || e.type === 'cyber') {
        outagesTotal++;
        if (e.source_id === 'probes' || d.lane === 'probes') {
          probeItems++;
          if (d.open !== false) {
            if (typeof d.services_failing === 'number') probeFailing += d.services_failing;
            else if (Array.isArray(d.services)) probeFailing += d.services.length;
            else probeFailing += 1;
          }
        } else {
          providerOutages++;
        }
      }
      if (trSet[e.type]) {
        airspace++;
        if (e.source_id === 'atd-faa' || e.type === 'transport') faaCount++;
      }
    });
    var srcs = sourcesData && Array.isArray(sourcesData.sources) ? sourcesData.sources : [];
    var feedsTotal = srcs.length;
    var feedsStale = srcs.filter(function (s) {
      return s && (s.freshness === 'stale' || s.ok === false);
    }).length;
    return {
      total: evs.length,
      severeHazards: severeHazards,
      hazardsTotal: hazardsTotal,
      probeFailing: probeFailing,
      probeItems: probeItems,
      providerOutages: providerOutages,
      outagesTotal: outagesTotal,
      airspace: airspace,
      faaCount: faaCount,
      feedsFresh: feedsTotal - feedsStale,
      feedsTotal: feedsTotal,
      feedsStale: feedsStale
    };
  }
  function trimWholeWords(text, maxChars) {
    var s = cleanDc(String(text || '')).replace(/\s+/g, ' ').trim();
    var cap = maxChars == null ? 64 : Math.max(8, maxChars);
    if (s.length <= cap) return s;
    var cut = s.slice(0, cap + 1);
    var idx = cut.lastIndexOf(' ');
    var body = idx > 4 ? cut.slice(0, idx) : s.slice(0, cap);
    return body.replace(/[,:;.\-\u2014]+$/, '').trim() + '\u2026';
  }
  function packTickerItems(widths, containerWidth, gap, startIndex) {
    if (!Array.isArray(widths) || !widths.length) return { indices: [], overflowSingle: false };
    var n = widths.length;
    var idx = ((startIndex || 0) % n + n) % n;
    var g = gap || 0;
    var avail = Math.max(0, containerWidth || 0);
    if (widths[idx] > avail) {
      return { indices: [idx], overflowSingle: true };
    }
    var indices = [], used = 0;
    for (var k = 0; k < n; k++) {
      var cur = (idx + k) % n;
      var w = widths[cur];
      var nextUsed = used + (indices.length ? g : 0) + w;
      if (nextUsed <= avail) {
        indices.push(cur);
        used = nextUsed;
      } else {
        break;
      }
    }
    return { indices: indices, overflowSingle: false };
  }
  function mapCalloutText(e) {
    if (!e || typeof e !== 'object') return '';
    var d = e.detail || {};
    var title = cleanDc(String(e.title || '')).replace(/\s+/g, ' ').trim();
    var shortPlace = cleanDc(String(e.place || ''))
      .replace(/\s*\([^)]*\)\s*/g, ' ')
      .replace(/,\s*United States$/i, '')
      .replace(/\s{2,}/g, ' ')
      .trim();
    if (e.type === 'volcano' && d.volcano) {
      return cleanDc(String(d.volcano)) + (d.alert_level ? ' \u00b7 ' + cleanDc(String(d.alert_level)) : '');
    }
    if (e.type === 'earthquake') {
      var mag = d.magnitude != null ? 'M ' + d.magnitude : 'Quake';
      var qp = shortPlace;
      if (qp.length > 24) {
        qp = qp.replace(/^\d+\s*km\s+[NESW]{1,3}\s+of\s+/i, '')
          .replace(/^northern\s+/i, 'N. ')
          .replace(/^southern\s+/i, 'S. ')
          .replace(/^eastern\s+/i, 'E. ')
          .replace(/^western\s+/i, 'W. ')
          .trim();
      }
      if (qp.length > 26) qp = trimWholeWords(qp, 26);
      return mag + (qp ? ' \u00b7 ' + qp : '');
    }
    if (e.type === 'smoke') {
      return d.plumes != null ? (d.plumes + ' smoke plumes') : 'Heavy smoke plumes';
    }
    if (e.type === 'weather' || e.type === 'storm' || e.type === 'flood' || e.type === 'wildfire') {
      if (shortPlace && (title + ' \u00b7 ' + shortPlace).length <= 34) {
        return title + ' \u00b7 ' + shortPlace;
      }
      return title.length <= 34 ? title : trimWholeWords(title, 34);
    }
    return title.length <= 34 ? title : trimWholeWords(title, 34);
  }
  function placeMapCallouts(candidates, boundsW, boundsH, maxCount) {
    if (!Array.isArray(candidates) || !boundsW || !boundsH) return [];
    var cap = maxCount == null ? 5 : maxCount;
    if (cap <= 0) return [];
    var pad = 6, margin = 6;
    function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
    function overlaps(a, b) {
      return a.left < b.right + margin && a.right + margin > b.left &&
        a.top < b.bottom + margin && a.bottom + margin > b.top;
    }
    var sorted = candidates.slice().sort(function (a, b) {
      if (!!a.isSelected !== !!b.isSelected) return a.isSelected ? -1 : 1;
      return (a.rank != null ? a.rank : 999) - (b.rank != null ? b.rank : 999);
    });
    var placed = [], rects = [];
    for (var i = 0; i < sorted.length && placed.length < cap; i++) {
      var c = sorted[i];
      if (!c || c.pinX < 0 || c.pinX > boundsW || c.pinY < 0 || c.pinY > boundsH) continue;
      var w = Math.max(20, c.w || 80), h = Math.max(16, c.h || 22);
      var maxX = Math.max(pad, boundsW - w - pad), maxY = Math.max(pad, boundsH - h - pad);
      var positions = [
        [c.pinX + 14, c.pinY - h / 2],
        [c.pinX - w - 14, c.pinY - h / 2],
        [c.pinX - w / 2, c.pinY - h - 14],
        [c.pinX - w / 2, c.pinY + 14],
        [clamp(c.pinX - w / 2, pad, maxX), c.pinY - h - 14],
        [clamp(c.pinX - w / 2, pad, maxX), c.pinY + 14],
        [clamp(c.pinX - w / 2, pad, maxX), c.pinY - h - 24],
        [clamp(c.pinX - w / 2, pad, maxX), c.pinY + 24],
        [clamp(c.pinX + 14, pad, maxX), clamp(c.pinY - h / 2, pad, maxY)],
        [clamp(c.pinX - w - 14, pad, maxX), clamp(c.pinY - h / 2, pad, maxY)],
        [clamp(c.pinX + 14, pad, maxX), clamp(c.pinY + 24, pad, maxY)],
        [clamp(c.pinX - w - 14, pad, maxX), clamp(c.pinY + 24, pad, maxY)]
      ];
      for (var k = 0; k < positions.length; k++) {
        var bx = Math.round(positions[k][0]), by = Math.round(positions[k][1]);
        var rect = { left: bx, top: by, right: bx + w, bottom: by + h };
        if (rect.left < pad || rect.right > boundsW - pad || rect.top < pad || rect.bottom > boundsH - pad) continue;
        var hit = false;
        for (var j = 0; j < rects.length; j++) {
          if (overlaps(rect, rects[j])) { hit = true; break; }
        }
        if (hit) continue;
        placed.push({ id: c.id, rowId: c.rowId || c.id, pinX: c.pinX, pinY: c.pinY, boxX: bx, boxY: by, w: w, h: h });
        rects.push(rect);
        break;
      }
    }
    return placed;
  }
  function distinctPlace(e) {
    if (!e || !e.place) return '';
    var p = cleanDc(String(e.place)).trim();
    var t = cleanDc(String(e.title || '')).trim();
    if (!p || p.toLowerCase() === t.toLowerCase()) return '';
    return p;
  }
  function hasRevision(e) {
    if (!e || typeof e !== 'object') return false;
    if (typeof e.what_changed === 'string' && e.what_changed.trim()) return true;
    if (Array.isArray(e.history) && e.history.length > 0) return true;
    if (e.updated && e.updated !== e.time) return true;
    var d = e.detail || {};
    return Boolean(d.measured_at || d.cleared_at);
  }
  function shortChangedTag(e) {
    if (!hasRevision(e)) return '';
    if (typeof e.what_changed === 'string' && e.what_changed.trim()) {
      return trimWholeWords(e.what_changed.trim(), 56);
    }
    var d = e.detail || {};
    if (Array.isArray(e.history) && e.history.length) {
      var latest = e.history.reduce(function (best, cur) {
        if (!cur || typeof cur !== 'object') return best;
        if (!best) return cur;
        return (Date.parse(cur.t || e.time) || 0) >= (Date.parse(best.t || e.time) || 0) ? cur : best;
      }, null);
      if (latest) {
        var when = fmtUtc(latest.t || e.updated || e.time);
        if (latest.from && latest.to && latest.from !== latest.to) {
          return 'Updated ' + when + ' \u00b7 ' + cleanDc(String(latest.to));
        }
        return 'Updated ' + when + ': ' + trimWholeWords(String(latest.why || 'updated'), 42);
      }
    }
    if (e.updated && e.updated !== e.time && fmtUtc(e.updated)) {
      return 'Updated ' + fmtUtc(e.updated);
    }
    if (d.cleared_at) return 'Probes cleared ' + cleanDc(String(d.cleared_at));
    if (d.measured_at) return 'Probe fail ' + cleanDc(String(d.measured_at));
    return '';
  }
  var api = {
    sourceLink: sourceLink, stockTag: stockTag, pickStock: pickStock, stockPicture: stockPicture,
    ILLUS: ILLUS, illustrationFor: illustrationFor, validatedCommonsImage: validatedCommonsImage,
    renderContext: renderContext, GROUPS: GROUPS, TYPES: TYPES, SEV: SEV, SHORT: SHORT,
    decodeEntities: decodeEntities, cleanDc: cleanDc, sanitizeEvent: sanitizeEvent,
    severityTokens: severityTokens, verificationTag: verificationTag,
    displaySource: displaySource, formatCoord: formatCoord, compactFacts: compactFacts,
    whatChangedLine: whatChangedLine, distinctPlace: distinctPlace, hasRevision: hasRevision, shortChangedTag: shortChangedTag,
    deriveLeadStory: deriveLeadStory,
    buildRecapItems: buildRecapItems, streamFocusId: streamFocusId, opsCounts: opsCounts,
    isSnapshotFresh: isSnapshotFresh, itemFreshness: itemFreshness,
    trimWholeWords: trimWholeWords, packTickerItems: packTickerItems,
    mapCalloutText: mapCalloutText, placeMapCallouts: placeMapCallouts,
    ago: ago, eventAge: eventAge, filterEvents: filterEvents, withoutLead: withoutLead,
    groupEvents: groupEvents, safeUrl: safeUrl
  };
  if (typeof module !== 'undefined') module.exports = api; else root.BND = api;
})(this);
