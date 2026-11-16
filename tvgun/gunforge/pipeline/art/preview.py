"""Offline evidence renderer, not a game or shader implementation."""
import html
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from artlib import rgba,yprime,write_json

CONTENT=(1776,936)

def transform(image,matrix,size):
    inverse=np.linalg.inv(matrix)
    return image.transform(size,Image.Transform.AFFINE,tuple(inverse[:2].ravel()),Image.Resampling.BICUBIC)

def translation(x,y):
    return np.array([[1.,0,x],[0,1.,y],[0,0,1.]])

def pose(puppet,folder,position,scale,angles,size=CONTENT):
    parts={p['id']:p for p in puppet['parts']}; matrices={}; visiting=set()
    def matrix(ident):
        if ident in matrices:return matrices[ident]
        if ident in visiting:raise ValueError('Rig parent cycle')
        visiting.add(ident); p=parts[ident]
        theta=math.radians(angles.get(ident,p.get('rest_deg',0)))
        rotate=np.array([[math.cos(theta),-math.sin(theta),0],[math.sin(theta),math.cos(theta),0],[0,0,1.]])
        pivot=p.get('pivot',[0,0]); parent=p.get('parent')
        if parent:
            # attach is expressed in the parent's file-local pixel coordinates.
            head=matrix(parent) @ translation(*p['attach'])
        else:
            head=translation(*position) @ np.diag([scale,scale,1])
        m=head@rotate@translation(-pivot[0],-pivot[1]); matrices[ident]=m
        visiting.remove(ident);return m
    out=Image.new('RGBA',size)
    for p in sorted(parts.values(),key=lambda p:p.get('z',0)):
        out.alpha_composite(transform(Image.open(Path(folder)/p['file']).convert('RGBA'),matrix(p['id']),size))
    return out

def render(station,folder,camera=(0,0),breath=(0,0),light_states=None,hud=None,overlay=False):
    folder=Path(folder); origin=station['content_origin']; canvas=station['canvas']
    out=Image.new('RGBA',canvas); spaces={}; rendered_layers={}
    for layer in sorted(station['layers'],key=lambda l:l['z']):
        parallax=layer['parallax']; pos=layer.get('pos',[0,0]); shift=np.array(camera)+np.array(breath)
        x,y=np.array(pos)-shift*parallax; spaces[layer['id']]=(x-pos[0],y-pos[1])
        image=Image.open(folder/layer['file']).convert('RGBA')
        if 'size' in layer:image=image.resize(tuple(layer['size']))
        out.alpha_composite(image,(round(x),round(y)))
        layer_canvas=Image.new('RGBA',canvas);layer_canvas.alpha_composite(image,(round(x),round(y)))
        rendered_layers[layer['id']]=layer_canvas
    # Approximate light compositing in encoded space, matching current preview specification.
    a=np.asarray(out).copy(); rgb=a[...,:3].astype(float)
    for light in station.get('lights',[]):
        intensity=(light_states or {}).get(light['id'],0)*light.get('intensity',1)
        spill=Image.open(folder/light['spill']).convert('L')
        if spill.size!=tuple(canvas):raise ValueError('Preview light spill must use station canvas')
        dx,dy=spaces.get(light['space'],(0,0))
        spill=spill.transform(tuple(canvas),Image.Transform.AFFINE,(1,0,-dx,0,1,-dy))
        color=tuple(bytes.fromhex(light['color'].lstrip('#')))
        rgb+=np.asarray(spill)[...,None]/255*np.array(color)*intensity
        if light.get('glow'):
            glow=Image.open(folder/light['glow']).convert('RGBA')
            if glow.size!=tuple(canvas):raise ValueError('Preview glow must use station canvas')
            glow=glow.transform(tuple(canvas),Image.Transform.AFFINE,(1,0,-dx,0,1,-dy))
            g=np.asarray(glow); rgb+=g[...,:3]*(g[...,3,None]/255)*intensity
    a[...,:3]=np.clip(rgb,0,255).astype('uint8');out=Image.fromarray(a)
    def occluded(layer,item):
        a=np.asarray(layer).copy()
        for ident in item.get('occluded_by',[]):
            a[...,3]=(a[...,3]*(1-np.asarray(rendered_layers[ident])[...,3]/255)).astype('uint8')
        return Image.fromarray(a)
    for item in station.get('preview_puppets',[]):
        model=json.loads((folder/item['metadata']).read_text(encoding='utf-8'))
        shift=spaces.get(item.get('space'),(0,0));pos=np.array(item['position'])+shift
        layer=pose(model,folder/item['folder'],pos,item['scale'],item.get('angles',{}),tuple(canvas))
        out.alpha_composite(occluded(layer,item))
    for item in station.get('preview_enemies',[]):
        model=json.loads((folder/item['metadata']).read_text(encoding='utf-8'))
        actor=Image.new('RGBA',canvas);shift=spaces.get(item.get('space'),(0,0))
        t=item.get('time',0);offset=math.sin(t*math.tau*.8)*item.get('wobble_amp',0)
        position=np.array(item['position'])+shift+[offset,0];enemy_origin=model['origin']
        for key in ['body','core_hardened' if item.get('hardened') else 'core']:
            f=model['files'][key];crop=f['crop_origin']
            matrix=translation(*position)@np.diag([item['scale'],item['scale'],1])@translation(crop[0]-enemy_origin[0],crop[1]-enemy_origin[1])
            texture=Image.open(folder/item['folder']/f['file']).convert('RGBA')
            if key=='core_hardened':
                from materials import hardened_eyes
                texture=hardened_eyes(texture,model)
            actor.alpha_composite(transform(texture,matrix,tuple(canvas)))
        a=np.asarray(actor).copy();a[...,3]=(a[...,3]*item.get('opacity',1)).astype('uint8')
        out.alpha_composite(occluded(Image.fromarray(a),item))
    out=out.crop((origin[0],origin[1],origin[0]+CONTENT[0],origin[1]+CONTENT[1]))
    draw=ImageDraw.Draw(out)
    if hud:
        for item in hud['elements']:
            if 'file' in item:out.alpha_composite(Image.open(folder/item['file']).convert('RGBA').resize(tuple(item['size'])),tuple(item['pos']))
            elif overlay:draw.rectangle([*item['pos'],item['pos'][0]+item['size'][0],item['pos'][1]+item['size'][1]],outline='white',width=2)
        if overlay:
            for name,rect in hud['reserved'].items():
                x,y,w,h=rect['rect'];draw.rectangle((x,y,x+w,y+h),outline='yellow',width=2);draw.text((x,y),name,fill='yellow')
    if overlay:
        draw.rectangle((60,60,CONTENT[0]-60,CONTENT[1]-60),outline='orange',width=2)
        for region in station.get('preview_hit_zones',[]):
            x,y,w,h=region['rect'];draw.ellipse((x,y,x+w,y+h),outline=region.get('color','red'),width=3)
    a=np.asarray(out).copy();lum=yprime(a)
    factor=np.minimum(1,.75/np.maximum(lum,1e-9));a[...,:3]=(a[...,:3]*factor[...,None]).astype('uint8')
    return Image.fromarray(a)

def movie(frames,output,fps=15):
    import imageio_ffmpeg
    first=np.asarray(frames[0].convert('RGB'))
    writer=imageio_ffmpeg.write_frames(str(output),(first.shape[1],first.shape[0]),fps=fps,
                                     codec='libx264',pix_fmt_in='rgb24',macro_block_size=1,
                                     output_params=['-crf','22'])
    writer.send(None)
    try:
        for frame in frames:writer.send(np.ascontiguousarray(frame.convert('RGB')).tobytes())
    finally:writer.close()

def whitebox(spec,hud):
    out=Image.new('L',CONTENT,150);draw=ImageDraw.Draw(out)
    for kind,color in [('covers',35),('slots',210),('lights',245)]:
        for r in spec.get(kind,[]):
            x,y,w,h=r;draw.rectangle((x,y,x+w,y+h),fill=color)
    for item in hud['reserved'].values():
        x,y,w,h=item['rect'];draw.rectangle((x,y,x+w,y+h),outline=0,width=3)
    return out

def gallery(items,output):
    """Copy approved-for-review previews only; static HTML never writes approvals."""
    import shutil
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    rows=[]
    order={'fail':0,'pending':1,'pass':2,'na':3}
    for index,item in enumerate(sorted(items,key=lambda i:order.get(i['status'],1))):
        preview=Path(item['preview']);dest=f'preview_{index}{preview.suffix.lower()}'
        shutil.copy2(preview,output/dest)
        media=f'<video controls src="{dest}"></video>' if preview.suffix.lower()=='.mp4' else f'<img src="{dest}" loading="lazy">'
        rows.append(f'<article><h2>{html.escape(item["id"])}</h2>{media}<pre>{html.escape(json.dumps(item,ensure_ascii=False,indent=2))}</pre></article>')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Art review</title><style>body{font:16px system-ui;margin:32px;background:#eee;color:#222}article{border-bottom:1px solid #aaa;padding:24px 0}img,video{max-width:100%;max-height:640px}pre{white-space:pre-wrap}</style><h1>Art review — offline evidence</h1>'+''.join(rows),encoding='utf-8')

def review_form(items,path):
    import yaml
    path=Path(path)
    if path.exists():raise FileExistsError('Never overwrite human review decisions')
    path.write_text(yaml.safe_dump({'items':[dict(id=i['id'],status='pending',note='') for i in items]},allow_unicode=True,sort_keys=False),encoding='utf-8')

def decisions(path):
    import yaml
    data=yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    seen=set()
    for row in data['items']:
        if row['id'] in seen or row['status'] not in {'pending','approved','rejected'}:raise ValueError('Invalid review decision')
        seen.add(row['id'])
    return data
