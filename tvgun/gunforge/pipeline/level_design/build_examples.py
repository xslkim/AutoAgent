"""Rebuild preserved Agent examples against the current locked runtime; keep proposal receipts."""
from pathlib import Path
from compiler import ROOT,DEFAULT_CACHE,read,read_package,compile_source,write_build
from checks import check
from freeze_baseline import dump

def main():
 path=ROOT/'gunforge/level_design/reviews/agent_example_runs.json';index=read(path)
 for example in index['examples'].values():
  # Derive portable source path from stable package/revision, never the recorded machine path.
  old_source=Path(example['source']);package=old_source.parent.parent.parent.name
  source_path=ROOT/'gunforge/level_design/packages'/package/'revisions'/example['source_revision']/'level.json'
  source,manifest=read_package(source_path);build=compile_source(source,source_manifest=manifest);out=write_build(build,DEFAULT_CACHE)
  if example['build_id']!=build['build_id']:
   example.setdefault('prior_runtime_builds',[]).append({'build_id':example['build_id'],'compiled':example['compiled']})
  example.update(source=str(source_path),build_id=build['build_id'],compiled=str(out),checks=check(source_path),runtime_rebuild_reason='Same immutable design rebuilt against current locked software; original proposal receipts preserved.')
 dump(path,index)
 print(path)
if __name__=='__main__':main()
