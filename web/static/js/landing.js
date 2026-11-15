/* Landing page: the live heat field behind the hero, the pinned loop, count-ups.
   Everything shown is read from static/data; nothing is typed in by hand. */
(function () {
  'use strict';

  var HS = window.HS;
  var canvas = document.getElementById('heat-field');
  var ctx = canvas.getContext('2d');
  var state = { city: null, cells: [], reveal: 0, pointer: null, hover: -1, meta: null, cache: {}, w: 0, h: 0, r: 4, dpr: 1 };
  var HEAT_LIMIT_K = 6;

  /* ---------- heat field ---------- */
  function resize() {
    var rect = canvas.getBoundingClientRect();
    state.dpr = Math.min(window.devicePixelRatio || 1, 2);
    state.w = rect.width; state.h = rect.height;
    canvas.width = Math.round(rect.width * state.dpr);
    canvas.height = Math.round(rect.height * state.dpr);
    layout();
  }

  /* Project lon/lat to the canvas, keeping the city to the right of the copy on wide screens. */
  function layout() {
    var raw = state.cache[state.city];
    if (!raw) return;
    var wide = state.w > 900;
    var box = wide
      ? { x: state.w * 0.52, y: state.h * 0.11, w: state.w * 0.44, h: state.h * 0.62 }
      : { x: state.w * 0.08, y: 76, w: state.w * 0.84, h: Math.max(140, state.h * 0.4 - 124) };
    var minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity, i;
    for (i = 0; i < raw.length; i++) {
      if (raw[i][0] < minLon) minLon = raw[i][0]; if (raw[i][0] > maxLon) maxLon = raw[i][0];
      if (raw[i][1] < minLat) minLat = raw[i][1]; if (raw[i][1] > maxLat) maxLat = raw[i][1];
    }
    var kx = Math.cos(((minLat + maxLat) / 2) * Math.PI / 180);
    var spanX = (maxLon - minLon) * kx, spanY = maxLat - minLat;
    var scale = Math.min(box.w / spanX, box.h / spanY);
    var offX = box.x + (box.w - spanX * scale) / 2, offY = box.y + (box.h - spanY * scale) / 2;
    var cx = offX + spanX * scale / 2, cy = offY + spanY * scale / 2, maxD = 0;
    state.cells = raw.map(function (c) {
      var x = offX + (c[0] - minLon) * kx * scale, y = offY + (maxLat - c[1]) * scale;
      var d = Math.hypot(x - cx, y - cy);
      if (d > maxD) maxD = d;
      return { x: x, y: y, heat: c[2], d: d, color: HS.rampColor(HS.RAMPS.diverging, HS.divergeT(c[2], HEAT_LIMIT_K)) || '#2a3337' };
    });
    state.cells.forEach(function (c) { c.d = c.d / (maxD || 1); });
    /* A res-9 hexagon has a circumradius of about 0.0016 degrees of latitude. */
    state.r = Math.max(1.6, 0.0016 * scale);
    draw();
  }

  function hexPath(x, y, r) {
    ctx.moveTo(x, y - r);
    ctx.lineTo(x + r * 0.866, y - r * 0.5);
    ctx.lineTo(x + r * 0.866, y + r * 0.5);
    ctx.lineTo(x, y + r);
    ctx.lineTo(x - r * 0.866, y + r * 0.5);
    ctx.lineTo(x - r * 0.866, y - r * 0.5);
    ctx.closePath();
  }

  function draw() {
    var dpr = state.dpr, p = state.reveal, ptr = state.pointer, cells = state.cells, i, c, a, near;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, state.w, state.h);
    var reach = Math.max(70, state.r * 9);
    for (i = 0; i < cells.length; i++) {
      c = cells[i];
      a = Math.max(0, Math.min(1, (p * 1.5 - c.d) * 3));
      if (a <= 0) continue;
      near = ptr ? Math.max(0, 1 - Math.hypot(c.x - ptr.x, c.y - ptr.y) / reach) : 0;
      ctx.globalAlpha = a * (0.62 + 0.38 * near);
      ctx.fillStyle = c.color;
      ctx.beginPath();
      hexPath(c.x, c.y, state.r * (0.92 + 0.5 * near * near));
      ctx.fill();
    }
    if (state.hover >= 0 && cells[state.hover]) {
      c = cells[state.hover];
      ctx.globalAlpha = 1; ctx.lineWidth = 2; ctx.strokeStyle = '#ecf2f0';
      ctx.beginPath(); hexPath(c.x, c.y, state.r * 1.7); ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  function nearest(x, y) {
    var best = -1, bd = Math.pow(Math.max(18, state.r * 3), 2), i, c, d;
    for (i = 0; i < state.cells.length; i++) {
      c = state.cells[i]; d = (c.x - x) * (c.x - x) + (c.y - y) * (c.y - y);
      if (d < bd) { bd = d; best = i; }
    }
    return best;
  }

  var raf = 0;
  function requestDraw() { if (!raf) raf = requestAnimationFrame(function () { raf = 0; draw(); }); }

  function onPointer(e) {
    var rect = canvas.getBoundingClientRect();
    var x = e.clientX - rect.left, y = e.clientY - rect.top;
    state.pointer = { x: x, y: y };
    state.hover = nearest(x, y);
    var city = cityMeta(state.city), label = document.getElementById('readout-label'), value = document.getElementById('readout-value');
    if (state.hover >= 0) {
      label.textContent = city.name + ', one cell';
      value.textContent = HS.hotter(state.cells[state.hover].heat) + (state.cells[state.hover].heat == null ? '' : ' than the city median');
    } else {
      label.textContent = city.name + ': summer surface heat, cell by cell';
      value.textContent = 'Move over the map';
    }
    requestDraw();
  }

  function cityMeta(id) { return state.meta.cities.filter(function (c) { return c.city_id === id; })[0]; }

  function showCity(id) {
    var load = state.cache[id] ? Promise.resolve(state.cache[id]) : HS.fetchJSON('data/' + id + '_hero.json');
    document.querySelectorAll('#hero-cities button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.city === id)); });
    return load.then(function (rows) {
      state.cache[id] = rows; state.city = id; state.hover = -1;
      var city = cityMeta(id);
      document.getElementById('readout-label').textContent = city.name + ': summer surface heat, cell by cell';
      document.getElementById('readout-value').textContent = 'Move over the map';
      document.getElementById('readout-note').textContent = 'Mean of ' + city.heat_scenes + ' clear Landsat scenes since ' + city.heat_from_year + ', against the city median. Each hexagon is about 26 acres.';
      state.reveal = 0;
      layout();
      if (HS.reducedMotion || !window.gsap) { state.reveal = 1; draw(); return; }
      gsap.killTweensOf(state);
      gsap.to(state, { reveal: 1, duration: 1.6, ease: 'power2.out', onUpdate: draw });
    });
  }

  /* ---------- numbers ---------- */
  function totals(meta) {
    function sum(key) { return meta.cities.reduce(function (a, c) { return a + (c[key] || 0); }, 0); }
    var years = meta.cities.reduce(function (a, c) { return [Math.min(a[0], c.panel_years[0]), Math.max(a[1], c.panel_years[1])]; }, [9999, 0]);
    return {
      cities: meta.cities.length, cells: sum('cells'), rows: sum('panel_rows'), candidates: sum('candidates'),
      trees: sum('trees_dated'), evaluated: sum('sites_evaluated'), inconclusive: sum('inconclusive'),
      detected: sum('detected'), cooling: sum('detected_cooling'), warming: sum('detected_warming'),
      scenes: sum('panel_scenes'), years: years
    };
  }

  function fillCounts(t) {
    document.querySelectorAll('[data-count]').forEach(function (node) {
      var target = t[node.dataset.count];
      if (target == null) return;
      node.dataset.target = target;
      node.textContent = HS.int(target);
    });
    document.getElementById('scene-years').textContent = t.years[0] + ' to ' + t.years[1];
  }

  function countUp(node) {
    var target = Number(node.dataset.target);
    if (!window.gsap || HS.reducedMotion || !target) return;
    var o = { v: 0 };
    gsap.to(o, { v: target, duration: 1.2, ease: 'power2.out', onUpdate: function () { node.textContent = HS.int(o.v); } });
  }

  /* ---------- the loop ---------- */
  var steps = [], words = ['Plan', 'Plant', 'Prove', 'Learn'], activeStep = -1;
  function setStep(i) {
    if (i === activeStep) return;
    activeStep = i;
    steps.forEach(function (li, n) {
      li.classList.toggle('is-active', n === i);
      li.querySelector('.step-tab').setAttribute('aria-expanded', String(n === i));
    });
    document.getElementById('ring-word').textContent = words[i];
    document.querySelectorAll('#ring-dots circle').forEach(function (dot, n) { dot.setAttribute('fill', n <= i ? '#ff7a45' : '#27353b'); });
    var ring = document.getElementById('ring-progress'), len = 804.25, offset = len * (1 - (i + 1) / 4);
    if (window.gsap && !HS.reducedMotion) gsap.to(ring, { attr: { 'stroke-dashoffset': offset }, duration: 0.5, ease: 'power2.out' });
    else ring.setAttribute('stroke-dashoffset', offset);
  }

  function initMotion() {
    var canPin = window.gsap && window.ScrollTrigger && !HS.reducedMotion && window.innerWidth > 900;
    if (!window.gsap || HS.reducedMotion) return;
    gsap.registerPlugin(ScrollTrigger);

    if (window.Lenis) {
      var lenis = new Lenis({ duration: 1.05, smoothWheel: true });
      lenis.on('scroll', ScrollTrigger.update);
      gsap.ticker.add(function (time) { lenis.raf(time * 1000); });
      gsap.ticker.lagSmoothing(0);
      document.querySelectorAll('a[href^="#"]').forEach(function (a) {
        a.addEventListener('click', function (e) {
          var target = document.querySelector(a.getAttribute('href'));
          if (!target) return;
          e.preventDefault();
          lenis.scrollTo(target, { offset: 0 });
          target.setAttribute('tabindex', '-1'); target.focus({ preventScroll: true });
        });
      });
    }

    /* Hero enters once on load. */
    gsap.from('[data-enter]', { y: 22, opacity: 0, duration: 0.8, ease: 'power3.out', stagger: 0.08, delay: 0.1 });

    /* The loop: pinned while the four steps play, on screens wide enough for it. */
    if (canPin) {
      ScrollTrigger.create({
        trigger: '#loop', start: 'top top', end: '+=1500', pin: true, anticipatePin: 1,
        onUpdate: function (self) { setStep(Math.min(3, Math.floor(self.progress * 4))); }
      });
    }

    /* Evidence tiles: counts run when the section arrives. */
    ScrollTrigger.create({
      trigger: '#tiles', start: 'top 80%', once: true,
      onEnter: function () {
        gsap.from('#tiles .tile', { y: 24, opacity: 0, duration: 0.6, ease: 'power3.out', stagger: 0.08 });
        document.querySelectorAll('#tiles [data-count]').forEach(countUp);
      }
    });
    document.querySelectorAll('.hero-facts [data-count]').forEach(countUp);
  }

  /* ---------- start ---------- */
  HS.fetchJSON('data/meta.json').then(function (meta) {
    state.meta = meta;
    HS.unit = meta.display.temperature_unit;
    fillCounts(totals(meta));

    var holder = document.getElementById('hero-cities');
    meta.cities.forEach(function (c) {
      var b = HS.el('button', { type: 'button', 'data-city': c.city_id, 'aria-pressed': 'false', text: c.name });
      b.addEventListener('click', function () { showCity(c.city_id); });
      holder.appendChild(b);
    });

    steps = Array.prototype.slice.call(document.querySelectorAll('#loop-steps .step'));
    steps.forEach(function (li, n) { li.querySelector('.step-tab').addEventListener('click', function () { setStep(n); }); });
    setStep(0);

    resize();
    window.addEventListener('resize', resize);
    var hero = document.querySelector('.hero');
    hero.addEventListener('pointermove', onPointer);
    hero.addEventListener('pointerleave', function () { state.pointer = null; state.hover = -1; requestDraw(); });

    initMotion();
    var lead = meta.cities.filter(function (c) { return c.lead; })[0] || meta.cities[0];
    return showCity(lead.city_id);
  }).catch(function (err) {
    document.getElementById('readout-value').textContent = 'The map data did not load';
    if (window.console) console.error(err);
  });
})();
