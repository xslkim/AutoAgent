"""Preserve the pre-migration working tree and build an isolated baseline project."""
import argparse, difflib, hashlib, json, os, shutil, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
REVIEWS=ROOT/'gunforge/level_design/reviews'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path,default=Path(os.environ.get('GUNFORGE_LEVEL_CACHE',ROOT.parent/'gunforge_cache/level_design')));args=ap.parse_args()
 base=args.cache/'baseline-v1'
 if base.exists(): raise SystemExit('Baseline already exists; refusing to overwrite evidence')
 raw=base/'original';raw.mkdir(parents=True)
 for folder in ['gunforge/framework','gunforge/games/g01/scripts','gunforge/games/g01/levels','gunforge/games/g01/bible']:
  shutil.copytree(ROOT/folder,raw/folder,ignore=shutil.ignore_patterns('.godot','*.log','__pycache__'))
 for source in ['gunforge/pipeline/build_0b.py','gunforge/start_game.ps1','requirements.txt']:
  target=raw/source;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/source,target)
 manifest={str(p.relative_to(raw)).replace('\\','/'):sha(p) for p in sorted(raw.rglob('*')) if p.is_file()}
 for rel in ['gunforge/games/g01/scripts/alley_rules.gd','gunforge/games/g01/scripts/alley_scene.gd']:
  runtime='gunforge/framework/runtime/'+('game_rules.gd' if rel.endswith('rules.gd') else 'game_scene.gd')
  assert manifest[rel]==manifest[runtime],f'Stale runtime: {runtime}'
 (base/'working_tree.patch').write_bytes(subprocess.check_output(['git','diff','--binary'],cwd=ROOT))
 untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
 for rel in untracked:
  src=ROOT/rel
  if src.is_file():
   target=base/'untracked'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
 project=base/'recording_project';shutil.copytree(raw/'gunforge/framework',project)
 from instrument_baseline import instrument
 source=(project/'main.gd').read_text(encoding='utf-8');s=instrument(source)
 (project/'main.gd').write_text(s,encoding='utf-8')
 (base/'recording_only.patch').write_text(''.join(difflib.unified_diff(source.splitlines(True),s.splitlines(True),fromfile='original/main.gd',tofile='recording/main.gd')),encoding='utf-8')
 dump(base/'source_manifest.json',manifest)
 index={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'status':subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),'original':str(raw),'recording_project':str(project),'manifest':str(base/'source_manifest.json'),'manifest_sha256':sha(base/'source_manifest.json'),'recording_patch_sha256':sha(base/'recording_only.patch'),'files':len(manifest),'untracked_files':untracked,'restore':'Copy original/gunforge/framework to a fresh directory, then Godot --editor --import --quit; run -- --fixed. Recording project changes only input isolation, observation and test ports.'}
 dump(REVIEWS/'baseline_source.json',index);print(json.dumps({'project':str(project),'files':len(manifest)}))
if __name__=='__main__':main()
