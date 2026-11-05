"""Small material preview (an ellipsoid or a bond) for the Color / Styles tabs."""
import numpy as np
from PIL import Image

from .raster import render_scene
from .scene import Scene
from .view import rot_x, rot_y


def material_preview(styles, settings, entry, kind='atom', size=120, background=(0.75, 0.75, 0.75)):
    """entry: effective style entry dict; kind 'atom' or 'bond'. Returns a PIL image."""
    sc = Scene()
    main = sc.mat('main', styles.material(entry))
    band = sc.mat('Equators', styles.material(styles.get('Equators')))
    cut = sc.mat('Cutout faces', styles.material(styles.get('Cutout faces')))
    if kind == 'atom':
        R = rot_y(0.5) @ rot_x(-0.45)
        sc.prims.append(dict(type='ellipsoid', c=np.zeros(3), V=R, a=np.array([1.0, 0.82, 0.7]),
                             style=entry.get('ellipse', 'PlainEllipse'), mat=main, band=band, cut=cut, oid=0))
    else:
        sc.prims.append(dict(type='cylinder', p0=np.array([-1.1, -0.8, -0.3]), p1=np.array([1.1, 0.8, 0.3]),
                             r=0.28, mat=main, oid=-1))
    rgba, _ = render_scene(sc, size, size, 1.25, (0.0, 0.0), settings, ss=2, background=background)
    return Image.fromarray(rgba[..., :3].copy())
