import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
CACHE=Path(os.environ.get('GUNFORGE_LEVEL_CACHE',ROOT.parent/'gunforge_cache/level_design')).resolve()
GODOT=Path(os.environ.get('GODOT_BIN',ROOT.parent/'gunforge_cache/tools/godot-4.6.3/Godot_v4.6.3-stable_win64_console.exe')).resolve()
