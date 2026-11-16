const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('gunforge/pipeline/art/t07_gallery.html','utf8');
const script=html.match(/<script>([\s\S]+)<\/script>/)[1];
function harness(saved='{}',clipboard=true){const elems=new Map();let copied='';function el(id){if(!elems.has(id))elems.set(id,{hidden:true,value:'',textContent:'',attrs:{},setAttribute(k,v){this.attrs[k]=v},scrollIntoView(){},focus(){},select(){},querySelectorAll(){return ['ok','revise','brighter','dimmer'].map(v=>({dataset:{value:v},setAttribute(){}}));}});return elems.get(id)}
 const c={document:{getElementById:el,querySelector:()=>el('nav')},localStorage:{getItem:()=>saved,setItem(){}},navigator:clipboard?{clipboard:{async writeText(v){copied=v}}}:{}};vm.createContext(c);vm.runInContext(script,c);return {c,el,get copied(){return copied}};}
(async()=>{let h=harness();h.c.prepareFeedback();assert.equal(h.el('result').hidden,true);assert.match(h.el('error').textContent,/还没选完/);
for(const g of ['scene','people','ink'])h.c.choose(g,'ok');h.c.prepareFeedback();assert.equal(h.el('result').hidden,false);assert.match(h.el('feedback').value,/512/);assert.match(h.el('feedback').value,/不代表A2技术项/);await h.c.copyFeedback();assert.equal(h.copied,h.el('feedback').value);
h.c.choose('scene','revise');h.c.prepareFeedback();assert.equal(h.el('result').hidden,true);assert.match(h.el('error').textContent,/写一句/);h.c.setNotes('把左侧留白放大');h.c.prepareFeedback();assert.match(h.el('feedback').value,/把左侧留白放大/);
h.c.setNotes('新意见');assert.equal(h.el('result').hidden,true);
h=harness('{"scene":"auto_approved","people":"ok","ink":true,"notes":5}');assert.match(h.el('progress').textContent,/1 \/ 3/);
h=harness('{}',false);for(const g of ['scene','people','ink'])h.c.choose(g,'ok');h.c.prepareFeedback();await h.c.copyFeedback();assert.match(h.el('copy-status').textContent,/Ctrl\+C/);
console.log('T07 feedback checks passed: incomplete/revision/draft/copy/fallback; no project approvals written.');})().catch(e=>{console.error(e);process.exitCode=1});
