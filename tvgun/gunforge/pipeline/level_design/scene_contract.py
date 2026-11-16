"""Validation for executable motion, composite alpha geometry and presentation."""
import json
import re
def validate_scene(source,root,error):
 entities=source['entities'];resources=source['resources'];presentation=source.get('presentation',{})
 def image(id):
  if id not in resources or resources[id]['kind']!='image':raise error('missing image binding: '+id)
 def metadata(id):
  if id not in resources or resources[id]['kind']!='metadata':raise error('missing metadata binding: '+id)
 def crop(id,rect):
  from PIL import Image
  with Image.open(root/resources[id]['path']) as data:width,height=data.size
  x,y,w,h=rect
  if x<0 or y<0 or w<=0 or h<=0 or x+w>width or y+h>height:raise error('image crop outside registered resource: '+id)
 def hit_mask(node,id):
  if 'hit_resource' not in node:return
  from PIL import Image
  if 'resource' not in node:raise error('hit mask needs visual image: '+id)
  image(node['resource']);image(node['hit_resource'])
  with Image.open(root/resources[node['resource']]['path']) as art, Image.open(root/resources[node['hit_resource']]['path']) as mask:
   if art.size!=mask.size or 'A' not in mask.getbands():raise error('hit mask must match visual image size and carry alpha: '+id)
 for id,entity in entities.items():
  hit_mask(entity,id)
  if 'mask_permission' in entity:
   gate=entity['mask_permission'];anchor=entities.get(gate['source'],{})
   if id==gate['source'] or not anchor.get('resource') or entity.get('properties',{}).get('virtual') or 'puppet' in entity:
    raise error('mask permission needs a distinct image anchor and a raster target: '+id)
   image(anchor['resource']);image(gate['resource'])
   from PIL import Image
   with Image.open(root/resources[anchor['resource']]['path']) as art, Image.open(root/resources[gate['resource']]['path']) as mask:
    if art.size!=mask.size or mask.mode!='L':raise error('permission mask must match anchor image and be 8-bit grayscale: '+id)
  if 'parts' in entity:
   if not entity['parts'] or set(entity.get('part_order',[]))!=set(entity['parts']):raise error('part order must name every part once: '+id)
   for part in entity['parts'].values():
    image(part['resource'])
    hit_mask(part,id)
    if 'source' in part:crop(part['resource'],part['source'])
    if 'hardened_visual' in part:
     if part.get('kind')!='weak' or 'mask_permission' not in entity:
      raise error('hardened visual needs a light-gated weak part: '+id)
     image(part['hardened_visual']['resource'])
  if 'motion' in entity:
   frames = entity['motion']['frames']
   if any('at_ms' not in frame for frame in frames):
    raise error('attack-time motion frame needs a declared encounter attack: '+id)
   times=[frame['at_ms'] for frame in frames]
   if times[0]!=0 or any(a>=b for a,b in zip(times,times[1:])):raise error('motion frames need increasing milliseconds from zero: '+id)
  if 'bob' in entity and 'motion' not in entity:raise error('bobbing needs an explicit motion anchor: '+id)
  for phase in entity.get('phases',[]):
   if phase['end_ms']<=phase['start_ms']:raise error('empty motion phase: '+id)
  if 'puppet' in entity:
   binding=entity['puppet'];definition=presentation.get('puppets',{}).get(binding['rig'])
   if definition is None or binding['target'] not in entities:raise error('missing puppet rig or target: '+id)
   if any(binding[name] not in definition['clips'] for name in ['idle','success','rest']):raise error('missing puppet animation: '+id)
 for layer in presentation.get('layers',{}).values():
  image(layer['resource'])
  if 'section' in layer and layer['section'] not in source.get('sections',{}):raise error('unknown layer section: '+layer['section'])
  if 'source' in layer:crop(layer['resource'],layer['source'])
 if 'hud_art' in presentation:
  hud=presentation['hud_art'];metadata(hud['layout']);metadata(hud['style'])
  for resource in hud['images'].values():image(resource)
  if 'lettering' in hud:
   letters=hud['lettering'];image(letters['title']);image(letters['first_chapter'])
   for section,resource in letters['chapters'].items():
    if section not in source.get('sections',{}):raise error('unknown lettering section: '+section)
    image(resource)
 for id,source_id in presentation.get('bottom_wipes',{}).items():
  overlay=entities.get(id,{});anchor=entities.get(source_id,{});additive_z=presentation.get('additive_z')
  if (additive_z is None or not overlay.get('resource') or not anchor.get('resource') or
      overlay.get('template')!='decoration' or 'parts' in overlay or 'puppet' in overlay or
      overlay.get('properties',{}).get('virtual') or overlay.get('properties',{}).get('z')!=additive_z+1 or
      anchor.get('properties',{}).get('z')!=additive_z):
   raise error('bottom wipe needs a raster decoration immediately above its additive source: '+id)
 if 'dragon' in presentation:
  dragon=presentation['dragon'];metadata(dragon['layout'])
  try:
   data=json.loads((root/resources[dragon['layout']]['path']).read_text(encoding='utf-8'))
   segments=[node['id'] for node in data['body_nodes']]
   paths={node['textures'][key] for node in data['body_nodes'] for key in ('paper','locked','ink','glow','purified')}
   paths.update((data['head']['upper_jaw'],data['head']['lower_jaw'],data['tail']['file'],
                 data['mouth']['core'],data['mouth']['glow'],data['mouth']['interior']))
   if data['max_active']!=1 or data['opening_order']!=segments[::-1] or not segments or data['body_scale']<=0:
    raise ValueError('expected ordered segments and a positive scale')
  except (ValueError,TypeError,KeyError) as exc:
   raise error('invalid dragon layout: '+str(exc)) from exc
  bindings={dragon['anchor']:'decoration',dragon['mouth']:'target',**dict.fromkeys(segments,'target')}
  if len(bindings)!=len(segments)+2 or any(entities.get(id,{}).get('template')!=template or
      not entities[id].get('properties',{}).get('virtual') for id,template in bindings.items()):
   raise error('dragon needs distinct virtual entities for its anchor and hit zones')
  if set(dragon['images'])!=paths:raise error('dragon image bindings must match the layout')
  for id in dragon['images'].values():image(id)
  if 'warning_effect' in dragon and source.get('effects',{}).get(dragon['warning_effect'],{}).get('kind')!='warning':
   raise error('dragon warning effect must name a warning')
 for definition in presentation.get('puppets',{}).values():
  metadata(definition['character']);image(definition['atlas'])
  for resource in definition['clips'].values():metadata(resource)
 for topic,cue in presentation.get('sound_bindings',{}).items():
  if topic.startswith('cue.') or cue not in source['cues']:raise error('invalid sound binding: '+topic)
 for binding in presentation.get('feedback',{}).values():
  if binding not in source.get('effects',{}):raise error('missing feedback effect: '+binding)
 for id,section in source.get('sections',{}).items():
  if any(target not in entities for target in section['targets']):raise error('unknown section target: '+id)
  if 'station' in section and section['station']>len(presentation.get('stations',[])):
   raise error('unknown station index: '+id)
 if presentation.get('support',{}).get('entity') not in [None,*entities]:raise error('unknown support entity')
 for resource,bounds in source.get('resource_bounds',{}).items():
  if resource not in source['initial_resources'] or bounds.get('min',-2**53)>bounds.get('max',2**53):raise error('invalid resource bounds: '+resource)
  value=source['initial_resources'][resource]
  if value<bounds.get('min',value) or value>bounds.get('max',value):raise error('initial resource outside bounds: '+resource)
 for effect in source.get('effects',{}).values():
  if not re.fullmatch(r'#[a-fA-F0-9]{6}(?:[a-fA-F0-9]{2})?',effect['color']):raise error('effect color needs explicit RGB/RGBA hex')
  if 'anchor_uv' in effect and effect['kind'] not in ('shot_trace','attack_release'):
   raise error('effect anchor_uv requires shot_trace or attack_release')
