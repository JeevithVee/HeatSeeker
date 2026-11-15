/* The tool. One map; the controls around it only change what the map shows.
   State lives in the URL (?city=&mode=&layer=&site=) so any view can be shared. */
(function () {
  'use strict';

  var HS = window.HS;
  var $ = function (id) { return document.getElementById(id); };
  var BASEMAP = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
  var BLANK_STYLE = { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#0a0f12' } }] };
  var NO_DATA = 'rgba(255,255,255,0.05)';
  var OUTCOMES = {
    detected_cooling: { label: 'Detected, cooler', color: '#5bc8f5' },
    detected_warming: { label: 'Detected, warmer', color: '#ff7a45' },
    inconclusive: { label: 'Inconclusive', color: '#7d8b88' },
    not_detectable: { label: 'Not detectable', color: '#4b5a57' }
  };
  /* Reading notes from the evaluation cross-review (MessageBoard, Agent 1 msg 6 and Agent 3 msg 9). */
  var CITY_NOTES = {
    nyc: 'New York: reliable cooling is not established. The pooled result is indistinguishable from zero under alternative specifications.',
    dc: 'Washington DC is planted almost everywhere, so few unplanted cells remain to compare against and they match poorly. Do not read its warmer contrasts as caused by planting.',
    sea: 'Seattle shows a negative association, not a causal estimate. Some of its comparison cells hold plantings with unknown dates.',
    sf: 'San Francisco has few heavily planted cells and its comparison cells match poorly. Nothing was detected.'
  };

  var S = { meta: null, city: null, mode: 'plan', layer: null, site: null, data: {}, detail: {}, logged: [], yearFrom: null, yearTo: null, map: null, ready: false, hoverId: null, selId: null };

  /* ---------- layers: what the map can be coloured by ---------- */
  var LAYERS = {
    priority: {
      mode: 'plan', name: 'Priority rank', ramp: 'amber',
      prep: function (c) { return { n: c.meta.candidates }; },
      t: function (p, k) { return p.rank == null ? null : 1 - (p.rank - 1) / Math.max(1, k.n - 1); },
      ends: function () { return ['Lower rank', 'Top rank']; },
      note: 'Predicted cooling × vulnerable residents ÷ cost. Cells outside the candidate rules are not ranked.',
      tip: function (p, k) { return p.rank == null ? 'Not a candidate' : 'Rank ' + p.rank + ' of ' + k.n; }
    },
    heat: {
      mode: 'plan', name: 'Surface heat', ramp: 'diverging',
      prep: function (c) { return { lim: Math.max(1, quantAbs(c, 'heat', 0.97)) }; },
      t: function (p, k) { return HS.divergeT(p.heat, k.lim); },
      ends: function (k) { return [HS.delta(-k.lim, 0), HS.delta(k.lim, 0)]; },
      mid: 'City median',
      note: function (c) { return 'Mean Landsat surface temperature against the city median, ' + c.meta.heat_scenes + ' clear summer scenes since ' + c.meta.heat_from_year + '.'; },
      tip: function (p) { return HS.hotter(p.heat) + (p.heat == null ? '' : ' than the city median'); }
    },
    vuln: {
      mode: 'plan', name: 'Vulnerable residents', ramp: 'violet',
      prep: function (c) { return { max: Math.max(1, quant(c, 'vuln', 0.97)) }; },
      t: function (p, k) { return p.vuln ? p.vuln / k.max : null; },
      ends: function (k) { return ['1', HS.int(k.max) + '+']; },
      note: 'Residents weighted by the share aged 65+ and the share on low incomes. Cells with none are left blank.',
      tip: function (p) { return HS.int(p.vuln || 0) + ' vulnerable residents'; }
    },
    canopy: {
      mode: 'plan', name: 'Tree canopy', ramp: 'green',
      prep: function () { return { max: 0.6 }; },
      t: function (p, k) { return p.canopy == null ? null : p.canopy / k.max; },
      ends: function () { return ['0%', '60%+']; },
      note: 'Share of the cell under tree canopy, Annual NLCD 2024.',
      tip: function (p) { return HS.pct(p.canopy) + ' tree canopy'; }
    },
    imperv: {
      mode: 'plan', name: 'Paved surface', ramp: 'slate',
      prep: function () { return { max: 1 }; },
      t: function (p) { return p.imperv; },
      ends: function () { return ['0%', '100%']; },
      note: 'Share of the cell that is roofs, roads and other sealed surface, Annual NLCD 2024.',
      tip: function (p) { return HS.pct(p.imperv) + ' paved'; }
    },
    planted: {
      mode: 'plant', name: 'Trees planted', ramp: 'teal',
      prep: function (c) {
        var vals = [];
        c.features.forEach(function (f) { var v = plantedInRange(c, f.properties.id); f.properties._pl = v; if (v > 0) vals.push(v); });
        vals.sort(function (a, b) { return a - b; });
        return { max: Math.max(5, HS.quantile(vals, 0.97) || 5) };
      },
      t: function (p, k) { return p._pl > 0 ? Math.max(0.12, p._pl / k.max) : null; },
      ends: function (k) { return ['1', HS.int(k.max) + '+']; },
      note: function () { return 'Dated plantings from the city tree inventory, ' + S.yearFrom + ' to ' + S.yearTo + '.'; },
      tip: function (p) { return HS.int(p._pl || 0) + (p._pl === 1 ? ' tree' : ' trees') + ' planted, ' + S.yearFrom + ' to ' + S.yearTo; }
    },
    effect: {
      mode: 'prove', name: 'Measured change', ramp: 'diverging',
      prep: function () { return { lim: 2 }; },
      t: function (p, k) { return HS.divergeT(p.eff, k.lim); },
      ends: function (k) { return [HS.delta(-k.lim, 1), HS.delta(k.lim, 1)]; },
      mid: 'No change',
      note: 'Change in surface temperature after planting, against matched unplanted cells. Only cells that reached 10 trees in 2015 to 2019 are measured.',
      tip: function (p) { return p.eff == null ? 'Not measured' : HS.delta(p.eff) + ' after planting, ' + OUTCOMES[p.outcome].label.toLowerCase(); }
    },
    outcome: {
      mode: 'prove', name: 'Result label', cats: true,
      prep: function () { return {}; },
      color: function (p) { return p.outcome ? OUTCOMES[p.outcome].color : null; },
      note: '"Detected" is a statistical label, not proof that planting caused the change.',
      tip: function (p) { return p.outcome ? OUTCOMES[p.outcome].label : 'Not measured'; }
    }
  };
  var MODE_LAYERS = { plan: ['priority', 'heat', 'vuln', 'canopy', 'imperv'], plant: ['planted'], prove: ['effect', 'outcome'] };

  function quant(c, key, q) {
    var v = c.features.map(function (f) { return f.properties[key]; }).filter(function (x) { return x != null && x > 0; }).sort(function (a, b) { return a - b; });
    return HS.quantile(v, q) || 0;
  }
  function quantAbs(c, key, q) {
    var v = c.features.map(function (f) { return f.properties[key]; }).filter(function (x) { return x != null; }).map(Math.abs).sort(function (a, b) { return a - b; });
    return HS.quantile(v, q) || 0;
  }
  function plantedInRange(c, id) {
    var by = c.detail.planted_by_year[id], total = 0, y;
    if (!by) return 0;
    for (y in by) if (+y >= S.yearFrom && +y <= S.yearTo) total += by[y];
    return total;
  }
  function cityMeta(id) { return S.meta.cities.filter(function (c) { return c.city_id === id; })[0]; }
  function cur() { return S.data[S.city]; }
  function featureOf(id) { return cur().byId[id]; }

  /* ---------- URL state ---------- */
  function readUrl() {
    var q = new URLSearchParams(location.search), ids = S.meta.cities.map(function (c) { return c.city_id; });
    S.city = ids.indexOf(q.get('city')) >= 0 ? q.get('city') : (S.meta.cities.filter(function (c) { return c.lead; })[0] || S.meta.cities[0]).city_id;
    S.mode = MODE_LAYERS[q.get('mode')] ? q.get('mode') : 'plan';
    S.layer = MODE_LAYERS[S.mode].indexOf(q.get('layer')) >= 0 ? q.get('layer') : MODE_LAYERS[S.mode][0];
    S.site = q.get('site');
  }
  function writeUrl() {
    var q = new URLSearchParams();
    q.set('city', S.city); q.set('mode', S.mode); q.set('layer', S.layer);
    if (S.site) q.set('site', S.site);
    history.replaceState(null, '', location.pathname + '?' + q.toString());
  }

  /* ---------- data ---------- */
  function loadCity(id) {
    if (S.data[id]) return Promise.resolve(S.data[id]);
    return Promise.all([HS.fetchJSON('data/' + id + '.geojson'), HS.fetchJSON('data/' + id + '_detail.json')]).then(function (r) {
      var byId = {};
      r[0].features.forEach(function (f) { byId[f.properties.id] = f; });
      S.data[id] = { meta: cityMeta(id), geojson: r[0], features: r[0].features, detail: r[1], byId: byId };
      return S.data[id];
    });
  }

  /* ---------- map ---------- */
  function initMap() {
    return fetch(BASEMAP).then(function (r) { if (!r.ok) throw new Error('basemap'); return r.json(); }).catch(function () { return BLANK_STYLE; }).then(function (style) {
      var m = cityMeta(S.city);
      S.map = new maplibregl.Map({ container: 'map', style: style, center: m.center, zoom: 10, attributionControl: false, dragRotate: false, pitchWithRotate: false, maxZoom: 16, minZoom: 8 });
      S.map.touchZoomRotate.disableRotation();
      S.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
      S.map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
      return new Promise(function (resolve) { S.map.on('load', resolve); });
    }).then(function () {
      var map = S.map, firstLabel = null;
      map.getStyle().layers.forEach(function (l) { if (!firstLabel && l.type === 'symbol') firstLabel = l.id; });
      map.addSource('cells', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({ id: 'cells-fill', type: 'fill', source: 'cells', paint: {
        'fill-color': ['coalesce', ['get', '_c'], NO_DATA],
        'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 1, ['has', '_c'], 0.82, 1]
      } }, firstLabel || undefined);
      map.addLayer({ id: 'cells-grid', type: 'line', source: 'cells', minzoom: 10.5, paint: { 'line-color': 'rgba(255,255,255,0.07)', 'line-width': 0.6 } }, firstLabel || undefined);
      map.addLayer({ id: 'cells-holdout', type: 'line', source: 'cells', filter: ['==', ['get', '_h'], 1], paint: { 'line-color': '#5bc8f5', 'line-width': 1.6, 'line-dasharray': [2, 1.5] } }, firstLabel || undefined);
      map.addLayer({ id: 'cells-logged', type: 'line', source: 'cells', filter: ['==', ['get', '_g'], 1], paint: { 'line-color': '#7be0a0', 'line-width': 2.5 } });
      map.addLayer({ id: 'cells-hover', type: 'line', source: 'cells', paint: { 'line-color': '#ecf2f0', 'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 3, ['boolean', ['feature-state', 'hover'], false], 1.5, 0] } });

      map.on('mousemove', 'cells-fill', onHover);
      map.on('mouseleave', 'cells-fill', function () { setHover(null); $('tip').hidden = true; map.getCanvas().style.cursor = ''; });
      map.on('click', 'cells-fill', function (e) { if (e.features.length) select(e.features[0].properties.id, false); });
      var attrib = document.querySelector('.maplibregl-ctrl-attrib');
      if (attrib) { attrib.classList.remove('maplibregl-compact-show'); attrib.removeAttribute('open'); }
      S.ready = true;
    });
  }

  function setHover(fid) {
    if (S.hoverId != null) S.map.setFeatureState({ source: 'cells', id: S.hoverId }, { hover: false });
    S.hoverId = fid;
    if (fid != null) S.map.setFeatureState({ source: 'cells', id: fid }, { hover: true });
  }

  function onHover(e) {
    if (!e.features.length) return;
    var f = e.features[0], p = featureOf(f.properties.id).properties, L = LAYERS[S.layer], tip = $('tip');
    S.map.getCanvas().style.cursor = 'pointer';
    setHover(f.id);
    tip.textContent = '';
    tip.appendChild(HS.el('b', { text: L.tip(p, cur().prep) }));
    tip.appendChild(HS.el('span', { text: 'Click for details' }));
    tip.hidden = false;
    var x = e.originalEvent.clientX + 14, y = e.originalEvent.clientY + 14;
    tip.style.left = Math.min(window.innerWidth - 270, x) + 'px';
    tip.style.top = Math.min(window.innerHeight - 70, y) + 'px';
  }

  /* Recolour every cell for the active layer and hand the data to the map. */
  function paint() {
    if (!S.ready) return;
    var c = cur(), L = LAYERS[S.layer], k = (c.prep = L.prep(c)), logged = {};
    S.logged.forEach(function (r) { if (r.city_id === S.city) logged[r.site_id] = 1; });
    c.features.forEach(function (f) {
      var p = f.properties, col = L.cats ? L.color(p) : HS.rampColor(HS.RAMPS[L.ramp], L.t(p, k));
      if (col) p._c = col; else delete p._c;
      p._h = S.mode === 'plan' && p.holdout ? 1 : 0;
      p._g = logged[p.id] ? 1 : 0;
    });
    S.map.getSource('cells').setData(c.geojson);
    S.hoverId = null; S.selId = null;
    if (S.site && c.byId[S.site]) { S.selId = c.byId[S.site].id; S.map.once('idle', markSelected); }
    renderLegend();
  }
  function markSelected() { if (S.selId != null) S.map.setFeatureState({ source: 'cells', id: S.selId }, { selected: true }); }

  /* ---------- legend ---------- */
  function renderLegend() {
    var c = cur(), L = LAYERS[S.layer], scale = $('legend-scale');
    $('legend-title').textContent = L.name + (S.layer === 'heat' || S.layer === 'effect' ? ', ' + HS.unitLabel() : '');
    scale.textContent = '';
    if (L.cats) {
      var ul = HS.el('ul', { class: 'legend-cats' });
      Object.keys(OUTCOMES).forEach(function (key) {
        var count = c.features.filter(function (f) { return f.properties.outcome === key; }).length;
        if (!count && key === 'not_detectable') return;
        var sw = HS.el('i'); sw.style.background = OUTCOMES[key].color;
        ul.appendChild(HS.el('li', {}, [sw, OUTCOMES[key].label + ': ' + HS.int(count)]));
      });
      scale.appendChild(ul);
    } else {
      var ramp = HS.el('div', { class: 'legend-ramp' }); ramp.style.background = HS.rampCss(HS.RAMPS[L.ramp]);
      var ends = L.ends(c.prep), labels = [HS.el('span', { text: ends[0] })];
      if (L.mid) labels.push(HS.el('span', { text: L.mid }));
      labels.push(HS.el('span', { text: ends[1] }));
      scale.appendChild(ramp); scale.appendChild(HS.el('div', { class: 'legend-ends' }, labels));
    }
    var note = typeof L.note === 'function' ? L.note(c) : L.note;
    if (S.mode === 'plan') note += ' Dashed outline: held back as a future control.';
    $('legend-note').textContent = note;
  }

  /* ---------- left panel ---------- */
  function renderPanel() {
    var c = cur(), m = c.meta;
    ['plan', 'plant', 'prove'].forEach(function (mode) { $('mode-' + mode).hidden = mode !== S.mode; });
    document.querySelectorAll('#modes button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.mode === S.mode)); });
    document.querySelectorAll('#cities button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.city === S.city)); });

    var opts = $('layer-options'); opts.textContent = '';
    MODE_LAYERS[S.mode].forEach(function (key) {
      var L = LAYERS[key], input = HS.el('input', { type: 'radio', name: 'layer', value: key }), sw = HS.el('i');
      input.checked = key === S.layer;
      sw.style.background = L.cats ? 'linear-gradient(90deg,#5bc8f5 0 33%,#7d8b88 33% 66%,#ff7a45 66%)' : HS.rampCss(HS.RAMPS[L.ramp]);
      input.addEventListener('change', function () { S.layer = key; writeUrl(); paint(); });
      opts.appendChild(HS.el('label', { class: 'layer' }, [input, HS.el('span', {}, [sw, L.name])]));
    });
    $('layers').hidden = MODE_LAYERS[S.mode].length < 2;

    if (S.mode === 'plan') {
      $('panel-title').textContent = 'Where to plant next';
      $('panel-sub').textContent = m.candidates
        ? HS.int(m.candidates) + ' candidate cells in ' + m.name + ', ranked by predicted cooling × vulnerable residents ÷ cost. ' + HS.int(m.holdouts) + ' are held back unplanted as future controls.'
        : 'No candidate cells in ' + m.name + ' under the current rules.';
      renderRanked();
    } else if (S.mode === 'plant') {
      $('panel-title').textContent = 'What has been planted';
      $('panel-sub').textContent = HS.int(m.trees_dated) + ' dated plantings in ' + m.name + ' from the city tree inventory, ' + m.plant_years[0] + ' to ' + m.plant_years[1] + '.';
      renderYears();
    } else {
      $('panel-title').textContent = 'Did past plantings cool anything?';
      $('panel-sub').textContent = HS.int(m.sites_evaluated) + ' cells in ' + m.name + ' reached 10 trees in ' + S.meta.treatment_window.join(' to ') + '. Each is compared with matched unplanted cells, before and after.';
      var stats = $('stats'); stats.textContent = '';
      [['Cells measured', m.sites_evaluated], ['Inconclusive', m.inconclusive], ['Detected, cooler', m.detected_cooling], ['Detected, warmer', m.detected_warming]].forEach(function (s) {
        stats.appendChild(HS.el('div', {}, [HS.el('dt', { text: s[0] }), HS.el('dd', { text: HS.int(s[1]) })]));
      });
      $('city-note').textContent = CITY_NOTES[S.city] + ' A single cell needs a change of about ' + Math.abs(HS.deltaValue(m.mde_median_k)).toFixed(1) + ' ' + HS.unitLabel() + ' to be detectable here.';
    }
  }

  function renderRanked() {
    var list = $('ranked'); list.textContent = '';
    var top = cur().features.filter(function (f) { return f.properties.rank != null; }).sort(function (a, b) { return a.properties.rank - b.properties.rank; }).slice(0, 12);
    top.forEach(function (f) {
      var p = f.properties, btn = HS.el('button', { type: 'button', 'aria-current': String(p.id === S.site) }, [
        HS.el('span', { class: 'rk', text: String(p.rank) }),
        HS.el('span', {}, [HS.el('span', { class: 'rt', text: (HS.INTERVENTION[p.kind] || p.kind) + (p.holdout ? ' · held back' : '') }), HS.el('span', { class: 'rs', text: HS.int(p.rec_vuln) + ' vulnerable residents' })]),
        HS.el('span', { class: 'rc', text: HS.usd(p.cost) })
      ]);
      btn.addEventListener('click', function () { select(p.id, true); });
      list.appendChild(HS.el('li', {}, [btn]));
    });
    if (!top.length) list.appendChild(HS.el('li', { class: 'hint', text: 'Nothing to rank here.' }));
  }

  function renderYears() {
    var m = cur().meta, from = $('year-from'), to = $('year-to'), y, bars = $('yearbars'), max = 0, total = 0;
    if (S.yearFrom == null || S.yearFrom < m.plant_years[0] || S.yearTo > m.plant_years[1]) { S.yearFrom = Math.max(m.plant_years[0], S.meta.treatment_window[0]); S.yearTo = m.plant_years[1]; }
    from.textContent = ''; to.textContent = ''; bars.textContent = '';
    for (y = m.plant_years[0]; y <= m.plant_years[1]; y++) {
      from.appendChild(HS.el('option', { value: y, text: String(y) })); to.appendChild(HS.el('option', { value: y, text: String(y) }));
      max = Math.max(max, m.planted_by_year[y] || 0);
    }
    from.value = S.yearFrom; to.value = S.yearTo;
    for (y = m.plant_years[0]; y <= m.plant_years[1]; y++) {
      var n = m.planted_by_year[y] || 0, bar = HS.el('i', { title: y + ': ' + HS.int(n) + ' trees' }), inside = y >= S.yearFrom && y <= S.yearTo;
      bar.style.height = Math.max(2, n / (max || 1) * 100) + '%';
      if (inside) { bar.className = 'in'; total += n; }
      bars.appendChild(bar);
    }
    var rt = $('range-total'); rt.textContent = '';
    rt.appendChild(HS.el('b', { text: HS.int(total) })); rt.appendChild(document.createTextNode(' trees planted from ' + S.yearFrom + ' to ' + S.yearTo + '.'));
    renderLogged();
  }

  function renderLogged() {
    var rows = S.logged.filter(function (r) { return r.city_id === S.city; }), list = $('logged');
    $('logged-wrap').hidden = !rows.length; list.textContent = '';
    rows.slice().reverse().forEach(function (r) {
      list.appendChild(HS.el('li', { text: r.planted_date + ': ' + HS.int(r.trees_planted) + ' × ' + (HS.INTERVENTION[r.intervention_type] || r.intervention_type) + ', cell ' + r.site_id }));
    });
  }

  /* ---------- right drawer ---------- */
  function sec(title, nodes) { return HS.el('div', { class: 'sec' }, [HS.el('h3', { text: title })].concat(nodes)); }
  function kv(pairs) {
    var dl = HS.el('dl', { class: 'kv' });
    pairs.forEach(function (p) { dl.appendChild(HS.el('dt', { text: p[0] })); dl.appendChild(HS.el('dd', { text: p[1] })); });
    return dl;
  }

  function renderDrawer() {
    var drawer = $('drawer'), body = $('drawer-body');
    document.body.classList.toggle('has-drawer', !!S.site);
    if (!S.site || !featureOf(S.site)) { drawer.hidden = true; return; }
    var c = cur(), p = featureOf(S.site).properties, m = c.meta;
    drawer.hidden = false; body.textContent = ''; body.scrollTop = 0;
    $('drawer-kicker').textContent = m.name + ' · cell';
    $('drawer-title').textContent = p.id;

    body.appendChild(sec('This block', [
      HS.el('p', { class: 'lead' }, [HS.el('b', { text: HS.hotter(p.heat) }), p.heat == null ? 'No clear recent scene for this cell.' : 'than the city median surface temperature, summer mornings since ' + m.heat_from_year + '.']),
      HS.el('div', { style: 'height:12px' }),
      kv([['Tree canopy', HS.pct(p.canopy)], ['Paved surface', HS.pct(p.imperv)], ['Residents', HS.int(p.pop)], ['Vulnerable residents', HS.int(p.vuln)], ['Trees in the inventory', HS.int(p.trees)], ['Land cover', HS.LAND_COVER[p.lc] || p.lc], ['Elevation', p.elev == null ? 'n/a' : HS.int(p.elev) + ' m']])
    ]));

    if (p.rank != null) {
      var lim = Math.max(1.5, Math.abs(p.c15lo), Math.abs(p.c15hi), Math.abs(p.c5lo), Math.abs(p.c5hi));
      body.appendChild(sec('Recommendation', [
        kv([['Rank in ' + m.name, p.rank + ' of ' + m.candidates], ['Suggested', HS.INTERVENTION[p.kind] || p.kind], ['Estimated cost', HS.usd(p.cost)]]),
        HS.rangeBar('After ' + S.meta.horizons_years[0] + ' years', -p.c5, -p.c5hi, -p.c5lo, lim),
        HS.rangeBar('After ' + S.meta.horizons_years[1] + ' years', -p.c15, -p.c15hi, -p.c15lo, lim),
        HS.el('div', { class: 'rangebar-axis' }, [HS.el('span', { text: 'Cooler' }), HS.el('span', { text: 'No change' }), HS.el('span', { text: 'Warmer' })]),
        HS.el('p', { class: 'small', text: 'Model prediction of surface temperature change, not a measurement. ' + (p.c15lo < 0 ? 'The range crosses zero, so the model cannot rule out no cooling here.' : '') + (p.holdout ? ' This cell is held back unplanted so it can serve as a control.' : '') })
      ]));
    }

    var by = c.detail.planted_by_year[p.id] || {}, years = m.plant_years, bars = HS.el('div', { class: 'minibars', role: 'img', 'aria-label': 'Trees planted in this cell per year' }), maxY = 0, y;
    for (y = years[0]; y <= years[1]; y++) maxY = Math.max(maxY, by[y] || 0);
    for (y = years[0]; y <= years[1]; y++) {
      var b = HS.el('i', { title: y + ': ' + (by[y] || 0) }); if (by[y]) b.style.height = Math.max(8, by[y] / maxY * 100) + '%'; else b.className = 'zero';
      bars.appendChild(b);
    }
    var plantNodes = [HS.el('p', { class: 'lead' }, [HS.el('b', { text: HS.int(p.planted) + (p.planted === 1 ? ' tree' : ' trees') }), 'with a planting date on record, ' + HS.int(p.planted_w) + ' of them in ' + S.meta.treatment_window.join(' to ') + '.'])];
    if (p.planted) { plantNodes.push(bars); plantNodes.push(HS.el('div', { class: 'minibars-axis' }, [HS.el('span', { text: String(years[0]) }), HS.el('span', { text: String(years[1]) })])); }
    plantNodes.push(plantForm(p));
    body.appendChild(sec('Plantings', plantNodes));

    if (p.eff != null) {
      var o = OUTCOMES[p.outcome], dot = HS.el('i'); dot.style.background = o.color;
      var rows = c.detail.series[p.id] || [];
      body.appendChild(sec('Measured result', [
        HS.el('span', { class: 'chip' }, [dot, o.label]),
        HS.el('div', { style: 'height:12px' }),
        kv([['Change after planting', HS.delta(p.eff)], ['Uncertainty interval', HS.delta(p.eff_lo) + ' to ' + HS.delta(p.eff_hi)], ['Smallest detectable change', '±' + Math.abs(HS.deltaValue(p.mde)).toFixed(1) + ' ' + HS.unitLabel()], ['Trees, 2015 to 2019', HS.int(p.dose)], ['Reached 10 trees in', String(p.t_year)], ['Scenes before / after', p.n_pre + ' / ' + p.n_post], ['Matched control cells', String(p.n_ctrl)]]),
        HS.seriesChart(rows, p.t_year),
        HS.el('p', { class: 'small', text: p.label === 'detected' ? 'A statistical label, not proof that planting caused this change.' : 'The change is smaller than this method can separate from noise at 30 m.' }),
        HS.el('p', { class: 'caveat', style: 'margin-top:12px', text: 'Surface temperature from satellite, late morning. Not the air temperature people feel.' })
      ]));
    } else {
      body.appendChild(sec('Measured result', [HS.el('p', { class: 'small', style: 'margin-top:0', text: 'Not measured. Only cells that reached 10 dated trees in ' + S.meta.treatment_window.join(' to ') + ' are compared against controls.' })]));
    }
  }

  function plantForm(p) {
    var now = new Date(), costs = S.meta.costs_usd;
    /* the local calendar day, not the UTC one */
    var today = now.getFullYear() + '-' + ('0' + (now.getMonth() + 1)).slice(-2) + '-' + ('0' + now.getDate()).slice(-2);
    var type = HS.el('select', { name: 'intervention_type', id: 'f-type' });
    Object.keys(costs).forEach(function (k) { type.appendChild(HS.el('option', { value: k, text: HS.INTERVENTION[k] || k })); });
    if (p.kind && costs[p.kind] != null) type.value = p.kind;
    var date = HS.el('input', { type: 'date', name: 'planted_date', id: 'f-date', value: today, max: today, required: '' });
    var trees = HS.el('input', { type: 'number', name: 'trees_planted', id: 'f-trees', min: 1, max: 5000, step: 1, value: 10, required: '', inputmode: 'numeric' });
    var cost = HS.el('input', { type: 'number', name: 'cost_usd', id: 'f-cost', min: 0, step: 100, value: costs[type.value], inputmode: 'numeric' });
    var err = HS.el('p', { class: 'err', role: 'alert' });
    var submit = HS.el('button', { type: 'submit', class: 'btn btn-primary btn-small', text: 'Log this planting' });
    type.addEventListener('change', function () { cost.value = costs[type.value]; });
    var form = HS.el('form', { class: 'form', novalidate: '' }, [
      HS.el('div', { class: 'two' }, [HS.el('label', { for: 'f-date' }, ['Date planted', date]), HS.el('label', { for: 'f-trees' }, ['Trees', trees])]),
      HS.el('div', { class: 'two' }, [HS.el('label', { for: 'f-type' }, ['Type', type]), HS.el('label', { for: 'f-cost' }, ['Cost, USD', cost])]),
      err, submit
    ]);
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var n = Number(trees.value);
      err.textContent = '';
      if (!date.value) { err.textContent = 'Enter the date of the planting.'; date.focus(); return; }
      if (date.value > today) { err.textContent = 'The date cannot be in the future.'; date.focus(); return; }
      if (!Number.isInteger(n) || n < 1 || n > 5000) { err.textContent = 'Enter a whole number of trees between 1 and 5,000.'; trees.focus(); return; }
      submit.disabled = true; submit.textContent = 'Saving';
      fetch('api/plantings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ city_id: S.city, site_id: p.id, planted_date: date.value, intervention_type: type.value, trees_planted: n, cost_usd: cost.value === '' ? null : Number(cost.value) }) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'The planting could not be saved.'); return j; }); })
        .then(function (row) {
          S.logged.push(row); submit.disabled = false; submit.textContent = 'Log this planting';
          toast('Logged ' + HS.int(row.trees_planted) + ' trees. It joins the next evaluation cycle.');
          paint(); if (S.mode === 'plant') renderLogged();
        })
        .catch(function (ex) { err.textContent = ex.message; submit.disabled = false; submit.textContent = 'Log this planting'; });
    });
    return HS.el('details', { class: 'table' }, [HS.el('summary', { text: 'Log a new planting in this cell' }), form]);
  }

  var toastTimer = 0;
  function toast(text) {
    var t = $('toast'); t.textContent = text; t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { t.hidden = true; }, 3800);
  }

  /* ---------- actions ---------- */
  function select(id, fly) {
    if (S.selId != null) S.map.setFeatureState({ source: 'cells', id: S.selId }, { selected: false });
    S.site = id;
    var f = id ? featureOf(id) : null;
    S.selId = f ? f.id : null;
    markSelected();
    writeUrl(); renderDrawer();
    if (S.mode === 'plan') renderRanked();
    if (f && fly) {
      var ring = f.geometry.coordinates[0], lon = 0, lat = 0;
      ring.slice(0, -1).forEach(function (pt) { lon += pt[0]; lat += pt[1]; });
      var pad = mapPadding();
      S.map.easeTo({ center: [lon / (ring.length - 1), lat / (ring.length - 1)], zoom: Math.max(S.map.getZoom(), 13.2), duration: HS.reducedMotion ? 0 : 900, offset: [(pad.left - pad.right) / 2, (pad.top - pad.bottom) / 2] });
    }
    if (f && window.gsap && !HS.reducedMotion) gsap.fromTo('#drawer', { x: 24, opacity: 0 }, { x: 0, opacity: 1, duration: 0.3, ease: 'power2.out', overwrite: true });
  }

  function mapPadding() {
    var wide = window.innerWidth > 860;
    return wide ? { top: 90, bottom: 30, left: 380, right: S.site ? 410 : 30 } : { top: 130, bottom: window.innerHeight * 0.45, left: 16, right: 16 };
  }

  function setMode(mode) {
    S.mode = mode;
    if (MODE_LAYERS[mode].indexOf(S.layer) < 0) S.layer = MODE_LAYERS[mode][0];
    writeUrl(); renderPanel(); paint(); renderDrawer();
    if (window.gsap && !HS.reducedMotion) gsap.fromTo('#panel-body > *', { y: 10, opacity: 0 }, { y: 0, opacity: 1, duration: 0.3, stagger: 0.03, ease: 'power2.out', overwrite: true });
  }

  function setCity(id, keepSite) {
    S.city = id;
    if (!keepSite) S.site = null;
    document.querySelectorAll('#cities button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.city === id)); });
    return loadCity(id).then(function (c) {
      if (S.city !== id) return;
      var b = c.meta.bounds;
      S.map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: mapPadding(), duration: HS.reducedMotion || keepSite ? 0 : 1400 });
      S.yearFrom = null;
      writeUrl(); renderPanel(); paint(); renderDrawer();
    });
  }

  /* ---------- start ---------- */
  HS.fetchJSON('data/meta.json').then(function (meta) {
    S.meta = meta; HS.unit = meta.display.temperature_unit;
    readUrl();
    var holder = $('cities');
    meta.cities.forEach(function (c) {
      var b = HS.el('button', { type: 'button', 'data-city': c.city_id, 'aria-pressed': String(c.city_id === S.city), text: c.name });
      b.addEventListener('click', function () { if (c.city_id !== S.city) setCity(c.city_id, false); });
      holder.appendChild(b);
    });
    document.querySelectorAll('#modes button').forEach(function (b) { b.addEventListener('click', function () { setMode(b.dataset.mode); }); });
    $('drawer-close').addEventListener('click', function () { select(null, false); });
    $('year-from').addEventListener('change', onYears); $('year-to').addEventListener('change', onYears);
    $('panel-toggle').addEventListener('click', function () {
      var collapsed = $('panel').classList.toggle('is-collapsed');
      this.setAttribute('aria-expanded', String(!collapsed)); $('panel-toggle-text').textContent = collapsed ? 'Show controls' : 'Hide controls';
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && S.site) select(null, false); });

    fetch('api/plantings').then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; }).then(function (rows) { S.logged = rows; if (S.ready && cur()) { paint(); if (S.mode === 'plant') renderLogged(); } });
    return Promise.all([initMap(), loadCity(S.city)]);
  }).then(function () {
    return setCity(S.city, true);
  }).catch(function (err) {
    $('panel-title').textContent = 'The tool could not load';
    $('panel-sub').textContent = 'The data files did not arrive. Reload the page, or check that the server is running.';
    if (window.console) console.error(err);
  });

  function onYears() {
    var a = +$('year-from').value, b = +$('year-to').value;
    S.yearFrom = Math.min(a, b); S.yearTo = Math.max(a, b);
    renderYears(); paint();
  }
})();
