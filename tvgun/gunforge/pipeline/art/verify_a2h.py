"""Meaningful failure controls for texture sampling and semantic-review gates."""
import json,copy,ast,hashlib
from pathlib import Path
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2h'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    old=read(REV/'mip_sampling_checks.json');new=read(REV/'hybrid_sampling_checks.json');plan=read(REV/'hybrid_texture_plan.json');extent=read(REV/'extent_proposals.json');warning=read(REV/'warning_checks.json')
    assert old['summary']['2']['max_error']>1/255,'Bad local mip scheme must not falsely pass'
    assert new['all_pass'] and all(r['max_premultiplied_channel_error']<1e-5 for r in new['rows'])
    assert plan['conservative_RGBA8_bytes']<=48_000_000
    assert len(extent['rows'])==7 and all(r['semantic_status'].startswith('pending') and not r['independent_preexisting_ground_truth'] for r in extent['rows'])
    for r in extent['rows']:
        assert hashlib.sha256(Path(r['source_image']).read_bytes()).hexdigest()==r['source_sha256'];assert hashlib.sha256(Path(r['proposal_mask']).read_bytes()).hexdigest()==r['proposal_sha256']
    assert warning['status']=='pass_numeric_pending_visual' and warning['effect_approval']=='pending'
    for p in Path(__file__).parent.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
    write_json(REV/'verification.json',{'old_tile_mipmap_failure_retained_and_detected':True,'global_mipmap_CPU_reference_matches':True,'conservative_48_decimal_MB_estimate_pass':True,'all_seven_extent_designs_still_pending':True,'extent_source_hashes_match':True,'warning_numeric_only_not_auto_approved':True,'python_syntax':'pass','engine_and_actual_0B':'pending'});print('A2h sampling failure controls, source hashes, semantic pending gates and syntax passed')
if __name__=='__main__':main()
