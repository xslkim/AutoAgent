"""Archive provenance for images generated through the built-in tool in this chat."""
import hashlib
import json
from PIL import Image
from opening_plan import ROOT

items=[
 ('workbench','exec-f35a3741-f8a2-4a12-af93-f9cda4d5111c.png',[],
  'Original widescreen flat cut-paper rainy-night workbench. Right: unlit rectangular twelve-layer paper city lamp, ordinary 1990s square town. Low center: flat shallow rectangular inkstone and small vermilion stamp pad. Left: chunky cassette recorder, desk lamp, sketchbook, carving knife and empty chair. Fine fibrous paper; indigo/purple 65%, muted apricot/mauve 25%, teal 10%. No people, hands, text, white, photography or heavy 3D.'),
 ('city','exec-4278be11-0718-47ba-b951-507e392c8961.png',[],
  'Original widescreen intimate 1990s Chinese paper-cut town lane. Twelve flat layers, dark nearer silhouettes and warm distant paper. Left soda stall, folding table, bottles, stools and roller shutter. Right blank cinema poster and bicycle. Middle footbridge and square apartment buildings, utility wire and sparrow. Exactly two small friendly bright paper residents in apron and everyday jacket, pinned joints. Indigo, purple, muted apricot, dusty mauve and teal. No ink, text, UI, white, ancient costumes or photography.'),
 ('crow','exec-97fe6a66-813f-4b33-a47b-f41d3f5495e0.png',['city'],
  'New close shot in this run\'s paper town, no people in framing. One thick-bodied black ink crow on wire, broad folded wings, feathered capillary edges and a few dripping ink threads, very restrained wet indigo/teal highlights. Exactly one SMALL FLAT VERMILION circular granular stamp on the center chest. Dark grey eyes, no red eyes. Muted apricot paper buildings behind for contrast. No extra bird or red marks, no sphere, jewel, white, text, horror or heavy 3D.'),
 ('title','exec-5db3d7d2-a224-44d6-bf78-f291b6883bdb.png',[],
  'Single isolated original title on genuinely transparent RGBA background. Exactly three Chinese characters, one horizontal line: 纸灯城. Expressive legible Chinese brush calligraphy, slightly dry brush tips and fiber gaps, muted warm apricot #D9A066. Full strokes inside canvas and 10% transparent margin. No other text, seals, red stamps, glow, shadow, outline, background, rectangle or watermark.'),
 ('cassette','exec-9e49d3a3-d880-43d5-aca9-0c4ffcf42fbc.png',['workbench'],
  'Continuity close-up of this run\'s original workbench. Preserve exact flat paper style, same chunky cassette recorder with handle, two orange visible reels and rectangular buttons. Warm desk lamp upper left, rainy indigo window, empty chair at right, paper offcuts and sketchbook foreground. No shadowbox in this close framing. No people, hands, text, white, photorealism, glass sheen or heavy 3D.'),
 ('macro','exec-13bf5592-bed2-437b-829d-489303e36f87.png',[],
  'Original widescreen extreme close-up entirely flat fibrous hand-cut colored paper. Foreground bottom left a small matte black ink pool has just reached muted apricot paper; capillary feathering extends a little rightward into clear empty paper. Behind, eight separated upright teal/mauve/purple/indigo layers with simple square town windows and tiny warm gaps. Shadowbox corner at right. No creature, people, hands, text, white, chrome puddle or photography.'),
 ('spill_end','exec-bf96f33c-f38e-4931-8394-da656e401a27.png',['workbench'],
  'Precise continuity edit: keep full original framing, lighting, dark indigo rainy NIGHT, empty chair, recorder, book, knife, desk lamp and unlit shadowbox city unchanged. ONLY tilt the rectangular inkstone 50 degrees onto its long right edge with a corner against stamp pad. Add a small flat black ink puddle and thin stream physically reaching the shadowbox lower-left corner, faint capillary feathering there. No room brightening, no new objects, people or hands.'),
 ('workbench_lit','exec-0cc60ef3-ffde-4ed2-9413-160f6f918e65.png',['spill_end'],
  'Lighting-only continuity edit: keep composition, tipped inkstone, ink trail, all tools, empty chair and DARK INDIGO RAINY NIGHT outside unchanged. ONLY turn on restrained muted warm-apricot internal backlight in the shadowbox; near layers stay dark indigo/teal, mid mauve, distant gently warm with thin glowing cut edges. Very faint warm spill directly before the box only. No white or cream glow, no sun, room exposure change, new objects, people or text.'),
]
records=[]
for name,source,refs,prompt in items:
    p=ROOT/'keyframes'/f'{name}.png';im=Image.open(p)
    records.append({'id':name,'tool':'builtin_image_gen','media_origin':'generated_for_this_film_2026-11-07','output':f'keyframes/{name}.png',
      'source_result_filename':source,'references':[f'keyframes/{x}.png' for x in refs],
      'prompt_spec':prompt,'prompt_record_note':'Archival production specification; original verbatim generation messages are in the chat tool calls.',
      'actual_size':list(im.size),'mode':im.mode,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
      'model':None,'seed':None,'amount':None,'cost_status':'not_reported'})
(ROOT/'image_generation_manifest.json').write_text(json.dumps({'no_historical_image_references':True,'records':records},ensure_ascii=False,indent=2),encoding='utf8')
print('Recorded',len(records),'new images')
