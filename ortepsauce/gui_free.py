"""Headless rendering (no Tk needed) - used by the command line --export option."""
import logging
import os

from .cif_reader import read_cif
from .export import export_gif, export_image, export_pov
from .model import build_model
from .settings import RenderSettings
from .shelx_reader import read_shelx
from .styles import StyleTable
from .view import default_orientation, fit_scale

logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)


def load_structure(path, block=0):
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.ins', '.res'):
        return read_shelx(path)
    return read_cif(path)[block][1]


def render_file(path, out, dpi=600, size=None, prob=50.0, labels=True, show_h=True,
                style='ORTEP ellipsoids', preset='POV-Ray (ORTEP-3)', complete=True, block=0,
                transparent=True, frames=200, shadows=False, engine='Built-in', povray_exe=None,
                antialias=True, progress=None, pack=False):
    """size: (width_px, height_px); default 6400 x 4800 for images, 1600 x 1200 for GIFs."""
    st = load_structure(path, block)
    model = build_model(st, complete=complete, pack=pack)
    s = RenderSettings(probability=prob, labels_on=labels, show_h=show_h, atom_style=style)
    styles = StyleTable(preset)
    low = out.lower()
    if size is None:
        size = (1600, 1200) if low.endswith('.gif') else (6400, 4800)
    W, H = int(size[0]), int(size[1])
    c = model.cart.mean(axis=0)
    R = default_orientation(model.cart)
    sc = fit_scale(model, R, c, aspect=W / H)
    # labels: keep the same size relative to the picture as a 10 pt label on a 6 inch high image
    f = (H / dpi) / 6.0 if not low.endswith('.gif') else H / 600.0
    s.label_size *= f
    s.halo_width *= f            # halo and line widths are in points too: scale them with the labels
    s.line_width *= f
    if low.endswith('.gif'):
        return export_gif(out, model, st, R, c, sc, (0, 0), s, styles, W, H, frames=frames, shadows=True,
                          progress=progress, transparent=transparent)
    if low.endswith('.pov'):
        return export_pov(out, model, st, R, c, sc, (0, 0), s, styles, W / H, image_height_in=H / dpi,
                          shadows=shadows or engine.startswith('POV'), width_px=W, height_px=H,
                          antialias=antialias)
    return export_image(out, model, st, R, c, sc, (0, 0), s, styles, W, H, dpi, transparent, antialias=antialias,
                        shadows=shadows, engine=engine, povray_exe=povray_exe, progress=progress)
