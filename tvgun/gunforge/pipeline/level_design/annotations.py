"""Append-only annotation responses. Agents may propose resolution; only users close."""
import argparse,time,uuid
from compiler import ROOT,read,canonical,CompileError,compile_source,read_package
from versions import immutable
def respond(note_path,new_source,message,actor='agent',close=False,store=None):
 note=read(note_path);source,manifest=read_package(new_source);build=compile_source(source,source_manifest=manifest)
 if close and actor!='user':raise CompileError('agent cannot close a user visual issue')
 anchor=note.get('anchor');exists=True
 if isinstance(anchor,str):exists=anchor in build['level']['events']
 elif isinstance(anchor,dict) and anchor.get('source'):
  node=source
  try:
   for key in anchor['source'].strip('/').split('/'):node=node[key]
  except (KeyError,TypeError):exists=False
 status='closed_by_user' if close else ('resolution_proposed' if exists else 'needs_reanchor')
 record={'id':uuid.uuid4().hex,'comment_id':note['comment_id'],'old_build_id':note.get('build_id',note.get('base_build_id')),'new_build_id':build['build_id'],'source_revision':build['source_revision'],'actor':actor,'status':status,'message':message,'time_ns':time.time_ns()}
 immutable((store or ROOT/'gunforge/level_design/reviews/comment_events')/(record['id']+'.json'),record)
 return record
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('note',type=__import__('pathlib').Path);parser.add_argument('new_source',type=__import__('pathlib').Path);parser.add_argument('--message',required=True);parser.add_argument('--actor',choices=['agent','user'],default='agent');parser.add_argument('--close',action='store_true');args=parser.parse_args()
 print(canonical(respond(args.note,args.new_source,args.message,args.actor,args.close)).decode())
