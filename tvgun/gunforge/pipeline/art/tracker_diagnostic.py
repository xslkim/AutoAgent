"""Trace synthetic C13 failures without mutating tracker or its parameters."""
import sys,json
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np
import cv2
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import guntrack as gt
def trace(path):
    im=cv2.imread(str(path));h,w=im.shape[:2];src=np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]);rows=[]
    for index,quad in enumerate([[[80,45],[560,45],[560,315],[80,315]],[[110,65],[540,35],[570,300],[65,320]],[[160,90],[480,75],[490,270],[140,280]]]):
        g=cv2.cvtColor(cv2.warpPerspective(im,cv2.getPerspectiveTransform(src,np.float32(quad)),(640,360)),cv2.COLOR_BGR2GRAY);g=cv2.GaussianBlur(g,(3,3),.6);t=gt.Tracker();thr,low=t._thresholds(g);cands=t._acq_candidates(g,thr,low);details=[]
        for ci,q in cands:
            lines=[];reason=None
            for e in range(4):
                fit=gt._fit_line_band(g,low,q[e],q[(e+1)%4],t.P.band,t.P,cen=q.mean(axis=0))
                if fit is None:reason='edge_fit_'+str(e);break
                lines.append(fit[0])
            if not reason:
                corners=[]
                for k in range(4):
                    cr=np.cross(lines[(k-1)%4],lines[k]);corners.append(cr[:2]/cr[2])
                corners=np.array(corners)
                if not gt._geo_valid(corners):reason='geometry'
                elif not gt._hollow_check(g,corners,low,t.P.acq_dark_frac):reason='interior_brightness'
                elif gt._h_from_corners(corners) is None:reason='homography'
            details.append({'candidate':int(ci),'rejection':reason,'quad':q.tolist()})
        H=t._acquire(g,thr,low);rows.append({'projection':index,'acquired':H is not None,'candidate_count':len(cands),'candidate_diagnostics':details,'low':int(low)})
    return rows
def main():
    out=ROOT/'gunforge/games/g01/reports/art/T07/revisions/A2e';files=[ROOT/'gunforge/games/g01/reports/art/T00/gallery/border_monitor.png']
    # A pure border control constructed with the exact current artwork framing.
    im=np.zeros((1124,1964,3),np.uint8);im[22:1102,22:1942]=255;im[46:1078,46:1918]=0;p=out/'pure_border_control.png';cv2.imwrite(str(p),im)
    cases={'control':p}
    for state in ['unlit','lit']:
        for display in ['monitor','tv']:cases[state+'_'+display]=Path('D:/gunforge_cache/g01/T07')/(state+'_'+display+'_display.png')
    results={name:trace(p) for name,p in cases.items()};(out/'tracker_diagnostic.json').write_text(json.dumps({'scope':'synthetic projections only; tracker source and settings unchanged','cases':results},indent=2),encoding='utf-8');print(json.dumps(results))
if __name__=='__main__':main()
