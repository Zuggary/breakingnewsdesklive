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
    outage: { label: 'Outage', color: '#ff7ab8' },
    smoke: { label: 'Smoke', color: '#b0a090' },
    tsunami: { label: 'Tsunami', color: '#27c2ff' },
    space: { label: 'Space weather', color: '#d58cff' },
    drought: { label: 'Drought', color: '#c9a06b' },
    other: { label: 'Other', color: '#93a1b5' }
  };
  var GROUPS = { hazards: ['Hazards', ['earthquake', 'weather', 'storm', 'flood', 'wildfire', 'volcano', 'drought', 'tsunami', 'smoke']],
    transport: ['Transport', ['transport']], outages: ['Outages and cyber', ['outage']], recalls: ['Recalls and safety', ['recall']],
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
  var api = { GROUPS: GROUPS, TYPES: TYPES, SEV: SEV, ago: ago, filterEvents: filterEvents, safeUrl: safeUrl };
  if (typeof module !== 'undefined') module.exports = api; else root.BND = api;
})(this);
