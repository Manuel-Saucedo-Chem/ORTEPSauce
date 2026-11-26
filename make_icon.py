"""Builds the program icon (ortepsauce.ico for the .exe, ortepsauce/icon.ico and icon.png for the
window) from icon_source.png – a picture of a molecule on a white background. The molecule is put on
a white rounded tile so the black bonds stay visible on dark taskbars too."""
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'icon_source.png')
SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]


def transparent_white(im):
    a = np.asarray(im.convert('RGB')).astype(np.float32) / 255.0
    # alpha from how far the pixel is from white (darkest channel decides)
    alpha = np.clip((1.0 - a.min(axis=2)) * 1.6, 0.0, 1.0)
    rgb = np.where(alpha[..., None] > 1e-3,
                   (a - (1.0 - alpha[..., None])) / np.maximum(alpha[..., None], 1e-3), 0.0)
    out = np.dstack([np.clip(rgb, 0, 1), alpha])
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8), 'RGBA')


def square(im, pad=0.04):
    bb = im.getbbox() or (0, 0, im.width, im.height)
    im = im.crop(bb)
    s = int(max(im.size) * (1 + 2 * pad))
    canvas = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    canvas.paste(im, ((s - im.width) // 2, (s - im.height) // 2), im)
    return canvas


def tile(mol, size=1024, radius=0.18, border=0.012):
    """White rounded square with a thin grey rim, molecule centred on it."""
    from PIL import ImageDraw
    S = size
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    b = int(S * border)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * radius), fill=(150, 150, 150, 255))
    d.rounded_rectangle([b, b, S - 1 - b, S - 1 - b], radius=int(S * radius) - b, fill=(255, 255, 255, 255))
    inner = int(S * 0.86)
    m = mol.resize((inner, inner), Image.LANCZOS)
    out.paste(m, ((S - inner) // 2, (S - inner) // 2), m)
    return out


def main():
    big = tile(square(transparent_white(Image.open(SRC)), pad=0.0))
    png = big.resize((512, 512), Image.LANCZOS)
    pkg = os.path.join(HERE, 'ortepsauce')
    png.save(os.path.join(pkg, 'icon.png'))
    ico = big.resize((256, 256), Image.LANCZOS)
    for path in (os.path.join(HERE, 'ortepsauce.ico'), os.path.join(pkg, 'icon.ico')):
        ico.save(path, sizes=SIZES)
    print('ortepsauce.ico, ortepsauce/icon.ico and ortepsauce/icon.png written')


if __name__ == '__main__':
    main()
