"""Offline art processing and transactional, fail-closed generation accounting."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'gunforge/games/g01'

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    def convert(obj):
        if isinstance(obj, np.ndarray):return obj.tolist()
        if isinstance(obj, np.generic):return obj.item()
        if isinstance(obj,(Path,Decimal)):return str(obj)
        raise TypeError(f'Unsupported JSON value: {type(obj).__name__}')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2,default=convert), encoding='utf-8')
    tmp.replace(path)

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def fingerprint(prompt, refs, model, params, pipeline_version, upstream):
    obj = dict(prompt=prompt, refs=[digest(p) for p in refs], model=model,
               params=params, pipeline_version=pipeline_version, upstream=upstream)
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()

def rgba(path):
    return np.asarray(Image.open(path).convert('RGBA')).copy()

def yprime(a):
    return np.asarray(a)[..., :3] @ np.array([.299, .587, .114]) / 255

def mask(path):
    return np.asarray(Image.open(path).convert('L')) >= 128

def disk(radius):
    y, x = np.ogrid[-radius:radius+1, -radius:radius+1]
    return x*x + y*y <= radius*radius

def effective_radius(m):
    opened = ndi.binary_opening(m, structure=disk(12))
    return float(np.sqrt(opened.sum()/np.pi)), opened

def crop_bleed(a, border=8):
    visible = a[..., 3] > 0
    if not visible.any():
        raise ValueError('Empty alpha cannot become a production asset')
    yy, xx = np.nonzero(visible)
    left, top, right, bottom = xx.min(), yy.min(), xx.max()+1, yy.max()+1
    out = np.pad(a[top:bottom, left:right], ((border,border),(border,border),(0,0)))
    solid = out[..., 3] > 0
    _, indices = ndi.distance_transform_edt(~solid, return_indices=True)
    out[~solid, :3] = out[indices[0][~solid], indices[1][~solid], :3]
    return out, [int(left-border), int(top-border)]

def components(a, min_fraction=.002):
    labels, count = ndi.label(a[..., 3] >= 128)
    candidates, rejected = [], []
    for label, sl in enumerate(ndi.find_objects(labels), 1):
        if sl is None:
            continue
        area = int((labels[sl] == label).sum())
        record = dict(label=label, area=area,
                      bbox=[sl[1].start, sl[0].start, sl[1].stop, sl[0].stop])
        (candidates if area >= a.shape[0]*a.shape[1]*min_fraction else rejected).append(record)
    return dict(candidates=candidates, rejected=rejected)

def encode_sdf(m):
    # Pixel centers nearest the boundary lie +/- 0.5 pixel from it.
    d = np.where(m, ndi.distance_transform_edt(m)-.5,
                 -(ndi.distance_transform_edt(~m)-.5))
    return np.rint(np.clip(128 + d*127/32, 0, 255)).astype('uint8')

def decode_sdf(a):
    return (np.asarray(a, dtype=float)-128)*32/127

def matte_birefnet(path, model_path, output):
    """Explicit local ONNX model only; does not download or trust remote code."""
    import onnxruntime as ort
    model_path = Path(model_path)
    if not model_path.is_file():
        raise FileNotFoundError('Configure a local BiRefNet ONNX model before matting')
    session = ort.InferenceSession(str(model_path), providers=['CPUExecutionProvider'])
    source = Image.open(path).convert('RGB')
    inp = session.get_inputs()[0]
    height, width = inp.shape[-2:]
    if not isinstance(height, int) or not isinstance(width, int):
        raise ValueError('Dynamic-size ONNX export needs an explicit adapter')
    a = np.asarray(source.resize((width,height)), dtype='float32')/255
    a = (a - [.485,.456,.406])/[.229,.224,.225]
    prediction = session.run(None, {inp.name:a.transpose(2,0,1)[None].astype('float32')})[-1]
    prediction = np.asarray(prediction).squeeze()
    if prediction.ndim != 2:
        raise ValueError('Unsupported BiRefNet ONNX output shape')
    # This adapter expects logits; capability test must confirm export convention.
    alpha = 1/(1+np.exp(-np.clip(prediction,-50,50)))
    result = source.convert('RGBA')
    result.putalpha(Image.fromarray(np.rint(alpha*255).astype('uint8')).resize(source.size))
    result.save(output)

def micro(amount):
    return int((Decimal(str(amount))*1_000_000).to_integral_value(rounding=ROUND_CEILING))

class Ledger:
    """Budget and manifests share one SQLite transaction; amounts stored as micro-USD."""
    def __init__(self, path, task_caps_cny, usd_cny=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.caps, self.fx = task_caps_cny, usd_cny
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, task TEXT, run TEXT, fingerprint TEXT, attempt INTEGER, reservation INTEGER, actual INTEGER, task_id TEXT, state TEXT, payload TEXT, UNIQUE(fingerprint, attempt))')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def reserve(self, ident, task, run, fp, attempt, worst_usd, payload):
        if self.fx is None or Decimal(str(self.fx)) <= 0:
            raise ValueError('Fixed USD/CNY exchange rate must be configured before paid calls')
        value = micro(worst_usd)
        if value <= 0 or attempt not in range(1,5):
            raise ValueError('Invalid reservation or retry limit exceeded')
        with self.connection() as db:
            existing = db.execute('SELECT fingerprint,attempt FROM attempts WHERE id=?',(ident,)).fetchone()
            if existing:
                if existing != (fp,attempt):
                    raise ValueError('Reservation ID reused for a different request')
                return False
            rows = db.execute('SELECT task,run,reservation,actual FROM attempts').fetchall()
            usage = lambda predicate: sum((r[3] if r[3] is not None else r[2]) for r in rows if predicate(r))
            gates = [(usage(lambda r:True), micro(600)),
                     (usage(lambda r:r[1]==run),micro(20)),
                     (usage(lambda r:r[0]==task),micro(Decimal(str(self.caps[task]))/Decimal(str(self.fx))))]
            if task in {'T02','T03','T04','T05','T06','T07'}:
                gates.append((usage(lambda r:r[0] in {'T02','T03','T04','T05','T06','T07'}),micro(Decimal(300)/Decimal(str(self.fx)))))
            if any(current+value > cap for current,cap in gates):
                raise ValueError('Budget exceeded including in-flight reservations')
            db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,NULL,NULL,?,?)',
                       (ident,task,run,fp,attempt,value,'reserved',json.dumps(payload,ensure_ascii=False)))
        return True

    def submitted(self, ident, provider_task_id):
        with self.connection() as db:
            row=db.execute('SELECT task_id,state FROM attempts WHERE id=?',(ident,)).fetchone()
            if row is None or row[1] not in {'reserved','submitted'}:
                raise ValueError('No active reservation')
            if row[0] is not None and row[0] != provider_task_id:
                raise ValueError('Cannot replace an existing provider task')
            db.execute('UPDATE attempts SET task_id=?,state=? WHERE id=?',(provider_task_id,'submitted',ident))

    def settle(self, ident, actual_usd):
        if Decimal(str(actual_usd)) < 0:
            raise ValueError('Actual cost cannot be negative')
        with self.connection() as db:
            row=db.execute('SELECT actual FROM attempts WHERE id=?',(ident,)).fetchone()
            if row is None:
                raise ValueError('Unknown reservation')
            if row[0] is not None and row[0] != micro(actual_usd):
                raise ValueError('Already settled at a different amount')
            db.execute('UPDATE attempts SET actual=?,state=? WHERE id=?',(micro(actual_usd),'settled',ident))

    def records(self):
        with self.connection() as db:
            db.row_factory=sqlite3.Row
            return [dict(r) for r in db.execute('SELECT * FROM attempts ORDER BY rowid')]

    def recovery(self):
        # Reserved without task_id is ambiguous after a crash: never resubmit automatically.
        return [dict(r, action='poll' if r['task_id'] else 'reconcile_before_resubmit')
                for r in self.records() if r['actual'] is None]
