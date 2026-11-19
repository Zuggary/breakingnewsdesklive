/* AN18 Part 1: sunlight maths. No network, no dependencies, no DOM. Same NOAA equations as desk/sun.py.
   Loaded by page/index.html (stream map) and by the site's tv.html (copy of this file). Tested with node.
   Everything here is computed from UTC; it is not a measurement. */
(function (root) {
  "use strict";
  const RAD = Math.PI / 180, DEG = 180 / Math.PI;
  const HORIZON = -0.833;                 // sunrise and sunset: sun's centre 0.833 deg below the horizon
  const BANDS = [HORIZON, -6, -12, -18];  // terminator, civil, nautical, astronomical edges

  function julianDay(ms) { return ms / 86400000 + 2440587.5; }

  // NOAA: equation of time (minutes) and declination (degrees) at a UTC instant (ms since epoch).
  function solar(ms) {
    const jc = (julianDay(ms) - 2451545.0) / 36525.0;
    const l0 = (((280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360) + 360) % 360;
    const m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc);
    const e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc);
    const mr = m * RAD;
    const c = Math.sin(mr) * (1.914602 - jc * (0.004817 + 0.000014 * jc)) + Math.sin(2 * mr) * (0.019993 - 0.000101 * jc) + Math.sin(3 * mr) * 0.000289;
    const trueLong = l0 + c;
    const omega = 125.04 - 1934.136 * jc;
    const app = trueLong - 0.00569 - 0.00478 * Math.sin(omega * RAD);
    const obl = 23.0 + (26.0 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60.0) / 60.0;
    const oblC = obl + 0.00256 * Math.cos(omega * RAD);
    const decl = Math.asin(Math.sin(oblC * RAD) * Math.sin(app * RAD));
    const y = Math.pow(Math.tan(oblC * RAD / 2), 2);
    const l0r = l0 * RAD;
    const eq = 4 * DEG * (y * Math.sin(2 * l0r) - 2 * e * Math.sin(mr) + 4 * e * y * Math.sin(mr) * Math.cos(2 * l0r)
      - 0.5 * y * y * Math.sin(4 * l0r) - 1.25 * e * e * Math.sin(2 * mr));
    return { eq: eq, decl: decl * DEG };
  }

  function wrap180(x) { x = ((x + 180) % 360 + 360) % 360 - 180; return x === -180 ? 180 : x; }

  // The place where the sun is straight overhead: {lat, lon} in degrees (east positive).
  function subsolar(ms) {
    const s = solar(ms);
    const d = new Date(ms);
    const utcMin = d.getUTCHours() * 60 + d.getUTCMinutes() + d.getUTCSeconds() / 60 + d.getUTCMilliseconds() / 60000;
    return { lat: s.decl, lon: wrap180((720 - utcMin - s.eq) / 4), eq: s.eq };
  }

  // Sun altitude in degrees (geometric, no refraction). Pass a precomputed `sp` from subsolar() to run it for many places.
  function altitude(lat, lon, ms, sp) {
    sp = sp || subsolar(ms);
    const p = lat * RAD, dl = sp.lat * RAD, h = (lon - sp.lon) * RAD;
    const s = Math.sin(p) * Math.sin(dl) + Math.cos(p) * Math.cos(dl) * Math.cos(h);
    return Math.asin(Math.max(-1, Math.min(1, s))) * DEG;
  }

  // Sunrise, sunset and solar noon around one "solar day" (centred on the local solar noon of UTC calendar day dayStartMs).
  // Two passes: the equation of time and declination are re-read at the event itself.
  function riseSet(lat, lon, dayStartMs) {
    const out = { sunrise: null, sunset: null, noon: null, polar: null };
    let noonMin = 720 - 4 * lon - solar(dayStartMs + (720 - 4 * lon) * 60000).eq;
    for (let i = 0; i < 2; i++) noonMin = 720 - 4 * lon - solar(dayStartMs + noonMin * 60000).eq;
    out.noon = dayStartMs + noonMin * 60000;
    const lr = lat * RAD;
    let rise = noonMin - 360, set = noonMin + 360, ok = true;
    const cosH = function (t) {
      const dec = solar(dayStartMs + t * 60000).decl * RAD;
      return Math.sin(HORIZON * RAD) / (Math.cos(lr) * Math.cos(dec)) - Math.tan(lr) * Math.tan(dec);
    };
    for (let i = 0; i < 3 && ok; i++) {
      const cr = cosH(rise), cs = cosH(set);
      if (Math.abs(cr) > 1 || Math.abs(cs) > 1) { ok = false; out.polar = (Math.abs(cr) > 1 ? cr : cs) < 0 ? "day" : "night"; break; }
      rise = noonMin - 4 * Math.acos(cr) * DEG;
      set = noonMin + 4 * Math.acos(cs) * DEG;
    }
    if (ok) { out.sunrise = dayStartMs + rise * 60000; out.sunset = dayStartMs + set * 60000; }
    return out;
  }

  function utcDayStart(ms) { const d = new Date(ms); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()); }

  // Date key YYYY-MM-DD of an instant in a time zone.
  const dateFmt = {};
  function localDate(ms, tz) {
    const f = dateFmt[tz] || (dateFmt[tz] = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }));
    return f.format(new Date(ms));
  }
  const ZABBR = { "America/New_York": "ET", "America/Detroit": "ET", "America/Indiana/Indianapolis": "ET", "America/Kentucky/Louisville": "ET", "America/Chicago": "CT", "America/Denver": "MT", "America/Boise": "MT",
    "America/Phoenix": "MT", "America/Los_Angeles": "PT", "America/Anchorage": "AKT", "Pacific/Honolulu": "HT", "America/Puerto_Rico": "AT" };
  const timeFmt = {};
  function fmtTime(ms, tz) {
    const f = timeFmt[tz] || (timeFmt[tz] = new Intl.DateTimeFormat("en-US", { timeZone: tz, hour: "numeric", minute: "2-digit", hour12: true }));
    return f.format(new Date(ms)).toLowerCase().replace(/\s/g, " ").replace(/[  ]/g, " ");
  }
  function fmtSpan(min) {
    const m = Math.max(0, Math.round(min));
    return m >= 60 ? Math.floor(m / 60) + " h " + (m % 60 < 10 ? "0" : "") + (m % 60) + " min" : m + " min";
  }

  // Sunrise and sunset on the local calendar day of `ms` at a place, and the daylight left. Polar cases say "no sunrise" or "no sunset".
  function hubSun(lat, lon, tz, ms) {
    const today = localDate(ms, tz);
    const base = utcDayStart(ms);
    let sunrise = null, sunset = null, polar = null;
    for (let off = -1; off <= 1; off++) {
      const r = riseSet(lat, lon, base + off * 86400000);
      if (r.sunrise !== null && localDate(r.sunrise, tz) === today) sunrise = r.sunrise;
      if (r.sunset !== null && localDate(r.sunset, tz) === today) sunset = r.sunset;
      if (r.polar) polar = r.polar;
    }
    const up = altitude(lat, lon, ms) > HORIZON;
    let state;
    if (sunrise === null && sunset === null) state = up ? "polar_day" : "polar_night";
    else state = up ? "day" : "night";
    let leftMin = 0;
    if (state === "polar_day") leftMin = null;
    else if (sunset !== null && sunset > ms) leftMin = (sunset - Math.max(ms, sunrise === null ? ms : sunrise)) / 60000;
    else if (sunset === null && up) leftMin = null;           // sun stays up past the end of the local day
    return { state: state, sunrise: sunrise, sunset: sunset, leftMin: leftMin, polar: polar, tz: tz };
  }

  // One line for the hub card.
  function hubCardText(lat, lon, tz, ms) {
    const s = hubSun(lat, lon, tz, ms);
    const ab = ZABBR[tz] || "";
    const parts = [];
    parts.push(s.sunrise === null ? "no sunrise" : "sunrise " + fmtTime(s.sunrise, tz));
    parts.push(s.sunset === null ? "no sunset" : "sunset " + fmtTime(s.sunset, tz) + (ab ? " " + ab : ""));
    if (s.state === "polar_day") parts.push("sun stays up");
    else if (s.state === "polar_night") parts.push("sun stays down");
    else if (s.leftMin === null) parts.push("daylight left until the end of the day");
    else if (s.state === "night" && s.sunrise !== null && s.sunrise > ms) parts.push("sun rises in " + fmtSpan((s.sunrise - ms) / 60000));
    else parts.push(s.leftMin > 0 ? "daylight left " + fmtSpan(s.leftMin) : "no daylight left");
    return "Sun: " + parts.join(", ") + " \u00b7 computed";
  }

  // ---- shading ----
  function smooth(x) { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); }
  // Night darkness 0..1 from altitude: day 0, civil to 0.40, nautical to 0.62, astronomical to 0.76, full night 0.82.
  const KNOTS = [[0, 0], [-0.833, 0.07], [-6, 0.40], [-12, 0.62], [-18, 0.76], [-26, 0.82]];
  function darkness(alt) {
    if (alt >= 0) return 0;
    for (let i = 1; i < KNOTS.length; i++) {
      if (alt >= KNOTS[i][0]) { const a = KNOTS[i - 1], b = KNOTS[i]; return a[1] + (b[1] - a[1]) * smooth((alt - a[0]) / (b[0] - a[0])); }
    }
    return KNOTS[KNOTS.length - 1][1];
  }
  const NIGHT = [4, 9, 24], ACCENT = [76, 195, 255], WARM = [255, 226, 168], GLINT = [255, 246, 222];
  // [r, g, b, a] with a in 0..255 (straight alpha). Night side navy with a faint sky-blue glow along the civil band, warm day side, gentle glint.
  function shade(alt, opts) {
    const dayTint = !opts || opts.dayTint !== false;
    if (alt < 0) {
      const d = darkness(alt);
      const g = 0.16 * Math.exp(-Math.pow((alt + 2.5) / 2.6, 2));          // soft sky-blue rim just past the terminator
      const r = NIGHT[0] * (1 - g) + ACCENT[0] * g, gr = NIGHT[1] * (1 - g) + ACCENT[1] * g, b = NIGHT[2] * (1 - g) + ACCENT[2] * g;
      return [r, gr, b, 255 * Math.min(1, d + g * 0.6)];
    }
    if (!dayTint) return [0, 0, 0, 0];
    const s = Math.sin(alt * RAD);
    const a = 0.20 * Math.pow(s, 0.55) * (1 - 0.35 * Math.pow(s, 4));     // warm tint, strongest in the middle of the day side
    const gl = 0.20 * Math.pow(s, 28);                                       // gentle highlight under the sun
    const t = gl / Math.max(1e-6, a + gl);
    return [WARM[0] * (1 - t) + GLINT[0] * t, WARM[1] * (1 - t) + GLINT[1] * t, WARM[2] * (1 - t) + GLINT[2] * t, 255 * Math.min(0.5, a + gl)];
  }

  // Phones: a flat equirectangular grid, RGBA bytes, cols x rows. Only the night side and its twilight bands (no day tint).
  function flatBands(ms, cols, rows, opts) {
    const sp = subsolar(ms), buf = new Uint8ClampedArray(cols * rows * 4);
    const dl = sp.lat * RAD, sd = Math.sin(dl), cd = Math.cos(dl);
    for (let y = 0; y < rows; y++) {
      const lat = 90 - (y + 0.5) / rows * 180, p = lat * RAD, sp1 = Math.sin(p) * sd, cp = Math.cos(p) * cd;
      for (let x = 0; x < cols; x++) {
        const lon = (x + 0.5) / cols * 360 - 180;
        const alt = Math.asin(Math.max(-1, Math.min(1, sp1 + cp * Math.cos((lon - sp.lon) * RAD)))) * DEG;
        const c = shade(alt, { dayTint: !!(opts && opts.dayTint) });
        const i = (y * cols + x) * 4;
        buf[i] = c[0]; buf[i + 1] = c[1]; buf[i + 2] = c[2]; buf[i + 3] = c[3];
      }
    }
    return { rgba: buf, cols: cols, rows: rows, sub: sp };
  }
  // Flat map line where the sun's altitude equals altDeg: array of polylines of [x, y] in a w x h frame (scan each column).
  function flatLine(ms, altDeg, w, h, steps) {
    steps = steps || 180;
    const sp = subsolar(ms), out = [];
    let cur = [];
    for (let i = 0; i <= steps; i++) {
      const lon = -180 + 360 * i / steps;
      let prev = altitude(-90, lon, ms, sp) - altDeg, found = null;
      for (let lat = -89; lat <= 90; lat += 1) {
        const v = altitude(lat, lon, ms, sp) - altDeg;
        if ((prev < 0) !== (v < 0)) { found = lat - 1 + (0 - prev) / (v - prev); break; }
        prev = v;
      }
      if (found === null) { if (cur.length) { out.push(cur); cur = []; } continue; }
      cur.push([(lon + 180) / 360 * w, (90 - found) / 180 * h]);
    }
    if (cur.length) out.push(cur);
    return out;
  }

  const api = { HORIZON: HORIZON, BANDS: BANDS, solar: solar, subsolar: subsolar, altitude: altitude, riseSet: riseSet, hubSun: hubSun, hubCardText: hubCardText,
    darkness: darkness, shade: shade, flatBands: flatBands, flatLine: flatLine, fmtTime: fmtTime, fmtSpan: fmtSpan, localDate: localDate, utcDayStart: utcDayStart, wrap180: wrap180 };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Sun = api;
})(typeof window !== "undefined" ? window : this);
