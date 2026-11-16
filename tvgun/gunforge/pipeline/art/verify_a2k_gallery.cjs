const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('gunforge/games/g01/reports/art/T07/gallery/index.html','utf8');
const script=html.match(/<script>([\s\S]+)<\/script>/)[1],els=new Map();let decision=null,copied='';
function el(id){if(!els.has(id))els.set(id,{hidden:true,value:'',textContent:'',addEventListener(){}});return els.get(id)}
const ctx={document:{getElementById:el,querySelector:()=>decision,querySelectorAll:()=>[]},navigator:{clipboard:{async writeText(v){copied=v}}}};
vm.createContext(ctx);vm.runInContext(script,ctx);ctx.prepare();assert.ok(el('out').hidden);assert.match(el('err').textContent,/先选择/);
decision={value:'上臂或握持仍有问题，请按补充意见修正'};ctx.prepare();assert.match(el('out').value,/仍有问题/);assert.match(el('out').value,/批量仍等真实0B五项验收/);assert.ok(el('out').value.includes('\n'));
ctx.copy().then(()=>{assert.equal(copied,el('out').value);console.log('A2k script compiles; feedback generation and copying pass in isolated VM.');});
