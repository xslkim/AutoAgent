import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from agent_workflow import propose,CompileError
from versions import publish
from build_gallery import source
from compiler import compile_source, read, read_package, write_build
from review_revision import prepare, preview
class AgentWorkflowTests(unittest.TestCase):
 def test_review_note_binds_archived_build_evidence_and_comparison(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   store,cache=root/'store',root/'cache'
   entry=publish(copy.deepcopy(source),store)
   level,manifest=read_package(entry)
   base=compile_source(level,source_manifest=manifest)
   base_path=write_build(base,cache)
   evidence={}
   for role in ('player','alpha','recording'):
    file=root/role
    file.write_bytes(role.encode())
    evidence[role]={'path':str(file),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
   note={
    'comment_id':'test-note','source_revision':base['source_revision'],'build_id':base['build_id'],
    'tick':120,'anchor':'next','text':'Delay the next target','status':'open','author':'test_harness',
    'evidence':evidence,
   }
   annotation,task,edit=(root/name for name in ('note.json','task.json','edit.json'))
   annotation.write_text(json.dumps(note),encoding='utf-8')
   field='/events/next/trigger/at_ms'
   prepared=prepare(annotation,task,[field],['/entities/protected_a'],store,cache)
   self.assertEqual(prepared['review']['source_pointer'],'/events/next/trigger')
   edit.write_text(json.dumps({'base_revision':base['source_revision'],'changes':[
    {'path':field,'expected':2000,'value':4000}
   ]}),encoding='utf-8')
   note['text']='Changed after task creation'
   annotation.write_text(json.dumps(note),encoding='utf-8')
   with self.assertRaisesRegex(CompileError,'no longer matches'):
    propose(task,edit,store,cache)
   note['text']='Delay the next target'
   annotation.write_text(json.dumps(note),encoding='utf-8')
   receipt=propose(task,edit,store,cache)
   self.assertEqual(receipt['review']['comment_id'],'test-note')
   comparison=preview(store/'reviews/agent_proposals'/(receipt['id']+'.json'),store,cache)
   self.assertEqual(comparison['base'],str(base_path))
   self.assertEqual(comparison['tick'],120)
   self.assertEqual(read(Path(comparison['candidate']))['level']['events']['next']['trigger']['at_ms'],4000)
   self.assertEqual(read(entry)['events']['next']['trigger']['at_ms'],2000)
   self.assertFalse((store/'adopted').exists())
   (root/'alpha').write_bytes(b'tampered')
   with self.assertRaisesRegex(CompileError,'changed review evidence'):
    propose(task,edit,store,cache)

 def test_scope_invariants_evidence_and_candidate(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);store=root/'store';entry=publish(copy.deepcopy(source),store);evidence=root/'frame.txt';evidence.write_text('test-only evidence')
   task={'package':source['id'],'base_revision':entry.parent.name,'evidence':[{'path':str(evidence),'sha256':hashlib.sha256(evidence.read_bytes()).hexdigest()}],'allowed_paths':['/events/next/trigger/at_ms'],'preserve':['/entities/protected_a']}
   patch={'base_revision':entry.parent.name,'changes':[{'path':'/events/next/trigger/at_ms','expected':2000,'value':4000}]}
   t=root/'task.json';p=root/'patch.json'
   def save():t.write_text(json.dumps(task));p.write_text(json.dumps(patch))
   save();result=propose(t,p,store);self.assertEqual(result['state'],'candidate_not_adopted');self.assertFalse((store/'adopted').exists())
   task['preserve']=['/events/next/trigger/at_ms'];save()
   with self.assertRaises(CompileError):propose(t,p,store)
   task['preserve']=[];task['allowed_paths']=['/entities/target_a'];save()
   with self.assertRaises(CompileError):propose(t,p,store)
   evidence.write_text('changed');save()
   with self.assertRaises(CompileError):propose(t,p,store)
if __name__=='__main__':unittest.main()
