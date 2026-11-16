"""ID-addressed candidates and compare-and-swap adoption. No implicit git staging."""
import argparse,contextlib,hashlib,json,os,re,tempfile,time,uuid
from pathlib import Path
from compiler import ROOT,DEFAULT_CACHE,CompileError,canonical,digest,read,read_package,compile_source,write_build

STORE=ROOT/'gunforge/level_design'
def process_is_alive(pid):
 if pid<=0:raise CompileError('invalid lock owner PID')
 if os.name=='nt':
  # os.kill(pid, 0) is destructive on Windows; query a process handle instead.
  # https://docs.python.org/3/library/os.html#os.kill
  import ctypes
  from ctypes import wintypes
  api=ctypes.WinDLL('kernel32',use_last_error=True)
  api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
  api.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)];api.GetExitCodeProcess.restype=wintypes.BOOL
  api.CloseHandle.argtypes=[wintypes.HANDLE];api.CloseHandle.restype=wintypes.BOOL
  handle=api.OpenProcess(0x1000,False,pid)
  if not handle:
   if ctypes.get_last_error()==87:return False
   raise CompileError('cannot verify owner PID; lock retained')
  try:
   status=wintypes.DWORD()
   if not api.GetExitCodeProcess(handle,ctypes.byref(status)):raise CompileError('cannot query owner status; lock retained')
   return status.value==259
  finally:api.CloseHandle(handle)
 try:os.kill(pid,0)
 except ProcessLookupError:return False
 except PermissionError:raise CompileError('cannot verify owner PID; lock retained')
 return True
def package_id(value):
 if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*',value):raise CompileError('invalid package ID')
 return value

def immutable(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 payload=canonical(data)+b'\n'
 fd,pending=tempfile.mkstemp(prefix='.record-',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as f:f.write(payload);f.flush();os.fsync(f.fileno())
  try:os.link(pending,path)
  except FileExistsError:
   if path.read_bytes()!=payload:raise CompileError('immutable record collision')
 finally:Path(pending).unlink(missing_ok=True)

def publish(source,store=STORE):
 # Validate before any published directory becomes visible.
 compile_source(source)
 payload=json.dumps(source,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
 revision=digest({'level.json':hashlib.sha256(payload.encode()).hexdigest()})
 revisions=store/'packages'/package_id(source['id'])/'revisions';revisions.mkdir(parents=True,exist_ok=True)
 target=revisions/revision
 if target.exists():
  if (target/'level.json').read_bytes()!=payload.encode('utf-8'):raise CompileError('source collision')
  return target/'level.json'
 # A directory rename publishes the complete source; incomplete .pending dirs are ignored.
 pending=Path(tempfile.mkdtemp(prefix='.pending-',dir=revisions))
 with (pending/'level.json').open('w',encoding='utf-8',newline='\n') as f:f.write(payload);f.flush();os.fsync(f.fileno())
 try:pending.rename(target)
 except OSError:
  if not target.exists() or (target/'level.json').read_bytes()!=payload.encode('utf-8'):raise
  (pending/'level.json').unlink();pending.rmdir()
 return target/'level.json'

def resolve(package,revision,store=STORE):
 if not re.fullmatch('[a-f0-9]{64}',revision):raise CompileError('invalid revision')
 entry=store/'packages'/package_id(package)/'revisions'/revision/'level.json'
 source,manifest=read_package(entry)
 if digest(manifest)!=revision or source['id']!=package:raise CompileError('source manifest mismatch')
 return entry,source,manifest

def patch(package,base,changes,store=STORE,*,preserve=()):
 _,source,_=resolve(package,base,store)
 if changes.get('base_revision')!=base:raise CompileError('stale patch base')
 changed=json.loads(canonical(source))
 if not changes.get('changes'):raise CompileError('empty patch')
 for change in changes['changes']:
  pointer=change['path']
  if not pointer.startswith('/') or pointer=='/id' or pointer.startswith('/schema_version'):raise CompileError('forbidden patch path')
  parts=[p.replace('~1','/').replace('~0','~') for p in pointer[1:].split('/')]
  node=changed
  for key in parts[:-1]:
   if not isinstance(node,dict) or key not in node:raise CompileError('patch traverses missing ID or array')
   node=node[key]
  if not isinstance(node,dict):raise CompileError('array-index patches forbidden; replace the explicit order')
  key=parts[-1];op=change.get('op','replace')
  if op=='add':
   if key in node:raise CompileError('add requires absent ID')
   node[key]=change['value']
  elif op in ['replace','remove']:
   if key not in node or 'expected' not in change or canonical(node[key])!=canonical(change['expected']):raise CompileError('patch test failed: '+pointer)
   if op=='remove':del node[key]
   else:node[key]=change['value']
  else:raise CompileError('unknown patch operation')
 for path in preserve:
  before,after=source,changed
  for key in path[1:].split('/'):
   key=key.replace('~1','/').replace('~0','~')
   if not isinstance(before,dict) or not isinstance(after,dict) or key not in before or key not in after:
    raise CompileError('preserved field missing: '+path)
   before,after=before[key],after[key]
  if canonical(before)!=canonical(after):
   raise CompileError('preserved field changed: '+path)
 target=publish(changed,store)
 receipt={'package':package,'base_revision':base,'source_revision':target.parent.name,'patch':changes,'source':str(target),'state':'candidate_not_adopted'}
 immutable(store/'reviews/candidates'/(digest(receipt)+'.json'),receipt)
 return target

@contextlib.contextmanager
def adoption_lock(package,store):
 path=store/'adopted'/(package+'.lock');path.parent.mkdir(parents=True,exist_ok=True)
 try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
 except FileExistsError:raise CompileError('adoption busy; inspect lock PID before explicit recovery')
 try:
  os.write(fd,canonical({'pid':os.getpid(),'created':time.time()}));os.fsync(fd);os.close(fd);yield
 finally:path.unlink(missing_ok=True)

def adopt(package,revision,expected,reason,actor,store=STORE,cache=None,reviewed_build=None,acknowledged_warnings=()):
 if actor!='user' or not reason.strip():raise CompileError('adoption requires explicit user actor and reason')
 entry,source,manifest=resolve(package,revision,store)
 build=compile_source(source,source_manifest=manifest)
 if reviewed_build is not None and reviewed_build!=build['build_id']:raise CompileError('reviewed build changed; preview the rebuilt candidate first')
 from checks import check
 checks=check(entry);codes={warning['code'] for warning in checks['warnings']}
 if not codes.issubset(set(acknowledged_warnings)):raise CompileError('unacknowledged warnings: '+', '.join(sorted(codes-set(acknowledged_warnings))))
 built=write_build(build,cache or DEFAULT_CACHE)
 with adoption_lock(package,store):
  pointer=store/'adopted'/(package+'.json');previous=read(pointer) if pointer.exists() else None
  actual=previous['source_revision'] if previous else None
  if actual!=expected:raise CompileError('adopted pointer changed; refresh and review')
  transaction=uuid.uuid4().hex
  record={'transaction':transaction,'package':package,'source_revision':revision,'build_id':build['build_id'],'previous_revision':actual,'actor':actor,'reason':reason,'compiled':str(built),'source':str(entry),'time_utc_ns':time.time_ns(),'warnings_acknowledged':sorted(codes),'warning_evidence':checks}
  # Orphan receipts after a crash are harmless; only the atomic pointer is authoritative.
  immutable(store/'reviews/adoptions'/(transaction+'.json'),record)
  pending=pointer.with_suffix('.'+transaction+'.tmp')
  with pending.open('wb') as f:f.write(canonical(record)+b'\n');f.flush();os.fsync(f.fileno())
  os.replace(pending,pointer)
 return record

def main():
 parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
 p=sub.add_parser('patch');p.add_argument('package');p.add_argument('base');p.add_argument('patch_file',type=Path)
 p=sub.add_parser('build');p.add_argument('package');p.add_argument('revision')
 p=sub.add_parser('adopt');p.add_argument('package');p.add_argument('revision');p.add_argument('--expected',default='none');p.add_argument('--reason',required=True);p.add_argument('--actor',choices=['user'],required=True);p.add_argument('--build-id',required=True);p.add_argument('--ack-warning',action='append',default=[])
 p=sub.add_parser('recover-lock');p.add_argument('package');p.add_argument('--pid',type=int,required=True)
 args=parser.parse_args()
 try:
  if args.command=='patch':print(patch(args.package,args.base,read(args.patch_file)))
  elif args.command=='build':
   _,source,manifest=resolve(args.package,args.revision);print(write_build(compile_source(source,source_manifest=manifest),DEFAULT_CACHE))
  elif args.command=='adopt':print(json.dumps(adopt(args.package,args.revision,None if args.expected=='none' else args.expected,args.reason,args.actor,reviewed_build=args.build_id,acknowledged_warnings=args.ack_warning),ensure_ascii=False))
  else:
   path=STORE/'adopted'/(package_id(args.package)+'.lock');lock=read(path)
   if lock['pid']!=args.pid:raise CompileError('lock owner changed')
   if process_is_alive(args.pid):raise CompileError('owner alive; lock retained')
   path.unlink();print('removed stale lock')
 except (CompileError,OSError,KeyError,TypeError) as e:raise SystemExit(str(e))
if __name__=='__main__':main()
