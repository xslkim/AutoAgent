"""CPU reference for approved runtime materials; source PNGs stay immutable."""
import numpy as np
from PIL import Image
def hardened_eyes(image,model):
    spec=model.get('hardened_eye_material')
    if not spec or model['id'] not in spec['applies_to']:return image
    out=np.array(image.convert('RGBA'));out[...,:3]=spec['eye_tint_rgb'];return Image.fromarray(out)
