const test = require('node:test');
const assert = require('node:assert/strict');
const {compare} = require('../site/static/model.js');
const machine={points:[[0,5],[100,15]],gravity:10,plate_kg:10};
const settings={load:10,fraction:1,share:1,strength:[[0,100],[100,100]],geometry:[[0,0,1],[100,100,1]],continuous:true};
test('first crossing and highest demand differ',()=>{
  const result=compare(machine,settings);
  assert.equal(result.crossing,50);
  assert.equal(result.hardest.x,100);
});
test('recorded poses only, no invented midrange failure',()=>{
  assert.equal(compare(machine,{...settings,continuous:false}).crossing,100);
});
test('no crossing at half of shared load',()=>{
  assert.equal(compare(machine,{...settings,share:0.5}).crossing,null);
});
test('descending flexion still follows lifting order',()=>{
  assert.equal(compare(machine,{...settings,geometry:[[0,100,1],[100,0,1]]}).crossing,50);
});
test('no extrapolation beyond strength measurements',()=>{
  const r=compare(machine,{...settings,strength:[[10,100],[30,100]]});
  assert.equal(r.crossing,null);
  assert.equal(r.hardest.x,30);
  assert.equal(compare(machine,{...settings,strength:[[110,100],[130,100]]}).hardest,null);
});

test('continuous comparison uses the polynomial peak between observations', () => {
  const record = {...machine, points:[[0,5],[100,5]],
    resistance_curve:{type:'polynomial',coefficients:[0.5,4,-4]}};
  const result = compare(record, settings);
  assert.equal(result.hardest.x, 50);
  assert.ok(Math.abs(result.crossing - 14.645) < 0.01);
  assert.equal(compare(record,{...settings,continuous:false}).crossing,null);
});

test('local spline coefficients and a narrow interval', () => {
  const {evaluateCurve,curvePositions} = require('../site/static/model.js');
  const curve = {type:'pchip', knots:[0,.001,1], coefficients:[[0,1000],[1,0]]};
  assert.equal(evaluateCurve(curve,.0005),.5);
  assert.equal(evaluateCurve(curve,1),1);
  assert.throws(()=>evaluateCurve(curve,-.1));
  assert.ok(curvePositions(curve).filter(p=>p>0 && p<.1).length >= 10);
});

test('custom decimal plates sum to kilograms; empty machine is an explicit zero', () => {
  const {plateTotal} = require('../site/static/model.js');
  assert.equal(plateTotal('20, 10, 2.5'), 32.5);
  assert.equal(plateTotal('0'), 0);
  for (const invalid of ['', '20,', '-5', '3 kg', '2x20']) {
    assert.throws(() => plateTotal(invalid));
  }
});

test('base is independent of load and reference calibration avoids double counting', () => {
  const {contactForce} = require('../site/static/model.js');
  const inputs = {load:0, baseStart:2, baseFinish:4, referenceIncludesBase:true};
  assert.equal(contactForce(machine, 50, inputs, false), 3);
  assert.equal(contactForce(machine, 50, {...inputs,load:10}, false), 10);
  assert.equal(contactForce(machine, 50, {...inputs,load:20}, false), 17);
  assert.equal(contactForce(machine, 50, {...inputs,load:20,referenceIncludesBase:false}, false), 23);
  assert.throws(() => contactForce(machine, 0, {...inputs,baseStart:6}, false));
});

test('unloaded resistance alone can reach capacity, with limb share applied once', () => {
  const inputs = {...settings, load:0, baseStart:20, share:0.5};
  assert.equal(compare(machine,inputs).crossing,0);
  assert.equal(compare(machine,{...inputs,baseStart:19}).crossing,null);
});

test('reverse calculator solves peak, endpoint, mean, and custom travel loads accurately', () => {
  const {platesForTargetForce, suggestPlates} = require('../site/static/model.js');
  const curveMachine = {
    points: [[0, 5], [100, 15]],
    gravity: 9.80665,
    plate_kg: 10,
    resistance_curve: {type: 'polynomial', coefficients: [0.5, 1.0]},
  };
  const base = {baseStart: 2, baseFinish: 2, referenceIncludesBase: false};
  // Peak ratio is 1.5 at 100%, so target 32 kgf => (32 - 2) / 1.5 = 20 kg
  const peakRes = platesForTargetForce(curveMachine, 32, 'peak', base, true);
  assert.ok(Math.abs(peakRes.requiredKg - 20) < 1e-6);
  assert.equal(peakRes.matchedPct, 100);
  assert.deepEqual(peakRes.suggestedPlates, [20]);

  // Start ratio is 0.5 at 0%, so target 12 kgf => (12 - 2) / 0.5 = 20 kg
  const startRes = platesForTargetForce(curveMachine, 12, 'start', base, true);
  assert.ok(Math.abs(startRes.requiredKg - 20) < 1e-6);

  // Mean ratio is 1.0, so target 27 kgf => (27 - 2) / 1.0 = 25 kg
  const meanRes = platesForTargetForce(curveMachine, 27, 'mean', base, true);
  assert.ok(Math.abs(meanRes.requiredKg - 25) < 1e-6);
  assert.deepEqual(meanRes.suggestedPlates, [25]);

  // Target below base resistance requires 0 plates
  const lowRes = platesForTargetForce(curveMachine, 1.5, 'peak', base, true);
  assert.equal(lowRes.requiredKg, 0);
  assert.equal(lowRes.coveredByBase, true);

  assert.deepEqual(suggestPlates(27.4).plates, [25, 2.5]);
});
