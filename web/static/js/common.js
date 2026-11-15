/* Shared by the landing page and the tool: units, number formats, colour ramps.
   Storage is Kelvin and fractions; conversion to display units happens here only. */
(function () {
  'use strict';

  var HS = (window.HS = window.HS || {});

  HS.reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  HS.fetchJSON = function (url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error(url + ' ' + r.status);
      return r.json();
    });
  };

  var nf0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
  HS.int = function (n) { return n == null ? 'n/a' : nf0.format(Math.round(n)); };
  HS.pct = function (frac) { return frac == null ? 'n/a' : Math.round(frac * 100) + '%'; };
  HS.usd = function (n) { return n == null ? 'n/a' : '$' + nf0.format(Math.round(n)); };
  HS.compact = function (n) {
    if (n == null) return 'n/a';
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, '') + 'M';
    if (n >= 1e4) return Math.round(n / 1e3) + 'k';
    return nf0.format(n);
  };

  /* A temperature DIFFERENCE in Kelvin, shown in the configured unit. */
  HS.unit = 'fahrenheit';
  HS.deltaValue = function (k) { return HS.unit === 'fahrenheit' ? k * 1.8 : k; };
  HS.unitLabel = function () { return HS.unit === 'fahrenheit' ? '°F' : '°C'; };
  HS.delta = function (k, digits) {
    if (k == null) return 'n/a';
    var v = HS.deltaValue(k), d = digits == null ? 1 : digits;
    var s = Math.abs(v).toFixed(d);
    if (Number(s) === 0) return '0' + (d ? '.' + '0'.repeat(d) : '') + ' ' + HS.unitLabel();
    return (v < 0 ? '−' : '+') + s + ' ' + HS.unitLabel();
  };
  /* "2.3 °F hotter" / "1.1 °F cooler" for a difference where positive means hotter. */
  HS.hotter = function (k) {
    if (k == null) return 'No clear reading';
    var v = HS.deltaValue(k), s = Math.abs(v).toFixed(1);
    if (Number(s) === 0) return 'At the city median';
    return s + ' ' + HS.unitLabel() + (v > 0 ? ' hotter' : ' cooler');
  };

  /* ---- Colour ramps -------------------------------------------------------
     Sequential ramps are one hue; on this dark surface a larger value is
     lighter. Diverging ramps use two hues around a neutral grey midpoint. */
  function hexToRgb(h) { return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)]; }
  function rgbToHex(c) { return '#' + c.map(function (x) { return ('0' + Math.round(x).toString(16)).slice(-2); }).join(''); }

  HS.RAMPS = {
    diverging: ['#4db2ff', '#2f77b8', '#2b4a63', '#3d4649', '#6b4030', '#c05a2c', '#ff7a45'],
    amber: ['#3a2a15', '#70470f', '#b06e10', '#e9a23a', '#ffdf9e'],
    green: ['#15301f', '#2a6340', '#4aa565', '#8adf9c', '#d3f8d9'],
    slate: ['#1d252e', '#3c4b60', '#667b99', '#9db0cf', '#dbe5f6'],
    violet: ['#231b3b', '#4a3a86', '#7c63cf', '#b29cf2', '#e3d9ff'],
    teal: ['#0f2c2c', '#1b5f5c', '#2f9d95', '#6fd6cb', '#c2f6ee']
  };

  /* value in [0,1] -> colour along the ramp's stops */
  HS.rampColor = function (stops, t) {
    if (t == null || isNaN(t)) return null;
    t = Math.max(0, Math.min(1, t));
    var x = t * (stops.length - 1), i = Math.min(stops.length - 2, Math.floor(x)), f = x - i;
    var a = hexToRgb(stops[i]), b = hexToRgb(stops[i + 1]);
    return rgbToHex([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]);
  };
  HS.rampCss = function (stops) { return 'linear-gradient(90deg,' + stops.join(',') + ')'; };

  /* symmetric diverging scale: -limit..+limit -> 0..1 */
  HS.divergeT = function (v, limit) { return v == null ? null : 0.5 + Math.max(-1, Math.min(1, v / limit)) / 2; };

  HS.quantile = function (sorted, q) {
    if (!sorted.length) return null;
    var p = (sorted.length - 1) * q, lo = Math.floor(p), hi = Math.ceil(p);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (p - lo);
  };

  HS.LAND_COVER = {
    developed_open_space: 'Developed, open space', developed_low_intensity: 'Developed, low intensity',
    developed_medium_intensity: 'Developed, medium intensity', developed_high_intensity: 'Developed, high intensity',
    deciduous_forest: 'Deciduous forest', evergreen_forest: 'Evergreen forest', mixed_forest: 'Mixed forest',
    open_water: 'Open water', woody_wetlands: 'Woody wetlands', emergent_herbaceous_wetlands: 'Herbaceous wetlands',
    grassland_herbaceous: 'Grassland', pasture_hay: 'Pasture', barren: 'Barren land', shrub_scrub: 'Shrub',
    cultivated_crops: 'Cropland'
  };
  HS.INTERVENTION = { street_trees: 'Street trees', park_trees: 'Park trees', cool_roof: 'Cool roof', cool_pavement: 'Cool pavement', tree_planting: 'Tree planting' };

  HS.el = function (tag, attrs, children) {
    var n = document.createElement(tag), k;
    for (k in attrs || {}) {
      if (k === 'text') n.textContent = attrs[k];
      else if (k === 'class') n.className = attrs[k];
      else n.setAttribute(k, attrs[k]);
    }
    (children || []).forEach(function (c) { n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  };
})();
