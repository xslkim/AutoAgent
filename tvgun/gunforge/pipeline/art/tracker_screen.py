"""Read-only adapter for current tracker. Run with existing cv2-capable interpreter."""
import sys
sys.dont_write_bytecode=True
import json
from pathlib import Path
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from guntrack import Tracker,_geo_valid

QUADS = [
    [[80,45],[560,45],[560,315],[80,315]],
    [[100,60],[540,45],[555,305],[75,315]],
    [[160,90],[480,75],[490,270],[140,280]],
    [[110,65],[540,35],[570,300],[65,320]],
]

def acquire_edges(gray, params=None):
    tracker = Tracker(params)
    threshold, low = tracker._thresholds(gray)
    tracker.H = tracker._acquire(gray, threshold, low)
    edges = len(tracker._measure_edges(gray, low)) if tracker.H is not None else 0
    return tracker.H, edges, low

def main():
    frame=cv2.imread(sys.argv[1])
    if frame is None:raise ValueError('Unreadable full display frame')
    h,w=frame.shape[:2]
    src=np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
    # Small deterministic sweep, never a replacement for camera recordings.
    samples=[]
    for quad in QUADS:
        projection=cv2.getPerspectiveTransform(src,np.float32(quad))
        projected=cv2.warpPerspective(frame,projection,(640,360))
        gray=cv2.cvtColor(projected,cv2.COLOR_BGR2GRAY)
        gray=cv2.GaussianBlur(gray,(3,3),.6)
        H,edges,low=acquire_edges(gray)
        admissible=bool(_geo_valid(np.array(quad,dtype=float)))
        samples.append({'acquired':H is not None,'edges':edges,'low_threshold':int(low),'within_tracker_geometry_contract':admissible,'role':'acquisition' if admissible else 'retained_out_of_contract_stress','expected':'acquire_four_edges' if admissible else 'reject_or_acquire_without_acceptance_credit'})
    tested=[s for s in samples if s['within_tracker_geometry_contract']]
    print(json.dumps({'status':'pass' if tested and all(s['acquired'] and s['edges']==4 for s in tested) else 'fail',
                     'reason':'Deterministic projected screenshot screening only; real recordings remain pending',
                     'details':{'samples':samples,'actual_camera_acceptance':'pending','historical_failure':'Original second quad exceeds existing tracker 15-degree opposite-edge divergence; retained as stress, not removed or used to relax tracker'}}))

if __name__=='__main__':main()
