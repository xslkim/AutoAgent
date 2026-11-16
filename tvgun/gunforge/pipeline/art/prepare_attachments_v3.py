"""Register native GPT attachments; resize/anchor preparation, no painted faces."""
import json,hashlib,shutil
from pathlib import Path
import numpy as np
from PIL import Image
from t05_puppets import pins
from artlib import GAME,write_json
from paper_ops import paper_palette

CACHE=Path('D:/gunforge_cache/g01/T05')
def main():
    for role in ['vendor','video']:
        folder=CACHE/role;dest=folder/'attachments_v3';dest.mkdir(exist_ok=True)
        model=json.loads((folder/'puppet.json').read_text(encoding='utf-8'));head=next(n for n in model['parts'] if n['id']=='head');original=Image.open(folder/head['file']).convert('RGBA')
        raw=Image.open(CACHE/(role+'_distress_head_v3_a1.png')).convert('RGBA');a=np.array(raw);box=Image.fromarray(np.uint8(a[...,3]>=128)*255).getbbox();crop=raw.crop(box)
        # Annotated copper neck pivot from the generated image, checked against image.
        pivot_raw={'vendor':[652,907],'video':[641,906]}[role]
        original_box=Image.fromarray(np.uint8(np.array(original)[...,3]>=128)*255).getbbox()
        ratio=(head['pivot'][1]-original_box[1])/(pivot_raw[1]-box[1])
        resized=crop.resize((round(crop.width*ratio),round(crop.height*ratio)),Image.Resampling.LANCZOS)
        resized=paper_palette(resized);resized.save(dest/'distress_head.png')
        pivot=[(pivot_raw[0]-box[0])*ratio,(pivot_raw[1]-box[1])*ratio]
        rawhand=Image.open(CACHE/(role+'_right_palm_v3_a1.png')).convert('RGBA');arr=np.array(rawhand);hb=Image.fromarray(np.uint8(arr[...,3]>=128)*255).getbbox();hc=rawhand.crop(hb)
        # Wrist center at 94% height (inside the wrist tab); palm-facing thumb is +X.
        row=round(hc.height*.94);xx=np.nonzero(np.asarray(hc)[row,:,3]>=128)[0];wp=np.array([xx.mean(),row]);scale=(76 if role=='vendor' else 79)/hc.height
        hand=paper_palette(hc.resize((round(hc.width*scale),round(hc.height*scale)),Image.Resampling.LANCZOS));hand.save(dest/'right_palm.png')
        for name in ['distress_head','right_palm']:shutil.copy2(CACHE/(role+'_'+name+'_v3_a1.png'),dest/(name+'_source.png'))
        write_json(dest/'attachments.json',{'head':{'file':'distress_head.png','pivot':pivot,'native_source':role+'_distress_head_v3_a1.png','source_pivot':pivot_raw,'scale':ratio,'crop':box,'expression':'worried_calling'},'palm':{'file':'right_palm.png','pivot':(wp*scale).tolist(),'native_source':role+'_right_palm_v3_a1.png','scale':scale,'crop':hb,'anatomical_side':'right','view':'palm_facing_viewer','thumb_side_in_upright_image':'right'},'base_pngs_sha256':{n['id']:hashlib.sha256((folder/n['file']).read_bytes()).hexdigest() for n in model['parts']},'acceptance':'pending_A2c_visual_review'})
        print(role,'head',resized.size,'pivot',pivot,'hand',hand.size,flush=True)

if __name__=='__main__':main()
