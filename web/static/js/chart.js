/* One small chart: a planted cell against its matched controls, by summer.
   Two lines on one axis, direct labels, a marker for the planting year, a
   crosshair tooltip and a table of the same numbers. */
(function () {
  'use strict';
  var HS = window.HS;
  var NS = 'http://www.w3.org/2000/svg';
  var SITE = '#5bc8f5', CTRL = '#b9c4c1';

  function svg(tag, attrs) {
    var n = document.createElementNS(NS, tag), k;
    for (k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }

  /* rows: [[year, siteRelK, controlRelK, scenes], ...]; plantYear: number */
  HS.seriesChart = function (rows, plantYear) {
    var W = 340, H = 190, m = { l: 38, r: 12, t: 14, b: 24 };
    var wrap = HS.el('div', { class: 'chart' });
    var vals = [];
    rows.forEach(function (r) { if (r[1] != null) vals.push(HS.deltaValue(r[1])); if (r[2] != null) vals.push(HS.deltaValue(r[2])); });
    if (rows.length < 2 || !vals.length) { wrap.appendChild(HS.el('p', { class: 'small', text: 'Not enough clear scenes to draw this cell.' })); return wrap; }
    var lo = Math.min.apply(null, vals.concat([0])), hi = Math.max.apply(null, vals.concat([0]));
    var pad = Math.max(0.5, (hi - lo) * 0.12); lo -= pad; hi += pad;
    var y0 = rows[0][0], y1 = rows[rows.length - 1][0];
    function x(year) { return m.l + (year - y0) / Math.max(1, y1 - y0) * (W - m.l - m.r); }
    function y(v) { return m.t + (hi - v) / (hi - lo) * (H - m.t - m.b); }

    var root = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': 'Summer surface temperature of this cell and of its matched controls, relative to the city, by year' });

    /* recessive grid: three ticks */
    var step = (hi - lo) > 8 ? 4 : (hi - lo) > 4 ? 2 : 1, t;
    for (t = Math.ceil(lo / step) * step; t <= hi; t += step) {
      root.appendChild(svg('line', { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), stroke: t === 0 ? 'rgba(255,255,255,0.32)' : 'rgba(255,255,255,0.09)', 'stroke-width': 1 }));
      var lab = svg('text', { x: m.l - 6, y: y(t) + 4, 'text-anchor': 'end', 'font-size': 11, fill: '#8c9c98', 'font-family': 'IBM Plex Mono, monospace' });
      lab.textContent = (t > 0 ? '+' : t < 0 ? '−' : '') + Math.abs(t);
      root.appendChild(lab);
    }
    [y0, y1].forEach(function (yr, i) {
      var tx = svg('text', { x: x(yr), y: H - 6, 'text-anchor': i ? 'end' : 'start', 'font-size': 11, fill: '#8c9c98', 'font-family': 'IBM Plex Mono, monospace' });
      tx.textContent = yr; root.appendChild(tx);
    });

    if (plantYear && plantYear >= y0 && plantYear <= y1) {
      root.appendChild(svg('rect', { x: x(plantYear), y: m.t, width: W - m.r - x(plantYear), height: H - m.t - m.b, fill: 'rgba(255,255,255,0.045)' }));
      root.appendChild(svg('line', { x1: x(plantYear), x2: x(plantYear), y1: m.t, y2: H - m.b, stroke: '#ecf2f0', 'stroke-width': 1, 'stroke-dasharray': '4 4' }));
      var pl = svg('text', { x: x(plantYear) + 5, y: m.t + 10, 'font-size': 11, fill: '#ecf2f0' });
      pl.textContent = 'Planted ' + plantYear; root.appendChild(pl);
    }

    function line(idx, color, width) {
      var d = '', started = false;
      rows.forEach(function (r) {
        if (r[idx] == null) return;
        d += (started ? 'L' : 'M') + x(r[0]).toFixed(1) + ' ' + y(HS.deltaValue(r[idx])).toFixed(1) + ' ';
        started = true;
      });
      root.appendChild(svg('path', { d: d, fill: 'none', stroke: color, 'stroke-width': width, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
    }
    line(2, CTRL, 2);
    line(1, SITE, 2.5);

    var cross = svg('line', { y1: m.t, y2: H - m.b, stroke: 'rgba(255,255,255,0.5)', 'stroke-width': 1, visibility: 'hidden' });
    var dotA = svg('circle', { r: 4.5, fill: SITE, stroke: '#111a1e', 'stroke-width': 2, visibility: 'hidden' });
    var dotB = svg('circle', { r: 4.5, fill: CTRL, stroke: '#111a1e', 'stroke-width': 2, visibility: 'hidden' });
    root.appendChild(cross); root.appendChild(dotB); root.appendChild(dotA);
    var hit = svg('rect', { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent' });
    root.appendChild(hit);
    wrap.appendChild(root);

    var tip = HS.el('div', { class: 'chart-tip', hidden: '' });
    wrap.appendChild(tip);
    function show(e) {
      var box = root.getBoundingClientRect(), px = (e.clientX - box.left) / box.width * W, best = rows[0], bd = Infinity;
      rows.forEach(function (r) { var d = Math.abs(x(r[0]) - px); if (d < bd) { bd = d; best = r; } });
      var cx = x(best[0]);
      cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.setAttribute('visibility', 'visible');
      [[dotA, 1], [dotB, 2]].forEach(function (p) {
        if (best[p[1]] == null) { p[0].setAttribute('visibility', 'hidden'); return; }
        p[0].setAttribute('cx', cx); p[0].setAttribute('cy', y(HS.deltaValue(best[p[1]]))); p[0].setAttribute('visibility', 'visible');
      });
      tip.hidden = false;
      tip.textContent = '';
      tip.appendChild(HS.el('b', { text: 'Summer ' + best[0] }));
      tip.appendChild(HS.el('div', { text: 'This cell ' + HS.delta(best[1]) }));
      tip.appendChild(HS.el('div', { text: 'Controls ' + HS.delta(best[2]) }));
      tip.appendChild(HS.el('div', { text: best[3] + (best[3] === 1 ? ' scene' : ' scenes') }));
      var left = cx / W * box.width;
      tip.style.left = Math.max(0, Math.min(box.width - 150, left + (left > box.width / 2 ? -150 : 12))) + 'px';
    }
    function hide() { tip.hidden = true; [cross, dotA, dotB].forEach(function (n) { n.setAttribute('visibility', 'hidden'); }); }
    hit.addEventListener('pointermove', show);
    hit.addEventListener('pointerleave', hide);

    var legend = HS.el('div', { class: 'chart-legend' });
    [['This cell', SITE], ['Mean of matched controls', CTRL]].forEach(function (p) {
      var i = HS.el('i'); i.style.background = p[1];
      legend.appendChild(HS.el('span', {}, [i, p[0]]));
    });
    wrap.appendChild(legend);
    wrap.appendChild(HS.el('p', { class: 'small', text: 'Yearly mean of clear summer scenes, in ' + HS.unitLabel() + ' relative to the city on the same day. Zero is the city baseline.' }));

    var table = HS.el('table'), head = HS.el('thead', {}, [HS.el('tr', {}, ['Summer', 'This cell', 'Controls', 'Scenes'].map(function (h) { return HS.el('th', { scope: 'col', text: h }); }))]);
    var body = HS.el('tbody');
    rows.forEach(function (r) { body.appendChild(HS.el('tr', {}, [HS.el('td', { text: String(r[0]) }), HS.el('td', { text: HS.delta(r[1]) }), HS.el('td', { text: HS.delta(r[2]) }), HS.el('td', { text: String(r[3]) })])); });
    table.appendChild(head); table.appendChild(body);
    wrap.appendChild(HS.el('details', { class: 'table' }, [HS.el('summary', { text: 'Show these numbers as a table' }), table]));
    return wrap;
  };

  /* A predicted temperature CHANGE with its range, on a shared scale.
     Negative (left) is cooler. All three arguments are changes in Kelvin. */
  HS.rangeBar = function (label, mid, lo, hi, limitK) {
    function pos(k) { return (0.5 + Math.max(-1, Math.min(1, k / limitK)) / 2) * 100; }
    var track = HS.el('div', { class: 'rangebar-track', 'aria-hidden': 'true' });
    var span = HS.el('div', { class: 'span' }); span.style.left = pos(lo) + '%'; span.style.width = Math.max(1, pos(hi) - pos(lo)) + '%';
    var zero = HS.el('div', { class: 'zero' }); zero.style.left = 'calc(50% - 1px)';
    var dot = HS.el('div', { class: 'dot' }); dot.style.left = pos(mid) + '%';
    track.appendChild(span); track.appendChild(zero); track.appendChild(dot);
    return HS.el('div', { class: 'rangebar' }, [
      HS.el('div', { class: 'rangebar-head' }, [HS.el('span', { text: label + ': ' + HS.delta(mid) }), HS.el('span', { text: HS.delta(lo) + ' to ' + HS.delta(hi) })]),
      track
    ]);
  };
})();
