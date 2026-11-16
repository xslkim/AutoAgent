const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('gunforge/games/g01/reports/art/T07/gallery/index.html','utf8');
const script=html.match(/<script>([\s\S]+)<\/script>/)[1],els=new Map();let decision=null,copied='';
function el(id){if(!els.has(id))els.set(id,{hidden:true,value:'',textContent:'',addEventListener(){},focus(){},select(){}});return els.get(id)}
const ctx={document:{getElementById:el,querySelector:()=>decision,querySelectorAll:()=>[]},navigator:{clipboard:{async writeText(v){copied=v}}}};
vm.createContext(ctx);vm.runInContext(script,ctx);ctx.prepare();assert.equal(el('result').hidden,true);
decision={value:'revise'};ctx.prepare();assert.equal(el('result').hidden,true);
el('notes').value='先改问题';ctx.prepare();assert.match(el('feedback').value,/继续留在 T07/);assert.ok(!el('feedback').value.includes('允许进入 T08'));
decision={value:'continue'};el('notes').value='';ctx.prepare();assert.match(el('feedback').value,/允许进入 T08 离线试做/);assert.match(el('feedback').value,/不登记为 A2 全技术通过/);assert.match(el('feedback').value,/批量仍等真实0B五项验收/);assert.match(el('feedback').value,/C04\/C12\/C14/);
assert.equal((html.match(/type="radio"/g)||[]).length,2);assert.ok(!/<input[^>]*\schecked/.test(html));
for(const src of [...html.matchAll(/(?:src|poster)="([^"]+)"/g)].map(m=>m[1]))assert.ok(fs.existsSync('gunforge/games/g01/reports/art/T07/gallery/'+src),src);
ctx.copy().then(()=>{assert.equal(copied,el('feedback').value);console.log('A2i review checks passed: stage boundary, retained gaps, 2 unselected options, media files present, no user draft touched.');});
