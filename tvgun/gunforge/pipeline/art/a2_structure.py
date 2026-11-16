"""Independent semantic wall-plane annotations; never inferred from image alpha."""
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from artlib import GAME,write_json
from checks import run
BASE=GAME/'reports/art';REV=BASE/'T07/revisions/A2f';CACHE=Path('D:/gunforge_cache/g01/T04/station')
POLYGONS={'mid_left':[{'id':'upper_wall','points':[[25,75],[300,160],[300,265],[25,195]]},{'id':'shutter_backing','points':[[30,470],[165,500],[165,870],[30,900]]}], 'mid_right':[{'id':'bicycle_wall_backing','points':[[1400,510],[1550,445],[1550,815],[1400,790]]},{'id':'upper_wall','points':[[1660,180],[1860,110],[1860,240],[1660,300]]}]}
def main():
    rows=[]
    for ident,regions in POLYGONS.items():
        im=Image.open(CACHE/'layers'/(ident+'_full.png')).convert('RGBA');mask=Image.new('L',im.size);d=ImageDraw.Draw(mask)
        for r in regions:d.polygon([tuple(p) for p in r['points']],fill=255)
        expected=np.array(mask)>=128;actual=np.array(im)[...,3]>=254;missing=expected&~actual
        # Defect test: independently authored expectation stays unchanged when art is damaged.
        damaged=actual.copy();x,y=regions[0]['points'][0];damaged[y+30:y+46,x+30:x+46]=False;negative=int((expected&~damaged).sum());assert negative>int(missing.sum())
        mask.save(REV/(ident+'_structural_required.png'))
        # Alpha shape and independent required geometry translate identically in
        # each camera state. With no occlusion credited, missing required pixels
        # are rejected even if a foreground object would temporarily hide them.
        states=[];station=json.loads((CACHE/'station.json').read_text(encoding='utf-8'));layer=next(l for l in station['layers'] if l['id']==ident)
        for dx,dy in [(0,0),(-68,-34),(-68,34),(68,-34),(68,34)]:
            step=np.rint(-np.array([dx,dy])*layer['parallax']).astype(int);expected_canvas=Image.new('L',im.size);expected_canvas.paste(mask,tuple(map(int,step)));actual_canvas=Image.new('RGBA',im.size);actual_canvas.alpha_composite(im,tuple(map(int,step)));ex=np.array(expected_canvas)[42:978,72:1848]>=128;al=np.array(actual_canvas)[42:978,72:1848,3]>=254;states.append({'camera_breath':[dx,dy],'missing_required_pixels':int((ex&~al).sum())})
        bg=Image.new('RGBA',im.size,(102,111,122,255));bg.alpha_composite(im);overlay=Image.new('RGBA',im.size);draw=ImageDraw.Draw(overlay)
        for r in regions:draw.polygon([tuple(p) for p in r['points']],fill=(70,210,150,70),outline=(70,230,160,255),width=4)
        bg.alpha_composite(overlay);bg.resize((960,510)).save(REV/(ident+'_structure_review.png'))
        rows.append({'layer':ident,'expected_pixels':int(expected.sum()),'missing_required_pixels':int(missing.sum()),'numeric_status':'pass' if not missing.any() and all(s['missing_required_pixels']==0 for s in states) else 'fail','negative_deleted_wall_detected':True,'regions':regions,'motion_states':states})
    write_json(REV/'structural_geometry_checks.json',{'annotation_version':'g01-wall-planes-1','source':'executor manually annotated wall planes from art/layout; polygons authored in source coordinates, independent of alpha','scope':'four solid architectural regions including shutter and wall behind bicycle; excludes irregular roofs, branches, cutout edges and unannotated geometry','semantic_review':'pending_user_spot_check','full_hidden_geometry_certified':False,'rows':rows});print(json.dumps(rows))
if __name__=='__main__':main()
