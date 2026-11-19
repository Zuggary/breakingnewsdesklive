"use strict";

const assert = require("node:assert/strict");
const Sun = require("../sun.js");
const { nightGeometry } = require("../sun-overlay.js");

const equinox = Date.UTC(2025, 2, 20, 12);
const sunLon = Sun.subsolar(equinox).lon;
const spring = nightGeometry(equinox);
const crossings = spring.lines.flat().filter(([, lat]) => Math.abs(lat) < 1e-8);
assert.equal(crossings.length, 2);
assert.ok(Math.abs(crossings[0][0] - (sunLon - 90)) < 1e-8);
assert.ok(Math.abs(crossings[1][0] - (sunLon + 90)) < 1e-8);

const winter = nightGeometry(Date.UTC(2025, 11, 21, 12));
assert.deepEqual(winter.polygons[0].slice(-2), [[180, 90], [-180, 90]]);

// Find the declination zero nearest the equinox noon to exercise the meridian case.
let before = equinox - 86400000;
let after = equinox;
while (after - before > 1) {
  const mid = Math.floor((before + after) / 2);
  if (Sun.subsolar(mid).lat < 0) before = mid;
  else after = mid;
}
const zero = nightGeometry(after);
assert.equal(zero.lines.length, 2);
for (const [[lon, south], [endLon, north]] of zero.lines) {
  assert.equal(lon, endLon);
  assert.equal(south, -90);
  assert.equal(north, 90);
}
for (const { polygons } of [spring, winter, zero]) {
  assert.ok(polygons.flat(2).every(Number.isFinite));
}

console.log("Sun overlay tests passed");
