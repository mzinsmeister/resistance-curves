/* Piecewise-linear quasi-static comparison in lifting order. No extrapolation. */
const AtlasModel = (() => {
  function interpolate(rows, x) {
    if (x < rows[0][0] || x > rows.at(-1)[0]) return null;
    for (let i = 1; i < rows.length; i++) {
      const [a, va] = rows[i - 1], [b, vb] = rows[i];
      if (x <= b) return va + (vb - va) * (x - a) / (b - a);
    }
  }

  function compare(record, settings) {
    const {load, strength, fraction, share, geometry, continuous} = settings;
    const order = Math.sign(geometry.at(-1)[1] - geometry[0][1]);
    if (!order) throw Error('Start and finish angles must differ.');
    const angles = geometry.map(([p, a]) => [p, a]);
    const arms = geometry.map(([p, a, r]) => [p, r]);
    const positions = [...new Set([...record.points, ...geometry].map(row => row[0]))].sort((a,b) => a-b);
    const demand = positions.map(p => [
      interpolate(angles, p),
      interpolate(record.points, p) * record.gravity * load / record.plate_kg * share * interpolate(arms, p)
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
  return {compare};
})();
if (typeof module !== 'undefined') module.exports = AtlasModel;
