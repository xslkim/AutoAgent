import argparse
import json
from pathlib import Path
import yaml
from PIL import Image
from artlib import rgba,crop_bleed,encode_sdf,mask,components,matte_birefnet,write_json
from checks import suite
from preview import render,whitebox,movie,gallery,review_form,decisions

def main():
    parser=argparse.ArgumentParser(description='Gunforge offline art tools; no paid API submission')
    parser.add_argument('command',choices=['crop','sdf','split','matte','checks','render','whitebox','gallery','review'])
    parser.add_argument('input',type=Path)
    parser.add_argument('output',type=Path,nargs='?')
    parser.add_argument('--model',type=Path)
    args=parser.parse_args()
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.command=='crop':
        a,origin=crop_bleed(rgba(args.input));Image.fromarray(a).save(args.output)
        write_json(args.output.with_suffix('.json'),{'crop_origin':origin,'size':[a.shape[1],a.shape[0]]})
    elif args.command=='sdf':Image.fromarray(encode_sdf(mask(args.input))).save(args.output)
    elif args.command=='split':write_json(args.output,components(rgba(args.input)))
    elif args.command=='matte':
        if not args.model:parser.error('--model is required; no implicit weight download')
        matte_birefnet(args.input,args.model,args.output)
    elif args.command=='review':print(yaml.safe_dump(decisions(args.input),allow_unicode=True))
    else:
        data=yaml.safe_load(args.input.read_text(encoding='utf-8'))
        if args.command=='checks':suite(data,args.input.parent,args.output)
        elif args.command=='render':render(data,args.input.parent).save(args.output)
        elif args.command=='whitebox':whitebox(data['layout'],data['hud']).save(args.output)
        elif args.command=='gallery':
            gallery(data['items'],args.output)
            review_form(data['items'],args.output.parent/'review.yaml')

if __name__=='__main__':main()
