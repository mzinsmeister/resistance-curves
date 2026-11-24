/* Piecewise-linear quasi-static comparison, smooth resistance evaluation, and reverse load calculator. */
const AtlasModel = (() => {
  const STANDARD_PLATES = [25, 20, 15, 10, 5, 2.5, 1.25];

  function interpolate(rows, x) {
    if (!rows || !rows.length || x < rows[0][0] || x > rows.at(-1)[0]) return null;
    for (let i = 1; i < rows.length; i++) {
      const [a, va] = rows[i - 1], [b, vb] = rows[i];
      if (x <= b) return va + (vb - va) * (x - a) / (b - a);
    }
    return rows[0][1];
  }

  function evaluateCurve(curve, travel) {
    if (!Number.isFinite(travel) || travel < 0 || travel > 1) {
      throw Error('Travel must be a finite fraction from 0 to 1.');
    }
    let coefficients = curve.coefficients;
    if (['pchip', 'interval_mean'].includes(curve.type)) {
      let i = 0;
      while (i < curve.knots.length - 2 && travel >= curve.knots[i + 1]) i++;
      travel -= curve.knots[i];
      coefficients = coefficients[i];
    }
    return Math.max(0, coefficients.reduceRight((sum, c) => sum * travel + c, 0));
  }

  function curvePositions(curve) {
    const knots = curve.knots || [0, 1];
    const positions = [0];
    for (let i = 1; i < knots.length; i++) {
      const width = knots[i] - knots[i - 1];
      const steps = Math.max(12, Math.ceil(width * 200));
      for (let j = 1; j < steps; j++) positions.push(100 * (knots[i - 1] + width * j / steps));
      positions.push(100 * knots[i]);
    }
    return positions;
  }

  function plateTotal(text) {
    const entries = text.split(',').map(entry => entry.trim());
    if (entries.some(entry => !/^(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$/.test(entry))) {
      throw Error('Enter each plate mass in kg, separated by commas. Use 0 for an empty machine.');
    }
    const total = entries.reduce((sum, entry) => sum + Number(entry), 0);
    if (!Number.isFinite(total)) throw Error('The total plate mass is too large.');
    return total;
  }

  function baseForce(position, settings) {
    const {baseStart = 0, baseFinish = baseStart} = settings;
    return baseStart + (baseFinish - baseStart) * (position / 100);
  }

  function plateRatioAt(record, position, settings, fitted = true) {
    const {referenceIncludesBase = false} = settings;
    const t = position / 100;
    const base = baseForce(position, settings);
    const reference = fitted && record.resistance_curve
      ? evaluateCurve(record.resistance_curve, t) * record.plate_kg
      : interpolate(record.points, position);
    const plateContribution = referenceIncludesBase ? reference - base : reference;
    if (plateContribution < -1e-9) {
      throw Error('The unloaded handle force exceeds the reported reference force. Check the base or the reference assumption.');
    }
    return Math.max(0, plateContribution) / record.plate_kg;
  }

  function contactForce(record, position, settings, fitted = true) {
    const {load} = settings;
    return baseForce(position, settings) + plateRatioAt(record, position, settings, fitted) * load;
  }

  function summarizeCurve(record, settings, fitted = true) {
    const points = [];
    let peak = -Infinity, peakPct = 0, min = Infinity, minPct = 0, area = 0;
    for (let i = 0; i <= 100; i++) {
      const f = contactForce(record, i, settings, fitted);
      points.push([i, f]);
      if (f > peak) { peak = f; peakPct = i; }
      if (f < min) { min = f; minPct = i; }
      if (i > 0) area += 0.5 * (points[i - 1][1] + f);
    }
    const start = points[0][1], finish = points[100][1], mean = area / 100;
    return {points, start, finish, peak, peakPct, min, minPct, mean};
  }

  function suggestPlates(targetKg, increments = STANDARD_PLATES) {
    if (!Number.isFinite(targetKg) || targetKg <= 0) {
      return {plates: [], totalKg: 0};
    }
    const step = increments.at(-1);
    const rounded = Math.round(targetKg / step) * step;
    let remaining = rounded;
    const plates = [];
    for (const plate of increments) {
      while (remaining + 1e-9 >= plate) {
        plates.push(plate);
        remaining = Math.round((remaining - plate) * 1000) / 1000;
      }
    }
    const totalKg = Math.round(plates.reduce((s, p) => s + p, 0) * 1000) / 1000;
    return {plates, totalKg};
  }

  function platesForTargetForce(record, targetKgf, targetMode = 'peak', settings = {}, fitted = true) {
    if (!Number.isFinite(targetKgf) || targetKgf < 0) {
      throw Error('Target force must be a finite, nonnegative number (kgf).');
    }
    const samples = [];
    for (let i = 0; i <= 100; i++) {
      samples.push({
        pct: i,
        base: baseForce(i, settings),
        ratio: plateRatioAt(record, i, settings, fitted),
      });
    }

    let requiredKg = 0;
    let matchedPct = null;
    let coveredByBase = false;

    if (targetMode === 'peak') {
      const maxBase = Math.max(...samples.map(s => s.base));
      if (targetKgf <= maxBase + 1e-9) {
        requiredKg = 0;
        coveredByBase = true;
        matchedPct = samples.find(s => s.base >= maxBase - 1e-9)?.pct ?? 0;
      } else {
        let best = Infinity;
        for (const s of samples) {
          if (s.ratio > 1e-9) {
            const candidate = (targetKgf - s.base) / s.ratio;
            if (candidate < best) {
              best = candidate;
              matchedPct = s.pct;
            }
          }
        }
        if (!Number.isFinite(best)) {
          throw Error('This machine has zero plate leverage across the modeled stroke.');
        }
        requiredKg = Math.max(0, best);
      }
    } else if (targetMode === 'mean') {
      let meanBase = 0, meanRatio = 0;
      for (let i = 1; i <= 100; i++) {
        meanBase += 0.5 * (samples[i - 1].base + samples[i].base) / 100;
        meanRatio += 0.5 * (samples[i - 1].ratio + samples[i].ratio) / 100;
      }
      if (targetKgf <= meanBase + 1e-9) {
        requiredKg = 0;
        coveredByBase = true;
      } else if (meanRatio <= 1e-9) {
        throw Error('Mean plate leverage is zero across the stroke.');
      } else {
        requiredKg = (targetKgf - meanBase) / meanRatio;
      }
    } else {
      const pct = targetMode === 'start' ? 0
        : targetMode === 'mid' ? 50
        : targetMode === 'finish' ? 100
        : Number(targetMode);
      if (!Number.isFinite(pct) || pct < 0 || pct > 100) {
        throw Error('Custom target travel must be between 0% and 100%.');
      }
      matchedPct = pct;
      const base = baseForce(pct, settings);
      const ratio = plateRatioAt(record, pct, settings, fitted);
      if (targetKgf <= base + 1e-9) {
        requiredKg = 0;
        coveredByBase = true;
      } else if (ratio <= 1e-9) {
        throw Error('Plate leverage is zero at ' + pct + '% travel; pick another position.');
      } else {
        requiredKg = (targetKgf - base) / ratio;
      }
    }

    const suggested = suggestPlates(requiredKg);
    const achievedSummary = summarizeCurve(record, {...settings, load: suggested.totalKg}, fitted);
    const achievedAtTarget = targetMode === 'peak' ? achievedSummary.peak
      : targetMode === 'mean' ? achievedSummary.mean
      : contactForce(record, matchedPct, {...settings, load: suggested.totalKg}, fitted);

    return {
      requiredKg,
      coveredByBase,
      matchedPct,
      suggestedPlates: suggested.plates,
      suggestedTotalKg: suggested.totalKg,
      achievedAtTarget,
      summary: summarizeCurve(record, {...settings, load: requiredKg}, fitted),
    };
  }

  function compare(record, settings) {
    const {strength, fraction, share, geometry, continuous} = settings;
    const order = Math.sign(geometry.at(-1)[1] - geometry[0][1]);
    if (!order) throw Error('Start and finish angles must differ.');
    const angles = geometry.map(([p, a]) => [p, a]);
    const arms = geometry.map(([p, a, r]) => [p, r]);
    const curve = continuous && record.resistance_curve;
    const samples = (record.points || []).map(row => row[0]);
    if (curve) samples.push(...curvePositions(curve), ...geometry.map(row => row[0]));
    const positions = [...new Set(samples)].sort((a, b) => a - b);
    const demand = positions.map(p => [
      interpolate(angles, p),
      contactForce(record, p, settings, continuous) * record.gravity * share * interpolate(arms, p)
    ]);
    const sorted = [...demand].sort((a, b) => a[0] - b[0]);
    let knots = demand.map(row => row[0]);
    if (continuous) knots.push(...strength.map(row => row[0]));
    knots = [...new Set(knots)].sort((a, b) => order * (a - b));
    const common = [];
    for (const x of knots) {
      const d = interpolate(sorted, x), c = interpolate(strength, x);
      if (d !== null && c !== null) common.push({x, d, c: c * fraction});
    }
    let crossing = null, hardest = null;
    for (let i = 0; i < common.length; i++) {
      const row = common[i], margin = row.c - row.d;
      if (!hardest || row.d / row.c > hardest.d / hardest.c) hardest = row;
      if (crossing === null && margin <= 0) {
        crossing = row.x;
        if (continuous && i) {
          const last = common[i - 1], prior = last.c - last.d;
          crossing = last.x + (row.x - last.x) * prior / (prior - margin);
        }
      }
    }
    return {demand, capacity: strength.map(([x, c]) => [x, c * fraction]), crossing, hardest, common};
  }

  return {
    compare,
    evaluateCurve,
    curvePositions,
    contactForce,
    plateTotal,
    summarizeCurve,
    suggestPlates,
    platesForTargetForce,
  };
})();
if (typeof module !== 'undefined') module.exports = AtlasModel;
