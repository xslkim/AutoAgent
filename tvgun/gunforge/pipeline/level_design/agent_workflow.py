"""Reviewable external-Agent workflow: evidence -> checked ID patch -> candidate.

Model invocation stays in the current chat. This validates the concrete proposal,
not an assertion that a model or a user has reviewed an image.
"""
import argparse,hashlib,json,time
from pathlib import Path
from compiler import ROOT,DEFAULT_CACHE,read,read_package,compile_source,write_build,CompileError
from versions import patch,immutable
from checks import check
from review_revision import review_context
def propose(task_path,patch_path,store=ROOT/'gunforge/level_design',cache=DEFAULT_CACHE):
 task=read(task_path);proposal=read(patch_path)
 if proposal.get('base_revision')!=task['base_revision']:raise CompileError('proposal uses stale task base')
 review=task.get('review')
 if review is not None:
  original=review_context(Path(review['path']),store,cache)
  if review!=original or any(task[key]!=original[key] for key in ('package','base_revision','request','evidence')):
   raise CompileError('task no longer matches the saved annotation')
 for evidence in task['evidence']:
  path=Path(evidence['path'])
  if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=evidence['sha256']:raise CompileError('missing or changed review evidence')
 allowed=task['allowed_paths']
 for change in proposal['changes']:
  if not any(change['path']==path or change['path'].startswith(path.rstrip('/')+'/') for path in allowed):raise CompileError('change outside requested scope: '+change['path'])
 entry=patch(task['package'],task['base_revision'],proposal,store,preserve=task.get('preserve',[]))
 source,manifest=read_package(entry);build=compile_source(source,source_manifest=manifest);compiled=write_build(build,cache)
 report=check(entry)
 receipt={'id':'proposal-'+str(time.time_ns()),'task':str(task_path),'task_sha256':hashlib.sha256(task_path.read_bytes()).hexdigest(),'patch_sha256':hashlib.sha256(patch_path.read_bytes()).hexdigest(),'base_revision':task['base_revision'],'source_revision':entry.parent.name,'build_id':build['build_id'],'source':str(entry),'compiled':str(compiled),'author':'agent','state':'candidate_not_adopted','checks':report,'preserved':task.get('preserve',[]),'user_feedback':'not inferred; see actual comments separately'}
 receipt['package']=task['package']
 if review is not None:
  receipt['review']=review
  receipt['changes']=proposal['changes']
  if isinstance(proposal.get('summary'),str):
   receipt['summary']=proposal['summary']
 immutable(store/'reviews/agent_proposals'/(receipt['id']+'.json'),receipt)
 return receipt
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('task',type=Path);parser.add_argument('patch',type=Path);args=parser.parse_args()
 try:print(json.dumps(propose(args.task,args.patch),ensure_ascii=False,indent=2))
 except (CompileError,KeyError,TypeError,OSError) as error:raise SystemExit(str(error))
