"""Compiler tests target corrupt sources, event timing and immutable build publication."""
import copy,json,tempfile,unittest
from pathlib import Path
from compiler import CompileError,compile_source,read,read_package,write_build

def level():
 return {'schema_version':1,'id':'test.gallery','ruleset':'gallery@1','seed':421,'tick_hz':60,'duration_ms':10000,'layout':{'width':960,'height':540},'entities':{'t1':{'template':'target','x':300,'y':200,'width':100,'height':80}},'events':{'start':{'trigger':{'at_ms':0},'actions':{'spawn':{'op':'spawn','entity':'t1'}},'order':['spawn'],'max_firings':1}},'queries':{},'resources':{},'cues':{},'initial_resources':{'ammo':4}}
class CompilerTests(unittest.TestCase):
 def test_general_motion_and_effect_contract(self):
  s=level();s['entities']['t1']['motion']={'frames':[{'at_ms':0,'x':10,'y':20},{'at_ms':2000,'x':500,'y':100,'scale':1.5}]}
  s['effects']={'arbitrary_pulse':{'kind':'pulse','duration_ms':500,'color':'#ddbbaa','radius':300}}
  s['events']['start']['actions']['stun']={'op':'stun','entity':'t1','duration_ms':300};s['events']['start']['order'].append('stun')
  s['queries']['local_age']={'op':'entity_age_ms','entity':'t1','space':'scalar','algorithm':'entity-clock60-v1'}
  self.assertIn('local_age',compile_source(s)['level']['queries'])
  s['entities']['t1']['motion']['frames'][1]['at_ms']=0;self.rejected(s)
 def test_bob_bounds_and_sound_binding_rejections(self):
  s=level();s['entities']['t1']['bob']={'amplitude_x':1,'amplitude_y':2,'period_ms':500};self.rejected(s)
  s=level();s['resource_bounds']={'ammo':{'min':5,'max':6}};self.rejected(s)
  s=level();s['presentation']={'sound_bindings':{'cue.started':'recursive'}};self.rejected(s)
 def test_unknown_composite_and_section_references_rejected(self):
  s=level();s['entities']['t1']['parts']={'wing':{'resource':'missing','x':0,'y':0,'width':1,'height':1}};s['entities']['t1']['part_order']=['wing'];self.rejected(s)
  s=level();s['sections']={'test':{'title':'Other game','index':1,'targets':['missing']}};self.rejected(s)
 def test_proven_unreachable_guard_and_zero_window(self):
  s=level();s['events']['start']['guards']=[{'resource':'ammo','compare':'eq','value':1},{'resource':'ammo','compare':'eq','value':2}];self.rejected(s)
  s=level();s['events']['start']['trigger']={'at_ms':1};s['events']['end']={'trigger':{'at_ms':2},'actions':{'remove':{'op':'remove','entity':'t1'}},'order':['remove'],'max_firings':1};self.rejected(s)
 def rejected(self,s):
  with self.assertRaises(CompileError):compile_source(s)
 def test_immutable_build_reproducible(self):
  s=level();a=compile_source(s);self.assertEqual(a,compile_source(copy.deepcopy(s)))
  with tempfile.TemporaryDirectory() as d:
   p=write_build(a,Path(d));self.assertEqual(p,write_build(a,Path(d)));p.write_text('corrupt')
   with self.assertRaises(CompileError):write_build(a,Path(d))
 def test_id_insertion_does_not_rebind_existing(self):
  s=level();original=compile_source(s)['source_map']['start'];s['events']['a_before']={'trigger':{'at_ms':1},'actions':{'emit':{'op':'emit','event':'foo'}},'order':['emit'],'max_firings':1}
  self.assertEqual(compile_source(s)['source_map']['start'],original)
 def test_relative_chain_quantizes_once(self):
  s=level()
  for id,parent in [('b','start'),('c','b')]:s['events'][id]={'trigger':{'after':parent,'delay_ms':1},'actions':{'emit':{'op':'emit','event':id}},'order':['emit'],'max_firings':1}
  mapping=compile_source(s)['source_map'];self.assertEqual(mapping['c']['declared_absolute_ms'],2);self.assertEqual(mapping['c']['tick'],1)
 def test_cycles_missing_refs_unknown_actions(self):
  for mutate in [lambda s:s['events']['start'].update(trigger={'after':'start','delay_ms':1}),lambda s:s['events']['start']['actions']['spawn'].update(entity='missing'),lambda s:s['events']['start']['actions']['spawn'].update(op='eval')]:
   s=level();mutate(s);self.rejected(s)
 def test_invalid_numbers_units_and_window(self):
  for mutate in [lambda s:s.update(duration_ms=1),lambda s:s['entities']['t1'].update(x=float('inf')),lambda s:s.update(tick_hz='60'),lambda s:s['events']['start'].update(trigger={'at_ms':10001})]:
   s=level();mutate(s);self.rejected(s)
 def test_safe_resource_root_and_hash(self):
  s=level();s['resources']['bad']={'path':'../outside','sha256':'0'*64,'kind':'image'};self.rejected(s)
 def test_protected_zone_and_public_fields(self):
  s=level();s['entities']['t1']['template']='protected';s['events']['start']['actions']['spawn']={'op':'permission','entity':'t1','kind':'primary'};self.rejected(s)
  s=level();s['events']['start']['actions']['spawn']={'op':'set','entity':'t1','field':'script','value':'evil'};self.rejected(s)
 def test_fragment_manifest_and_duplicate_ids(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);s=level();fragment={'entities':s.pop('entities')};s['includes']=['entities.json'];(root/'level.json').write_text(json.dumps(s));(root/'entities.json').write_text(json.dumps(fragment));source,manifest=read_package(root/'level.json');self.assertEqual(len(manifest),2);self.assertIn('t1',source['entities']);compile_source(source,source_manifest=manifest)
   s['entities']=fragment['entities'];(root/'level.json').write_text(json.dumps(s))
   with self.assertRaises(CompileError):read_package(root/'level.json')
 def test_duplicate_json_keys(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'bad.json';p.write_text('{"id":"one","id":"two"}')
   with self.assertRaises(CompileError):read(p)
if __name__=='__main__':unittest.main(verbosity=2)
