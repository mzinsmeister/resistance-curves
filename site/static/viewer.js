(() => {
  const el = id => document.getElementById(id);
  const m = JSON.parse(el('record').textContent);
  let comparing = false;
  const fmt = n => Number(n.toFixed(1)).toString();
  const svgNS = 'http://www.w3.org/2000/svg';
  function svgNode(tag, attrs, text) {
    const node = document.createElementNS(svgNS, tag);
    for (const [key,val] of Object.entries(attrs)) node.setAttribute(key,val);
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function chart(series, xlabel, ylabel, marker, reverse) {
    const all = series.flatMap(s => s.points);
    const min = Math.min(...all.map(p=>p[0])), max = Math.max(...all.map(p=>p[0]));
    const rawTop = Math.max(1,...all.map(p=>p[1]));
    const step = 10 ** Math.floor(Math.log10(rawTop));
    const top = Math.ceil(rawTop/step)*step;
    const X = x => 64+540*(reverse ? max-x : x-min)/(max-min || 1);
    const Y = y => 257-205*y/top;
    const svg = svgNode('svg',{viewBox:'0 0 640 323',role:'img','aria-label':ylabel+' by '+xlabel});
    const add = (tag,attrs,t) => svg.append(svgNode(tag,attrs,t));
    add('text',{x:16,y:22},ylabel);
    for (let i=0;i<=4;i++) {
      const val=top*i/4;
      add('line',{x1:64,x2:604,y1:Y(val),y2:Y(val),class:'grid'});
      add('text',{x:54,y:Y(val)+5,'text-anchor':'end'},fmt(val));
      const x=min+i*(max-min)/4;
      add('text',{x:X(x),y:281,'text-anchor':'middle'},fmt(x));
    }
    add('text',{x:334,y:313,'text-anchor':'middle'},xlabel);
    for(const s of series) {
      if(s.line) add('polyline',{points:s.points.map(([x,y])=>X(x)+','+Y(y)).join(' '),
        fill:'none',stroke:s.color,'stroke-width':3,'stroke-dasharray':s.dashed?'7 5':'none'});
      if(!s.line || s.points.length<=15) for(const [x,y] of s.points) {
        const point = svgNode('circle',{cx:X(x),cy:Y(y),r:5,fill:s.color});
        point.append(svgNode('title',{},fmt(x)+' · '+fmt(y)+' '+ylabel));
        svg.append(point);
      }
    }
    if(marker!==null) add('line',{x1:X(marker),x2:X(marker),y1:48,y2:257,stroke:'#ab4236','stroke-width':2,'stroke-dasharray':'3 4'});
    el('chart').replaceChildren(svg);
  }
  const number = (id,min,max=Infinity) => {
    const v=el(id).valueAsNumber;
    if(!Number.isFinite(v)||v<min||v>max) throw Error('Check the value for '+el(id).parentElement.firstChild.textContent.trim()+'.');
    return v;
  };
  function strengthPoints() {
    if(el('strength').value!=='custom') return m.strength[Number(el('strength').value)].points;
    const rows=el('custom').value.trim().split(/\n/).map(line=>line.split(',').map(s=>s.trim()===''?NaN:Number(s)));
    if(rows.length<2 || rows.some((p,i)=>p.length!==2||!p.every(Number.isFinite)||p[0]<0||p[0]>180||p[1]<=0||(i&&p[0]<=rows[i-1][0])))
      throw Error('Enter two or more rows of increasing flexion angle (0–180°) and positive torque (N·m), separated by a comma.');
    return rows;
  }
  const teal='#08746e', gold='#a85614';
  function render() {
    el('controls').hidden=!comparing;
    el('force').setAttribute('aria-pressed',String(!comparing));
    el('compare')?.setAttribute('aria-pressed',String(comparing));
    el('graph-title').textContent=comparing?'Torque demand and strength':'Contact force through the rep';
    el('comparison-source').replaceChildren();
    const sparse=['reported','belt_cam'].includes(m.mechanism);
    try {
      const load=number('load',0);
      const continuous = !sparse || el('interpolate').checked;
      if(!comparing) {
        const series = [];
        if (continuous) {
          const curve = m.resistance_curve;
          const points = AtlasModel.curvePositions(curve).map(p => [p, load * AtlasModel.evaluateCurve(curve, p / 100)]);
          series.push({points, color:teal, line:true, dashed:sparse});
        }
        if (sparse) series.push({points:m.points.map(([x,y])=>[x,y*load/m.plate_kg]),color:teal,line:false});
        chart(series,
          'Travel through lifting stroke (%)','Contact force (kgf)',null,false);
        el('legend').textContent='●  Machine resistance';
        el('result').textContent = sparse
          ? (continuous ? 'The dashed line estimates resistance between recorded positions.' : 'Markers show recorded positions. Enable the fit to estimate the intervening stroke.')
          : 'The fitted curve approximates the calculated machine resistance.';
        return;
      }
      const strength=strengthPoints(), fraction=number('capacity',1,100)/100, share=number('share',1,100)/100;
      let geometry=m.geometry;
      if(!geometry.length) {
        const arm=number('arm',0.001);
        geometry=[[0,number('start',0,180),arm],[100,number('finish',0,180),arm]];
      }
      const r=AtlasModel.compare(m,{load,strength,fraction,share,geometry,continuous});
      chart([{points:r.demand,line:continuous,color:teal,dashed:sparse},
             {points:r.capacity,line:true,color:gold}],
        'Joint flexion angle (°) · lifting direction','Joint torque (N·m)',r.crossing,geometry[0][1]>geometry.at(-1)[1]);
      el('legend').replaceChildren();
      for (const [name,color] of [['●  Machine demand',teal],['●  Available strength',gold]]) {
        const span=document.createElement('span'); span.textContent=name; span.style.color=color; el('legend').append(span);
      }
      const source=el('comparison-source');
      if(el('strength').value==='custom') source.textContent='Personal strength measurements supplied for this session.';
      else {
        const selected=m.strength[Number(el('strength').value)];
        source.textContent=selected.source+' ';
        if(selected.url) {const a=document.createElement('a');a.textContent='Read study';a.href=selected.url;source.append(a);}
      }
      if(!r.hardest) {
        el('result').textContent='No comparable positions. Supply strength measurements covering the machine’s joint angles.'; return;
      }
      const range=fmt(r.common[0].x)+'° to '+fmt(r.common.at(-1).x)+'°';
      const limit=r.crossing===null?'Demand stays below capacity at the compared positions.':
        (continuous?'Modeled strength limit reached by ':'First recorded position at or above capacity: ')+fmt(r.crossing)+'°. ';
      el('result').textContent=limit+' Highest demand relative to strength: '+fmt(100*r.hardest.d/r.hardest.c)+'% at '+fmt(r.hardest.x)+'°. Comparison covers '+range+'.';
    } catch(err) {
      el('chart').replaceChildren(); el('legend').textContent=''; el('result').textContent=err.message;
    }
  }
  for (const [i,s] of m.strength.entries()) el('strength').add(new Option(s.name,String(i)));
  el('strength').add(new Option('Personal measurements','custom'));
  el('strength').value=m.strength.some(s=>s.name.includes('illustrative'))?String(m.strength.findIndex(s=>s.name.includes('illustrative'))):m.strength.length?'0':'custom';
  el('force').onclick=()=>{comparing=false;render();};
  if(el('compare')) el('compare').onclick=()=>{comparing=true;render();};
  function update(){el('custom-panel').hidden=el('strength').value!=='custom';render();}
  document.querySelector('aside').addEventListener('input',update);
  update();
})();
