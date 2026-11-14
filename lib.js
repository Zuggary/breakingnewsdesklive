/* Pure helpers, shared by the page and the Node tests. */
(function (root) {
  var TYPES = {
    earthquake: { label: 'Earthquake', color: '#ff9340' },
    weather: { label: 'Weather', color: '#5cb3ff' },
    storm: { label: 'Cyclone', color: '#b48cff' },
    flood: { label: 'Flood', color: '#3fd0d0' },
    wildfire: { label: 'Wildfire', color: '#ff5c5c' },
    volcano: { label: 'Volcano', color: '#f2d04b' },
    space: { label: 'Space weather', color: '#d58cff' },
    drought: { label: 'Drought', color: '#c9a06b' },
    other: { label: 'Other', color: '#93a1b5' }
  };
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
      if (f.type && f.type !== 'all' && e.type !== f.type) return false;
      if (f.region && f.region !== 'all' && e.region !== f.region) return false;
      if (f.day && now - Date.parse(e.time) > 864e5) return false;
      return true;
    });
  }
  function safeUrl(u) { return /^https:\/\/[^\s]+$/.test(u || '') ? u : null; }
  var api = { TYPES: TYPES, SEV: SEV, ago: ago, filterEvents: filterEvents, safeUrl: safeUrl };
  if (typeof module !== 'undefined') module.exports = api; else root.BND = api;
})(this);
