"""Preserve early CRLF artifacts and add correctly content-addressed aliases.

No original file is changed or removed. Use once for pre-release builder output.
"""
from compiler import ROOT,read_package,digest
from versions import immutable
def repair():
 packages=ROOT/'gunforge/level_design/packages';repairs=[]
 for entry in sorted(packages.glob('*/revisions/*/level.json')):
  _,manifest=read_package(entry);actual=digest(manifest)
  if actual==entry.parent.name:continue
  target=entry.parent.parent/actual
  for name in manifest:
   dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);payload=(entry.parent/name).read_bytes()
   try:
    with dest.open('xb') as file:file.write(payload)
   except FileExistsError:
    if dest.read_bytes()!=payload:raise ValueError('immutable alias collision')
  repairs.append({'original':str(entry),'canonical_alias':str(target/'level.json'),'original_directory_id':entry.parent.name,'actual_source_revision':actual,'reason':'early builder hashed LF text before Windows newline translation; byte-preserving alias'})
 record={'repairs':repairs,'original_files':'preserved unchanged','future_publication':'versions.publish writes sorted JSON with explicit LF; revision hashes the actual published bytes'}
 immutable(ROOT/'gunforge/level_design/reviews/source_layout_repair.json',record)
 return record
if __name__=='__main__':print(repair())
