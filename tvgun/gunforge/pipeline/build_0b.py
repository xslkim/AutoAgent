"""Build first-station runtime inputs from the reviewed, hash-checked asset pack."""
import hashlib
import json
import math
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
GAME = ROOT/'gunforge/games/g01'
SOURCE = GAME/'assets/stations/g01_st_l1_01_alley'
OUT = ROOT/'gunforge/framework/runtime'


def read(path):
    return json.loads(path.read_bytes())


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main():
    manifest = read(SOURCE/'manifest.json')
    if manifest['status'] != 'approved_offline_candidate':
        raise ValueError('First station needs offline approval.')
    for entry in manifest['files']:
        path = (SOURCE/entry['file']).resolve()
        if not path.is_relative_to(SOURCE.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError(f'Unverified source {entry["file"]}')
    OUT.mkdir(parents=True, exist_ok=True)
    for folder in ('vendor','crow','ui','pickups','ink_on_lamp'):
        shutil.copytree(SOURCE/folder,OUT/folder,dirs_exist_ok=True)
    crow = read(OUT/'crow/enemy.json')
    combined = Image.new('RGBA',(1024,1024))
    for key in ('body','core'):
        info = crow['files'][key]
        with Image.open(OUT/'crow'/info['file']) as sprite:
            combined.alpha_composite(sprite.convert('RGBA'),tuple(info['crop_origin']))
    combined.resize((264,264),Image.Resampling.LANCZOS).save(OUT/'crow/defeated.png')
    shutil.copyfile(GAME/'levels/alley_0b.json',OUT/'level.json')
    shutil.copyfile(GAME/'bible/runtime_presentation.json',OUT/'presentation.json')
    for source, dest in [('alley_rules.gd','game_rules.gd'),('alley_scene.gd','game_scene.gd'),('alley_pose.gd','game_pose.gd')]:
        if (GAME/'scripts'/source).is_file():
            shutil.copyfile(GAME/'scripts'/source,OUT/dest)
    config = read(OUT/'level.json')
    for wave in config['waves']:
        deadline = 0
        for enemy in wave['enemies']:
            action = .4+.15+.3+.5+.5+.25+.15
            if enemy['deadline']-enemy['at']<=action or enemy['at']<deadline:
                raise ValueError('Unfair or overlapping first-station threat schedule')
            deadline = enemy['deadline']
    station = read(SOURCE/'station/station.json')
    rows = []
    for layer in station['layers']:
        with Image.open(SOURCE/'station'/layer['file']) as src:
            im = src.convert('RGBA')
        scale = 1 if layer['id']=='lamp' else .65
        size = tuple(max(1,round(n*scale)) for n in im.size)
        target = OUT/'station'/layer['file']
        target.parent.mkdir(parents=True,exist_ok=True)
        im.resize(size,Image.Resampling.LANCZOS).save(target)
        layer['runtime_size'] = list(size)
        layer['draw_size'] = list(im.size)
        rows.append({'file':'station/'+layer['file'],'bytes':sum(max(1,size[0]>>i)*max(1,size[1]>>i)*4 for i in range(int(math.log2(max(size)))+1))})
    for light in station['lights']:
        for key in ('spill','glow'):
            with Image.open(SOURCE/'station'/light[key]) as src:
                im = src.convert('RGBA')
            size = tuple(round(n*.65) for n in im.size)
            target = OUT/'station'/light[key]
            target.parent.mkdir(parents=True,exist_ok=True)
            im.resize(size,Image.Resampling.LANCZOS).save(target)
            rows.append({'file':'station/'+light[key],'bytes':sum(max(1,size[0]>>i)*max(1,size[1]>>i)*4 for i in range(int(math.log2(max(size)))+1))})
    dump(OUT/'station/station.json',station)
    total = sum(row['bytes'] for row in rows)
    if total>48_000_000:
        raise ValueError(f'Station textures exceed 48MB: {total}')
    dump(OUT/'build.json',{'source_manifest_sha256':hashlib.sha256((SOURCE/'manifest.json').read_bytes()).hexdigest(),
                         'station_mipmapped_rgba_bytes':total,'station_sources':rows,
                         'level_fairness':'pass_one_round_remaining_lamp_reload_reacquire'})
    print(f'0B runtime prepared, station RGBA8+mips {total/1e6:.2f} MB')


if __name__=='__main__':
    main()
