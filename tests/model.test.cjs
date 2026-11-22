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
