"""Assemble the self-contained first-station review pack from accepted source versions."""
import argparse
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageOps

from a2_memory import allocation
from artlib import GAME, ROOT, digest, effective_radius, write_json
from checks import run
from paper_ops import limit_luminance

REPORT = GAME / 'reports/art/T08'
PACK = REPORT / 'asset_pack'
CACHE = Path('D:/gunforge_cache/g01')
UI_SIZES = {
    'life_wick': (72, 128), 'ammo_light': (64, 96), 'score_seal': (224, 224),
    'prompt_bar': (1200, 144), 'crosshair': (80, 80), 'continue_panel': (960, 640),
}
NEW = [*(f'cover_{i:02d}' for i in range(3)), *UI_SIZES, 'pickup_light', 'pickup_wick']


def read(path):
    return json.loads(path.read_bytes())


def copy(root, dest, paths):
    for name in paths:
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)


def texture(path, size, *, fit=True, pad=0):
    with Image.open(path) as raw:
        im = raw.convert('RGBA')
    a = im.getchannel('A')
    bounds = a.point(lambda x: 255 if x >= 32 else 0).getbbox()
    if not bounds or a.getextrema()[0] != 0:
        raise ValueError(f'{path.name} needs an isolated transparent sprite')
    im = im.crop(bounds)
    if not fit:
        return im.resize(size, Image.Resampling.LANCZOS)
    inner = (size[0]-pad*2, size[1]-pad*2)
    return ImageOps.pad(im, size, Image.Resampling.LANCZOS) if not pad else ImageOps.expand(
        ImageOps.pad(im, inner, Image.Resampling.LANCZOS), pad)


def assemble(cache, sources):
    station_root = cache / 'T04/station'
    station = read(station_root / 'station.json')
    paths = ['station.json']
    for layer in station['layers']:
        paths.extend(layer[key] for key in ('file', 'extent') if key in layer)
        if layer.get('blocks_shots'):
            paths.append(f'layers/{layer["id"]}_block.png')
    for light in station['lights']:
        paths.extend(light[key] for key in ('spill', 'glow') if light.get(key))
    copy(station_root, PACK/'station', paths)
    copy(GAME/'bible/geometry/alley_extent_v1', PACK/'geometry_baseline',
         [p.name for p in (GAME/'bible/geometry/alley_extent_v1').iterdir() if p.is_file()])
    resident = ROOT/'art2d/assets/paper_lantern_vendor/export'
    copy(resident, PACK/'vendor', [p.relative_to(resident) for p in resident.rglob('*') if p.is_file()])
    crow = cache/'T06/crow'
    model = read(crow/'enemy.json')
    copy(crow, PACK/'crow', ['enemy.json', *(v['file'] for v in model['files'].values())])
    with Image.open(PACK/'crow/body.png') as body:
        body.getchannel('A').save(PACK/'crow/alpha.png')
    copy(GAME/'assets/ui', PACK/'ui', ['hud_layout.json'])

    for directory in ('ui', 'ink_on_lamp', 'pickups'):
        (PACK/directory).mkdir(parents=True, exist_ok=True)
    for ident in NEW:
        path = sources/f'{ident}.png'
        if ident in UI_SIZES:
            sprite = limit_luminance(texture(path, UI_SIZES[ident], fit=ident not in {'prompt_bar', 'continue_panel'}))
            sprite.save(PACK/f'ui/{ident}.png')
            if ident in {'life_wick', 'ammo_light'}:
                a = np.array(sprite)
                gray = a[..., :3].astype('float32').mean(axis=2) * .43
                a[..., :3] = np.stack((gray*.83, gray*.89, gray), axis=2).astype('uint8')
                Image.fromarray(a).save(PACK/f'ui/{ident}_empty.png')
        elif ident.startswith('cover_'):
            limit_luminance(texture(path, (256, 256), pad=4), high=.35).save(PACK/f'ink_on_lamp/{ident}.png')
        else:
            sprite = limit_luminance(texture(path, (256, 256), pad=4))
            m = np.asarray(sprite.resize((112,112), Image.Resampling.LANCZOS))[...,3]>=128
            radius, _ = effective_radius(m)
            if radius < 40:
                raise ValueError(f'{ident}: effective radius {radius:.2f} px, needs 40')
            sprite.save(PACK/f'pickups/{ident}.png')
    write_json(PACK/'ui/ui.json', {
        'layout': 'hud_layout.json', 'source_sizes': UI_SIZES, 'mipmaps': False,
        'continue_panel': {'size': [960, 640], 'slice_insets_ltrb': [88, 88, 88, 88]},
        'crosshair': {'display_size': [40,40], 'center': [.5,.5], 'opacity': .7},
        'text_is_rendered_separately': True,
    })


def memory():
    station = read(PACK/'station/station.json')
    light_paths = [light[key] for light in station['lights'] for key in ('spill','glow')]
    source_paths = [r['file'] for r in station['layers']] + light_paths
    categories = {
        'station_original': [allocation(PACK/'station'/name, bpp=4) for name in source_paths],
        'actors_and_objects': [allocation(p, bpp=4) for folder in ('vendor','crow','ink_on_lamp','pickups')
                               for p in sorted((PACK/folder).glob('*.png'))],
        'effects_and_ui': [allocation(p, mips=False, bpp=4) for p in sorted((PACK/'ui').glob('*.png'))],
    }
    sizes = {}
    for key, rows in categories.items():
        for row in rows:
            row['file'] = Path(row['file']).relative_to(PACK).as_posix()
        sizes[key] = sum(r['allocated_bytes'] for r in rows)
    hybrid = read(GAME/'reports/art/T07/revisions/A2h/hybrid_texture_plan.json')
    proposed = hybrid['conservative_RGBA8_bytes']
    nonstation = sizes['actors_and_objects'] + sizes['effects_and_ui']
    write_json(REPORT/'memory.json', {
        'scope': 'offline RGBA8 allocation estimate including exact mip chains; T08 does not provide a GPU upload implementation',
        'original_full_textures_bytes': sizes, 'assets': categories,
        'hybrid_station_candidate_bytes': proposed,
        'hybrid_total_candidate_bytes': proposed + nonstation,
        'original_total_bytes': sizes['station_original'] + nonstation,
        'transitional_placeholder_rgba8_bytes': 4,
        'hybrid_transition_candidate_bytes': proposed + nonstation + 4,
        'second_real_station_peak': 'pending',
        'limits_bytes': {'station': 48000000, 'actors': 32000000, 'effects_ui': 16000000,
                         'combined': 96000000, 'transition': 160000000},
        'excluded': ['framebuffers', 'postprocessing', 'font cache', 'driver allocation overhead'],
        'actual_GPU': 'pending',
    })


def manifest():
    write_json(PACK/'manifest.json', {
        'station': 'g01_st_l1_01_alley', 'status': 'A3_offline_review_candidate',
        'resident_source': 'f90d2b5', 'role': 'human_hostage_or_NPC_only',
        'targets': ['streetlamp_shade', 'visible_chest_ink', 'crow', 'pickups'],
        'files': [{'file': p.relative_to(PACK).as_posix(), 'sha256': digest(p)}
                  for p in sorted(PACK.rglob('*')) if p.is_file() and p.name != 'manifest.json'],
    })


def verify():
    files = [p for folder in ('ink_on_lamp','ui','pickups') for p in sorted((PACK/folder).glob('*.png'))]
    palette = [list(bytes.fromhex(x['hex'][1:])) for x in read(GAME/'bible/palette.json')['colors']]
    sheet = Image.new('RGB',(960, 182*((len(files)+3)//4)), '#283144')
    draw = ImageDraw.Draw(sheet)
    rows = []
    for i, file in enumerate(files):
        im = Image.open(file).convert('RGBA')
        size = UI_SIZES.get(file.stem.removesuffix('_empty'), (256,256))
        spec = {'file':file.name,'kind':'color','size':list(size),'palette_rgb':palette}
        row = {key:run(key,spec,file.parent) for key in ('C01','C03','C04')}
        row['C04']['diagnostic_only'] = True
        a = np.asarray(im.getchannel('A'))
        row['alpha'] = {'transparent_pixels':int((a==0).sum()),'visible_pixels':int((a>=128).sum()),
                        'matte_review': 'black/white contact sheet; no known matte color'}
        rows.append({'file':file.relative_to(PACK).as_posix(), **row})
        x,y = (i%4)*240,(i//4)*182
        draw.text((x+12,y+5), file.stem, fill='#e8d8bd')
        sprite = im.copy()
        sprite.thumbnail((106,142), Image.Resampling.LANCZOS)
        for j,color in enumerate(('#11141c','#f2eee7')):
            bx = x+8+j*114
            draw.rectangle((bx,y+22,bx+108,y+172), fill=color)
            sheet.paste(sprite, (bx+(108-sprite.width)//2,y+22+(150-sprite.height)//2), sprite)
    (REPORT/'gallery').mkdir(exist_ok=True)
    sheet.save(REPORT/'gallery/asset_sheet.jpg',quality=92)
    with ThreadPoolExecutor(max_workers=3) as pool:
        ocr = pool.map(lambda p:run('C05',{'file':p.name,'expected_text':''},p.parent), files)
        for row, result in zip(rows, ocr):
            row['C05'] = result
    station = read(PACK/'station/station.json')
    blockers = []
    for layer in station['layers']:
        if not layer.get('blocks_shots'):
            continue
        with Image.open(PACK/'station'/layer['file']) as source:
            visible = Image.new('L', tuple(station['canvas']))
            visible.paste(source.getchannel('A'), tuple(layer['pos']))
        with Image.open(PACK/f'station/layers/{layer["id"]}_block.png') as mask:
            mismatches = int(np.count_nonzero((np.asarray(visible)>=128) != (np.asarray(mask)>=128)))
        blockers.append({'layer':layer['id'],'status':'pass' if mismatches==0 else 'fail',
                         'different_pixels':mismatches})
    sdf = run('C16',{'alpha':'alpha.png','sdf':'sdf.png','source_color':False},PACK/'crow')
    write_json(REPORT/'asset_checks.json',{'assets':rows,'C08_station_blockers':blockers,
               'C16_crow_sdf':sdf,'C14':'pending independent reviewer and calibration'})


def publish_offline():
    review = yaml.safe_load((REPORT/'review.yaml').read_text(encoding='utf-8'))
    if review['status'] != 'approved_offline_sample':
        raise ValueError('The T08 offline sample still needs reviewer approval.')

    evidence = read(REPORT/'manifest.json')
    approved_sample = REPORT/'gallery/alley_sample.mp4'
    sample_record = next(r for r in evidence['files'] if r['file'] == 'gallery/alley_sample.mp4')
    pack_record = next(r for r in evidence['files'] if r['file'] == 'asset_pack/manifest.json')
    approval = review['offline_sample_decision']
    if not (digest(approved_sample) == sample_record['sha256'] == approval['sample_sha256']
            and digest(PACK/'manifest.json') == pack_record['sha256'] == approval['pack_manifest_sha256']):
        raise ValueError('Review evidence changed after publishing the sample.')

    manifest_data = read(PACK/'manifest.json')
    station = 'g01_st_l1_01_alley'
    if manifest_data['station'] != station:
        raise ValueError('Unexpected station in T08 asset pack.')
    files = {Path(r['file']):r['sha256'] for r in manifest_data['files']}
    actual = {p.relative_to(PACK) for p in PACK.rglob('*') if p.is_file()} - {Path('manifest.json')}
    if len(files) != len(manifest_data['files']) or files.keys() != actual:
        raise ValueError('Review manifest does not match the files in the T08 pack.')
    for path, checksum in files.items():
        if not (PACK/path).resolve().is_relative_to(PACK.resolve()) or digest(PACK/path) != checksum:
            raise ValueError(f'Unverified T08 asset: {path}')

    assets = GAME/'assets'
    station_manifest = Path('stations')/station/'manifest.json'
    dest = (assets/station_manifest).parent
    asset_index = read(assets/'manifest.json')
    manifest_data.update(
        status='approved_offline_candidate',
        source_pack_manifest_sha256=pack_record['sha256'],
        reviewed_sample_sha256=sample_record['sha256'],
        engine_acceptance=False,
        actual_0B_approved=False,
        production_approved=False,
    )
    record = {'station':station,'manifest':station_manifest.as_posix(),
              'status':'approved_offline_candidate','review':'../reports/art/T08/review.yaml'}
    candidates = asset_index.setdefault('offline_candidates', [])
    registered = next((r for r in candidates if r['station'] == station), None)
    if registered is not None and registered != record:
        raise FileExistsError('The asset index already has a different candidate for this station.')

    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        with TemporaryDirectory(dir=dest.parent, prefix='t08_publish_') as tmp:
            staged = Path(tmp)/station
            copy(PACK, staged, files)
            write_json(staged/'manifest.json', manifest_data)
            staged.rename(dest)
    if read(dest/'manifest.json') != manifest_data or any(
        not (dest/path).is_file() or digest(dest/path) != checksum for path, checksum in files.items()
    ):
        raise ValueError('The installed T08 pack differs from the reviewed candidate.')
    if registered is None:
        candidates.append(record)
        write_json(assets/'manifest.json',asset_index)
    print(f'{len(files)} verified assets published for offline integration: {dest}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=CACHE)
    parser.add_argument('--sources', type=Path, default=REPORT/'generation')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--verify', action='store_true', help='Run file checks and make an alpha contact sheet')
    mode.add_argument('--publish-offline', action='store_true', help='Copy the reviewed candidate into assets')
    args = parser.parse_args()
    if args.verify:
        verify()
    elif args.publish_offline:
        publish_offline()
    else:
        assemble(args.cache, args.sources)
        memory()
        manifest()
