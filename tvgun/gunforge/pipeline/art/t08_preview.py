"""Render and measure the T08 offline alley sequence at native content coordinates."""
import argparse
import json
import math
import subprocess
import sys
from contextlib import ExitStack

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

from artlib import ROOT, write_json, yprime
from materials import hardened_eyes
from preview import CONTENT
from t08_assets import PACK, REPORT, read

sys.path.insert(0, str(ROOT/'art2d/tools/qa'))
from render import Preview

FPS, DURATION = 15, 36
GALLERY = REPORT/'gallery'
W, H = CONTENT
FONT = 'C:/Windows/Fonts/msyh.ttc'
AMBER = (217, 160, 102)
CUES = {'lamp': 4.8, 'crow_hit': 9.7, 'crow_clear': 12.4, 'rescue': 15,
        'light': 19, 'wick': 22, 'relight': 27, 'transition': 32}


def rgba(path):
    with Image.open(path) as im:
        return im.convert('RGBA')


def smooth(x):
    x = min(1, max(0, x))
    return x*x*(3-2*x)


def composite(size, items):
    image = Image.new('RGBA', size)
    for sprite, point in items:
        image.alpha_composite(sprite, point)
    return image


def opacity(sprite, amount):
    im = sprite.copy()
    im.putalpha(sprite.getchannel('A').point(lambda a: round(a*amount)))
    return im


def radius(mask):
    # Equivalent to opening by the art checker's 12px disk.
    padded = np.pad(mask, 12)
    eroded = ndi.distance_transform_edt(padded) > 12
    if not eroded.any():
        return 0.
    return float(np.sqrt((ndi.distance_transform_edt(~eroded) <= 12).sum()/np.pi))


class Station:
    def __init__(self):
        folder = PACK/'station'
        model = read(folder/'station.json')
        self.origin = np.array(model['content_origin'])
        self.layers = [(item, rgba(folder/item['file'])) for item in
                       sorted(model['layers'], key=lambda layer: layer['z'])]
        self.lamp = next((item, im) for item, im in self.layers if item['id'] == 'lamp')
        self.shade_box = (497, 253, 697, 373)
        self.shade = self.lamp[1].crop(self.shade_box).getchannel('A')
        light = model['lights'][0]
        self.spill = Image.open(folder/light['spill']).convert('L')
        self.glow = rgba(folder/light['glow'])
        self.color = np.array(list(bytes.fromhex(light['color'][1:])), dtype='float32') * light['intensity']
        self.covers = [rgba(PACK/f'ink_on_lamp/cover_{i:02d}.png').resize((151,94), Image.Resampling.LANCZOS)
                       for i in range(3)]

    def point(self, t):
        camera = np.array([55*math.sin(t*.58), 27*math.sin(t*.81)])
        breath = np.array([8*math.sin(t*1.27), 4*math.sin(t*1.71)])
        return camera, breath

    def exposure(self, point, shift, amount):
        px = tuple(np.rint(point + self.origin + shift*self.lamp[0]['parallax']).astype(int))
        return self.spill.getpixel(px)/255*amount

    def frame(self, shift, amount, cover_index):
        under, over = [], []
        for layer, image in self.layers:
            pos = tuple(np.rint(np.array(layer['pos']) - self.origin - shift*layer['parallax']).astype(int))
            (over if layer.get('blocks_shots') else under).append((image, pos))
            if layer['id'] == 'lamp':
                shade_at = (pos[0]+self.shade_box[0], pos[1]+self.shade_box[1])
        bg = composite(CONTENT, under)
        dx, dy = np.rint(self.origin + shift*self.lamp[0]['parallax']).astype(int)
        box = (dx, dy, dx+W, dy+H)
        if amount > 0:
            pix = np.array(bg)
            rgb = pix[..., :3].astype('float32')
            rgb += np.asarray(self.spill.crop(box), dtype='float32')[..., None] * (self.color*amount/255)
            glow = np.asarray(self.glow.crop(box), dtype='float32')
            rgb += glow[..., :3]*(glow[..., 3:]/255*amount)
            pix[..., :3] = np.clip(rgb, 0, 255).astype('uint8')
            bg = Image.fromarray(pix)
        if amount < 1:
            cover = composite(self.shade.size, [(self.covers[cover_index], (24,16))])
            a = np.minimum(np.asarray(cover.getchannel('A')), np.asarray(self.shade))
            cover.putalpha(Image.fromarray(np.rint(a*(1-amount)).astype('uint8')))
            bg.alpha_composite(cover, shade_at)
        return bg, over, shade_at


def resident_frames(times):
    sampler = """
import {read} from './pipeline/export/build.mjs';
import {world, sample, attachmentAt} from './pipeline/rig/runtime.mjs';
const dir = process.argv[1];
const {rig, clips} = read(dir+'/character.json');
const requests = JSON.parse(process.argv[2]);
const files = Object.fromEntries(Object.entries(clips).map(([k,v]) => [k,read(dir+'/'+v)]));
const frames = requests.map(([name,t]) => {
  const clip = files[name];
  const time = clip.meta.loop ? (t % clip.duration) : Math.min(t,clip.duration);
  return {w:world(rig,sample(clip,time,false)),attachments:rig.attachments.map(s=>attachmentAt(s,clip,time))};
});
console.log(JSON.stringify({rig,frames}));
"""
    rescue = CUES['rescue']
    requests = [('struggle', t) if t < rescue else ('rescued_bounce', t-rescue) if t < rescue+2.3
                else ('thank', t-rescue-2.3) for t in times]
    data = json.loads(subprocess.check_output(
        ['node','--input-type=module','-e',sampler,str(PACK/'vendor'),json.dumps(requests,separators=(',',':'))],
        cwd=ROOT/'art2d', encoding='utf-8'))
    renderer = Preview(data['rig'], rgba(PACK/'vendor/atlas.png'))
    renderer.size, renderer.origin = (430,560), (210,532)
    renderer.scale = 512/data['rig']['height']
    return renderer, data['frames']


class Crow:
    def __init__(self):
        folder = PACK/'crow'
        model = read(folder/'enemy.json')
        self.size = 264
        self.scale = self.size/1024
        self.sprites = {}
        for key in ('body', 'core', 'core_hardened'):
            spec = model['files'][key]
            im = rgba(folder/spec['file'])
            if key == 'core_hardened':
                im = hardened_eyes(im, model)
            full = composite((1024,1024), [(im, tuple(spec['crop_origin']))])
            self.sprites[key] = full.resize((self.size,self.size), Image.Resampling.LANCZOS)
        self.stamp = np.array(model['core_center'])*self.scale
        a = np.asarray(self.sprites['body'].getchannel('A'))
        self.distance = ndi.distance_transform_edt(a >= 128)
        self.noise = ndi.gaussian_filter(np.random.default_rng(421).normal(size=a.shape), 1.4)*8

    def frame(self, t, lit):
        defeat = t-CUES['crow_clear']
        hit = t-CUES['crow_hit']
        recoil = 0 if hit < 0 else math.exp(-7*max(0,hit-.10))*math.cos(12*max(0,hit-.10))
        body = self.sprites['body'].copy()
        warning = 2.6 <= t < 4.65
        key = 'core' if lit or warning else 'core_hardened'
        mark = self.sprites[key].copy()
        pulse = .5+.5*math.sin(t*math.tau*1.5)
        if warning:
            mark = opacity(mark, .35+.65*pulse)
        if defeat >= 0:
            fraction = np.clip((self.distance+self.noise-defeat*75+2)/4, 0, 1)
            body.putalpha(Image.fromarray(np.rint(np.asarray(body.getchannel('A'))*fraction).astype('uint8')))
        box = (round(self.size*(1-.14*recoil)),round(self.size*(1+.10*recoil)))
        body = body.resize(box, Image.Resampling.BICUBIC)
        mark = mark.resize(box, Image.Resampling.BICUBIC)
        mark.putalpha(Image.fromarray(np.minimum(np.asarray(mark.getchannel('A')), np.asarray(body.getchannel('A')))))
        alpha = body.getchannel('A')
        stamp = np.asarray(mark.getchannel('A')) >= 128
        body.alpha_composite(mark)
        p = (self.stamp*np.array(box)/self.size).astype(int)
        if warning:
            fx = Image.new('RGBA', body.size)
            r = 18+8*pulse
            ImageDraw.Draw(fx).ellipse((*list(p-r),*list(p+r)), outline=(*AMBER,round(105+110*pulse)), width=3)
            body.alpha_composite(fx)
        state = 'dissolving' if defeat >= 0 else 'warning' if warning else 'normal' if lit else 'hardened'
        eye_metrics = None
        if state == 'hardened':
            labels, _ = ndi.label(stamp)
            eyes = sorted(ndi.find_objects(labels), key=lambda box: -(box[1].stop-box[1].start))[:2]
            surrounding = (np.asarray(alpha)>=128) & ndi.binary_dilation(stamp,iterations=5) & ~stamp
            eye_metrics = {
                'minimum_width': min((b[1].stop-b[1].start for b in eyes), default=0) if len(eyes)==2 else 0,
                'contrast': float(np.median(yprime(np.asarray(body))[stamp]) -
                                  np.median(yprime(np.asarray(body))[surrounding])),
            }
        return body, alpha, stamp, p, state, eye_metrics


def hud(frame, t, fonts, images, layout, cursor):
    layer = Image.new('RGBA', CONTENT)
    for element in layout['elements']:
        ident, pos, size = element['id'], element['pos'], element['size']
        if ident in {'life','ammo'}:
            key = 'life_wick' if ident == 'life' else 'ammo_light'
            cells = element['count']
            count = (4 if 8 <= t < CUES['wick'] else 5) if ident == 'life' else (
                6 if t < CUES['lamp'] or CUES['light'] <= t < CUES['relight'] else 4)
            w, h = element['cell']
            for index in range(cells):
                sprite = images[key if index<count else key+'_empty']
                layer.alpha_composite(sprite, (pos[0]+index*(w+element['gap']),pos[1]))
        elif ident == 'score':
            layer.alpha_composite(images['score_seal'], tuple(pos))
            score = 500*sum(t >= CUES[event] for event in ('lamp','crow_clear','rescue'))
            ImageDraw.Draw(layer).text((pos[0]+size[0]//2,pos[1]+size[1]//2), str(score),
                                       font=fonts[0], anchor='mm', fill=(228,179,132,255))
        elif 30 <= t < 31.7:
            layer.alpha_composite(images['prompt_bar'], tuple(pos))
            ImageDraw.Draw(layer).text((W//2,60), '请对准屏幕', font=fonts[1], anchor='mm', fill=(235,219,188,255))
    if cursor is not None:
        layer.alpha_composite(images['crosshair'], tuple(round(v-20) for v in cursor))
    frame.alpha_composite(layer)


def aim_cue(t, marks):
    active = [(abs(t-CUES[k]), k) for k in marks if -1.15 <= t-CUES[k] < .35]
    return marks[min(active)[1]] if active else None


def sparks(frame, t, marks):
    layer = Image.new('RGBA', CONTENT)
    draw = ImageDraw.Draw(layer)
    for key, xy in marks.items():
        dt = t-CUES[key]
        if not 0 <= dt < .62:
            continue
        p = np.array(xy)
        reach = 15+dt*104
        alpha = round(240*(1-dt/.62))
        for i in range(10):
            angle = i*math.tau/10+.23
            v = np.array([math.cos(angle), math.sin(angle)])
            draw.line((*list(p+v*reach*.62), *list(p+v*reach)), fill=(*AMBER,alpha), width=3)
        draw.ellipse((*list(p-reach*.55),*list(p+reach*.55)), outline=(*AMBER,alpha), width=2)
    frame.alpha_composite(layer)


def target(name, alpha, at, front):
    x, y = at
    mask = np.asarray(alpha, dtype='float32')
    blockers = np.asarray(front.crop((x,y,x+alpha.width,y+alpha.height)).getchannel('A'), dtype='float32')
    return name, (mask*(1-blockers/255)) >= 128, at


def bounds(mask, at):
    ys, xs = np.nonzero(mask)
    if not xs.size:
        return None
    return (int(xs.min()+at[0]),int(ys.min()+at[1]),int(xs.max()+at[0]+1),int(ys.max()+at[1]+1))


def intersects(a, b):
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])


def stats(targets, layout, overlay, shot_time, paper_body):
    draw = ImageDraw.Draw(overlay)
    pad = 60
    draw.rectangle((pad,pad,W-pad,H-pad), outline='#d6a462', width=2)
    reserved = []
    for name, entry in layout['reserved'].items():
        if entry['when'] != 'playing':
            continue
        x,y,w,h = entry['rect']
        reserved.append((x,y,x+w,y+h))
        draw.rectangle(reserved[-1], outline='#eed184', width=2)
        draw.text((x+3,y+2), name, fill='#eed184')
    if paper_body:
        draw.rectangle(paper_body, outline='#a0d9ad', width=2)
        draw.text((paper_body[0],paper_body[3]+5), 'protected paper resident', fill='#a0d9ad')
    records = []
    for name, mask, at in targets:
        rect = bounds(mask, at)
        r = radius(mask)
        in_safe = bool(rect and rect[0] >= pad and rect[1] >= pad and rect[2] <= W-pad and rect[3] <= H-pad)
        hud_clear = bool(rect and not any(intersects(rect, b) for b in reserved))
        human_clear = bool(not rect or not paper_body or name == 'chest_ink' or not intersects(rect,paper_body))
        records.append({'id':name,'bbox':rect,'effective_radius':round(r,3),
                        'edge_clear':in_safe,'hud_clear':hud_clear,'human_clear':human_clear})
        color = (232,110,87,255)
        edge = mask & ~ndi.binary_erosion(mask, iterations=2)
        outline = Image.new('RGBA', (mask.shape[1],mask.shape[0]), color)
        outline.putalpha(Image.fromarray(edge.astype('uint8')*230))
        overlay.alpha_composite(outline, at)
        if rect:
            draw.rectangle(rect, outline=color, width=2)
            draw.text((rect[0],rect[1]-15),f'{name} {r:.1f}px',fill=color)
    overlaps = [(a['id'],b['id']) for i,a in enumerate(records) for b in records[i+1:]
                if a['bbox'] and b['bbox'] and intersects(a['bbox'],b['bbox'])]
    draw.text((65, H-54),f'T08  {shot_time:05.2f}s  /  red = visible hit mask, green = protected paper',fill='white')
    return records, overlaps


def writer(path, stack):
    obj = imageio_ffmpeg.write_frames(str(path), (888,468), fps=FPS, codec='libx264',
                                      pix_fmt_in='rgb24', macro_block_size=1,
                                      output_params=['-crf','19','-movflags','+faststart'])
    obj.send(None)
    stack.callback(obj.close)
    return obj


def main(still):
    GALLERY.mkdir(parents=True, exist_ok=True)
    times = [2.9,5.8,6.8,8,10,13.4,15.3,18.2,21.3,24.4,26.4,30.8,32.7,35.5] if still else [
        i/FPS for i in range(FPS*DURATION)]
    vendor, poses = resident_frames(times)
    station, crow = Station(), Crow()
    layout = read(PACK/'ui/hud_layout.json')
    dimensions = {'life_wick':(36,64),'life_wick_empty':(36,64),'ammo_light':(32,48),'ammo_light_empty':(32,48),
                  'score_seal':(112,112),'prompt_bar':(600,72),'crosshair':(40,40),'continue_panel':(480,320)}
    images = {k:rgba(PACK/f'ui/{k}.png').resize(v,Image.Resampling.LANCZOS) for k,v in dimensions.items()}
    images['crosshair'] = opacity(images['crosshair'], .7)
    pickups = {key:rgba(PACK/f'pickups/pickup_{key}.png').resize((112,112),Image.Resampling.LANCZOS)
               for key in ('light','wick')}
    fonts = (ImageFont.truetype(FONT,31),ImageFont.truetype(FONT,34))
    rows = []
    with ExitStack() as stack:
        if not still:
            clean_writer, debug_writer = (writer(GALLERY/f'{name}.mp4', stack) for name in ('alley_sample','alley_overlay'))
        for index,(t,pose) in enumerate(zip(times,poses)):
            cam, breath = station.point(t)
            shift = cam+breath
            light = smooth((t-CUES['lamp'])/.65)*(1-smooth((t-23)/1.1))
            light = max(light, smooth((t-CUES['relight'])/.6))
            cover = 0 if t<23 else (1 if t<25.5 else 2)
            frame, near, lamp_at = station.frame(shift, light, cover)
            front = composite(CONTENT, near)
            targets, marks = [], {}
            lamp_xy = np.array(lamp_at)+np.array([99,65])
            if t < CUES['lamp'] or 24.1 <= t < CUES['relight']:
                targets.append(target('lamp', station.shade, lamp_at, front))
            marks.update(lamp=lamp_xy, relight=lamp_xy)

            shadow = Image.new('RGBA', CONTENT)
            vendor_at = tuple(np.rint(np.array([735,830])-shift*.45-np.array(vendor.origin)).astype(int))
            ground = np.array(vendor_at)+np.array(vendor.origin)
            ImageDraw.Draw(shadow).ellipse((ground[0]-62,ground[1]-8,ground[0]+62,ground[1]+9),fill=(24,17,36,105))
            frame.alpha_composite(shadow)
            paper = vendor.art(pose)
            frame.alpha_composite(paper, vendor_at)
            ink_index = next((i for i, s in enumerate(pose['attachments']) if s and s['part']=='rescue_ink'), None)
            if ink_index is not None:
                slots = pose['attachments']
                ink = vendor.art({**pose,'attachments':[s if i==ink_index else None for i,s in enumerate(slots)]})
                hand = vendor.art({**pose,'attachments':[s if i>ink_index else None for i,s in enumerate(slots)]})
                a = np.asarray(ink.getchannel('A'), dtype='float32')
                a *= 1-np.asarray(hand.getchannel('A'), dtype='float32')/255
                ink_alpha = Image.fromarray(a.astype('uint8'))
                if t < CUES['rescue']:
                    targets.append(target('chest_ink', ink_alpha, vendor_at, front))
            xy = vendor.xy(pose['w']['ink_anchor']['x'],pose['w']['ink_anchor']['y'])
            marks['rescue'] = np.array(xy)+vendor_at
            paper_bounds = bounds(np.asarray(paper.getchannel('A'))>=128,vendor_at)

            weak_outside = 0
            crow_readability = None
            if 1.6 <= t < CUES['crow_clear']+1.3:
                approach = smooth((t-5.25)/2.4)
                pos = np.array([1110+210*approach+7*math.sin(t*2),351+199*approach+7*math.sin(t*2.7)])-shift*.45
                exposure = station.exposure(pos, shift, light)
                bird, alpha, stamp, stamp_xy, state, eye_metrics = crow.frame(t, exposure >= .30)
                recoil_time = t-CUES['crow_hit']
                if recoil_time >= 0:
                    decay = max(0,recoil_time-.10)
                    pos[0] += 20*math.exp(-7*decay)*math.cos(12*decay)
                at = tuple(np.rint(pos - np.array(bird.size)/2).astype(int))
                bird_target = target('crow', alpha, at, front)
                weak_outside = int((stamp & ~bird_target[1]).sum())
                if t < CUES['crow_clear']:
                    mask = bird_target[1]
                    patch = frame.crop((at[0],at[1],at[0]+bird.width,at[1]+bird.height))
                    background = yprime(np.asarray(patch))[mask]
                    crow_readability = {'state':state,'exposure':exposure,'background':float(np.median(background)),
                                        'body_contrast':float(np.median(abs(yprime(np.asarray(bird))[mask]-background))),
                                        'eyes':eye_metrics}
                    targets.append(bird_target)
                frame.alpha_composite(bird,at)
                marks['crow_hit'] = marks['crow_clear'] = np.array(at)+stamp_xy

            for key, point, start in (('light',(1055,677),17.5),('wick',(1195,688),20.5)):
                if start <= t < CUES[key]+.62:
                    dt = t-CUES[key]
                    p = np.array(point)-shift*.45+[0,-4*math.sin(t*4)-max(0,dt)*75]
                    at = tuple(np.rint(p-56).astype(int))
                    sprite = pickups[key]
                    if dt < 0:
                        targets.append(target(key, sprite.getchannel('A'), at, front))
                    else:
                        sprite = opacity(sprite, max(0,1-dt/.62))
                    frame.alpha_composite(sprite,at)
                    marks[key] = p

            frame.alpha_composite(front)
            sparks(frame,t,marks)
            hud(frame,t,fonts,images,layout,aim_cue(t,marks))
            if t >= CUES['transition']:
                placeholder = Image.new('RGBA', CONTENT, (47,51,68,255))
                ImageDraw.Draw(placeholder).text((W//2,H//2-45),'下一站',font=fonts[1],anchor='mm',fill=(217,199,170))
                if t >= 34:
                    placeholder.alpha_composite(images['continue_panel'], ((W-480)//2,(H-320)//2))
                    ImageDraw.Draw(placeholder).text((W//2,H//2),'继续',font=fonts[1],anchor='mm',fill=(234,208,170))
                frame = Image.blend(frame,placeholder,smooth((t-32)/1.25))
                targets = []
                paper_bounds = None
            rgb = np.asarray(frame.convert('RGB'), dtype='float32')
            lum = rgb @ np.array([.299,.587,.114],dtype='float32')/255
            peak_fraction = float(np.mean(lum>.75))
            limited = np.floor(rgb*np.minimum(1,.75/np.maximum(lum,1e-6))[...,None]).astype('uint8')
            frame = Image.fromarray(limited).convert('RGBA')
            debug = frame.copy()
            records, overlaps = stats(targets, layout, debug, t, paper_bounds)
            rows.append({'t':round(t,4),'camera':cam,'breath':breath,'light':light,'cover':cover,
                         'target_overlap':overlaps,'targets':records,'weak_outside':weak_outside,
                         'crow_readability':crow_readability,'prelimit_overbright_fraction':peak_fraction})
            if still or index in (45,94,145,226,380,499):
                frame.resize((888,468),Image.Resampling.LANCZOS).convert('RGB').save(GALLERY/f'frame_{round(t*10):03d}.jpg',quality=93)
                if still:
                    debug.resize((888,468),Image.Resampling.LANCZOS).convert('RGB').save(GALLERY/f'debug_{round(t*10):03d}.jpg',quality=93)
            if not still:
                for encoder, image in ((clean_writer,frame),(debug_writer,debug)):
                    encoder.send(np.asarray(image.resize((888,468),Image.Resampling.LANCZOS).convert('RGB')))
            if index%75==0:
                print(f'T08 {index}/{len(times)}',flush=True)

    by_target = {key:[item for row in rows for item in row['targets'] if item['id']==key]
                 for key in ('lamp','chest_ink','crow','light','wick')}
    failing = [row for row in rows if row['target_overlap'] or row['weak_outside'] or
               any(not (r['edge_clear'] and r['hud_clear'] and r['human_clear'] and r['effective_radius']>=40)
                   for r in row['targets'])]
    crows = [r['crow_readability'] for r in rows if r['crow_readability']]
    normal = [r['body_contrast'] for r in crows if r['state']=='normal']
    hardened = [r['eyes'] for r in crows if r['state']=='hardened']
    unreadable = [r for r in crows if r['background']<.25 or
                  (r['state']=='normal' and r['body_contrast']<.20) or
                  (r['eyes'] and (r['eyes']['contrast']<.30 or r['eyes']['minimum_width']<16))]
    summary = {
        'scope': 'deterministic CPU preview in content coordinates, scripted impacts; full engine and gun pending',
        'frames': len(rows), 'fps': FPS, 'duration': DURATION,
        'target_summary': {k:{'frames':len(v),'minimum_effective_radius':min(r['effective_radius'] for r in v)}
                           for k,v in by_target.items() if v},
        'target_failures': len(failing), 'max_prelimit_overbright_fraction': max(r['prelimit_overbright_fraction'] for r in rows),
        'crow_slots': {
            'minimum_background': min((r['background'] for r in crows), default=None),
            'minimum_normal_contrast': min(normal, default=None),
            'minimum_hardened_eye_contrast': min((r['contrast'] for r in hardened), default=None),
            'minimum_hardened_eye_width': min((r['minimum_width'] for r in hardened), default=None),
            'readability_failures': len(unreadable),
        },
        'rows':rows,
    }
    write_json(REPORT/('still_checks.json' if still else 'checks.json'),summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'}),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stills', action='store_true')
    main(parser.parse_args().stills)
