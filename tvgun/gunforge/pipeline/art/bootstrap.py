"""Copy specification data to implementation files, never modify source docs."""
import re
import yaml
from pathlib import Path
from artlib import ROOT,GAME,write_json

def main():
    if (Path(__file__).parent/'config.yaml').exists():
        raise FileExistsError('Bootstrap already initialized; preserve configuration and manifests. Run verify.py instead.')
    art=(ROOT/'docs/ART_PLAN_PAPER_LANTERN_CITY.md').read_text(encoding='utf-8')
    game=(ROOT/'docs/GAME01_PAPER_LANTERN_CITY.md').read_text(encoding='utf-8')
    bible=GAME/'bible';bible.mkdir(parents=True,exist_ok=True)
    rigs=bible/'rigs';rigs.mkdir(exist_ok=True)
    template=re.search(r'```yaml\s*\n(template: humanoid_10.*?)```',art,re.S).group(1)
    (rigs/'humanoid_10.yaml').write_text(template,encoding='utf-8')
    colors=re.findall(r'\| ([^|\n]+) \| ([^|\n]+) \| `(#\w{6})` \|',game)
    write_json(bible/'palette.json',{'source':'GAME01 §4.3 / ART_PLAN §2.4',
        'colors':[dict(role=r.strip(),name=n.strip(),hex=h) for r,n,h in colors],
        'level_ratios':{'night':.6,'main':.3,'accent':.1},
        'level_colors':{'l1':{'night':['#141A33','#2A1E3D'],'main':['#D9A066','#C97B84'],'accent':['#B04A9A','#4E9A92']},
                        'l2':{'night':['#2A1E3D','#141A33'],'main':['#B04A9A','#4A90B8'],'accent':['#D9A066']},
                        'l3':{'night':['#141A33'],'main':['#4E9A92','#B8C4D6'],'accent':['#D9A066']}},
        'cinnabar_max_fraction':.01})
    hud={'content_size':[1776,936],'edge_band':60,'reserved':{
        'life':{'rect':[8,832,244,96],'when':'playing'},'ammo':{'rect':[1514,848,254,80],'when':'playing'},
        'score':{'rect':[1624,8,144,144],'when':'playing'},'prompt':{'rect':[572,8,632,104],'when':'playing'},
        'subtitle':{'rect':[288,776,1200,136],'when':'cutscene_or_wave_gap'}},
        'elements':[{'id':'life','pos':[24,848],'size':[212,64],'count':5,'cell':[36,64],'gap':8},
                    {'id':'ammo','pos':[1530,864],'size':[222,48],'count':6,'cell':[32,48],'gap':6},
                    {'id':'score','pos':[1640,24],'size':[112,112]},
                    {'id':'prompt','pos':[588,24],'size':[600,72]}]}
    write_json(GAME/'assets/ui/hud_layout.json',hud)
    caps=[0,5,60,20,60,60,50,0,60,100,150,60,150,150,40,180,0]
    config={'game':'g01','usd_cny':7.0,'exchange_rate_basis':'fixed planning rate, not a live market quotation',
            'cache':'D:/gunforge_cache/g01','task_caps_cny':{f'T{i:02}':v for i,v in enumerate(caps)},
            'run_cap_usd':20,'game_cap_usd':600,'phase_0A_cap_cny':300,
            'checker_version':'art-checks-0.1-un-calibrated',
            'generation':{'mode':'builtin_image_gen','requires_api_key':False,'model':None,
                          'per_batch_call_cap':10,'phase_0A_call_cap':120,
                          'cost_if_unreported':None,'external_api_enabled':False},
            'task_call_caps':{'T00':0,'T01':3,'T02':36,'T03':10,'T04':24,'T05':32,'T06':16,'T07':0,
                              'T08':24,'T09':48,'T10':100,'T11':32,'T12':100,'T13':100,'T14':40,'T15':24,'T16':0},
            'external_budget_enabled':False,
            'providers':{'builtin_image_gen':{'enabled':True,'verified':False,'verification_task':'T01'}},
            'gates':{'T09_requires':'actual_0B_five_checks_approved','offline_previews_are_final_acceptance':False},
            'retry_limits':{'total':4,'visual_or_ocr':1,'style_score':2}}
    (Path(__file__).parent/'config.yaml').write_text(yaml.safe_dump(config,allow_unicode=True,sort_keys=False),encoding='utf-8')
    for folder in ['style_refs','rigs']:(bible/folder).mkdir(exist_ok=True)
    Path('D:/gunforge_cache/g01/T00').mkdir(parents=True,exist_ok=True)
    write_json(GAME/'assets/manifest.json',{'schema_version':1,'frozen':False,'assets':[],
        'notes':'hud_layout.json is deterministic specification data; generated assets require human approval'})
    (GAME/'reports/art/T00').mkdir(parents=True,exist_ok=True)

if __name__=='__main__':main()
