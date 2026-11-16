"""Prepare full-layer design-extent proposals for explicit semantic review."""
import json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy import ndimage as ndi
from artlib import GAME,write_json
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2h';CACHE=Path('D:/gunforge_cache/g01/T04/station')
NAMES={'far_base':'01 远景底纸','far_town':'02 远处城镇','mid_ground':'03 地面','mid_left':'04 左侧商铺','mid_right':'05 右侧商铺','near_left':'06 左侧近景枝叶','near_right':'07 右侧近景枝叶'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    station=json.loads((CACHE/'station.json').read_text(encoding='utf-8'));rows=[];font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22)
    for l in station['layers']:
        if 'extent' not in l:continue
        ident=l['id'];p=CACHE/'layers'/(ident+'_full.png');im=Image.open(p).convert('RGBA');a=np.array(im)[...,3]>=128;mask=Image.fromarray(np.uint8(a)*255);mask.save(REV/(ident+'_extent_proposal.png'))
        # Two representations make hidden alpha visible without painting source art.
        left=Image.new('RGBA',im.size,(116,123,134,255));left.alpha_composite(im);right=Image.new('RGB',im.size,(25,28,42));right.paste((222,216,194),(0,0,im.width,im.height),mask)
        panel=Image.new('RGB',(1200,380),(32,37,52));panel.paste(left.convert('RGB').resize((590,313)),(5,48));panel.paste(right.resize((590,313)),(605,48));d=ImageDraw.Draw(panel);d.text((12,8),NAMES[ident]+' / 独立看整张纸',font=font,fill=(230,216,190));d.text((612,8),'范围提案：浅色有纸，深色为空',font=font,fill=(230,216,190));panel.save(REV/(ident+'_extent_review.jpg'),quality=92)
        # Freeze hashes now: any future asset edit is checked against this versioned
        # proposal only AFTER explicit acceptance of the intended whole silhouette.
        holes=ndi.binary_fill_holes(a)&~a;rows.append({'layer':ident,'name':NAMES[ident],'proposal_mask':str(REV/(ident+'_extent_proposal.png')),'proposal_sha256':sha(REV/(ident+'_extent_proposal.png')),'source_image':str(p),'source_sha256':sha(p),'internal_transparent_pixels':int(holes.sum()),'semantic_status':'pending_explicit_whole_shape_design_acceptance','independent_preexisting_ground_truth':False})
    write_json(REV/'extent_proposals.json',{'version':'g01-alley-full-extent-proposal-1','status':'pending_design_review','purpose':'User must confirm intended complete shape and cutouts, including previously occluded areas. A match to current alpha alone is not completeness verification.','not_automatic_C07b_pass':True,'four_previous_wall_regions':'approved; scope unchanged','rows':rows});print('Seven full-layer extent design proposals prepared, not certified')
if __name__=='__main__':main()
