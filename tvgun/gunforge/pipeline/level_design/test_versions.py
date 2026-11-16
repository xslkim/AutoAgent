import copy,tempfile,unittest
import os
from unittest import mock
from pathlib import Path
from versions import publish,patch,adopt,resolve,CompileError,read,adoption_lock,process_is_alive
from compiler import read_package,digest
ACK=['HUD_UNDECLARED','DISPLAY_PROFILE_UNTESTED','HUMAN_DIFFICULTY_UNCALIBRATED']
from build_gallery import source

class VersionsTests(unittest.TestCase):
 def test_launch_follows_adoption_and_explicit_candidate_does_not(self):
  from resolve_launch import selected_build
  package=self.source['id']
  self.assertIsNone(selected_build(package,store=self.store,cache=self.cache))
  target=patch(package,self.base,self.change(),self.store)
  adopted=adopt(package,target.parent.name,None,'isolated launch test','user',self.store,self.cache,acknowledged_warnings=ACK)
  selected=selected_build(package,store=self.store,cache=self.cache)
  self.assertEqual(read(selected)['source_revision'],adopted['source_revision'])
  self.assertEqual(read(selected)['level']['events']['next']['at_tick'],144)
  before=(self.store/'adopted'/(package+'.json')).read_bytes()
  self.assertIsNone(selected_build(package,True,self.store,self.cache))
  self.assertEqual((self.store/'adopted'/(package+'.json')).read_bytes(),before)
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.store=Path(self.temp.name)/'store';self.cache=Path(self.temp.name)/'cache'
  self.source=copy.deepcopy(source);self.path=publish(self.source,self.store);self.base=self.path.parent.name
 def tearDown(self):self.temp.cleanup()
 def change(self,expected=2000,value=2400):return {'base_revision':self.base,'changes':[{'path':'/events/next/trigger/at_ms','expected':expected,'value':value}]}
 def test_patch_isolation_and_reconstruction(self):
  self.assertEqual(digest(read_package(self.path)[1]),self.base)
  target=patch(self.source['id'],self.base,self.change(),self.store)
  self.assertEqual(read(self.path)['events']['next']['trigger']['at_ms'],2000)
  self.assertEqual(read(target)['events']['next']['trigger']['at_ms'],2400)
  self.assertEqual(target,patch(self.source['id'],self.base,self.change(),self.store))
  self.assertFalse((self.store/'adopted').exists())
  resolve(self.source['id'],target.parent.name,self.store)
 def test_reject_stale_test_and_array_patch(self):
  for changes in [self.change(expected=1999),{'base_revision':'a'*64,'changes':[]},{'base_revision':self.base,'changes':[{'path':'/events/next/order/0','expected':'a0','value':'a0'}]}]:
   with self.assertRaises(CompileError):patch(self.source['id'],self.base,changes,self.store)
 def test_invalid_patch_never_publishes(self):
  before=list((self.store/'packages'/self.source['id']/'revisions').iterdir())
  change={'base_revision':self.base,'changes':[{'path':'/events/next/actions/a0/entity','expected':'target_b','value':'missing'}]}
  with self.assertRaises(CompileError):patch(self.source['id'],self.base,change,self.store)
  self.assertEqual(before,list((self.store/'packages'/self.source['id']/'revisions').iterdir()))
 def test_atomic_adopt_cas_and_rollback(self):
  package=self.source['id'];next_path=patch(package,self.base,self.change(),self.store)
  with self.assertRaises(CompileError):adopt(package,self.base,None,'missing warning acknowledgment','user',self.store,self.cache)
  first=adopt(package,self.base,None,'isolated test only','user',self.store,self.cache,acknowledged_warnings=ACK)
  with self.assertRaises(CompileError):adopt(package,next_path.parent.name,None,'stale','user',self.store,self.cache,acknowledged_warnings=ACK)
  pointer=self.store/'adopted'/(package+'.json');self.assertEqual(read(pointer),first)
  adopt(package,next_path.parent.name,self.base,'isolated next','user',self.store,self.cache,acknowledged_warnings=ACK)
  adopt(package,self.base,next_path.parent.name,'isolated rollback','user',self.store,self.cache,acknowledged_warnings=ACK)
  self.assertEqual(read(pointer)['source_revision'],self.base)
  with adoption_lock(package,self.store):
   with self.assertRaises(CompileError):adopt(package,self.base,self.base,'busy','user',self.store,self.cache,acknowledged_warnings=ACK)
 def test_no_implicit_adoption_and_manifest_tamper(self):
  with self.assertRaises(CompileError):adopt(self.source['id'],self.base,None,'','agent',self.store,self.cache)
  self.path.write_text('{}',encoding='utf-8')
  with self.assertRaises(CompileError):resolve(self.source['id'],self.base,self.store)
 def test_crash_before_pointer_replace_keeps_old_version(self):
  package=self.source['id'];pointer=self.store/'adopted'/(package+'.json')
  adopt(package,self.base,None,'isolated starting version','user',self.store,self.cache,acknowledged_warnings=ACK)
  before=pointer.read_bytes();candidate=patch(package,self.base,self.change(),self.store)
  with mock.patch('versions.os.replace',side_effect=OSError('simulated crash before atomic replace')):
   with self.assertRaises(OSError):adopt(package,candidate.parent.name,self.base,'isolated crash','user',self.store,self.cache,acknowledged_warnings=ACK)
  self.assertEqual(pointer.read_bytes(),before)
  self.assertFalse((self.store/'adopted'/(package+'.lock')).exists())
 def test_process_probe_is_read_only(self):
  self.assertTrue(process_is_alive(os.getpid()))
if __name__=='__main__':unittest.main()
