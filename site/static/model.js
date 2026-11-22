/* Piecewise-linear quasi-static comparison in lifting order. No extrapolation. */
const AtlasModel = (() => {
  function interpolate(rows, x) {
    if (x < rows[0][0] || x > rows.at(-1)[0]) return null;
    for (let i = 1; i < rows.length; i++) {
      const [a, va] = rows[i - 1], [b, vb] = rows[i];
      if (x <= b) return va + (vb - va) * (x - a) / (b - a);
    }
  }

  function evaluateCurve(curve, travel) {
    if (!Number.isFinite(travel) || travel < 0 || travel > 1) {
      throw Error('Travel must be a finite fraction from 0 to 1.');
    }
    let coefficients = curve.coefficients;
    if (curve.type === 'pchip') {
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
      for (let j = 1; j < steps; j++) positions.push(100 * (knots[i-1] + width * j / steps));
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

  function contactForce(record, position, settings, fitted) {
    const {load, baseStart = 0, baseFinish = baseStart, referenceIncludesBase = false} = settings;
    const t = position / 100;
    const base = baseStart + (baseFinish - baseStart) * t;
    const reference = fitted && record.resistance_curve
      ? evaluateCurve(record.resistance_curve, t) * record.plate_kg
      : interpolate(record.points, position);
    const plateContribution = referenceIncludesBase ? reference - base : reference;
    if (plateContribution < -1e-9) {
      throw Error('The unloaded handle force exceeds the reported reference force. Check the base or the reference assumption.');
    }
    return base + Math.max(0, plateContribution) * load / record.plate_kg;
  }

  function compare(record, settings) {
    const {strength, fraction, share, geometry, continuous} = settings;
    const order = Math.sign(geometry.at(-1)[1] - geometry[0][1]);
    if (!order) throw Error('Start and finish angles must differ.');
    const angles = geometry.map(([p, a]) => [p, a]);
    const arms = geometry.map(([p, a, r]) => [p, r]);
    const curve = continuous && record.resistance_curve;
    const samples = record.points.map(row => row[0]);
    if (curve) samples.push(...curvePositions(curve), ...geometry.map(row => row[0]));
    const positions = [...new Set(samples)].sort((a,b) => a-b);
    const demand = positions.map(p => [
      interpolate(angles, p),
      contactForce(record, p, settings, continuous) * record.gravity * share * interpolate(arms, p)
    ]);
    const sorted = [...demand].sort((a,b) => a[0]-b[0]);
    let knots = demand.map(row => row[0]);
    if (continuous) knots.push(...strength.map(row => row[0]));
    knots = [...new Set(knots)].sort((a,b) => order*(a-b));
    const common = [];
    for (const x of knots) {
      const d = interpolate(sorted, x), c = interpolate(strength, x);
      if (d !== null && c !== null) common.push({x, d, c: c*fraction});
    }
    let crossing = null, hardest = null;
    for (let i=0; i<common.length; i++) {
      const row = common[i], margin = row.c-row.d;
      if (!hardest || row.d/row.c > hardest.d/hardest.c) hardest = row;
      if (crossing === null && margin <= 0) {
        crossing = row.x;
        if (continuous && i) {
          const last = common[i-1], prior = last.c-last.d;
          crossing = last.x + (row.x-last.x)*prior/(prior-margin);
        }
      }
    }
    return {demand, capacity: strength.map(([x,c]) => [x,c*fraction]), crossing, hardest, common};
  }
  return {compare, evaluateCurve, curvePositions, contactForce, plateTotal};
})();
if (typeof module !== 'undefined') module.exports = AtlasModel;
