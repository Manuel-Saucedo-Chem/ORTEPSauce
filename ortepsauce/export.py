"""Image, GIF and POV-Ray export (all off-screen, no GUI needed).

progress callbacks receive (fraction 0..1, message)."""
import copy
import math
import os
import shutil
import tempfile

import matplotlib
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .canvas_view import SceneView
from .pov_export import run_povray, write_ini, write_pov
from .raster import render_scene
from .scene import build_scene
from .styles import VECTOR_STYLES, hex_to_rgb
from .view import rot_x, rot_y, rot_z

class ExportCancelled(Exception):
    pass


DEFAULT_WIDTH = 6400
DEFAULT_HEIGHT = 4800
AA_THRESHOLD = 0.3


def _figure(width_in, height_in, dpi, background, transparent):
    fig = Figure(figsize=(width_in, height_in), dpi=dpi,
                 facecolor='none' if transparent else background)
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    return fig, ax


def _noop(*a):
    pass


def render_pixels(model, struct, R, center, scale, pan, settings, W, H, styles, antialias=True,
                  shadows=False, transparent=False, engine='Built-in', povray_exe=None, reflections=True,
                  progress=None):
    """Shaded picture as RGBA uint8 (no labels) + the Scene (for label anchors)."""
    progress = progress or _noop
    scene = build_scene(model, R, center, settings, styles, cell=struct.cell if struct else None)
    bg = hex_to_rgb(settings.background)
    if engine.startswith('POV'):
        if not povray_exe:
            raise RuntimeError('POV-Ray executable not set (Export tab → POV-Ray → Browse…).')
        tmp = tempfile.mkdtemp(prefix='ortepsauce_')
        try:
            pov = os.path.join(tmp, 'scene.pov')
            png = os.path.join(tmp, 'render.png')
            write_pov(pov, scene, settings, scale, W / H, pan=pan, labels=None,
                      shadows=shadows, reflections=reflections)
            progress(0.02, 'POV-Ray rendering …')
            ok, msg = run_povray(povray_exe, pov, png, W, H, antialias=antialias, threshold=AA_THRESHOLD,
                                 alpha=transparent,
                                 progress=lambda f: progress(0.02 + 0.83 * f, f'POV-Ray rendering {f:.0%}'))
            if not ok:
                raise RuntimeError(f'POV-Ray failed:\n{msg}')
            from PIL import Image
            rgba = np.asarray(Image.open(png).convert('RGBA')).copy()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        rgba, _ = render_scene(scene, W, H, scale, pan, settings, ss=2 if antialias else 1, background=bg,
                               transparent=transparent, shadows=shadows,
                               progress=lambda f, m: progress(0.85 * f, m))
    return rgba, scene


def export_image(path, model, struct, R, center, scale, pan, settings, styles,
                 width_px=DEFAULT_WIDTH, height_px=DEFAULT_HEIGHT, dpi=600, transparent=False, antialias=True,
                 shadows=False, engine='Built-in', povray_exe=None, reflections=True, progress=None):
    """Render width_px x height_px pixels (dpi is stored as print resolution) and save.
    Format from extension: png / tif / jpg / svg / pdf."""
    progress = progress or _noop
    W, H = int(width_px), int(height_px)
    fig, ax = _figure(W / dpi, H / dpi, dpi, settings.background, transparent)
    view = SceneView(ax)
    if settings.atom_style in VECTOR_STYLES:
        progress(0.3, 'Drawing …')
        view.draw(model, struct, R, center, scale, pan, settings, styles, W, H, transparent=transparent)
    else:
        rgba, scene = render_pixels(model, struct, R, center, scale, pan, settings, W, H, styles,
                                    antialias=antialias, shadows=shadows, transparent=transparent,
                                    engine=engine, povray_exe=povray_exe, reflections=reflections,
                                    progress=progress)
        aspect = W / H
        extent = (pan[0] - scale * aspect, pan[0] + scale * aspect, pan[1] - scale, pan[1] + scale)
        ax.set_facecolor('none' if transparent else settings.background)
        view.show_raster(model, scene, rgba, None, extent, settings, styles=styles)
    progress(0.9, 'Writing file …')
    kw = {}
    low = path.lower()
    if low.endswith(('.jpg', '.jpeg')):
        kw['pil_kwargs'] = {'quality': 95}
    elif low.endswith(('.tif', '.tiff')):
        kw['pil_kwargs'] = {'compression': 'tiff_lzw'}
    # keep text as editable text in SVG / PDF / EPS (Illustrator, Inkscape …)
    rc = {'svg.fonttype': 'none', 'pdf.fonttype': 42, 'ps.fonttype': 42}
    if low.endswith(('.eps', '.ps')):
        kw['format'] = 'eps' if low.endswith('.eps') else 'ps'
    with matplotlib.rc_context(rc):
        fig.savefig(path, dpi=dpi, transparent=transparent,
                    facecolor='none' if transparent else settings.background, **kw)
    progress(1.0, f'Saved {path}')
    return path


def spin_rotation(axis, angle, direction='Clockwise'):
    """Rotation about a SCREEN axis (x right, y up, z toward the viewer).
    'Clockwise' as seen looking from the positive end of the axis: from above for 'Vertical' (y),
    from the right for 'Horizontal' (x), from the viewer for 'In-plane' (z)."""
    sign = -1.0 if direction == 'Clockwise' else 1.0
    return {'Vertical': rot_y, 'Horizontal': rot_x, 'In-plane': rot_z}[axis](sign * angle)


def _gif_frame_worker(job):
    """Runs in a separate process: shaded pixels for one animation frame (no labels)."""
    (model, struct, Rf, center, scale, pan, settings, W, H, styles, shadows, transparent) = job
    rgba, scene = render_pixels(model, struct, Rf, center, scale, pan, settings, W, H, styles,
                                shadows=shadows, transparent=transparent)
    return rgba, scene


def _kill_pool(pool):
    """Stop a process pool now (do not wait for queued frames)."""
    if pool is None:
        return
    procs = list(getattr(pool, '_processes', {}).values())
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception:  # noqa: BLE001
        pass
    for p in procs:
        try:
            p.terminate()
        except Exception:  # noqa: BLE001
            pass


def _workers():
    env = os.environ.get('ORTEPSAUCE_WORKERS')
    if env and env.isdigit():
        return max(1, int(env))
    n = os.cpu_count() or 2
    return max(1, min(n - 1, 8))


def export_gif(path, model, struct, R, center, scale, pan, settings, styles, width_px=1200, height_px=900,
               frames=200, degrees=360.0, axis='Vertical', delay_ms=50, shadows=True, progress=None,
               direction='Clockwise', transparent=True, parallel=True, grain=False, matte=None, cancel=None):
    """Rotating animation (.gif, or .png = animated PNG with full alpha / true color).
    Frames are rendered in parallel processes with the full-quality renderer; labels are added
    afterwards exactly as on screen.
    grain: keep the per-pixel crand grain of Speckled-type finishes (it shimmers when animated).
    matte: color the soft edges and label halos are blended onto (the slide background) when the
    background is transparent; default = settings.background.
    cancel: optional threading.Event; when set, rendering stops (worker processes are terminated) and
    ExportCancelled is raised."""
    from PIL import Image
    progress = progress or _noop
    settings = copy.copy(settings)
    settings.grain = bool(grain)
    if transparent and matte:
        settings.background = matte
    W, H = int(width_px), int(height_px)
    dpi = 100
    fig, ax = _figure(W / dpi, H / dpi, dpi, settings.background, transparent)
    view = SceneView(ax)
    a = W / H
    extent = (pan[0] - scale * a, pan[0] + scale * a, pan[1] - scale, pan[1] + scale)
    rots = [spin_rotation(axis, math.radians(degrees) * f / frames, direction) @ R for f in range(frames)]
    vector = settings.atom_style in VECTOR_STYLES
    results = [None] * frames
    if not vector:
        jobs = [(model, struct, Rf, center, scale, pan, settings, W, H, styles, shadows, transparent)
                for Rf in rots]
        done = 0
        pool = None

        def check():
            if cancel is not None and cancel.is_set():
                raise ExportCancelled('Export cancelled')
        if parallel and frames > 2 and _workers() > 1:
            try:
                from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
                import multiprocessing as mp
                ctx = mp.get_context(os.environ['ORTEPSAUCE_MP']) if os.environ.get('ORTEPSAUCE_MP') else None
                pool = ProcessPoolExecutor(max_workers=_workers(), mp_context=ctx)
                futs = {pool.submit(_gif_frame_worker, j): k for k, j in enumerate(jobs)}
                pending = set(futs)
                while pending:
                    check()
                    fin, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
                    for fut in fin:
                        results[futs[fut]] = fut.result()
                        done += 1
                        progress(0.9 * done / frames, f'GIF frame {done}/{frames} ({_workers()} processes) …')
            except ExportCancelled:
                _kill_pool(pool)
                pool = None
                raise
            except Exception:  # noqa: BLE001 - e.g. no multiprocessing available: render serially
                results = [None] * frames
                done = 0
            finally:
                if pool is not None:
                    pool.shutdown(cancel_futures=True)
        for k, j in enumerate(jobs):
            if results[k] is None:
                check()
                results[k] = _gif_frame_worker(j)
                done += 1
                progress(0.9 * done / frames, f'GIF frame {done}/{frames} …')
    images = []
    for f in range(frames):
        if vector:
            if cancel is not None and cancel.is_set():
                raise ExportCancelled('Export cancelled')
            view.draw(model, struct, rots[f], center, scale, pan, settings, styles, W, H, ss=2,
                      transparent=transparent)
            progress(0.9 * (f + 1) / frames, f'GIF frame {f + 1}/{frames} …')
        else:
            rgba, scene = results[f]
            view.show_raster(model, scene, rgba, None, extent, settings, styles=styles)
        fig.canvas.draw()
        images.append(np.asarray(fig.canvas.buffer_rgba()).copy())
    progress(0.93, 'Encoding …')
    if path.lower().endswith('.png'):
        pil = [Image.fromarray(im, 'RGBA' if transparent else 'RGBA').convert('RGBA' if transparent else 'RGB')
               for im in images]
        pil[0].save(path, save_all=True, append_images=pil[1:], duration=delay_ms, loop=0,
                    disposal=1, blend=0)
    else:
        _save_gif(path, images, delay_ms, transparent, settings.background)
    progress(1.0, f'Saved {path}')
    return path


def _save_gif(path, images, delay_ms, transparent, background):
    """GIF: one 255-color palette for the whole animation + index 255 = transparent.
    GIF transparency is on/off per pixel, so soft edges are blended onto the background (matte) color.
    The palette is built only from the visible (opaque) pixels of up to 8 frames: median cut refined
    by k-means, so all 255 entries go to the molecule instead of the empty background."""
    from PIL import Image
    bg = np.array(hex_to_rgb(background)) * 255
    rgbs, masks, samples = [], [], []
    pick = set(np.linspace(0, len(images) - 1, min(8, len(images))).astype(int).tolist())
    rng = np.random.default_rng(0)
    for k, im in enumerate(images):
        a = im[..., 3:4].astype(np.float32) / 255.0
        rgb = im[..., :3].astype(np.float32)
        if transparent:
            rgb = rgb * a + bg * (1 - a)              # matte for the anti-aliased edge pixels
            masks.append(im[..., 3] < 128)
        rgb8 = np.clip(rgb + 0.5, 0, 255).astype(np.uint8)
        rgbs.append(Image.fromarray(rgb8))
        if k in pick:
            vis = rgb8[im[..., 3] >= 128] if transparent else rgb8.reshape(-1, 3)
            if len(vis) > 150_000:
                vis = vis[rng.choice(len(vis), 150_000, replace=False)]
            samples.append(vis)
    smp = np.concatenate(samples) if samples else np.zeros((1, 3), np.uint8)
    if transparent:
        smp = np.concatenate([smp, np.tile(np.clip(bg + 0.5, 0, 255).astype(np.uint8), (64, 1))])
    strip = Image.fromarray(smp[None, :, :])
    pal = strip.quantize(colors=255, method=Image.Quantize.MEDIANCUT, kmeans=4)
    frames_q = []
    for k, im in enumerate(rgbs):
        q = im.quantize(palette=pal, dither=Image.Dither.NONE)
        if transparent:
            arr = np.asarray(q).copy()
            arr[masks[k]] = 255
            q = Image.fromarray(arr, 'P')
            q.putpalette(pal.getpalette())
        frames_q.append(q)
    kw = dict(transparency=255) if transparent else {}
    frames_q[0].save(path, save_all=True, append_images=frames_q[1:], duration=delay_ms, loop=0,
                     optimize=False, disposal=2, **kw)


def export_pov(path, model, struct, R, center, scale, pan, settings, styles, aspect,
               include_labels=True, image_height_in=6.0, shadows=True, reflections=True,
               width_px=DEFAULT_WIDTH, height_px=DEFAULT_HEIGHT, antialias=True):
    """Write a .pov scene plus a matching .ini (Width/Height/Antialias/Antialias_Threshold)."""
    scene = build_scene(model, R, center, settings, styles, cell=struct.cell)
    labels = None
    if include_labels and settings.labels_on:
        fig, ax = _figure(image_height_in * aspect, image_height_in, 100, settings.background, False)
        view = SceneView(ax)
        view.styles = styles
        view.anchor_xy, view.anchor_r, view.visible = scene.anchor_xy, scene.anchor_r, scene.visible
        view._overlay(model, settings, (), [], None)
        labels = view.label_positions
    write_pov(path, scene, settings, scale, aspect, pan=pan, labels=labels,
              image_height_in=image_height_in, title=struct.title, shadows=shadows, reflections=reflections)
    base = os.path.splitext(path)[0]
    write_ini(base + '.ini', os.path.basename(path), width_px, height_px, antialias=antialias,
              threshold=AA_THRESHOLD, output=os.path.basename(base) + '.png')
    return path
