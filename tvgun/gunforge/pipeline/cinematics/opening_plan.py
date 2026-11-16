"""Original opening CG. All media is generated for this run; no project art inputs."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / 'games/g01/cinematics/opening_original'
STYLE = '''Original cinematic for Paper Lantern City. A handcrafted flat cut-paper diorama with
fine visible paper fibers, clean cuts, twelve separated flat layers, slight offset cast shadows,
dark indigo foreground silhouettes, warmer translucent distant paper. Restrained indigo #141A33,
purple #2A1E3D, apricot #D9A066, dusty pink #C97B84 and teal #4E9A92. Ordinary 1990s China,
square apartment buildings, roller shutters, cassette recorder, bicycle, folding tables.
No photographic realism, plastic, 3D bevels, ancient Chinese architecture, ancient costumes,
white highlights, white flashes, text, lettering, watermark, graphic overlays or borders.
Keep exposure stable. Slow deliberate movement. No dialogue, narration, singing or music;
only the specifically described quiet Foley. Preserve flat paper texture throughout.'''

SHOTS = [
 dict(id='s01', start=0, duration=9, kind='still', frame='workbench',
      beat='雨夜，空椅与工作台。录音机启动，留下爷爷的声音。'),
 dict(id='s02', start=9, duration=9, kind='h3', frame='cassette',
      beat='磁带双轴慢转。雕刀、纸屑和纸城的影子。',
      motion='A close shot of a chunky old portable cassette recorder on a paper craftsman desk. Two tape reels turn slowly clockwise behind its small rectangular window. One large rectangular play button is depressed. A few thin paper offcuts beside it tremble in a draft. Empty chair softly out of focus behind. Warm desk lamp at left, indigo rainy window. Camera slides extremely slowly right. Quiet tape transport whirr, one mechanical click, rain far away.'),
 dict(id='s03', start=18, duration=9, kind='still', frame='city',
      beat='灯中的老城：夜市、旧影院、铁路的记忆。'),
 dict(id='s04', start=27, duration=8, kind='h3', frame='workbench',
      beat='整理时失手，砚台被碰倾。',
      motion='Preserve this exact paper workbench and the same rectangular shadowbox city lamp. In the lower foreground the shallow black rectangular inkstone is accidentally nudged from outside the frame. It TILTS onto its long right edge, spilling a small stream of black ink across the tabletop toward the base of the paper lamp on the right. The inkstone is the only solid object that moves. Leave the recorder, notebook, lamp and chair fixed. No person, no face and no hands enter frame. No magic movement of the inkstone back upright. The spill happens once and settles. Locked camera. A small scrape, a dull ceramic knock, soft liquid spill.'),
 dict(id='s05', start=35, duration=8, kind='h3', frame='macro',
      beat='墨沿纸纤维渗入灯中。',
      motion='Extreme macro view of a single clean flat muted apricot paper sheet edge in the base of a dark wooden shadowbox lamp. Black liquid ink enters from lower left and creeps slowly from left to right into the fine paper fibers. Tiny capillary branching feathered ink edges clearly visible. Behind it, separate upright flat teal and mauve paper layers form a miniature old Chinese town in soft focus. Restrained directional wet highlights cover less than five percent of the ink. No splashing, no tentacles, no creature yet. Camera tracks slowly along the creeping ink edge. Intimate faint paper fiber crackle and soft liquid trickle.'),
 dict(id='s06', start=43, duration=10, kind='h3', frame='workbench',
      beat='夜深，灯芯温柔亮起。镜头推向灯城。',
      motion='Preserve exactly this paper craftsman workbench, empty chair and rectangular wooden shadowbox lamp. The small city inside the right-hand shadowbox gradually lights up from farthest to nearest flat paper layers with restrained apricot amber light, little windows waking in sequence. The room itself stays dark. Slowly push the camera toward the city inside the shadowbox until the town fills most of the frame. No humans, no hands, no glass shine. Gentle electrical switch click, faint filament hum, distant rain. No exposure pulse or white flash.'),
 dict(id='s07', start=53, duration=11, kind='h3', frame='city',
      beat='灯城醒来。亮色纸居民在九十年代的街头活动。',
      motion='Preserve this exact flat layered paper town and all its buildings. The two small friendly warm-apricot paper residents in everyday 1990s jacket and apron gently come alive, with simple pinned paper puppet joint movements. One apron-wearing stallkeeper lifts an arm in greeting, the other walks two small steps beside the upright vintage bicycle. They are vulnerable townspeople, never attackers. Keep bright paper faces and bodies, no black silhouettes for people. A tiny paper bird flutters above a utility wire. Very slow lateral camera drift creates subtle separation between the flat layers. Quiet bicycle bell, distant kettle, muted market rustle, no intelligible speech.'),
 dict(id='s08', start=64, duration=9, kind='h3', frame='crow',
      beat='墨吞掉麻雀的轮廓，一点朱砂浮出。',
      motion='Preserve this thick-bodied black ink bird silhouette with ONE small flat vermilion circular ink-paste mark in the CENTER OF THE CHEST, not in an eye. The bird is wet flowing ink, never a resin toy. It slowly opens its ragged broad paper-like wings, then lifts from the utility wire. A short ink thread drips and breaks. Warm apricot paper buildings remain clearly visible behind it. No more than one red mark, no red eyes, no gemstone or glowing sphere. Keep the scene mysterious and gentle, not frightening. Slow push in. Ink trickles, a single soft flutter, quiet wind. No scream, no voice.'),
 dict(id='s09', start=73, duration=11, kind='h3', frame='crow',
      beat='手电光照入，墨化成烟。光留在纸上。',
      motion='Begin from this exact black ink bird against warm translucent paper town layers. A narrow soft amber flashlight beam enters diagonally from the upper right, grazes the bird chest and gently holds there. Where light touches ink, the ink disperses into delicate black wisps and tiny ink blossoms, revealing the warm paper buildings behind. Bird dissolves completely by the end, leaving the town intact. No explosion, no white flash, no fire, no blood. The single flat chest vermilion mark disappears with the ink. Hold on the quiet lit paper town for the final second. Camera stays still. Soft light chime and quiet vapor hiss, no gunshot, no music.'),
 dict(id='s10', start=84, duration=6, kind='title', frame='city',
      beat='片名《纸灯城》。录音轻轻停下，把光交给玩家。'),
]

# Grandpa speaks only from a newly designed fictional voice. No borrowed voice reference.
LINES = [
 dict(start=2.0, end=8.5, text='听见了吗？下雨的时候，老城就是这个声儿。'),
 dict(start=10.0, end=17.2, text='从前啊，夜市一开灯，谁家的窗户都舍不得关。'),
 dict(start=19.0, end=26.3, text='后来，街拆了。我就一层一层，把它刻在纸里。'),
 dict(start=29.0, end=34.5, text='这张纸呀，最怕沾上墨水。'),
 dict(start=36.0, end=42.1, text='一小滴，也能把一条街的模样，慢慢盖住。'),
 dict(start=44.5, end=51.5, text='可灯一亮，你听，它们又热闹起来了。'),
 dict(start=55.0, end=62.8, text='卖汽水的，修车的，还有总不肯早早回家的小麻雀。'),
 dict(start=65.5, end=71.8, text='要是哪天，你看见城里暗了一块，别怕。'),
 dict(start=74.0, end=82.6, text='把光照过去。记着，照走的是墨，留下的，是咱们的城。'),
]

VOICE_STYLE = '七十五岁的中国北方老爷爷，温和自然，略低沉、略沙哑、有一点气息，像坐在家里轻声给孙辈讲旧事；慢而连贯，有回忆的笑意，句末轻轻放下，不煽情，不播音，不朗诵。普通话。'
