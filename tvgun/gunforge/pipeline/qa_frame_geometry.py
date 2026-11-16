"""Python reference cases for FRAME-driven normal-coordinate inward sampling."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from guntrack import Tracker, TrackerParams


def main():
    out = ROOT/'out/gunforge0b/frames'
    out.mkdir(parents=True,exist_ok=True)
    results = []
    for i,(white,dark) in enumerate(((24,48),(40,24),(12,72))):
        native = np.zeros((1080,1920),dtype='uint8')
        native[:] = 255
        native[white:1080-white,white:1920-white] = 0
        inset = white+dark
        native[inset:1080-inset,inset:1920-inset] = 130
        frame = np.zeros((360,640),dtype='uint8')
        frame[45:315,80:560] = cv2.resize(native,(480,270),interpolation=cv2.INTER_AREA)
        frame.tofile(out/f'frame_{i}.bin')
        params = TrackerParams()
        params.frame_white,params.frame_dark = white,dark
        tracker = Tracker(params)
        tracker.H = np.array([[4,0,-320],[0,4,-180],[0,0,1]],dtype='float64')
        count = len(tracker._measure_edges(frame,180))
        assert count==4,(white,dark,count)
        results.append({'white':white,'dark':dark,'python_measured_edges':count})
    report = ROOT/'gunforge/games/g01/reports/0B/frame_geometry_python.json'
    report.write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
    print(results)


if __name__=='__main__':
    main()
