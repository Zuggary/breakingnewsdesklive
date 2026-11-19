(function (root) {
  "use strict";
  const isNode = typeof module !== "undefined" && module.exports;
  const Sun = isNode ? require("./sun.js") : root.Sun;
  const RAD = Math.PI / 180;

  function nightGeometry(ms) {
    const { lat: decl, lon: sunLon } = Sun.subsolar(ms);
    const edges = [sunLon - 90, sunLon + 90].map(Sun.wrap180).sort((a, b) => a - b);
    if (Math.abs(decl) < 1e-6) {
      // At zero declination the terminator is two meridians and neither pole is in darkness.
      const [west, east] = edges;
      const spans = sunLon > west && sunLon < east ? [[-180, west], [east, 180]] : [[west, east]];
      return {
        polygons: spans.filter(([a, b]) => a < b).map(([a, b]) => [[a, -90], [b, -90], [b, 90], [a, 90]]),
        lines: edges.flatMap(lon => lon === 180 ? [-180, 180] : [lon]).map(lon => [[lon, -90], [lon, 90]])
      };
    }

    const samples = new Set(edges);
    for (let lon = -180; lon <= 180; lon += 2) samples.add(lon);
    const tanDecl = Math.tan(decl * RAD);
    const line = [...samples].sort((a, b) => a - b).map(lon =>
      [lon, Math.atan(-Math.cos((lon - sunLon) * RAD) / tanDecl) / RAD]);
    const pole = decl < 0 ? 90 : -90;
    return { polygons: [[...line, [180, pole], [-180, pole]]], lines: [line] };
  }

  if (isNode) module.exports = { nightGeometry };
  else root.SunOverlay = { nightGeometry };
})(typeof window !== "undefined" ? window : this);
