(() => {
  const STORAGE_KEY = 'resistanceAtlas.loadPrefs.v1';
  const DEFAULT_LOAD = 20;
  const el = id => document.getElementById(id);
  const grid = el('machine-grid');
  if (!grid) return;

  const cards = [...grid.querySelectorAll('.card')];
  const index = JSON.parse(el('catalog-index').textContent);
  const bySlug = new Map(index.map(item => [item.slug, item]));

  const searchInput = el('filter-search');
  const brandSelect = el('filter-brand');
  const shapeSelect = el('filter-shape');
  const sortSelect = el('filter-sort');
  const loadInput = el('library-load');
  const pillsWrap = el('movement-pills');
  const examplesToggle = el('toggle-examples');
  const emptyState = el('empty-state');

  let activeMovement = '';

  function readLoadPref() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      if (saved && Number.isFinite(saved.total) && saved.total >= 0) return saved.total;
    } catch (_) {}
    return DEFAULT_LOAD;
  }

  function writeLoadPref(total) {
    try {
      const prev = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        mode: prev.mode || 'total',
        total,
        plates: prev.plates || String(total),
      }));
    } catch (_) {}
  }

  // Populate brands & movement pills
  const brands = [...new Set(cards.map(c => c.dataset.brand))].sort((a, b) => a.localeCompare(b));
  for (const brand of brands) {
    brandSelect.add(new Option(brand, brand));
  }

  const movements = new Map();
  for (const c of cards) {
    if (!movements.has(c.dataset.movement)) {
      movements.set(c.dataset.movement, c.dataset.movementLabel);
    }
  }
  const sortedMovements = [...movements.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  for (const [slug, label] of sortedMovements) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'pill';
    btn.dataset.movement = slug;
    btn.textContent = label;
    pillsWrap.append(btn);
  }

  const fmt = n => Number(n.toFixed(1)).toString();

  function updateCardMetrics(loadKg) {
    const statsBySlug = new Map();
    for (const card of cards) {
      const slug = card.dataset.slug;
      const rec = bySlug.get(slug);
      if (!rec) continue;
      const baseStart = rec.base_resistance?.starting_kgf ?? 0;
      const baseFinish = rec.base_resistance?.finish_kgf ?? baseStart;
      const summary = AtlasModel.summarizeCurve(rec, {
        load: loadKg,
        baseStart,
        baseFinish,
        referenceIncludesBase: Boolean(rec.reference_includes_base),
      }, true);

      card.querySelector('[data-field="start"]').textContent = fmt(summary.start) + ' kgf';
      card.querySelector('[data-field="peak"]').textContent = fmt(summary.peak) + ' kgf';
      card.querySelector('[data-field="finish"]').textContent = fmt(summary.finish) + ' kgf';

      // Redraw sparkline for active plate load
      const top = Math.max(summary.peak, 1e-6);
      const coords = summary.points.map(([x, y]) => [x, 92 - 80 * y / top]);
      const lineStr = coords.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
      const areaStr = `0,96 ${lineStr} 100,96`;
      const peakCoord = coords[summary.peakPct] || coords[0];
      const lineEl = card.querySelector('.spark-line');
      const areaEl = card.querySelector('.spark-area');
      const peakEl = card.querySelector('.spark-peak');
      if (lineEl) lineEl.setAttribute('points', lineStr);
      if (areaEl) areaEl.setAttribute('points', areaStr);
      if (peakEl && peakCoord) {
        peakEl.setAttribute('cx', peakCoord[0].toFixed(2));
        peakEl.setAttribute('cy', peakCoord[1].toFixed(2));
      }

      const ratio = summary.min > 0.05 ? summary.peak / summary.min : 99;
      statsBySlug.set(slug, {peak: summary.peak, ratio});
    }
    el('stat-load').textContent = fmt(loadKg) + ' kg';
    return statsBySlug;
  }

  function applyFilters() {
    const q = searchInput.value.trim().toLowerCase();
    const brand = brandSelect.value;
    const shape = shapeSelect.value;
    const showExamples = examplesToggle ? examplesToggle.checked : false;
    const loadKg = Math.max(0, Number.isFinite(loadInput.valueAsNumber) ? loadInput.valueAsNumber : DEFAULT_LOAD);

    const stats = updateCardMetrics(loadKg);
    const visible = [];

    for (const card of cards) {
      const isExample = card.dataset.example === 'true';
      const matchesExample = showExamples || !isExample;
      const matchesMove = !activeMovement || card.dataset.movement === activeMovement;
      const matchesBrand = !brand || card.dataset.brand === brand;
      const matchesShape = !shape || card.dataset.shape === shape;
      const haystack = `${card.dataset.name} ${card.dataset.brand} ${card.dataset.movementLabel} ${card.dataset.shape}`.toLowerCase();
      const matchesSearch = !q || haystack.includes(q);

      const show = matchesExample && matchesMove && matchesBrand && matchesShape && matchesSearch;
      card.hidden = !show;
      if (show) visible.push(card);
    }

    const sortBy = sortSelect.value;
    visible.sort((a, b) => {
      if (sortBy === 'peak-desc') return (stats.get(b.dataset.slug)?.peak ?? 0) - (stats.get(a.dataset.slug)?.peak ?? 0);
      if (sortBy === 'peak-asc') return (stats.get(a.dataset.slug)?.peak ?? 0) - (stats.get(b.dataset.slug)?.peak ?? 0);
      if (sortBy === 'ratio-desc') return (stats.get(b.dataset.slug)?.ratio ?? 0) - (stats.get(a.dataset.slug)?.ratio ?? 0);
      return a.dataset.name.localeCompare(b.dataset.name);
    });
    for (const card of visible) grid.append(card);

    el('result-count').textContent = `${visible.length} machine${visible.length === 1 ? '' : 's'}`;
    el('stat-visible').textContent = String(visible.length);
    emptyState.hidden = visible.length > 0;
  }

  pillsWrap.addEventListener('click', evt => {
    const btn = evt.target.closest('.pill');
    if (!btn) return;
    activeMovement = btn.dataset.movement || '';
    for (const p of pillsWrap.querySelectorAll('.pill')) {
      p.classList.toggle('is-active', p === btn);
    }
    applyFilters();
  });

  searchInput.addEventListener('input', applyFilters);
  brandSelect.addEventListener('change', applyFilters);
  shapeSelect.addEventListener('change', applyFilters);
  sortSelect.addEventListener('change', applyFilters);
  if (examplesToggle) examplesToggle.addEventListener('change', applyFilters);

  loadInput.addEventListener('input', () => {
    const v = loadInput.valueAsNumber;
    if (Number.isFinite(v) && v >= 0) {
      writeLoadPref(v);
      applyFilters();
    }
  });

  el('reset-filters')?.addEventListener('click', () => {
    searchInput.value = '';
    brandSelect.value = '';
    shapeSelect.value = '';
    sortSelect.value = 'name';
    activeMovement = '';
    for (const p of pillsWrap.querySelectorAll('.pill')) {
      p.classList.toggle('is-active', (p.dataset.movement || '') === '');
    }
    applyFilters();
  });

  // Initialize load from last-used preference (default 20 kg)
  const initialLoad = readLoadPref();
  loadInput.value = String(initialLoad);
  applyFilters();
})();
