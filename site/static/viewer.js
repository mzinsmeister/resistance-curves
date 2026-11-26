(() => {
  const STORAGE_KEY = 'resistanceAtlas.loadPrefs.v1';
  const DEFAULT_LOAD = 20;
  const KG_TO_LB = 2.20462262;
  const el = id => document.getElementById(id);
  const m = JSON.parse(el('record').textContent);

  let comparing = false;
  let lastRevResult = null;
  let revTouched = false;

  const fmt = (n, digits = 1) => Number(n.toFixed(digits)).toString();
  const svgNS = 'http://www.w3.org/2000/svg';
  const TEAL = '#0a7a74';
  const AMBER = '#c96a1b';
  const CRIMSON = '#c53434';

  function svgNode(tag, attrs, text) {
    const node = document.createElementNS(svgNS, tag);
    for (const [key, val] of Object.entries(attrs)) node.setAttribute(key, String(val));
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function readLoadPrefs() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      if (saved && typeof saved === 'object') {
        return {
          mode: saved.mode === 'plates' ? 'plates' : 'total',
          total: Number.isFinite(saved.total) && saved.total >= 0 ? saved.total : DEFAULT_LOAD,
          plates: typeof saved.plates === 'string' && saved.plates.trim() ? saved.plates : String(DEFAULT_LOAD),
        };
      }
    } catch (_) {}
    return {mode: 'total', total: DEFAULT_LOAD, plates: String(DEFAULT_LOAD)};
  }

  function saveLoadPrefs(mode, total, platesText) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        mode,
        total: Number.isFinite(total) && total >= 0 ? total : DEFAULT_LOAD,
        plates: platesText || String(total),
      }));
    } catch (_) {}
  }

  function niceTop(rawTop) {
    const safe = Math.max(1, rawTop * 1.12);
    const exp = Math.floor(Math.log10(safe));
    const mag = 10 ** exp;
    const norm = safe / mag;
    const nice = norm <= 1.2 ? 1.2 : norm <= 1.6 ? 1.6 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 3 ? 3 : norm <= 4 ? 4 : norm <= 5 ? 5 : norm <= 6 ? 6 : norm <= 8 ? 8 : 10;
    return nice * mag;
  }

  function sampleSeriesAt(points, x) {
    if (!points.length) return null;
    const asc = points[0][0] <= points.at(-1)[0];
    const sorted = asc ? points : [...points].reverse();
    if (x < sorted[0][0] - 1e-6 || x > sorted.at(-1)[0] + 1e-6) return null;
    if (x <= sorted[0][0]) return sorted[0][1];
    if (x >= sorted.at(-1)[0]) return sorted.at(-1)[1];
    for (let i = 1; i < sorted.length; i++) {
      const [a, va] = sorted[i - 1], [b, vb] = sorted[i];
      if (x <= b) return va + (vb - va) * (x - a) / (b - a);
    }
    return sorted.at(-1)[1];
  }

  function drawChart(series, xlabel, ylabel, opts = {}) {
    const {marker = null, reverse = false, shadeExceed = null, xUnit = '%', fixedTop = null, tooltipFormatter} = opts;
    const all = series.flatMap(s => s.points);
    const min = Math.min(...all.map(p => p[0]));
    const max = Math.max(...all.map(p => p[0]));
    const top = fixedTop !== null ? fixedTop : niceTop(Math.max(1, ...all.map(p => p[1])));

    const W = 720, H = 370;
    const padL = 62, padR = 26, padT = 34, padB = 56;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;

    const X = x => padL + plotW * (reverse ? max - x : x - min) / (max - min || 1);
    const Y = y => padT + plotH * (1 - y / top);
    const invX = px => {
      const frac = Math.max(0, Math.min(1, (px - padL) / plotW));
      return reverse ? max - frac * (max - min) : min + frac * (max - min);
    };

    const svg = svgNode('svg', {
      viewBox: `0 0 ${W} ${H}`,
      role: 'img',
      'aria-label': `${ylabel} by ${xlabel}`,
    });
    const add = (tag, attrs, text) => {
      const node = svgNode(tag, attrs, text);
      svg.append(node);
      return node;
    };

    // Gradient defs
    const defs = add('defs', {});
    const grad = svgNode('linearGradient', {id: 'curve-fill', x1: '0', y1: '0', x2: '0', y2: '1'});
    grad.append(svgNode('stop', {offset: '0%', 'stop-color': TEAL, 'stop-opacity': '0.20'}));
    grad.append(svgNode('stop', {offset: '100%', 'stop-color': TEAL, 'stop-opacity': '0.01'}));
    defs.append(grad);

    // Axis title
    add('text', {x: padL, y: 18, fill: '#4a5e60', 'font-size': 12.5, 'font-weight': 650}, ylabel);

    // Gridlines & ticks
    for (let i = 0; i <= 4; i++) {
      const val = top * i / 4;
      const py = Y(val);
      add('line', {
        x1: padL, x2: W - padR, y1: py, y2: py,
        stroke: i === 0 ? '#b7c6c3' : '#e5ecea',
        'stroke-width': i === 0 ? 1.3 : 1,
      });
      add('text', {
        x: padL - 10, y: py + 4, 'text-anchor': 'end',
        fill: '#5a6e70', 'font-size': 12,
      }, fmt(val));

      const xv = min + i * (max - min) / 4;
      const px = X(xv);
      if (i > 0 && i < 4) {
        add('line', {
          x1: px, x2: px, y1: padT, y2: padT + plotH,
          stroke: '#edf2f0', 'stroke-width': 1, 'stroke-dasharray': '3 4',
        });
      }
      add('text', {
        x: px, y: padT + plotH + 22, 'text-anchor': 'middle',
        fill: '#5a6e70', 'font-size': 12,
      }, fmt(xv, 0) + xUnit);
    }

    add('text', {
      x: padL + plotW / 2, y: H - 10, 'text-anchor': 'middle',
      fill: '#4a5e60', 'font-size': 12.5, 'font-weight': 600,
    }, xlabel);

    // Shaded exceed-capacity region for strength comparison
    if (shadeExceed && shadeExceed.length > 1) {
      let run = [];
      const flush = () => {
        if (run.length < 2) { run = []; return; }
        const upper = run.map(r => `${X(r.x)},${Y(r.d)}`).join(' ');
        const lower = [...run].reverse().map(r => `${X(r.x)},${Y(r.c)}`).join(' ');
        add('polygon', {points: `${upper} ${lower}`, fill: CRIMSON, 'fill-opacity': 0.14});
        run = [];
      };
      for (const row of shadeExceed) {
        if (row.d >= row.c) run.push(row);
        else flush();
      }
      flush();
    }

    // Series rendering (always smooth lines; area fill for primary curve)
    for (const s of series) {
      if (s.area && s.points.length >= 2) {
        const pts = s.points.map(([x, y]) => `${X(x).toFixed(2)},${Y(y).toFixed(2)}`).join(' ');
        const firstX = X(s.points[0][0]).toFixed(2);
        const lastX = X(s.points.at(-1)[0]).toFixed(2);
        const baseY = Y(0).toFixed(2);
        add('polygon', {points: `${firstX},${baseY} ${pts} ${lastX},${baseY}`, fill: 'url(#curve-fill)'});
      }
      if (s.line && s.points.length >= 2) {
        add('polyline', {
          points: s.points.map(([x, y]) => `${X(x).toFixed(2)},${Y(y).toFixed(2)}`).join(' '),
          fill: 'none',
          stroke: s.color,
          'stroke-width': s.width || 3,
          'stroke-linecap': 'round',
          'stroke-linejoin': 'round',
          'stroke-dasharray': s.dashed ? '7 5' : 'none',
        });
      }
      if (s.markers) {
        for (const [x, y] of s.points) {
          add('circle', {
            cx: X(x), cy: Y(y), r: s.markerRadius || 4.5,
            fill: s.hollow ? '#ffffff' : s.color,
            stroke: s.color,
            'stroke-width': s.hollow ? 2.2 : 1.5,
          });
        }
      }
    }

    // Crossing / sticking-point vertical line
    if (marker !== null && Number.isFinite(marker)) {
      const mx = X(marker);
      add('line', {
        x1: mx, x2: mx, y1: padT, y2: padT + plotH,
        stroke: CRIMSON, 'stroke-width': 2, 'stroke-dasharray': '5 4',
      });
      const pillW = 94;
      const pillX = Math.max(padL + 2, Math.min(W - padR - pillW - 2, mx - pillW / 2));
      add('rect', {
        x: pillX, y: padT + 4, width: pillW, height: 22, rx: 6,
        fill: CRIMSON,
      });
      add('text', {
        x: pillX + pillW / 2, y: padT + 19, 'text-anchor': 'middle',
        fill: '#ffffff', 'font-size': 11.5, 'font-weight': 700,
      }, `Limit ${fmt(marker)}°`);
    }

    // Interactive crosshair overlay
    const crossLine = add('line', {
      x1: 0, x2: 0, y1: padT, y2: padT + plotH,
      stroke: '#0f1b1d', 'stroke-width': 1.2, 'stroke-dasharray': '3 3',
      opacity: 0,
    });
    const hoverDots = series.filter(s => s.line).map(s => add('circle', {
      cx: 0, cy: 0, r: 5.5, fill: s.color, stroke: '#ffffff', 'stroke-width': 2.2, opacity: 0,
    }));

    const hitRect = add('rect', {
      x: padL, y: padT, width: plotW, height: plotH,
      fill: 'transparent', style: 'cursor:crosshair',
    });

    const tooltip = el('chart-tooltip');
    const stage = el('chart').parentElement;

    function hideHover() {
      crossLine.setAttribute('opacity', '0');
      hoverDots.forEach(d => d.setAttribute('opacity', '0'));
      tooltip.hidden = true;
    }

    function onMove(evt) {
      const rect = svg.getBoundingClientRect();
      const sx = ((evt.clientX - rect.left) / rect.width) * W;
      if (sx < padL || sx > W - padR) { hideHover(); return; }
      const xv = invX(sx);
      const px = X(xv);
      crossLine.setAttribute('x1', px);
      crossLine.setAttribute('x2', px);
      crossLine.setAttribute('opacity', '0.55');

      const lineSeries = series.filter(s => s.line);
      const vals = [];
      lineSeries.forEach((s, idx) => {
        const yv = sampleSeriesAt(s.points, xv);
        vals.push(yv);
        if (yv !== null) {
          hoverDots[idx].setAttribute('cx', px);
          hoverDots[idx].setAttribute('cy', Y(yv));
          hoverDots[idx].setAttribute('opacity', '1');
        } else {
          hoverDots[idx].setAttribute('opacity', '0');
        }
      });

      if (tooltipFormatter) {
        tooltip.innerHTML = tooltipFormatter(xv, vals);
        tooltip.hidden = false;
        const stageRect = stage.getBoundingClientRect();
        const relX = evt.clientX - stageRect.left;
        const relY = evt.clientY - stageRect.top;
        const left = relX > stageRect.width * 0.62 ? relX - tooltip.offsetWidth - 14 : relX + 14;
        const topPx = Math.max(8, Math.min(stageRect.height - tooltip.offsetHeight - 8, relY - 24));
        tooltip.style.left = `${Math.max(8, left)}px`;
        tooltip.style.top = `${topPx}px`;
      }
    }

    hitRect.addEventListener('pointermove', onMove);
    hitRect.addEventListener('pointerdown', onMove);
    hitRect.addEventListener('pointerleave', hideHover);

    el('chart').replaceChildren(svg);
  }

  const number = (id, min, max = Infinity) => {
    const v = el(id).valueAsNumber;
    if (!Number.isFinite(v) || v < min || v > max) {
      throw Error('Check the value for ' + (el(id).previousElementSibling?.textContent?.trim() || id) + '.');
    }
    return v;
  };

  function strengthPoints() {
    if (el('strength').value !== 'custom') return m.strength[Number(el('strength').value)].points;
    const rows = el('custom').value.trim().split(/\n/).map(line => line.split(',').map(s => s.trim() === '' ? NaN : Number(s)));
    if (rows.length < 2 || rows.some((p, i) => p.length !== 2 || !p.every(Number.isFinite) || p[0] < 0 || p[0] > 180 || p[1] <= 0 || (i && p[0] <= rows[i - 1][0]))) {
      throw Error('Enter two or more rows of increasing joint angle (0–180°) and positive torque (N·m), separated by a comma.');
    }
    return rows;
  }

  function updateKPIs(summary) {
    const g = m.gravity || 9.80665;
    el('kpi-start').textContent = `${fmt(summary.start)} kgf`;
    el('kpi-start-n').textContent = `${fmt(summary.start * g, 0)} N`;
    el('kpi-peak-label').textContent = `Peak (${summary.peakPct}%)`;
    el('kpi-peak').textContent = `${fmt(summary.peak)} kgf`;
    el('kpi-peak-n').textContent = `${fmt(summary.peak * g, 0)} N`;
    el('kpi-finish').textContent = `${fmt(summary.finish)} kgf`;
    el('kpi-finish-n').textContent = `${fmt(summary.finish * g, 0)} N`;
    const ratio = summary.min > 0.05 ? `${fmt(summary.peak / summary.min, 2)}×` : '—';
    el('kpi-ratio').textContent = ratio;
    el('kpi-mean').textContent = `Avg ${fmt(summary.mean)} kgf`;
  }

  function updateReverseCalculator(loading) {
    const modeSel = el('rev-point').value;
    el('rev-custom-panel').hidden = modeSel !== 'custom';
    try {
      const targetKgf = number('rev-target', 0);
      const targetMode = modeSel === 'custom' ? number('rev-custom-pct', 0, 100) : modeSel;
      const res = AtlasModel.platesForTargetForce(m, targetKgf, targetMode, loading, true);
      lastRevResult = res;
      const lb = res.requiredKg * KG_TO_LB;
      el('rev-kg').textContent = `${fmt(res.requiredKg)} kg (${fmt(lb, 0)} lb)`;
      if (res.coveredByBase) {
        el('rev-detail').textContent = 'Already met by the unloaded machine’s base resistance — 0 kg of plates needed.';
      } else {
        const stack = res.suggestedPlates.length ? res.suggestedPlates.join(' + ') + ' kg' : '0 kg';
        const where = modeSel === 'peak' ? `peak (${res.matchedPct}%)`
          : modeSel === 'mean' ? 'stroke avg'
          : `${fmt(res.matchedPct, 0)}% travel`;
        el('rev-detail').textContent = `Nearest standard plates: ${stack} = ${fmt(res.suggestedTotalKg, 2)} kg → ${fmt(res.achievedAtTarget)} kgf at ${where}.`;
      }
      el('rev-apply').disabled = false;
    } catch (err) {
      lastRevResult = null;
      el('rev-kg').textContent = '—';
      el('rev-detail').textContent = err.message;
      el('rev-apply').disabled = true;
    }
  }

  function setLegend(items) {
    const wrap = el('legend');
    wrap.replaceChildren();
    for (const [label, color] of items) {
      const span = document.createElement('span');
      span.className = 'legend-item';
      const dot = document.createElement('i');
      dot.className = 'legend-dot';
      dot.style.background = color;
      span.append(dot, document.createTextNode(label));
      wrap.append(span);
    }
  }

  function highlightActiveLoadChip(load) {
    for (const btn of document.querySelectorAll('#total-presets .chip')) {
      btn.classList.toggle('is-active', Math.abs(Number(btn.dataset.setLoad) - load) < 1e-6);
    }
  }

  function highlightActiveShareChip(share) {
    for (const btn of document.querySelectorAll('.share-presets .chip')) {
      btn.classList.toggle('is-active', Math.abs(Number(btn.dataset.setShare) - share) < 1e-6);
    }
  }

  function render() {
    el('controls').hidden = !comparing;
    el('force').setAttribute('aria-pressed', String(!comparing));
    el('compare')?.setAttribute('aria-pressed', String(comparing));
    el('graph-title').textContent = comparing ? 'Torque demand vs. normal lifter strength' : 'Contact force through the rep';
    el('comparison-source').replaceChildren();
    el('result').classList.remove('is-warning');

    try {
      const individual = el('load-mode').value === 'plates';
      el('total-panel').hidden = individual;
      el('plates-panel').hidden = !individual;
      for (const btn of document.querySelectorAll('.seg-btn')) {
        btn.classList.toggle('is-active', btn.dataset.loadMode === (individual ? 'plates' : 'total'));
      }

      const varyBase = el('vary-base').checked;
      el('finish-base-panel').hidden = !varyBase;

      const load = individual ? AtlasModel.plateTotal(el('plates').value) : number('load', 0);
      saveLoadPrefs(individual ? 'plates' : 'total', load, el('plates').value);
      highlightActiveLoadChip(load);

      const baseStart = number('base-start', 0);
      const baseFinish = varyBase ? number('base-finish', 0) : baseStart;
      el('base-pill').textContent = varyBase ? `${fmt(baseStart)}–${fmt(baseFinish)} kgf` : `${fmt(baseStart)} kgf`;

      const loading = {
        load,
        baseStart,
        baseFinish,
        referenceIncludesBase: el('reference-basis')?.value === 'included',
      };

      const summary = AtlasModel.summarizeCurve(m, loading, true);
      updateKPIs(summary);

      if (!revTouched) {
        el('rev-target').value = String(Math.max(5, Math.round(summary.peak)));
      }
      updateReverseCalculator(loading);

      el('load-summary').textContent =
        `${fmt(load, 2)} kg plates (${fmt(load * KG_TO_LB, 0)} lb) · ` +
        `Start ${fmt(summary.start)} · Peak ${fmt(summary.peak)} · Finish ${fmt(summary.finish)} kgf`;

      if (!comparing) {
        const curvePoints = AtlasModel.curvePositions(m.resistance_curve).map(p => [
          p,
          AtlasModel.contactForce(m, p, loading, true),
        ]);
        const series = [{
          points: curvePoints,
          color: TEAL,
          line: true,
          area: true,
          markers: false,
        }];
        if (m.mechanism === 'belt_cam' && m.points && m.points.length <= 12) {
          series.push({
            points: m.points.map(([x]) => [x, AtlasModel.contactForce(m, x, loading, true)]),
            color: TEAL,
            line: false,
            markers: true,
            hollow: true,
            markerRadius: 4.5,
          });
        }
        drawChart(series, 'Travel through lifting stroke (%)', 'Contact force (kgf)', {
          xUnit: '%',
          tooltipFormatter: (pct, [kgf]) => {
            const g = m.gravity || 9.80665;
            return `<strong>${fmt(pct, 0)}% travel</strong>` +
              `<div class="tt-row"><span>Contact force</span><span>${fmt(kgf)} kgf</span></div>` +
              `<div class="tt-row"><span>Newtons</span><span>${fmt(kgf * g, 0)} N</span></div>` +
              `<div class="tt-row"><span>Pounds-force</span><span>${fmt(kgf * KG_TO_LB)} lbf</span></div>`;
          },
        });
        const legendItems = [['Machine resistance curve', TEAL]];
        if (m.mechanism === 'belt_cam') legendItems.push(['Measured cam poses', TEAL]);
        setLegend(legendItems);
        el('result').textContent =
          `Peak resistance hits ${fmt(summary.peak)} kgf at ${summary.peakPct}% of the stroke ` +
          `(${fmt(summary.start)} kgf at start → ${fmt(summary.finish)} kgf at finish, stroke average ${fmt(summary.mean)} kgf).`;
        return;
      }

      // Strength comparison mode
      const strength = strengthPoints();
      const capPct = number('capacity', 1, 300);
      el('capacity-label').textContent = `${fmt(capPct, 0)}%`;
      el('capacity-range').value = String(Math.max(30, Math.min(220, capPct)));
      const fraction = capPct / 100;
      const sharePct = number('share', 1, 100);
      highlightActiveShareChip(sharePct);
      const share = sharePct / 100;

      let geometry = m.geometry;
      if (!geometry.length) {
        const arm = number('arm', 0.001);
        geometry = [[0, number('start', 0, 180), arm], [100, number('finish', 0, 180), arm]];
      }

      const r = AtlasModel.compare(m, {...loading, strength, fraction, share, geometry, continuous: true});
      const reverse = geometry[0][1] > geometry.at(-1)[1];
      const normalize = Boolean(el('normalize-strength')?.checked);

      // Compute shape alignment score over overlapping joint angles
      let matchScore = null;
      if (r.common.length >= 2) {
        const maxD = Math.max(...r.common.map(row => row.d), 1e-9);
        const maxC = Math.max(...r.common.map(row => row.c), 1e-9);
        const meanAbsDiff = r.common.reduce((acc, row) => acc + Math.abs(row.d / maxD - row.c / maxC), 0) / r.common.length;
        matchScore = Math.max(0, Math.round((1 - meanAbsDiff) * 100));
      }

      if (normalize) {
        const demPeak = r.common.length >= 2
          ? Math.max(...r.common.map(row => row.d), 1e-9)
          : Math.max(...r.demand.map(p => p[1]), 1e-9);
        const capPeak = r.common.length >= 2
          ? Math.max(...r.common.map(row => row.c), 1e-9)
          : Math.max(...r.capacity.map(p => p[1]), 1e-9);
        const demNorm = r.demand.map(([x, y]) => [x, 100 * y / demPeak]);
        const capNorm = r.capacity.map(([x, y]) => [x, 100 * y / capPeak]);
        const normTop = Math.max(100, ...demNorm.map(p => p[1]), ...capNorm.map(p => p[1]));
        drawChart(
          [
            {points: demNorm, line: true, area: true, color: TEAL},
            {points: capNorm, line: true, color: AMBER, markers: true, hollow: true, markerRadius: 4},
          ],
          'Joint angle (°) · lifting direction →',
          'Relative profile (% of peak in shared ROM)',
          {
            marker: null,
            reverse,
            xUnit: '°',
            fixedTop: normTop <= 105 ? 100 : niceTop(normTop),
            tooltipFormatter: (ang, [demP, capP]) => {
              const demAbs = sampleSeriesAt(r.demand, ang);
              const capAbs = sampleSeriesAt(r.capacity, ang);
              let html = `<strong>Joint angle ${fmt(ang, 0)}°</strong>`;
              if (demP !== null) html += `<div class="tt-row"><span>Machine curve</span><span>${fmt(demP, 0)}% (${fmt(demAbs)} N·m)</span></div>`;
              if (capP !== null) html += `<div class="tt-row"><span>Human strength</span><span>${fmt(capP, 0)}% (${fmt(capAbs)} N·m)</span></div>`;
              return html;
            },
          }
        );
      } else {
        drawChart(
          [
            {points: r.demand, line: true, area: true, color: TEAL},
            {points: r.capacity, line: true, color: AMBER, markers: true, hollow: true, markerRadius: 4},
          ],
          'Joint angle (°) · lifting direction →',
          'Joint torque (N·m)',
          {
            marker: r.crossing,
            reverse,
            shadeExceed: r.common,
            xUnit: '°',
            tooltipFormatter: (ang, [dem, cap]) => {
              let html = `<strong>Joint angle ${fmt(ang, 0)}°</strong>`;
              if (dem !== null) html += `<div class="tt-row"><span>Machine demand</span><span>${fmt(dem)} N·m</span></div>`;
              if (cap !== null) html += `<div class="tt-row"><span>Lifter capacity</span><span>${fmt(cap)} N·m</span></div>`;
              if (dem !== null && cap !== null && cap > 0) {
                html += `<div class="tt-row"><span>Effort</span><span>${fmt(100 * dem / cap, 0)}%</span></div>`;
              }
              return html;
            },
          }
        );
      }

      setLegend([
        [normalize ? 'Machine torque shape (% of peak)' : 'Machine torque demand (N·m)', TEAL],
        [normalize ? 'Human strength shape (% of peak)' : 'Empirical normal lifter capacity (N·m)', AMBER],
      ]);

      const source = el('comparison-source');
      if (el('strength').value === 'custom') {
        source.textContent = 'Using personal isometric torque measurements entered for this session.';
      } else {
        const selected = m.strength[Number(el('strength').value)];
        source.textContent = 'Strength curve: ' + selected.source + ' ';
        if (selected.url) {
          const a = document.createElement('a');
          a.textContent = 'Read study ↗';
          a.href = selected.url;
          a.target = '_blank';
          a.rel = 'noopener';
          source.append(a);
        }
      }

      if (!r.hardest) {
        el('result').textContent = 'No overlapping joint angles between machine geometry and selected strength curve.';
        return;
      }
      const range = `${fmt(r.common[0].x, 0)}° to ${fmt(r.common.at(-1).x, 0)}°`;
      const matchNote = matchScore !== null ? ` Curve shape alignment: ${matchScore}%.` : '';
      if (normalize) {
        el('result').textContent =
          `Comparing relative curve shapes across ${range}.${matchNote} ` +
          `Peak effort relative to strength occurs at ${fmt(r.hardest.x, 0)}°.`;
      } else if (r.crossing !== null) {
        el('result').classList.add('is-warning');
        el('result').textContent =
          `Predicted sticking point at ${fmt(r.crossing, 0)}° (effort peaks at ${fmt(100 * r.hardest.d / r.hardest.c, 0)}% at ${fmt(r.hardest.x, 0)}° across ${range}).${matchNote}`;
      } else {
        el('result').textContent =
          `Load stays within available strength across ${range} — hardest point is ${fmt(100 * r.hardest.d / r.hardest.c, 0)}% of capacity at ${fmt(r.hardest.x, 0)}°.${matchNote}`;
      }
    } catch (err) {
      el('load-summary').textContent = '';
      el('result').classList.add('is-warning');
      el('result').textContent = err.message;
    }
  }

  // Populate strength dropdown (empirical pooled average adult first)
  if (el('strength')) {
    for (const [i, s] of m.strength.entries()) {
      el('strength').add(new Option(s.name, String(i)));
    }
    el('strength').add(new Option('Personal measurements (custom)', 'custom'));
    el('strength').value = m.strength.length ? '0' : 'custom';
  }

  // Movement-appropriate anatomical defaults when uncalibrated
  if (el('share') && Number.isFinite(m.default_share)) {
    el('share').value = String(m.default_share);
  }
  if (el('start') && el('finish') && el('arm')) {
    const moveDefaults = {
      'elbow-flexion': [20, 120, 0.26],
      'elbow-extension': [110, 15, 0.26],
      'knee-extension': [95, 15, 0.38],
      'knee-flexion': [15, 100, 0.38],
      'shoulder-abduction': [20, 95, 0.28],
      'ankle-plantarflexion': [80, 120, 0.16],
    };
    const [dStart, dFinish, dArm] = moveDefaults[m.movement] || [20, 120, 0.28];
    el('start').value = String(dStart);
    el('finish').value = String(dFinish);
    el('arm').value = String(dArm);
  }

  // Auto-solve plate mass where machine torque demand just reaches 100% of lifter capacity at sticking point
  el('match-strength')?.addEventListener('click', () => {
    try {
      const strength = strengthPoints();
      const fraction = number('capacity', 1, 300) / 100;
      const share = number('share', 1, 100) / 100;
      const baseStart = number('base-start', 0);
      const baseFinish = el('vary-base').checked ? number('base-finish', 0) : baseStart;
      const loadingBase = {
        baseStart,
        baseFinish,
        referenceIncludesBase: el('reference-basis')?.value === 'included',
      };
      let geometry = m.geometry;
      if (!geometry.length) {
        const arm = number('arm', 0.001);
        geometry = [[0, number('start', 0, 180), arm], [100, number('finish', 0, 180), arm]];
      }
      // Binary search for exact plate mass L where max(demand / capacity) == 1.0
      const evalRatio = L => {
        const r = AtlasModel.compare(m, {...loadingBase, load: L, strength, fraction, share, geometry, continuous: true});
        return r.hardest ? r.hardest.d / r.hardest.c : 0;
      };
      let lo = 0, hi = 250;
      if (evalRatio(0) >= 1) {
        hi = 0;
      } else {
        while (evalRatio(hi) < 1 && hi < 2000) hi *= 2;
        for (let k = 0; k < 28; k++) {
          const mid = (lo + hi) / 2;
          if (evalRatio(mid) >= 1) hi = mid;
          else lo = mid;
        }
      }
      const matchedKg = Math.round(hi * 4) / 4; // nearest 0.25 kg
      if (el('load-mode').value === 'plates') {
        const sug = AtlasModel.suggestPlates(matchedKg);
        el('plates').value = sug.plates.length ? sug.plates.join(', ') : '0';
      } else {
        el('load').value = String(matchedKg);
      }
      if (el('normalize-strength')) el('normalize-strength').checked = false;
      render();
    } catch (_) {}
  });

  // Restore saved load preference (default 20 kg)
  const prefs = readLoadPrefs();
  el('load-mode').value = prefs.mode;
  el('load').value = String(prefs.total);
  el('plates').value = prefs.plates;

  // Mode segmented buttons
  for (const btn of document.querySelectorAll('.seg-btn')) {
    btn.addEventListener('click', () => {
      const next = btn.dataset.loadMode;
      if (next === 'plates' && el('load-mode').value === 'total') {
        const cur = el('load').valueAsNumber;
        if (Number.isFinite(cur) && cur >= 0) {
          const sug = AtlasModel.suggestPlates(cur);
          el('plates').value = sug.plates.length ? sug.plates.join(', ') : '0';
        }
      } else if (next === 'total' && el('load-mode').value === 'plates') {
        try {
          el('load').value = String(AtlasModel.plateTotal(el('plates').value));
        } catch (_) {}
      }
      el('load-mode').value = next;
      render();
    });
  }

  // Quick load chips
  el('total-presets')?.addEventListener('click', evt => {
    const btn = evt.target.closest('[data-set-load]');
    if (!btn) return;
    el('load').value = btn.dataset.setLoad;
    render();
  });

  // Plate adder chips
  el('plate-adders')?.addEventListener('click', evt => {
    const addBtn = evt.target.closest('[data-add-plate]');
    const clearBtn = evt.target.closest('[data-clear-plates]');
    if (clearBtn) {
      el('plates').value = '0';
      render();
      return;
    }
    if (!addBtn) return;
    const plate = addBtn.dataset.addPlate;
    const raw = el('plates').value.trim();
    el('plates').value = (!raw || raw === '0') ? plate : `${raw}, ${plate}`;
    render();
  });

  // Reverse calculator events
  el('rev-target')?.addEventListener('input', () => { revTouched = true; render(); });
  el('rev-point')?.addEventListener('change', () => { revTouched = true; render(); });
  el('rev-custom-pct')?.addEventListener('input', () => { revTouched = true; render(); });
  el('rev-apply')?.addEventListener('click', () => {
    if (!lastRevResult) return;
    const targetKg = lastRevResult.suggestedTotalKg;
    if (el('load-mode').value === 'plates') {
      el('plates').value = lastRevResult.suggestedPlates.length ? lastRevResult.suggestedPlates.join(', ') : '0';
    } else {
      el('load').value = String(targetKg);
    }
    render();
  });

  // Strength slider & share chips
  el('capacity-range')?.addEventListener('input', () => {
    el('capacity').value = el('capacity-range').value;
    render();
  });
  for (const btn of document.querySelectorAll('[data-set-share]')) {
    btn.addEventListener('click', () => {
      el('share').value = btn.dataset.setShare;
      render();
    });
  }

  // Tabs
  el('force').addEventListener('click', () => { comparing = false; render(); });
  el('compare')?.addEventListener('click', () => { comparing = true; render(); });

  // Lightbox for annotated force diagrams
  const lightbox = el('lightbox');
  if (lightbox) {
    document.addEventListener('click', evt => {
      const trigger = evt.target.closest('[data-lightbox-src]');
      if (!trigger) return;
      el('lightbox-img').src = trigger.dataset.lightboxSrc;
      el('lightbox-img').alt = trigger.dataset.lightboxLabel || '';
      el('lightbox-caption').textContent = trigger.dataset.lightboxLabel || '';
      lightbox.showModal();
    });
    el('lightbox-close').addEventListener('click', () => lightbox.close());
    lightbox.addEventListener('click', evt => {
      if (evt.target === lightbox) lightbox.close();
    });
  }

  function update() {
    if (el('custom-panel') && el('strength')) {
      el('custom-panel').hidden = el('strength').value !== 'custom';
    }
    render();
  }
  document.querySelector('aside').addEventListener('input', update);
  document.querySelector('aside').addEventListener('change', update);
  update();
})();
