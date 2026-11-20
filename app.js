(function () {
  'use strict';
  var B = window.BND, $ = function (id) { return document.getElementById(id); };
  var state = {
    events: [],
    world: [],
    generated: '',
    lead: null,
    sourcesData: null,
    sourcesById: {},
    streamId: null,
    f: { type: 'all', region: 'all', hours: 72, sev: '' },
    sel: null,
    globe: false,
    rot: [-40, 20],
    pts: [],
    calloutRects: [],
    allRows: [],
    rows: [],
    limit: 12,
    rankOf: {},
    tickerItems: [],
    tickerIdx: 0,
    tickerStepLen: 1,
    tickerPaused: false,
    streamLoaded: false
  };
  var DEFAULT_LIMIT = 12;
  var filterDrawerUserToggled = false;
  var cv = $('map'), ctx = cv ? cv.getContext('2d') : null;
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var REFRESH_MS = 300000;
  var TICKER_STEP_MS = 6000;
  var nextRefreshAt = Date.now() + REFRESH_MS;
  var posterSnapshot = $('stream-poster') ? $('stream-poster').cloneNode(true) : null;
  var regionSelect = null;
  var resizeRaf = 0;

  var ZONES = [
    ['UTC', 'UTC'],
    ['PT', 'America/Los_Angeles'],
    ['DC', 'America/New_York'],
    ['LDN', 'Europe/London'],
    ['TYO', 'Asia/Tokyo']
  ];

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function get(u) {
    return fetch(u, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error(u);
      return r.json();
    });
  }

  function findEventById(id) {
    if (!id) return null;
    for (var i = 0; i < state.events.length; i++) {
      if (state.events[i] && state.events[i].id === id) return state.events[i];
    }
    return null;
  }

  function isArchivedSnapshot(now) {
    var buildMs = Date.parse(state.generated);
    return Number.isFinite(buildMs) && (now - buildMs > 6 * 3600000);
  }

  function filterClock(now) {
    return isArchivedSnapshot(now) ? Date.parse(state.generated) : now;
  }

  function freshnessFor(e, now) {
    var srcMeta = e && e.source_id ? state.sourcesById[e.source_id] : null;
    return B.itemFreshness(e, state.generated, now, srcMeta);
  }

  /* ---------- clocks & countdown ---------- */
  function syncFilterDrawer() {
    var drawer = $('filter-drawer');
    if (!drawer) return;
    if (window.innerWidth >= 760) {
      drawer.open = true;
    } else if (!filterDrawerUserToggled) {
      drawer.open = false;
    }
  }

  function updateClocks() {
    var box = $('clocks');
    var nowMs = Date.now();
    var d = new Date(nowMs);
    var zoneTimes = ZONES.map(function (z) {
      try {
        return d.toLocaleTimeString('en-GB', {
          timeZone: z[1], hour: '2-digit', minute: '2-digit', hour12: false
        });
      } catch (err) {
        return '--:--';
      }
    });
    if (box) {
      if (!box.children.length) {
        ZONES.forEach(function (z) {
          var cell = el('span', 'clock-cell');
          cell.appendChild(el('small', null, z[0]));
          cell.appendChild(el('b', null, ''));
          box.appendChild(cell);
        });
      }
      ZONES.forEach(function (z, idx) {
        box.children[idx].lastChild.textContent = zoneTimes[idx];
      });
    }
    var mc = $('mobile-clock');
    if (mc) {
      mc.textContent = 'UTC ' + zoneTimes[0] + ' \u00b7 DC ' + zoneTimes[2];
    }
    var nu = $('next-update');
    if (nu) {
      var rem = Math.max(0, Math.ceil((nextRefreshAt - nowMs) / 1000));
      var mm = String(Math.floor(rem / 60)).padStart(2, '0');
      var ss = String(rem % 60).padStart(2, '0');
      nu.textContent = 'NEXT UPDATE ' + mm + ':' + ss;
    }
  }

  /* ---------- operational monitor & section tabs ---------- */
  function syncOpsButtons() {
    var map = {
      'ops-all': 'all',
      'ops-hazards': 'g:hazards',
      'ops-outages': 'g:outages',
      'ops-airspace': 'g:transport'
    };
    Object.keys(map).forEach(function (id) {
      var btn = $(id);
      if (!btn) return;
      var active = state.f.type === map[id];
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', String(active));
    });
  }

  function setCategoryFilter(key) {
    state.f.type = key;
    state.limit = DEFAULT_LIMIT;
    var cats = $('cats');
    if (cats) {
      Array.prototype.forEach.call(cats.querySelectorAll('.cat'), function (btn) {
        btn.setAttribute('aria-pressed', String(btn.dataset.key === key));
      });
    }
    syncOpsButtons();
    render();
  }

  function setRegionFilter(reg) {
    state.f.region = reg || 'all';
    state.limit = DEFAULT_LIMIT;
    if (regionSelect) regionSelect.value = state.f.region;
    render();
  }

  function renderOpsMonitor() {
    var now = Date.now();
    var counts = B.opsCounts(state.events, state.sourcesData, now);
    if ($('ops-all-val')) $('ops-all-val').textContent = counts.total + ' events';
    if ($('ops-all-sub')) {
      $('ops-all-sub').textContent = B.formatSevCount({ extreme: counts.extremeTotal, severe: counts.severeTotal }) + ' across all feeds';
    }
    if ($('ops-haz-val')) {
      $('ops-haz-val').textContent = B.formatSevCount({ extreme: counts.extremeHazards, severe: counts.severeHazards }) + ' \u00b7 ' + counts.hazardsTotal + ' hazards';
    }
    if ($('ops-haz-sub')) $('ops-haz-sub').textContent = 'Quakes, NWS, storms, fires';
    if ($('ops-out-val')) {
      $('ops-out-val').textContent = counts.probeFailing + (counts.probeFailing === 1 ? ' probe' : ' probes') + ' \u00b7 ' + counts.providerOutages + ' status';
    }
    if ($('ops-out-sub')) {
      $('ops-out-sub').textContent = counts.probeItems ? ('30 services probed \u00b7 ' + counts.outagesTotal + ' outage items') : '30 signed-out probes + status feeds';
    }
    if ($('ops-air-val')) {
      $('ops-air-val').textContent = B.formatSevCount({ extreme: counts.extremeAirspace, severe: counts.severeAirspace }) + ' \u00b7 ' + counts.airspace + ' aviation';
    }
    if ($('ops-air-sub')) {
      $('ops-air-sub').textContent = counts.faaCount + ' FAA delays \u00b7 ' + Math.max(0, counts.airspace - counts.faaCount) + ' SIGMETs';
    }
    if ($('ops-src-val')) {
      $('ops-src-val').textContent = counts.feedsTotal ? (counts.feedsFresh + '/' + counts.feedsTotal + ' FEEDS OK') : 'PUBLIC FEEDS';
    }
    if ($('ops-src-sub')) {
      if (!counts.feedsTotal) {
        $('ops-src-sub').textContent = 'Feed terms & licences \u2192';
      } else if (counts.feedsStale) {
        $('ops-src-sub').textContent = counts.feedsStale + ' degraded \u00b7 Licences \u2192';
      } else {
        $('ops-src-sub').textContent = 'Feed terms & licences \u2192';
      }
    }
    if ($('ops-sources-inline')) {
      $('ops-sources-inline').textContent = (counts.feedsTotal ? (counts.feedsFresh + '/' + counts.feedsTotal + ' feeds OK') : 'Feeds') + ' \u2192';
    }
    syncOpsButtons();
  }

  function bindOpsButtons() {
    ['ops-all', 'ops-hazards', 'ops-outages', 'ops-airspace'].forEach(function (id) {
      var btn = $(id);
      if (!btn || btn.dataset.bound) return;
      btn.dataset.bound = '1';
      btn.onclick = function () {
        var target = btn.dataset.filter || 'all';
        setCategoryFilter(state.f.type === target && target !== 'all' ? 'all' : target);
      };
    });
  }

  /* ---------- filters & category tabs ---------- */
  function updateCatsScroll() {
    var box = $('cats'), sc = $('cats-scroll'), nextBtn = $('cats-next');
    if (!box || !sc) return;
    var maxScroll = Math.max(0, box.scrollWidth - box.clientWidth);
    var hasOverflow = maxScroll > 4;
    sc.classList.toggle('has-more-left', hasOverflow && box.scrollLeft > 4);
    sc.classList.toggle('has-more-right', hasOverflow && box.scrollLeft < maxScroll - 4);
    if (nextBtn) {
      nextBtn.hidden = !hasOverflow;
      var atEnd = hasOverflow && box.scrollLeft >= maxScroll - 4;
      nextBtn.textContent = atEnd ? '\u2039' : '\u203a';
      nextBtn.setAttribute('aria-label', atEnd ? 'First categories' : 'More categories');
    }
  }

  function bindCatsScroll() {
    var box = $('cats'), nextBtn = $('cats-next');
    if (box && !box.dataset.scrollBound) {
      box.dataset.scrollBound = '1';
      box.addEventListener('scroll', updateCatsScroll, { passive: true });
    }
    if (nextBtn && !nextBtn.dataset.bound) {
      nextBtn.dataset.bound = '1';
      nextBtn.onclick = function () {
        var b = $('cats');
        if (!b) return;
        var maxScroll = Math.max(0, b.scrollWidth - b.clientWidth);
        if (b.scrollLeft >= maxScroll - 4) {
          b.scrollTo({ left: 0, behavior: reduce ? 'auto' : 'smooth' });
        } else {
          b.scrollBy({ left: Math.max(180, Math.round(b.clientWidth * 0.72)), behavior: reduce ? 'auto' : 'smooth' });
        }
      };
    }
  }

  function buildCats() {
    var box = $('cats');
    if (!box) return;
    box.textContent = '';
    function chip(key, label, count) {
      var b = el('button', 'cat');
      b.type = 'button';
      b.dataset.key = key;
      b.setAttribute('aria-pressed', String(state.f.type === key));
      b.appendChild(document.createTextNode(label));
      b.appendChild(el('b', '', String(count)));
      b.onclick = function () { setCategoryFilter(key); };
      box.appendChild(b);
    }
    chip('all', 'All', state.events.length);
    Object.keys(B.GROUPS).forEach(function (g) {
      var n = B.filterEvents(state.events, { type: 'g:' + g, hours: 0 }).length;
      if (n) {
        var lbl = B.GROUPS[g][0]
          .replace('Outages and cyber', 'Outages')
          .replace('Recalls and safety', 'Recalls')
          .replace('Official notices', 'Notices');
        chip('g:' + g, lbl, n);
      }
    });
    bindCatsScroll();
    requestAnimationFrame(updateCatsScroll);
  }

  function buildFilters() {
    var box = $('filters');
    if (!box) return;
    box.textContent = '';
    buildCats();
    var regs = ['all'].concat(Array.from(new Set(state.events.map(function (e) { return e.region; }).filter(Boolean))).sort());
    var ss = el('select', 'chip');
    ss.setAttribute('aria-label', 'Severity');
    [['', 'Any severity'], ['extreme', 'Extreme only'], ['severe', 'Severe or worse'], ['moderate', 'Moderate or worse']].forEach(function (o) {
      var op = el('option', '', o[1]); op.value = o[0]; ss.appendChild(op);
    });
    ss.value = state.f.sev || '';
    ss.onchange = function () { state.f.sev = ss.value; state.limit = DEFAULT_LIMIT; render(); };

    var rs = el('select', 'chip');
    rs.setAttribute('aria-label', 'Region');
    regs.forEach(function (r) {
      var o = el('option', '', r === 'all' ? 'All regions' : r); o.value = r; rs.appendChild(o);
    });
    rs.value = state.f.region || 'all';
    rs.onchange = function () { setRegionFilter(rs.value); };
    regionSelect = rs;

    var ts = el('select', 'chip');
    ts.setAttribute('aria-label', 'Event age');
    [['0', 'Any age'], ['72', 'Last 72 hours'], ['24', 'Last 24 hours'], ['6', 'Last 6 hours'], ['1', 'Last hour']].forEach(function (o) {
      var op = el('option', '', o[1]); op.value = o[0]; ts.appendChild(op);
    });
    ts.value = String(state.f.hours);
    ts.onchange = function () { state.f.hours = +ts.value; state.limit = DEFAULT_LIMIT; render(); };

    var clr = el('button', 'chip', 'Reset filters');
    clr.type = 'button';
    clr.onclick = function () {
      state.f = { type: 'all', region: 'all', hours: 72, sev: '' };
      state.limit = DEFAULT_LIMIT;
      ss.value = '';
      rs.value = 'all';
      ts.value = '72';
      setCategoryFilter('all');
    };

    box.appendChild(ss);
    box.appendChild(rs);
    box.appendChild(ts);
    box.appendChild(clr);

    var drawer = $('filter-drawer');
    var toggle = drawer ? drawer.querySelector('.filter-toggle') : null;
    if (toggle && !toggle.dataset.bound) {
      toggle.dataset.bound = '1';
      toggle.addEventListener('click', function () {
        if (window.innerWidth < 760) filterDrawerUserToggled = true;
      });
    }
    syncFilterDrawer();
  }

  /* ---------- item-boundary discrete ticker ---------- */
  function buildTickerNode(e, now, maxTitleChars, stepText, mobileMode) {
    var wrap = el('span', 'tk-item');
    var v = B.verificationTag(e);
    var f = freshnessFor(e, now);
    var titleText = maxTitleChars ? B.trimWholeWords(e.title, maxTitleChars) : B.cleanDc(e.title);
    var a = el('a', 'tk-title', titleText);
    a.href = '/event?id=' + encodeURIComponent(e.id);
    if (mobileMode) {
      var head = el('span', 'tk-head');
      head.appendChild(el('span', 'tk-sep', '\u25a0'));
      var vt = el('span', 'tk-verif', v.short);
      vt.style.color = v.color;
      head.appendChild(vt);
      head.appendChild(el('span', 'tk-meta', '[' + B.displaySource(e, { compact: true }) + ' \u00b7 ' + f.ageText + ']'));
      if (stepText) head.appendChild(el('span', 'tk-step-inline', stepText));
      wrap.appendChild(head);
      wrap.appendChild(a);
    } else {
      wrap.appendChild(el('span', 'tk-sep', '\u25a0'));
      var vt2 = el('span', 'tk-verif', v.short);
      vt2.style.color = v.color;
      wrap.appendChild(vt2);
      wrap.appendChild(a);
      wrap.appendChild(el('span', 'tk-meta', '[' + B.displaySource(e, { compact: true }) + ' \u00b7 ' + f.ageText + ']'));
    }
    return wrap;
  }

  function layoutTicker() {
    var track = $('ticker-track'), vp = $('ticker-viewport'), step = $('ticker-step');
    if (!track || !vp) return;
    var items = state.tickerItems;
    if (!items.length) {
      track.textContent = '';
      track.appendChild(el('span', 'tk-item', 'No active official alerts in snapshot. Check official sources before acting.'));
      if (step) step.textContent = '0/0';
      return;
    }

    var now = Date.now();
    if (window.innerWidth <= 759) {
      var idx = ((state.tickerIdx || 0) % items.length + items.length) % items.length;
      state.tickerIdx = idx;
      state.tickerStepLen = 1;
      var stepLabel = (idx + 1) + '/' + items.length;
      track.textContent = '';
      track.appendChild(buildTickerNode(items[idx], now, null, stepLabel, true));
      if (step) step.textContent = stepLabel;
      return;
    }

    var cs = getComputedStyle(vp);
    var padX = (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
    var vpWidth = Math.max(160, vp.clientWidth - padX);

    track.style.visibility = 'hidden';
    track.textContent = '';
    items.forEach(function (e) { track.appendChild(buildTickerNode(e, now, null, null, false)); });
    var widths = Array.prototype.map.call(track.children, function (node) {
      return Math.ceil(node.getBoundingClientRect().width);
    });

    var packed = B.packTickerItems(widths, vpWidth, 20, state.tickerIdx);
    state.tickerStepLen = Math.max(1, packed.indices.length);
    track.textContent = '';

    if (packed.overflowSingle && packed.indices.length) {
      var item = items[packed.indices[0]];
      var probe = buildTickerNode(item, now, null, null, false);
      var aProbe = probe.querySelector('.tk-title');
      if (aProbe) {
        aProbe.textContent = '';
        aProbe.style.minWidth = '0';
      }
      track.appendChild(probe);
      var fixedW = Math.ceil(probe.getBoundingClientRect().width);
      var cap = Math.max(36, Math.floor((vpWidth - fixedW - 14) / 7.2));
      track.textContent = '';
      var node = buildTickerNode(item, now, cap, null, false);
      track.appendChild(node);
      while (cap > 24 && node.getBoundingClientRect().width > vpWidth) {
        cap -= 4;
        var link = node.querySelector('.tk-title');
        if (link) link.textContent = B.trimWholeWords(item.title, Math.max(24, cap));
      }
    } else {
      packed.indices.forEach(function (idx) {
        track.appendChild(buildTickerNode(items[idx], now, null, null, false));
      });
    }

    track.style.visibility = '';
    if (step && packed.indices.length) {
      var first = packed.indices[0] + 1;
      var last = packed.indices[packed.indices.length - 1] + 1;
      step.textContent = (first === last ? String(first) : (first + '\u2013' + last)) + '/' + items.length;
    }
  }

  function renderTicker() {
    var items = state.events.filter(function (e) {
      if (e.ticker_ok === true) return true;
      if (e.ticker_ok === false) return false;
      return e.type !== 'headline' && e.type !== 'statement' && (e.severity === 'extreme' || e.severity === 'severe');
    }).slice(0, 12);
    if (!items.length) {
      items = state.events.filter(function (e) { return e.type !== 'headline' && e.type !== 'statement'; }).slice(0, 8);
    }
    state.tickerItems = items;
    if (state.tickerIdx >= items.length) state.tickerIdx = 0;
    layoutTicker();
  }

  function bindTickerToggle() {
    var btn = $('ticker-toggle');
    if (!btn || btn.dataset.bound) return;
    btn.dataset.bound = '1';
    btn.onclick = function () {
      state.tickerPaused = !state.tickerPaused;
      btn.setAttribute('aria-pressed', String(state.tickerPaused));
      btn.textContent = state.tickerPaused ? 'Resume' : 'Pause';
      btn.setAttribute('aria-label', state.tickerPaused ? 'Resume wire ticker' : 'Pause wire ticker');
    };
  }

  /* ---------- lead story, newcomer recap & secondary columns ---------- */
  function renderLeadStory(data) {
    var now = Date.now();
    var feed = (data && data.lead) ? data : B.deriveLeadStory(state.events, state.generated);
    var lead = feed && feed.lead;
    if (!lead || !lead.headline) return;
    state.lead = lead;

    var leadEv = findEventById(lead.id);
    if (!leadEv) {
      for (var i = 0; i < state.events.length; i++) {
        if (state.events[i] && state.events[i].title === lead.headline) {
          leadEv = state.events[i];
          break;
        }
      }
    }

    var sev = (leadEv && leadEv.severity) || lead.severity || 'moderate';
    var st = B.severityTokens(sev);
    var v = leadEv ? B.verificationTag(leadEv) : B.verificationTag({ confidence: lead.label });
    var leadFresh = leadEv ? freshnessFor(leadEv, now) : B.itemFreshness({ time: lead.updated || feed.as_of }, state.generated, now, null);
    var secLabel = leadEv ? (B.TYPES[leadEv.type] || B.TYPES.other).label : (lead.kind === 'big' ? 'TOP WIRE' : 'LEAD STORY');

    var card = $('lead-story');
    if (card) {
      card.style.setProperty('--lead-bar', st.bar);
      card.style.setProperty('--sev-bar', st.bar);
      card.style.setProperty('--sev-soft', st.soft);
      card.style.setProperty('--sev-text', st.text);
      card.hidden = false;
    }

    if ($('lead-kicker')) {
      $('lead-kicker').textContent = lead.kind === 'big' ? 'URGENT LEAD' : (lead.kind === 'curated' ? 'CORROBORATED LEAD' : 'LEAD DISPATCH');
    }
    if ($('lead-type')) $('lead-type').textContent = secLabel.toUpperCase();
    if ($('lead-sev')) $('lead-sev').textContent = st.label;
    if ($('lead-label')) {
      $('lead-label').textContent = lead.label ? String(lead.label).toUpperCase() : v.code;
      $('lead-label').style.setProperty('--verif-color', v.color);
    }
    if ($('lead-stream-tag')) {
      $('lead-stream-tag').hidden = !(leadEv && state.streamId && leadEv.id === state.streamId);
    }
    if ($('lead-src-age')) {
      $('lead-src-age').textContent = B.displaySource(leadEv || lead, { compact: true }) + ' \u00b7 ' + leadFresh.ageText;
    }

    if ($('lead-facts')) {
      var factParts = [];
      var dp = B.distinctPlace(leadEv || lead);
      if (dp) factParts.push(dp.toUpperCase());
      var cf = leadEv ? B.compactFacts(leadEv) : [];
      cf.slice(0, 3).forEach(function (item) { factParts.push(item.toUpperCase()); });
      $('lead-facts').textContent = factParts.length ? factParts.join(' \u00b7 ') : 'ATTRIBUTED PUBLIC WIRE \u00b7 VERIFIED DISPATCH';
    }

    var link = $('lead-link');
    if (link) {
      link.textContent = B.cleanDc(lead.headline);
      link.href = leadEv ? ('/event?id=' + encodeURIComponent(leadEv.id)) : (lead.sources && lead.sources[0] && B.safeUrl(lead.sources[0].url) ? lead.sources[0].url : './');
    } else if ($('lead-headline')) {
      $('lead-headline').textContent = B.cleanDc(lead.headline);
    }

    if ($('lead-summary')) $('lead-summary').textContent = B.cleanDc(lead.summary || (leadEv && leadEv.summary) || '');

    var rep = $('lead-reported');
    if (rep) {
      var repText = lead.reported_line || (leadEv && leadEv.detail && leadEv.detail.reported_line);
      rep.textContent = '';
      if (repText) {
        rep.hidden = false;
        rep.appendChild(el('span', 'rep-kicker', 'ATTRIBUTED REPORTING'));
        rep.appendChild(document.createTextNode(B.cleanDc(repText)));
      } else if (leadEv || (lead.sources && lead.sources.length)) {
        rep.hidden = false;
        rep.appendChild(el('span', 'rep-kicker', 'PRIMARY PROVENANCE'));
        var srcName = B.displaySource(leadEv || { source: lead.sources && lead.sources[0] && lead.sources[0].name });
        rep.appendChild(document.createTextNode('Attributed directly to ' + srcName + ' official bulletin.'));
      } else {
        rep.hidden = true;
      }
    }

    if ($('lead-changed-text')) {
      $('lead-changed-text').textContent = leadEv ? B.whatChangedLine(leadEv) : B.whatChangedLine({ time: lead.updated || feed.as_of });
    }

    var meta = $('lead-meta');
    if (meta) {
      meta.textContent = '';
      var asOf = lead.updated || feed.as_of || feed.generated;
      if (Number.isFinite(Date.parse(asOf))) {
        var time = el('time', '', asOf.slice(0, 16).replace('T', ' ') + ' UTC');
        time.dateTime = asOf;
        meta.appendChild(time);
      }
      var srcs = lead.sources || [];
      srcs.forEach(function (source) {
        if (source && source.name) meta.appendChild(B.sourceLink(source.url, B.cleanDc(source.name)));
      });
      if (leadEv) {
        var pl = el('a', '', 'Event record');
        pl.href = '/event?id=' + encodeURIComponent(leadEv.id);
        meta.appendChild(pl);
      }
      var prov = el('a', '', 'Source & licence');
      prov.href = '/data';
      meta.appendChild(prov);
    }

    renderRecap(leadEv);
    renderSecondaryColumns(leadEv);
    renderStreamRundown();
  }

  function renderRecap(leadEv) {
    var list = $('recap-list');
    if (!list) return;
    list.textContent = '';
    var now = Date.now();
    var entries = B.selectBriefingItems(state.events, leadEv || state.lead, 2);

    if (!entries.length) {
      list.appendChild(el('li', '', 'No additional monitored events in snapshot. Check official sources.'));
      return;
    }

    entries.forEach(function (ev, idx) {
      var li = el('li');
      var a = el('a', 'recap-link');
      a.href = '/event?id=' + encodeURIComponent(ev.id);
      var top = el('span', 'recap-top');
      top.appendChild(el('span', 'recap-item-tag', String(idx + 1).padStart(2, '0') + ' ALSO MONITORED'));
      var v = B.verificationTag(ev);
      var vNode = el('span', 'recap-item-tag', '[' + v.short + ']');
      vNode.style.color = v.color;
      top.appendChild(vNode);
      var f = freshnessFor(ev, now);
      top.appendChild(el('span', 'recap-item-src', B.displaySource(ev, { compact: true }) + ' \u00b7 ' + f.ageText));
      a.appendChild(top);
      var dp = B.distinctPlace(ev);
      var facts = B.compactFacts(ev);
      var line = B.cleanDc(ev.title) + (dp ? ' \u2014 ' + dp : '');
      if (facts.length) line += ' (' + facts.slice(0, 2).join(', ') + ')';
      a.appendChild(el('span', 'recap-headline', line));
      li.appendChild(a);
      list.appendChild(li);
    });
  }

  function renderSecondaryColumns(leadEv) {
    var box = $('secondary-columns');
    if (!box) return;
    box.textContent = '';
    var now = Date.now();
    var pool = B.withoutLead(B.filterEvents(state.events, { hours: 72 }, filterClock(now)), state.lead);
    if (leadEv) {
      pool = pool.filter(function (e) { return e.id !== leadEv.id; });
    }
    var grouped = B.groupEvents(pool).map(function (g) { return g.ev; });
    var chosen = [], seenIds = {}, seenTypes = {};
    grouped.forEach(function (e) {
      if (chosen.length >= 4 || seenIds[e.id]) return;
      if (!seenTypes[e.type]) {
        seenIds[e.id] = 1;
        seenTypes[e.type] = 1;
        chosen.push(e);
      }
    });
    grouped.forEach(function (e) {
      if (chosen.length >= 4 || seenIds[e.id]) return;
      seenIds[e.id] = 1;
      chosen.push(e);
    });

    if (!chosen.length) {
      box.appendChild(el('div', 'empty', 'No secondary events in this window.'));
      return;
    }

    chosen.forEach(function (e) {
      var st = B.severityTokens(e.severity);
      var v = B.verificationTag(e);
      var f = freshnessFor(e, now);
      var card = el('article', 'sec-card');
      card.style.setProperty('--sev-bar', st.bar);
      card.style.setProperty('--sev-soft', st.soft);
      card.style.setProperty('--sev-text', st.text);

      var top = el('div', 'sec-card-top');
      top.appendChild(el('span', 'sec-badge', (B.TYPES[e.type] || B.TYPES.other).label));
      top.appendChild(el('span', 'sev-badge', st.code));
      var vb = el('span', 'verif-badge', v.short);
      vb.style.setProperty('--verif-color', v.color);
      top.appendChild(vb);
      if (state.streamId && e.id === state.streamId) {
        top.appendChild(el('span', 'stream-badge', 'ON STREAM NOW'));
      }
      card.appendChild(top);

      var h3 = el('h3');
      var btn = el('button', 'sec-card-btn', B.cleanDc(e.title));
      btn.type = 'button';
      btn.onclick = function () { focusEvent(e.id, true); };
      h3.appendChild(btn);
      card.appendChild(h3);

      card.appendChild(el('p', 'sec-card-sum', B.cleanDc(e.summary || '')));
      var chgText = B.hasRevision(e) ? B.whatChangedLine(e) : B.compactFacts(e).slice(0, 2).join(' \u00b7 ');
      if (chgText) card.appendChild(el('p', 'sec-card-chg', chgText));

      var foot = el('div', 'sec-card-foot');
      foot.appendChild(el('span', '', B.displaySource(e, { compact: true }) + ' \u00b7 ' + f.ageText));
      var rec = el('a', '', 'Full record');
      rec.href = '/event?id=' + encodeURIComponent(e.id);
      foot.appendChild(rec);
      card.appendChild(foot);

      box.appendChild(card);
    });
  }

  /* ---------- focus plaque & stream facade ---------- */
  function renderFocusPlaque() {
    var box = $('focus-plaque');
    if (!box) return;
    var now = Date.now();
    var leadId = state.lead && state.lead.id;
    var geoRow = null;
    for (var i = 0; i < state.allRows.length; i++) {
      var rowEv = state.allRows[i] && state.allRows[i].ev;
      if (rowEv && rowEv.lat != null && rowEv.lon != null && rowEv.id !== leadId) {
        geoRow = rowEv;
        break;
      }
    }
    var nonLeadEv = null;
    if (!geoRow) {
      for (var j = 0; j < state.events.length; j++) {
        if (state.events[j] && state.events[j].id !== leadId) {
          nonLeadEv = state.events[j];
          break;
        }
      }
    }
    var target = findEventById(state.sel) ||
      geoRow ||
      (state.allRows[0] && state.allRows[0].ev) ||
      nonLeadEv ||
      state.events[0] ||
      null;

    box.textContent = '';
    if (!target) {
      box.appendChild(el('div', 'plaque-meta', 'No focused event loaded.'));
      return;
    }

    var st = B.severityTokens(target.severity);
    var v = B.verificationTag(target);
    var f = freshnessFor(target, now);
    box.style.setProperty('--sev-bar', st.bar);
    box.style.setProperty('--sev-soft', st.soft);
    box.style.setProperty('--sev-text', st.text);

    var rk = state.rankOf && state.rankOf[target.id] != null ? state.rankOf[target.id] : null;
    var pinLabel = state.sel
      ? ('SELECTED' + (rk != null ? (' #' + String(rk + 1).padStart(2, '0')) : ''))
      : ('MAP PIN' + (rk != null ? (' #' + String(rk + 1).padStart(2, '0')) : ''));

    var meta = el('div', 'plaque-meta');
    meta.appendChild(el('span', 'sec-badge', pinLabel));
    meta.appendChild(el('span', 'sev-badge', st.label));
    var vb = el('span', 'verif-badge', v.code);
    vb.style.setProperty('--verif-color', v.color);
    meta.appendChild(vb);
    meta.appendChild(el('span', 'sec-badge', (B.TYPES[target.type] || B.TYPES.other).label));
    if (state.streamId && target.id === state.streamId && target.id !== leadId) {
      meta.appendChild(el('span', 'stream-badge', 'ON STREAM NOW'));
    }
    var facts = B.compactFacts(target);
    if (facts.length) meta.appendChild(el('span', 'plaque-facts', facts.join(' \u00b7 ')));
    box.appendChild(meta);

    var dp = B.distinctPlace(target);
    box.appendChild(el('div', 'plaque-title', B.cleanDc(target.title) + (dp ? ' \u2014 ' + dp : '')));
    box.appendChild(el('p', 'plaque-sum', B.cleanDc(target.summary || '')));
    box.appendChild(el('p', 'plaque-chg', B.whatChangedLine(target)));

    var acts = el('div', 'plaque-actions');
    acts.appendChild(el('span', '', B.displaySource(target) + ' \u00b7 ' + f.ageText));
    var linkWrap = el('span', 'maptools');
    var offUrl = B.safeUrl(target.source_url);
    if (offUrl) {
      var oa = el('a', '', 'Official source');
      oa.href = offUrl;
      oa.rel = 'noopener';
      linkWrap.appendChild(oa);
    }
    var pa = el('a', '', 'Event record');
    pa.href = '/event?id=' + encodeURIComponent(target.id);
    linkWrap.appendChild(pa);
    acts.appendChild(linkWrap);
    box.appendChild(acts);
  }

  function renderStreamRundown() {
    var box = $('stream-rundown');
    if (!box) return;
    box.textContent = '';
    var now = Date.now();
    var queue = [];
    var seen = {};
    var focusEv = findEventById(state.streamId);
    if (focusEv && focusEv.type !== 'headline' && focusEv.type !== 'statement') {
      queue.push(focusEv);
      seen[focusEv.id] = 1;
    }
    state.events.forEach(function (e) {
      if (queue.length >= 3 || !e || seen[e.id]) return;
      if (e.type !== 'headline' && e.type !== 'statement') {
        seen[e.id] = 1;
        queue.push(e);
      }
    });

    var head = el('div', 'rundown-head');
    head.appendChild(el('span', '', 'ON AIR ROTATION'));
    head.appendChild(el('span', '', '20s camera dwell \u00b7 Public sources'));
    box.appendChild(head);

    if (!queue.length) {
      box.appendChild(el('p', 'sub', 'No broadcast events in queue.'));
      return;
    }

    queue.forEach(function (e, idx) {
      var st = B.severityTokens(e.severity);
      var f = freshnessFor(e, now);
      var isOn = (state.sel && state.sel === e.id) || (!state.sel && state.streamId === e.id);
      var btn = el('button', 'rundown-row' + (isOn ? ' is-active' : ''));
      btn.type = 'button';
      btn.style.setProperty('--sev-bar', st.bar);
      btn.style.setProperty('--sev-soft', st.soft);
      btn.style.setProperty('--sev-text', st.text);
      btn.appendChild(el('span', 'rd-rank', String(idx + 1).padStart(2, '0')));
      btn.appendChild(el('span', 'rd-sev', st.code));
      btn.appendChild(el('span', 'rd-title', B.trimWholeWords(e.title, 54)));
      btn.appendChild(el('span', 'rd-meta', B.displaySource(e, { compact: true }) + ' \u00b7 ' + f.ageText));
      btn.onclick = function () { focusEvent(e.id, true); };
      box.appendChild(btn);
    });
  }

  function updateStreamFacade() {
    var now = Date.now();
    var badge = $('stream-badge'), line = $('stream-now-line'), playBtn = $('stream-play');
    var ev = findEventById(state.streamId);
    var leadId = state.lead && state.lead.id;

    if (badge) {
      badge.textContent = 'ON STREAM NOW';
    }
    if (line) {
      if (ev && (!leadId || ev.id !== leadId)) {
        var f = freshnessFor(ev, now);
        line.textContent = B.cleanDc(ev.title) + ' \u00b7 ' + B.displaySource(ev, { compact: true }) + ' \u00b7 ' + f.ageText;
      } else {
        var geo0 = null;
        for (var i = 0; i < state.events.length; i++) {
          var cand = state.events[i];
          if (cand && cand.id !== leadId && cand.lat != null && cand.lon != null && cand.type !== 'headline' && cand.type !== 'statement') {
            geo0 = cand;
            break;
          }
        }
        if (geo0) {
          var gf = freshnessFor(geo0, now);
          line.textContent = 'Lead dispatch (left) \u00b7 3D flyover: ' + B.cleanDc(geo0.title) + ' \u00b7 ' + B.displaySource(geo0, { compact: true }) + ' \u00b7 ' + gf.ageText;
        } else {
          line.textContent = 'Autonomous 3D wire desk \u00b7 Public sources';
        }
      }
    }
    if (playBtn) {
      var spans = playBtn.querySelectorAll('span');
      if (spans.length > 1) {
        spans[1].textContent = 'Play Live Stream (Muted)';
      }
      if (!playBtn.dataset.bound) {
        playBtn.dataset.bound = '1';
        playBtn.onclick = activateStreamEmbed;
      }
    }
  }

  function activateStreamEmbed() {
    var stage = $('stream-stage');
    if (!stage || state.streamLoaded) return;
    state.streamLoaded = true;
    stage.classList.add('is-playing');
    var host = (location.hostname || '').trim();
    var parents = ['breakingnewsdesklive.com'];
    if (host && parents.indexOf(host) === -1) parents.push(host);
    var src = 'https://player.twitch.tv/?channel=breakingnewsdesklive&muted=true&autoplay=true&' +
      parents.map(function (p) { return 'parent=' + encodeURIComponent(p); }).join('&');

    stage.textContent = '';
    var iframe = document.createElement('iframe');
    iframe.className = 'stream-iframe';
    iframe.title = 'Breaking News Desk Live Twitch stream (muted)';
    iframe.src = src;
    iframe.allowFullscreen = true;
    iframe.setAttribute('allow', 'autoplay; fullscreen');
    stage.appendChild(iframe);

    var parent = stage.parentNode;
    if (parent && !parent.querySelector('.stream-active-bar')) {
      var bar = el('div', 'stream-active-bar');
      bar.appendChild(el('span', 'stream-note', 'Twitch embed active (starts muted).'));
      var closeBtn = el('button', 'stream-close-btn', 'Unload stream');
      closeBtn.type = 'button';
      closeBtn.onclick = function () {
        state.streamLoaded = false;
        stage.classList.remove('is-playing');
        bar.remove();
        stage.textContent = '';
        if (posterSnapshot) {
          stage.appendChild(posterSnapshot.cloneNode(true));
          updateStreamFacade();
        }
      };
      bar.appendChild(closeBtn);
      var cadence = parent.querySelector('.stream-cadence');
      if (cadence) parent.insertBefore(bar, cadence);
      else parent.appendChild(bar);
    }
  }

  /* ---------- wire rail list ---------- */
  function focusEvent(id, scrollIntoView) {
    state.sel = state.sel === id ? null : id;
    if (state.sel && state.rankOf[state.sel] != null && state.rankOf[state.sel] >= state.limit) {
      state.limit = Math.min(state.allRows.length, state.rankOf[state.sel] + 5);
    }
    render();
    if (scrollIntoView && state.sel) {
      var node = $('ev-' + state.sel);
      if (node) node.scrollIntoView({ block: 'nearest', behavior: reduce ? 'auto' : 'smooth' });
    }
  }

  function evRow(e, label, now, count, members) {
    var st = B.severityTokens(e.severity);
    var v = B.verificationTag(e);
    var srcMeta = state.sourcesById[e.source_id];
    var f = freshnessFor(e, now);

    var li = el('li', 'card s-' + e.severity + (state.sel === e.id ? ' sel' : ''));
    li.style.setProperty('--sev-bar', st.bar);
    li.style.setProperty('--sev-soft', st.soft);
    li.style.setProperty('--sev-text', st.text);
    li.id = 'ev-' + e.id;

    var h = el('button', 'head');
    h.type = 'button';
    h.setAttribute('aria-expanded', String(state.sel === e.id));
    h.dataset.event = e.id;

    h.appendChild(el('span', 'rank', label.padStart(2, '0')));
    h.appendChild(el('span', 'sev', st.code));

    var tagsCol = el('span', 'tags-col');
    tagsCol.appendChild(el('span', 'typ', (B.TYPES[e.type] || B.TYPES.other).label));
    var vt = el('span', 'vtag', v.short);
    vt.style.color = v.color;
    tagsCol.appendChild(vt);
    h.appendChild(tagsCol);

    var bodyCol = el('span', 'body-col');
    var title = el('span', 'title', B.cleanDc(e.title));
    if (state.streamId && e.id === state.streamId) {
      title.prepend(el('span', 'inline-stream-pill', 'ON STREAM'), ' ');
    }
    if (count > 1) {
      var badge = el('span', 'feed-count', 'x' + count);
      badge.setAttribute('aria-label', count + ' grouped events');
      title.prepend(badge, ' ');
    }
    bodyCol.appendChild(title);

    var dp = B.distinctPlace(e);
    var chg = B.shortChangedTag(e);
    if (dp || chg) {
      var sub = el('span', 'row-sub');
      if (dp) sub.appendChild(el('span', '', dp));
      if (chg) sub.appendChild(el('span', 'row-chg', chg));
      bodyCol.appendChild(sub);
    }
    h.appendChild(bodyCol);

    var srcAge = el('span', 'srcage');
    srcAge.appendChild(el('span', 'src', B.displaySource(e, { compact: true })));
    srcAge.appendChild(el('span', 'when', f.ageText));
    h.appendChild(srcAge);

    h.onclick = function () { focusEvent(e.id, false); };
    li.appendChild(h);

    if (state.sel === e.id) {
      var m = el('div', 'more');
      m.appendChild(el('p', 'what-changed', 'What changed: ' + B.whatChangedLine(e)));

      if (Array.isArray(e.history) && e.history.length) {
        var hl = el('ul', 'dg');
        e.history.forEach(function (item) {
          hl.appendChild(el('li', '', (item.t || '') + (item.from && item.to ? (' \u00b7 ' + item.from + ' \u2192 ' + item.to) : '') + (item.why ? (' \u00b7 ' + item.why) : '')));
        });
        m.appendChild(hl);
      }

      if (e.detail && e.detail.reported_line) {
        var rl = el('p', 'stat-line');
        rl.appendChild(el('b', '', 'Reported:'));
        rl.appendChild(document.createTextNode(B.cleanDc(e.detail.reported_line)));
        m.appendChild(rl);
      }
      if (e.confidence) {
        var cfp = el('p', 'stat-line');
        cfp.appendChild(el('b', '', e.confidence));
        cfp.appendChild(document.createTextNode(
          e.confidence === 'Corroborated' ? 'Two or more independent sources support this.' :
          e.confidence === 'Official single source' ? 'One official source. Not yet corroborated.' :
          'Not yet verified by the desk.'
        ));
        m.appendChild(cfp);
      } else {
        var vfp = el('p', 'stat-line');
        vfp.appendChild(el('b', '', v.label));
        vfp.appendChild(document.createTextNode(
          v.code === 'UNVERIFIED' ? 'Not verified by the desk; check the named source directly.' :
          'Attributed directly to the named public feed.'
        ));
        m.appendChild(vfp);
      }

      if (e.status) {
        var stp = el('p', 'stat-line');
        stp.appendChild(el('b', '', e.status));
        stp.appendChild(document.createTextNode(
          e.status === 'UNVERIFIED' ? 'A claim by the named outlet or party. This site does not verify it.' :
          'New in the feeds. Details may change.'
        ));
        m.appendChild(stp);
      }

      m.appendChild(el('p', '', B.cleanDc(e.summary)));

      var ctxBox = B.renderContext(e.context || {}, e);
      if (e.context || ctxBox.querySelector('figure')) m.appendChild(ctxBox);

      if (e.links && e.links.length) {
        m.appendChild(el('p', 'src', 'Also reported by (the outlet\u2019s own headline, as a link): '));
        var ul = el('ul', 'dg');
        e.links.forEach(function (x) {
          var li2 = el('li');
          li2.appendChild(B.sourceLink(x.url, B.cleanDc(x.label) + ': ' + B.cleanDc(x.title), 'noopener nofollow'));
          ul.appendChild(li2);
        });
        m.appendChild(ul);
      }

      if (members && members.length > 1) {
        m.appendChild(el('p', 'src', 'Identical rows grouped here: '));
        var gl = el('ul', 'dg');
        members.forEach(function (x) {
          var xf = freshnessFor(x, now);
          var li3 = el('li');
          var pa = el('a', '', B.cleanDc(x.title) + ' (' + xf.ageText + ')');
          pa.href = '/event?id=' + encodeURIComponent(x.id);
          li3.appendChild(pa);
          gl.appendChild(li3);
        });
        m.appendChild(gl);
      }

      var s = el('p', 'src');
      var licenceNote = srcMeta && srcMeta.licence ? (' \u00b7 Licence: ' + srcMeta.licence) : '';
      var freshNote = srcMeta ? (' \u00b7 Feed status: ' + (f.stale ? 'stale (' + B.ago(srcMeta.checked || state.generated, now) + ')' : 'OK')) : '';
      s.appendChild(document.createTextNode('Source: ' + B.cleanDc(e.source) + '. Event time: ' + e.time.replace('T', ' ').replace('Z', ' UTC') + licenceNote + freshNote + '.'));
      m.appendChild(s);

      var actRow = el('div', 'action-row');
      var u = B.safeUrl(e.source_url);
      if (u) {
        var a = el('a', 'action-link', 'Open the official page');
        a.href = u;
        a.rel = 'noopener';
        actRow.appendChild(a);
      }
      var pl = el('a', 'action-link', 'Permalink');
      pl.href = '/event?id=' + encodeURIComponent(e.id);
      actRow.appendChild(pl);
      var pa2 = el('a', 'action-link', 'Feed terms & status');
      pa2.href = '/data';
      actRow.appendChild(pa2);
      var ca = el('a', 'action-link', 'Report an error');
      ca.href = '/corrections';
      actRow.appendChild(ca);
      m.appendChild(actRow);

      m.appendChild(el('p', 'warn',
        (e.type === 'headline' || e.type === 'statement')
          ? 'Headlines and statements are claims by the named outlet or party. This site does not verify them. It is automated and may be wrong. Check official sources.'
          : 'Check official sources. This site is automated and may be wrong or late.'
      ));
      li.appendChild(m);
    }
    return li;
  }

  function render() {
    var now = Date.now();
    var evs = B.withoutLead(B.filterEvents(state.events, state.f, filterClock(now)), state.lead);
    var ol = $('list');
    var active = document.activeElement;
    var activeRow = ol && ol.contains(active) ? active.dataset : {};
    if (ol) ol.textContent = '';

    var allRows = state.allRows = B.groupEvents(evs).slice(0, 60);
    state.rankOf = {};
    allRows.forEach(function (g, i) {
      state.rankOf[g.ev.id] = i;
    });

    var rows = state.rows = allRows.slice(0, state.limit);
    var countText = rows.length < allRows.length
      ? ('Top ' + rows.length + ' of ' + allRows.length + ' ranked')
      : (evs.length + (evs.length === state.events.length ? ' events' : ' of ' + state.events.length + ' events'));
    if ($('count')) $('count').textContent = countText;
    if ($('list-count')) $('list-count').textContent = countText;

    if (ol && !evs.length) {
      ol.appendChild(el('li', 'empty', 'No events match these filters.'));
    }

    rows.forEach(function (g, i) {
      if (ol) ol.appendChild(evRow(g.ev, String(i + 1), now, g.members.length, g.members));
    });

    var moreBar = $('rail-more-bar'), moreBtn = $('load-more');
    if (moreBar && moreBtn) {
      if (allRows.length > rows.length) {
        moreBar.hidden = false;
        var nextBatch = Math.min(DEFAULT_LIMIT, allRows.length - rows.length);
        moreBtn.textContent = 'Show ' + nextBatch + ' more items (' + rows.length + ' of ' + allRows.length + ')';
        if (!moreBtn.dataset.bound) {
          moreBtn.dataset.bound = '1';
          moreBtn.onclick = function () {
            state.limit = Math.min(state.allRows.length, state.limit + DEFAULT_LIMIT);
            render();
          };
        }
      } else {
        moreBar.hidden = true;
      }
    }

    if (activeRow.event && ol) {
      Array.prototype.some.call(ol.querySelectorAll('.head'), function (button) {
        if (button.dataset.event !== activeRow.event) return false;
        button.focus({ preventScroll: true });
        return true;
      });
    }

    renderFocusPlaque();
    renderStreamRundown();
    renderChangesBoard();
    renderProbeBoard();
    renderRegionBoard();
    draw();
  }

  /* ---------- sourced operational sidebar boards ---------- */
  function renderChangesBoard() {
    var box = $('changes-list');
    if (!box) return;
    box.textContent = '';
    var now = Date.now();
    var leadId = state.lead && state.lead.id;
    var pool = leadId ? state.events.filter(function (e) { return e && e.id !== leadId; }) : state.events.slice();
    var ranked = pool.sort(function (a, b) {
      function prio(e) {
        var d = e.detail || {};
        if (Array.isArray(e.history) && e.history.length) return 4;
        if (e.updated && e.updated !== e.time) return 3;
        if (d.measured_at || d.cleared_at) return 2;
        if (e.first_seen && e.first_seen !== e.time) return 1;
        return 0;
      }
      return prio(b) - prio(a);
    }).slice(0, 4);

    if (!ranked.length) {
      box.appendChild(el('li', 'sub', 'No source changes recorded.'));
      return;
    }

    ranked.forEach(function (e) {
      var f = freshnessFor(e, now);
      var li = el('li');
      var btn = el('button', 'ledger-btn' + (state.sel === e.id ? ' is-sel' : ''));
      btn.type = 'button';
      var top = el('span', 'ledger-top');
      top.appendChild(el('span', '', B.displaySource(e, { compact: true })));
      top.appendChild(el('span', '', f.ageText));
      btn.appendChild(top);
      btn.appendChild(el('span', 'ledger-title', B.trimWholeWords(e.title, 70)));
      btn.appendChild(el('span', 'ledger-chg', B.whatChangedLine(e)));
      btn.onclick = function () { focusEvent(e.id, true); };
      li.appendChild(btn);
      box.appendChild(li);
    });
  }

  function renderProbeBoard() {
    var box = $('probe-board');
    if (!box) return;
    box.textContent = '';
    var now = Date.now();
    var outages = state.events.filter(function (e) { return e && (e.type === 'outage' || e.type === 'cyber'); });
    var probes = outages.filter(function (e) { return e.source_id === 'probes' || (e.detail && e.detail.lane === 'probes'); });
    var activeProbes = probes.filter(function (e) { return !e.detail || e.detail.open !== false; });
    var clearedProbes = probes.filter(function (e) { return e.detail && e.detail.open === false; });
    var providers = outages.filter(function (e) { return !(e.source_id === 'probes' || (e.detail && e.detail.lane === 'probes')); });

    var sum = el('p', 'probe-summary');
    var probeNote = activeProbes.length
      ? (activeProbes.length + ' active probe alert(s) across 30 monitored services' + (clearedProbes.length ? (' (' + clearedProbes.length + ' recently cleared).') : '.'))
      : ('0 active probe alerts across 30 monitored services' + (clearedProbes.length ? (' (' + clearedProbes.length + ' recently cleared).') : ' (checked every 3m).'));
    sum.appendChild(document.createTextNode(probeNote + ' '));
    var meth = el('a', '', 'Probe method');
    meth.href = '/data#probes';
    sum.appendChild(meth);
    box.appendChild(sum);

    activeProbes.concat(providers).concat(clearedProbes).slice(0, 4).forEach(function (e) {
      var st = B.severityTokens(e.severity);
      var f = freshnessFor(e, now);
      var v = B.verificationTag(e);
      var btn = el('button', 'probe-row-btn');
      btn.type = 'button';
      btn.style.setProperty('--sev-bar', st.bar);
      var top = el('span', 'ledger-top');
      top.appendChild(el('span', '', B.displaySource(e, { compact: true }) + ' \u00b7 ' + v.short));
      top.appendChild(el('span', '', f.ageText));
      btn.appendChild(top);
      btn.appendChild(el('span', 'ledger-title', B.cleanDc(e.title)));
      btn.onclick = function () { focusEvent(e.id, true); };
      box.appendChild(btn);
    });
  }

  function renderRegionBoard() {
    var box = $('region-board');
    if (!box) return;
    box.textContent = '';
    var now = Date.now();
    var byReg = {};
    state.events.forEach(function (e) {
      if (!e || !e.region) return;
      if (!byReg[e.region]) byReg[e.region] = { name: e.region, total: 0, extreme: 0, severe: 0, lead: e };
      byReg[e.region].total++;
      if (e.severity === 'extreme') byReg[e.region].extreme++;
      else if (e.severity === 'severe') byReg[e.region].severe++;
      if ((e.score || 0) > (byReg[e.region].lead.score || 0)) byReg[e.region].lead = e;
    });

    var regs = Object.keys(byReg).sort(function (a, b) { return byReg[b].total - byReg[a].total; });
    if (!regs.length) {
      box.appendChild(el('p', 'sub', 'No regional counts available.'));
      return;
    }

    regs.forEach(function (reg) {
      var info = byReg[reg];
      var f = freshnessFor(info.lead, now);
      var btn = el('button', 'region-btn');
      btn.type = 'button';
      btn.setAttribute('aria-pressed', String(state.f.region === reg));
      var top = el('span', 'region-top');
      top.appendChild(el('span', '', reg));
      top.appendChild(el('span', '', String(info.total)));
      btn.appendChild(top);
      var sevStr = (info.extreme || info.severe) ? (B.formatSevCount({ extreme: info.extreme, severe: info.severe }) + ' \u00b7 ') : '';
      btn.appendChild(el('span', 'region-meta',
        sevStr + B.displaySource(info.lead, { compact: true }) + ' \u00b7 ' + f.ageText));
      btn.onclick = function () {
        setRegionFilter(state.f.region === reg ? 'all' : reg);
      };
      box.appendChild(btn);
    });
  }

  function renderFeedBoard() {
    var box = $('feed-board');
    if (!box) return;
    box.textContent = '';
    var srcs = state.sourcesData && Array.isArray(state.sourcesData.sources) ? state.sourcesData.sources : [];
    if (!srcs.length) {
      box.appendChild(el('p', 'sub', 'Source status unavailable.'));
      return;
    }

    var sorted = srcs.slice().sort(function (a, b) {
      if (!!a.ok !== !!b.ok) return a.ok ? 1 : -1;
      return (b.count || 0) - (a.count || 0);
    }).slice(0, 12);

    sorted.forEach(function (s) {
      var isDegraded = s.freshness === 'stale' || s.ok === false;
      var a = el('a', 'feed-row-link');
      a.href = '/data';
      a.appendChild(el('span', 'feed-row-name', B.cleanDc(s.name || s.id)));
      var meta = el('span', 'feed-row-meta');
      meta.appendChild(el('span', '', (s.count || 0) + ' items'));
      meta.appendChild(el('span', 'feed-badge ' + (isDegraded ? 'is-stale' : 'is-fresh'), isDegraded ? 'DEGRADED' : 'OK'));
      a.appendChild(meta);
      box.appendChild(a);
    });

    var parent = box.parentNode;
    if (parent) {
      var foot = parent.querySelector('.feed-foot');
      if (!foot) {
        foot = el('div', 'feed-foot');
        parent.appendChild(foot);
      }
      foot.textContent = '';
      var okCount = srcs.filter(function (s) { return s && s.freshness !== 'stale' && s.ok !== false; }).length;
      foot.appendChild(el('span', '', 'Showing top ' + sorted.length + ' of ' + srcs.length + ' feeds \u00b7 ' + okCount + '/' + srcs.length + ' healthy'));
      var allLink = el('a', '', 'Full feed & licence table \u2192');
      allLink.href = '/data';
      foot.appendChild(allLink);
    }
  }

  /* ---------- world monitor map + live solar terminator + readable callouts ---------- */
  var RAD = Math.PI / 180;
  function project(lon, lat, W, H) {
    if (!state.globe) {
      var k = Math.min(W / 360, H / 180);
      return { x: (W - 360 * k) / 2 + (lon + 180) * k, y: (H - 180 * k) / 2 + (90 - lat) * k, v: true };
    }
    var l0 = state.rot[0] * RAD, p0 = state.rot[1] * RAD, l = lon * RAD, p = lat * RAD, R = Math.min(W, H) * 0.45;
    var cosc = Math.sin(p0) * Math.sin(p) + Math.cos(p0) * Math.cos(p) * Math.cos(l - l0);
    return {
      x: W / 2 + R * Math.cos(p) * Math.sin(l - l0),
      y: H / 2 - R * (Math.cos(p0) * Math.sin(p) - Math.sin(p0) * Math.cos(p) * Math.cos(l - l0)),
      v: cosc > 0
    };
  }

  function size() {
    if (!cv) return [600, 300];
    var g = state.globe;
    if ($('mapbox')) $('mapbox').classList.toggle('globe', g);
    var w = cv.clientWidth || 600, d = window.devicePixelRatio || 1;
    var W = Math.round(w * d), H = Math.round((cv.clientHeight || w / 2) * d);
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    return [W, H];
  }

  function drawSolarTerminator(W, H, dpr, nowMs) {
    if (!window.Sun || !window.SunOverlay || !ctx) return;
    var sub = window.Sun.subsolar(nowMs);
    if ($('sun-readout')) {
      $('sun-readout').textContent = 'SUN ' + Math.abs(sub.lat).toFixed(1) + '\u00b0' + (sub.lat >= 0 ? 'N' : 'S') +
        ' ' + Math.abs(sub.lon).toFixed(1) + '\u00b0' + (sub.lon >= 0 ? 'E' : 'W');
    }
    if (!state.globe) {
      var ng = window.SunOverlay.nightGeometry(nowMs);
      ctx.fillStyle = 'rgba(2, 6, 14, 0.54)';
      ng.polygons.forEach(function (poly) {
        ctx.beginPath();
        poly.forEach(function (pt, idx) {
          var p = project(pt[0], pt[1], W, H);
          if (idx === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        });
        ctx.closePath();
        ctx.fill();
      });
      ctx.strokeStyle = 'rgba(242, 179, 61, 0.72)';
      ctx.lineWidth = 1.5 * dpr;
      ng.lines.forEach(function (line) {
        ctx.beginPath();
        line.forEach(function (pt, idx) {
          var p = project(pt[0], pt[1], W, H);
          if (idx === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        });
        ctx.stroke();
      });
      var sp = project(sub.lon, sub.lat, W, H);
      ctx.beginPath();
      ctx.arc(sp.x, sp.y, 4 * dpr, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(242, 179, 61, 0.85)';
      ctx.fill();
    } else {
      var R = Math.min(W, H) * 0.45;
      ctx.save();
      ctx.beginPath();
      ctx.arc(W / 2, H / 2, R, 0, Math.PI * 2);
      ctx.clip();
      var step = 5;
      ctx.fillStyle = 'rgba(2, 6, 14, 0.52)';
      for (var lat = -85; lat < 90; lat += step) {
        for (var lon = -180; lon < 180; lon += step) {
          if (window.Sun.altitude(lat + step / 2, lon + step / 2, nowMs, sub) < 0) {
            var p = project(lon + step / 2, lat + step / 2, W, H);
            if (p.v) {
              var sz = (R * 0.11);
              ctx.fillRect(p.x - sz / 2, p.y - sz / 2, sz, sz);
            }
          }
        }
      }
      var ng2 = window.SunOverlay.nightGeometry(nowMs);
      ctx.strokeStyle = 'rgba(242, 179, 61, 0.78)';
      ctx.lineWidth = 1.5 * dpr;
      ng2.lines.forEach(function (line) {
        var open = false;
        ctx.beginPath();
        line.forEach(function (pt) {
          var p = project(pt[0], pt[1], W, H);
          if (!p.v) { open = false; return; }
          if (!open) { ctx.moveTo(p.x, p.y); open = true; }
          else ctx.lineTo(p.x, p.y);
        });
        ctx.stroke();
      });
      ctx.restore();
    }
  }

  function renderMapCallouts(rawCands, cssW, cssH, pinObstacles) {
    var layer = $('map-labels');
    if (!layer) return;
    layer.textContent = '';
    state.calloutRects = [];
    if (!rawCands.length || cssW < 180 || cssH < 90) return;

    var nodes = {};
    var cands = [];
    rawCands.forEach(function (c) {
      var st = B.severityTokens(c.ev.severity);
      var box = el('div', 'map-callout' + (c.isSelected ? ' is-sel' : ''));
      box.style.visibility = 'hidden';
      box.style.setProperty('--sev-bar', st.bar);
      box.style.setProperty('--sev-text', st.text);
      box.appendChild(el('span', 'mc-rank', String(c.rank + 1).padStart(2, '0')));
      box.appendChild(el('span', 'mc-text', B.mapCalloutText(c.ev)));
      layer.appendChild(box);
      var rect = box.getBoundingClientRect();
      var w = Math.ceil(rect.width || box.offsetWidth || 120);
      var h = Math.ceil(rect.height || box.offsetHeight || 22);
      nodes[c.rowId] = { node: box, st: st };
      cands.push({
        id: c.ev.id,
        rowId: c.rowId,
        pinX: c.pinX,
        pinY: c.pinY,
        w: w,
        h: h,
        rank: c.rank,
        isSelected: c.isSelected
      });
    });

    var maxCallouts = cssW < 440 ? 4 : 6;
    var placed = B.placeMapCallouts(cands, cssW, cssH, maxCallouts, pinObstacles);
    var placedMap = {};
    placed.forEach(function (p) { placedMap[p.rowId] = p; });

    Object.keys(nodes).forEach(function (rowId) {
      var p = placedMap[rowId];
      var entry = nodes[rowId];
      if (!p) {
        entry.node.remove();
        return;
      }
      entry.node.style.left = p.boxX + 'px';
      entry.node.style.top = p.boxY + 'px';
      entry.node.style.visibility = '';
    });

    if (placed.length) {
      var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('class', 'map-leaders');
      svg.setAttribute('viewBox', '0 0 ' + cssW + ' ' + cssH);
      placed.forEach(function (p) {
        var entry = nodes[p.rowId];
        var cx = Math.max(p.boxX, Math.min(p.pinX, p.boxX + p.w));
        var cy = Math.max(p.boxY, Math.min(p.pinY, p.boxY + p.h));
        var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', String(Math.round(p.pinX)));
        line.setAttribute('y1', String(Math.round(p.pinY)));
        line.setAttribute('x2', String(Math.round(cx)));
        line.setAttribute('y2', String(Math.round(cy)));
        line.setAttribute('stroke', entry.st.bar);
        line.setAttribute('stroke-width', '1');
        line.setAttribute('stroke-opacity', '0.85');
        svg.appendChild(line);
      });
      layer.prepend(svg);
    }

    state.calloutRects = placed;
  }

  function draw() {
    if (!cv || !ctx) return;
    var s = size(), W = s[0], H = s[1];
    var cssW = cv.clientWidth || W, cssH = cv.clientHeight || H;
    var dprX = W / cssW, dprY = H / cssH, dpr = dprX;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#070c12';
    ctx.fillRect(0, 0, W, H);

    if (state.globe) {
      var R = Math.min(W, H) * 0.45;
      ctx.beginPath();
      ctx.arc(W / 2, H / 2, R, 0, Math.PI * 2);
      ctx.fillStyle = '#0b1522';
      ctx.fill();
      ctx.strokeStyle = '#2d4560';
      ctx.lineWidth = 1.5 * dpr;
      ctx.stroke();
    }

    // 30-degree graticule
    ctx.strokeStyle = '#122031';
    ctx.lineWidth = 1 * dpr;
    for (var glat = -60; glat <= 60; glat += 30) {
      var onLat = false;
      ctx.beginPath();
      for (var glon = -180; glon <= 180; glon += 6) {
        var gp = project(glon, glat, W, H);
        if (!gp.v) { onLat = false; continue; }
        if (!onLat) { ctx.moveTo(gp.x, gp.y); onLat = true; } else ctx.lineTo(gp.x, gp.y);
      }
      ctx.stroke();
    }
    for (var mlon = -150; mlon <= 180; mlon += 30) {
      var onLon = false;
      ctx.beginPath();
      for (var mlat = -84; mlat <= 84; mlat += 6) {
        var mp = project(mlon, mlat, W, H);
        if (!mp.v) { onLon = false; continue; }
        if (!onLon) { ctx.moveTo(mp.x, mp.y); onLon = true; } else ctx.lineTo(mp.x, mp.y);
      }
      ctx.stroke();
    }

    // Continents
    ctx.fillStyle = '#17283b';
    ctx.strokeStyle = '#2b4460';
    ctx.lineWidth = 1 * dpr;
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
      ctx.fill();
      ctx.stroke();
    });

    drawSolarTerminator(W, H, dpr, Date.now());

    var evs = state.allRows.flatMap(function (row) {
      return row.members.map(function (event) { return { event: event, rowId: row.ev.id }; });
    });
    state.pts = [];
    var bgPins = [], topPins = [], selPins = [], pinObstacles = [];

    evs.forEach(function (entry) {
      var e = entry.event;
      if (e.lat == null || e.lon == null) return;
      var p = project(e.lon, e.lat, W, H);
      if (!p.v) return;
      var rk = state.rankOf && state.rankOf[entry.rowId] != null ? state.rankOf[entry.rowId] : 99;
      var on = state.sel === entry.rowId;
      var item = { entry: entry, e: e, p: p, rk: rk, on: on };
      if (on) selPins.push(item);
      else if (rk < 10) topPins.push(item);
      else bgPins.push(item);
    });

    bgPins.reverse();
    topPins.sort(function (a, b) { return b.rk - a.rk; });
    var drawOrder = bgPins.concat(topPins).concat(selPins);

    drawOrder.forEach(function (item) {
      var e = item.e, p = item.p, rk = item.rk, on = item.on, rowId = item.entry.rowId;
      var col = B.SEV[e.severity] || '#9fb4c8';
      var r = (4 + (e.score || 40) / 14) * dpr;
      var pinR = rk < 10 ? Math.max(r, 8.5 * dpr) : r;
      ctx.beginPath();
      ctx.arc(p.x, p.y, pinR * 1.5, 0, Math.PI * 2);
      ctx.fillStyle = col + '2b';
      ctx.fill();
      ctx.beginPath();
      ctx.arc(p.x, p.y, pinR, 0, Math.PI * 2);
      ctx.fillStyle = col;
      ctx.fill();
      ctx.lineWidth = (on ? 2.5 : 1) * dpr;
      ctx.strokeStyle = on ? '#ffffff' : '#070c12';
      ctx.stroke();
      if (rk < 10) {
        ctx.fillStyle = '#070c12';
        ctx.font = 'bold ' + Math.max(10 * dpr, Math.round(pinR * 1.08)) + 'px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(String(rk + 1), p.x, p.y + dpr * 0.5);
      }
      var cx = p.x / dprX, cy = p.y / dprY;
      state.pts.push({ rowId: rowId, x: cx, y: cy, r: Math.max(pinR / dpr * 1.9, 14) });
      if (rk < 12 || on) {
        pinObstacles.push({ x: cx, y: cy, r: pinR / dpr });
      }
    });

    var calloutCands = [], seenCalloutRows = {}, geoCount = 0;
    for (var ri = 0; ri < state.allRows.length; ri++) {
      var row = state.allRows[ri];
      var rkRow = state.rankOf && state.rankOf[row.ev.id] != null ? state.rankOf[row.ev.id] : ri;
      var isSel = state.sel === row.ev.id;
      var geoEv = null, geoProj = null;
      for (var mi = 0; mi < row.members.length; mi++) {
        var mem = row.members[mi];
        if (mem && mem.lat != null && mem.lon != null) {
          var gp = project(mem.lon, mem.lat, W, H);
          if (gp.v) { geoEv = mem; geoProj = gp; break; }
        }
      }
      if (!geoEv) continue;
      if (geoCount < 6 || isSel) {
        if (!seenCalloutRows[row.ev.id]) {
          seenCalloutRows[row.ev.id] = 1;
          calloutCands.push({
            rowId: row.ev.id,
            ev: geoEv,
            pinX: geoProj.x / dprX,
            pinY: geoProj.y / dprY,
            rank: rkRow,
            isSelected: isSel
          });
          if (geoCount < 6) geoCount++;
        }
      }
    }

    renderMapCallouts(calloutCands, cssW, cssH, pinObstacles);
  }

  function hit(ev) {
    if (!cv) return null;
    var b = cv.getBoundingClientRect(), x = ev.clientX - b.left, y = ev.clientY - b.top, best = null, bd = 1e9;
    state.pts.forEach(function (p) {
      var d = Math.hypot(p.x - x, p.y - y);
      if (d < p.r && d < bd) { bd = d; best = p; }
    });
    if (best) return best;
    for (var i = 0; i < state.calloutRects.length; i++) {
      var c = state.calloutRects[i];
      if (x >= c.boxX && x <= c.boxX + c.w && y >= c.boxY && y <= c.boxY + c.h) {
        return { rowId: c.rowId };
      }
    }
    return null;
  }

  if (cv) {
    var drag = null;
    cv.addEventListener('pointerdown', function (e) {
      drag = { x: e.clientX, y: e.clientY, rot: state.rot.slice(), moved: false };
    });
    window.addEventListener('pointermove', function (e) {
      if (!drag || !state.globe) return;
      var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
      state.rot = [drag.rot[0] - dx * 0.4, Math.max(-80, Math.min(80, drag.rot[1] + dy * 0.4))];
      draw();
    });
    window.addEventListener('pointerup', function (e) {
      if (drag && !drag.moved) {
        var h = hit(e);
        if (h) focusEvent(h.rowId, true);
      }
      drag = null;
    });
    window.addEventListener('pointercancel', function () { drag = null; });
    cv.addEventListener('keydown', function (e) {
      var offsets = { ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, 10], ArrowDown: [0, -10] };
      var offset = offsets[e.key];
      if (!state.globe || !Array.isArray(offset)) return;
      e.preventDefault();
      state.rot = [state.rot[0] + offset[0], Math.max(-80, Math.min(80, state.rot[1] + offset[1]))];
      draw();
    });
  }

  if ($('proj')) {
    $('proj').onclick = function () {
      state.globe = !state.globe;
      this.setAttribute('aria-pressed', String(state.globe));
      this.textContent = state.globe ? 'Flat map' : 'Globe view';
      if (cv) {
        cv.tabIndex = state.globe ? 0 : -1;
        cv.setAttribute('aria-label', state.globe
          ? 'Globe of current events. Use the arrow keys to rotate. The list has the same events.'
          : 'Map of current events and live solar terminator. The list has the same events.');
      }
      draw();
    };
  }
  if ($('reset')) {
    $('reset').onclick = function () {
      state.rot = [-40, 20];
      state.sel = null;
      render();
    };
  }
  window.addEventListener('resize', function () {
    if (resizeRaf) cancelAnimationFrame(resizeRaf);
    resizeRaf = requestAnimationFrame(function () {
      resizeRaf = 0;
      syncFilterDrawer();
      updateCatsScroll();
      draw();
      layoutTicker();
    });
  });

  /* ---------- hero, stats & history ---------- */
  function hero(d) {
    var evs = state.events, now = new Date(), nowMs = now.getTime();
    var snapFresh = B.isSnapshotFresh(d.generated, nowMs);
    var leadId = state.lead && state.lead.id;

    if ($('dateline')) {
      $('dateline').textContent = 'LIVE GLOBAL WIRE \u00b7 PUBLIC SOURCES';
    }
    if ($('verdict')) {
      $('verdict').textContent = 'All feeds: ' + B.formatSevCount(evs) + ' \u00b7 ' + evs.length + ' events';
    }
    if ($('map-heading')) {
      $('map-heading').textContent = 'WORLD MONITOR';
    }

    var big = evs.filter(function (e) { return e.big && (!leadId || e.id !== leadId); })[0], tl = $('topline');
    if (big && tl) {
      var bf = freshnessFor(big, nowMs);
      tl.hidden = false;
      tl.textContent = '';
      tl.appendChild(el('b', 'tl-label', 'TOP HEADLINE'));
      var ta = el('a', 'tl-title', B.cleanDc(big.title));
      ta.href = '/event?id=' + encodeURIComponent(big.id);
      tl.appendChild(ta);
      tl.appendChild(el('span', 'tl-meta', ((big.detail && big.detail.measured_at) ? 'Measured by the desk, first failure ' + big.detail.measured_at : B.cleanDc(big.source)) + ' \u00b7 ' + bf.ageText));
    } else if (tl) {
      tl.hidden = true;
    }

    var t = $('tiles');
    if (t) {
      t.textContent = '';
      t.appendChild(el('span', 'tile-scope', 'ALL ' + evs.length + ':'));
      ['extreme', 'severe', 'moderate', 'minor'].forEach(function (k) {
        var n = evs.filter(function (e) { return e.severity === k; }).length;
        var c = el('span', 'tile' + (n === 0 ? ' is-zero' : ''));
        c.setAttribute('data-sev', k);
        c.appendChild(el('b', '', String(n)));
        c.appendChild(document.createTextNode(k));
        t.appendChild(c);
      });
    }

    if ($('srcline')) {
      var ageStr = B.ago(d.generated, nowMs);
      $('srcline').textContent = snapFresh
        ? ('Updated ' + ageStr + ' \u00b7 ' + evs.length + ' items \u00b7 ')
        : ('Snapshot ' + ageStr + ' \u00b7 ' + evs.length + ' items \u00b7 ');
      var l = el('a', '', 'Sources & licences');
      l.href = '/data';
      $('srcline').appendChild(l);
    }
  }

  function stats() {
    var box = $('stats');
    if (!box) return;
    box.textContent = '';
    var now = Date.now(), ref = filterClock(now);
    if ($('counts-heading')) {
      $('counts-heading').textContent = 'WIRE CADENCE';
    }
    var by = {};
    state.events.forEach(function (e) { by[e.type] = (by[e.type] || 0) + 1; });
    var dayEvents = state.events.filter(function (e) { return ref - Date.parse(e.time) < 864e5; });
    box.appendChild(el('p', 'sub', 'Active breakdown across ' + Object.keys(by).length + ' event types.'));
    var g = el('div', 'chips');
    Object.keys(by).sort(function (x, y) { return by[y] - by[x]; }).forEach(function (t) {
      var c = el('span', 'stat');
      c.appendChild(el('b', '', String(by[t])));
      c.appendChild(el('span', '', (B.TYPES[t] || B.TYPES.other).label));
      g.appendChild(c);
    });
    box.appendChild(g);

    if ($('last-hour')) {
      $('last-hour').textContent = '24h window: ' + dayEvents.length + ' events (' + B.formatSevCount(dayEvents) + ')';
    }
  }

  var hist = [];
  function drawHist(hours) {
    var c = $('hist');
    if (!c) return;
    var x = c.getContext('2d'), d = window.devicePixelRatio || 1;
    var W = (c.clientWidth || 300) * d, H = 132 * d;
    c.width = W;
    c.height = H;
    var ref = hist.length ? Math.max(Date.now(), Date.parse(hist[hist.length - 1].t) || 0) : Date.now();
    if (hist.length && Date.now() - (Date.parse(hist[hist.length - 1].t) || 0) > 6 * 36e5) {
      ref = Date.parse(hist[hist.length - 1].t) || Date.now();
    } else {
      ref = Date.now();
    }
    var cut = ref - hours * 36e5;
    var pts = hist.filter(function (r) { return Date.parse(r.t) >= cut; });
    x.clearRect(0, 0, W, H);
    var label = 'Event counts in the last ' + hours + ' hours. ';
    if (pts.length < 2) {
      c.setAttribute('aria-label', label + 'Collecting data.');
      x.fillStyle = '#d8e4f0';
      x.font = '600 ' + Math.round(13 * d) + 'px "Public Sans", system-ui, sans-serif';
      x.fillText('Collecting data. The chart fills in over the next hours.', 8 * d, 24 * d);
      return;
    }
    var counts = pts.map(function (r) { return r.count; });
    var low = Math.min.apply(null, counts), high = Math.max.apply(null, counts);
    c.setAttribute('aria-label', label + 'Latest count: ' + counts[counts.length - 1] + '. Counts ranged from ' + low + ' to ' + high + '.');
    var max = high + 2, min = low - 2;
    var t0 = Date.parse(pts[0].t), t1 = Date.parse(pts[pts.length - 1].t) || t0 + 1;
    var topPad = 22 * d, bottomPad = 24 * d, leftPad = 42 * d, rightPad = 10 * d;
    x.strokeStyle = '#f2b33d';
    x.lineWidth = 2 * d;
    x.beginPath();
    pts.forEach(function (r, i) {
      var px = leftPad + (Date.parse(r.t) - t0) / Math.max(1, t1 - t0) * Math.max(10, W - leftPad - rightPad);
      var py = H - bottomPad - (r.count - min) / Math.max(1, max - min) * (H - topPad - bottomPad);
      if (i) x.lineTo(px, py); else x.moveTo(px, py);
    });
    x.stroke();
    x.fillStyle = '#d8e4f0';
    x.font = '600 ' + Math.round(12.5 * d) + 'px "Public Sans", system-ui, sans-serif';
    x.textAlign = 'left';
    x.fillText(max + ' events', 8 * d, 15 * d);
    x.fillText(min + '', 8 * d, H - 28 * d);
    function tl(t) {
      var dt = new Date(t);
      return hours > 30 ? dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : dt.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
    }
    x.textAlign = 'left'; x.fillText(tl(t0), leftPad, H - 6 * d);
    x.textAlign = 'center'; x.fillText(tl((t0 + t1) / 2), (leftPad + (W - rightPad)) / 2, H - 6 * d);
    x.textAlign = 'right'; x.fillText(tl(t1), W - rightPad, H - 6 * d);
    x.textAlign = 'left';
    x.strokeStyle = '#22364d';
    x.lineWidth = 1 * d;
    x.beginPath();
    x.moveTo(8 * d, H - 22 * d);
    x.lineTo(W - rightPad, H - 22 * d);
    x.stroke();
  }

  function histInit() {
    fetch('data/log.jsonl', { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error('log');
      return r.text();
    }).then(function (t) {
      hist = t.split('\n').filter(Boolean).map(function (l) {
        try { return JSON.parse(l); } catch (e) { return null; }
      }).filter(Boolean);
      if ($('hist-wrap')) $('hist-wrap').hidden = false;
      drawHist(24);
      Array.prototype.forEach.call(document.querySelectorAll('[data-h]'), function (b) {
        b.onclick = function () {
          Array.prototype.forEach.call(document.querySelectorAll('[data-h]'), function (o) {
            o.setAttribute('aria-pressed', String(o === b));
          });
          drawHist(+b.dataset.h);
        };
      });
    }).catch(function () {
      if ($('hist-wrap')) $('hist-wrap').hidden = true;
    });
  }

  function legend() {
    var lg = $('legend');
    if (!lg) return;
    lg.textContent = '';
    ['extreme', 'severe', 'moderate', 'minor'].forEach(function (t) {
      var s = el('span'), i = el('i');
      i.style.background = B.SEV[t];
      s.appendChild(i);
      s.appendChild(document.createTextNode(t));
      lg.appendChild(s);
    });
    lg.appendChild(el('span', '', 'Numbers 1\u201310 match wire rail'));
  }

  function loadAll(isRefresh) {
    nextRefreshAt = Date.now() + REFRESH_MS;
    Promise.all([
      get('data/events.json'),
      get('data/lead-story.json').catch(function () { return null; }),
      get('data/sources.json').catch(function () { return null; })
    ]).then(function (feeds) {
      var data = feeds[0];
      var leadData = feeds[1];
      var srcData = feeds[2];

      state.events = (data.events || []).map(B.sanitizeEvent);
      state.generated = data.generated || '';
      state.sourcesData = srcData;
      state.sourcesById = {};
      if (srcData && Array.isArray(srcData.sources)) {
        srcData.sources.forEach(function (s) {
          if (s && s.id) state.sourcesById[s.id] = s;
        });
      }

      var snapFresh = B.isSnapshotFresh(data.generated, Date.now());
      if ($('dot')) $('dot').className = 'dot' + (snapFresh ? '' : ' stale');

      var effectiveLead = (leadData && leadData.lead) ? leadData : B.deriveLeadStory(state.events, state.generated);
      state.streamId = B.streamFocusId(state.events, effectiveLead.lead);

      if (!isRefresh) {
        buildFilters();
        legend();
        bindOpsButtons();
        bindTickerToggle();
      } else {
        buildCats();
      }
      syncFilterDrawer();
  updateClocks();
      renderOpsMonitor();
      renderLeadStory(effectiveLead);
      updateStreamFacade();
      renderChangesBoard();
      renderProbeBoard();
      renderFeedBoard();
      stats();
      hero(data);
      renderTicker();
      render();
      if (!isRefresh) histInit();
    }).catch(function () {
      var message = 'Data could not be loaded. Try again in a minute.';
      if ($('count')) $('count').textContent = message;
      if ($('list') && !$('list').children.length) {
        $('list').appendChild(el('li', 'empty', message));
      }
    });
  }

  syncFilterDrawer();
  updateClocks();
  setInterval(updateClocks, 1000);
  setInterval(function () {
    if (!state.tickerPaused && !reduce && state.tickerItems.length > 1) {
      state.tickerIdx = (state.tickerIdx + state.tickerStepLen) % state.tickerItems.length;
      layoutTicker();
    }
  }, TICKER_STEP_MS);
  setInterval(function () { loadAll(true); }, REFRESH_MS);
  get('data/world.json').then(function (world) { state.world = world; draw(); }).catch(function () {});
  loadAll(false);
})();
