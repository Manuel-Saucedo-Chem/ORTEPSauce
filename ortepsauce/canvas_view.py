"""Draws a structure into a matplotlib Axes: shaded raster image or vector line drawing,
plus the overlay (labels, Q-peak labels, cell axis letters, selection rings).
Shared by the GUI, image export and GIF export so all three look identical."""
import numpy as np
from PIL import Image
from matplotlib import patheffects
from matplotlib.artist import Artist
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

from .raster import render_scene
from .renderer import OrtepRenderer
from .scene import build_scene
from .styles import NONMETALS, color_rgb, hex_to_rgb


def label_visible(settings, element):
    w = settings.label_which
    if w == 'All':
        return True
    if w == 'Non-H':
        return element not in ('H', 'D')
    if w == 'Heavy atoms':
        return element not in ('H', 'D', 'C')
    if w == 'Metals only':
        return element not in NONMETALS
    return True


def atom_label_visible(settings, model, i):
    """Element filter of the Labels tab + 'no labels on wire atoms' unless asked for."""
    if not label_visible(settings, model.elements[i]):
        return False
    if not getattr(settings, 'wire_labels', False) and model.labels[i] in getattr(settings, 'wire', ()):
        return False
    return True


def label_runs(model, i, settings, styles, name):
    """Label split into colored runs: with settings.label_elem_color the element symbol takes the
    atom color (e.g. 'Fe' pink, '1' in the label color)."""
    fc = tuple(color_rgb(settings.label_color))
    if not getattr(settings, 'label_elem_color', False) or styles is None:
        return [(name, fc)]
    el = model.elements[i]
    if not name[:len(el)].lower() == el.lower():
        return [(name, fc)]
    col = tuple(styles.material(styles.atom_entry(model.labels[i], el))['color'])
    if 0.3 * col[0] + 0.59 * col[1] + 0.11 * col[2] > 0.85:      # white H etc. would vanish
        col = fc
    runs = [(name[:len(el)], col)]
    if name[len(el):]:
        runs.append((name[len(el):], fc))
    return runs


def display_name(model, i, settings):
    return model.labels[i] + (settings.sym_suffix if model.generated[i] else '')


DRAG_FACTORS = {'Smooth (1/2 res)': 2, 'Faster (1/3 res)': 3, 'Fastest (1/4 res)': 4}


def _up2(a):
    """Smooth 2x enlargement (bilinear-like) using cheap uint8 arithmetic."""
    h, w = a.shape[:2]
    a2 = a >> 1
    r2 = np.empty_like(a2)
    r2[:, :-1] = a2[:, 1:]
    r2[:, -1] = a2[:, -1]
    d2 = np.empty_like(a2)
    d2[:-1] = a2[1:]
    d2[-1] = a2[-1]
    dr = np.empty_like(a2)
    dr[:-1] = r2[1:]
    dr[-1] = r2[-1]
    out = np.empty((2 * h, 2 * w) + a.shape[2:], np.uint8)
    out[0::2, 0::2] = a
    out[0::2, 1::2] = a2 + r2
    out[1::2, 0::2] = a2 + d2
    out[1::2, 1::2] = (a2 >> 1) + (r2 >> 1) + (d2 >> 1) + (dr >> 1)
    return out


def upscale(a, f):
    if f == 2:
        return _up2(a)
    if f == 4:
        return _up2(_up2(a))
    h, w = a.shape[:2]
    return np.asarray(Image.fromarray(a, 'RGBA').resize((w * f, h * f), Image.BILINEAR))


class RawImage(Artist):
    """Figure-level RGBA uint8 image drawn pixel-for-pixel (row 0 = top of the figure)."""

    def __init__(self, data):
        super().__init__()
        self.set_zorder(-10)
        self.set_data(data)

    def set_data(self, data):
        self._data = np.ascontiguousarray(data[::-1])
        self.stale = True

    def draw(self, renderer):
        if not self.get_visible():
            return
        gc = renderer.new_gc()
        renderer.draw_image(gc, 0, 0, self._data)
        gc.restore()


class SceneView:
    def __init__(self, ax):
        self.ax = ax
        self.image = None
        self.artists = []
        self.anchor_xy = np.zeros((0, 2))
        self.anchor_r = np.zeros(0)
        self.visible = np.zeros(0, bool)
        self.oid = None
        self.sel_bond = None
        self.highlight = []
        self.extent = None
        self.label_positions = []      # (text, x, y) for POV export
        self._pool = {}                # atom index -> (runs, [Text artists])
        self.styles = None
        self._pool_sig = None
        self._last_overlay = ([], None)

    def _clear(self):
        for a in self.artists:
            try:
                a.remove()
            except (ValueError, AttributeError):
                pass
        self.artists = []

    def draw(self, model, struct, R, center, scale, pan, settings, styles, width_px, height_px,
             selection=(), fast=False, ss=None, transparent=False):
        ax = self.ax
        s = settings
        self.styles = styles
        self._clear()
        aspect = width_px / max(height_px, 1)
        x0, x1 = pan[0] - scale * aspect, pan[0] + scale * aspect
        y0, y1 = pan[1] - scale, pan[1] + scale
        bg = hex_to_rgb(s.background)
        ax.set_facecolor('none' if transparent else s.background)
        cell = struct.cell if struct is not None else None

        if model is None or model.n == 0:
            if self.image is not None:
                self.image.set_visible(False)
            ax.set_xlim(x0, x1)
            ax.set_ylim(y0, y1)
            return

        if s.atom_style == 'Line drawing (vector)':
            if self.image is not None:
                self.image.set_visible(False)
            ax.patch.set_visible(not transparent)
            rend = OrtepRenderer(s, styles)
            n_before = len(ax.collections)
            xy, rr, vis = rend.draw(ax, model, R, center, cell=cell)
            self.artists += list(ax.collections[n_before:])
            self.anchor_xy, self.anchor_r, self.visible = xy, rr, vis
            self.oid = None
            q_xy = [(qi, c[:2]) for qi, c in getattr(rend, 'q_draw', [])]
            cell_P = None
            if s.show_cell and cell is not None:
                corners = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], float)
                cell_P = (corners @ cell.A.T - center) @ R.T
        else:
            scene = build_scene(model, R, center, s, styles, cell=cell)
            W, H = int(width_px), int(height_px)
            if fast:
                f = DRAG_FACTORS.get(s.drag_quality, 2)
                if W * H < 400_000:
                    f = min(f, 2)
            else:
                f = 1
            w, h = (-(-W // f), -(-H // f)) if f > 1 else (W, H)
            sup = 1 if fast else (ss or s.antialias)
            # render the reduced frame over exactly the same area (w*f >= W, so widen the extent)
            sc_f = scale * (h * f) / H
            pan_f = (pan[0] + (w * f - W) / 2 * (2 * scale / H), pan[1] - (h * f - H) / 2 * (2 * scale / H))
            rgba, oid = render_scene(scene, w, h, sc_f, pan_f, s, ss=sup, background=bg,
                                     transparent=transparent, quick=bool(fast))
            if f > 1:
                rgba = upscale(rgba, f)[:H, :W]
            self.show_raster(model, scene, rgba, oid, (x0, x1, y0, y1), s, selection, halo=not fast)
            return

        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        self._overlay(model, s, selection, q_xy, cell_P, halo=not fast)

    def show_raster(self, model, scene, rgba, oid, extent, s, selection=(), halo=True, styles=None):
        """Display an already rendered frame (used directly by the GUI's background renderer)."""
        ax = self.ax
        if styles is not None:
            self.styles = styles
        self._clear()
        # RawImage puts the pixels 1:1 on the figure - no matplotlib resampling cost
        if self.image is None:
            self.image = RawImage(rgba)
            ax.figure.add_artist(self.image)
        else:
            self.image.set_data(rgba)
            self.image.set_visible(True)
        ax.patch.set_visible(False)
        self.oid = oid
        self.extent = extent
        self.anchor_xy, self.anchor_r, self.visible = scene.anchor_xy, scene.anchor_r, scene.visible
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        self._overlay(model, s, selection, scene.q_xy, scene.cell_corners, halo=halo)

    # ------------------------------------------------------------------ overlay
    def refresh_overlay(self, model, s, selection=()):
        """Redraw only labels / selection on top of the current picture (cheap)."""
        self._clear()
        self._overlay(model, s, selection, *self._last_overlay)

    def _overlay(self, model, s, selection, q_xy, cell_P, halo=True):
        self._last_overlay = (q_xy, cell_P)
        ax = self.ax
        self.label_positions = []
        is_h = model.is_h()
        if s.labels_on:
            fc = color_rgb(s.label_color)
            use_halo = s.label_halo and halo
            sig = (id(model), s.label_size, s.label_font, s.label_bold, s.label_italic, fc, use_halo,
                   s.background, s.sym_suffix, s.halo_width)
            if sig != self._pool_sig:            # (re)build the reusable label artists
                for _, arts in self._pool.values():
                    for a in arts:
                        a.remove()
                self._pool = {}
                self._pool_sig = sig
            fx = [patheffects.withStroke(linewidth=s.halo_width, foreground=s.background)] if use_halo else None
            shown = set()
            for i in range(model.n):
                if not self.visible[i] or not atom_label_visible(s, model, i):
                    continue
                name = display_name(model, i, s)
                if name in s.hidden_labels:
                    continue
                off = 0.7 * self.anchor_r[i] + s.label_offset
                dx, dy = s.label_offsets.get(name, (0.0, 0.0))
                x, y = self.anchor_xy[i, 0] + off + dx, self.anchor_xy[i, 1] + off + dy
                runs = label_runs(model, i, s, self.styles, name)
                ent = self._pool.get(i)
                if ent is not None and ent[0] != runs:
                    for a in ent[1]:
                        a.remove()
                    ent = None
                if ent is None:
                    kw = dict(fontsize=s.label_size * (0.8 if is_h[i] else 1.0), family=s.label_font,
                              weight='bold' if s.label_bold else 'normal',
                              style='italic' if s.label_italic else 'normal', zorder=20, va='bottom',
                              path_effects=fx)
                    arts = [ax.text(x, y, runs[0][0], color=runs[0][1], ha='left', **kw)]
                    for t_, c_ in runs[1:]:
                        arts.append(ax.annotate(t_, xy=(1, 0), xycoords=arts[-1], color=c_, ha='left', **kw))
                    self._pool[i] = (runs, arts)
                else:
                    ent[1][0].set_position((x, y))
                    for a in ent[1]:
                        a.set_visible(True)
                shown.add(i)
                self.label_positions.append((name, x, y))
            for i, (_, arts) in self._pool.items():
                if i not in shown:
                    for a in arts:
                        a.set_visible(False)
        else:
            for _, arts in self._pool.values():
                for a in arts:
                    a.set_visible(False)
        if s.labels_on:
            for qi, c in q_xy:
                self.artists.append(ax.text(c[0] + 0.12, c[1] + 0.12, model.q_labels[qi],
                                            fontsize=s.label_size * 0.75, color='#6a4c93', zorder=20,
                                            family=s.label_font))
        if cell_P is not None:
            cols = {4: '#d62728', 2: '#2ca02c', 1: '#1f77b4', 0: '#333333'}
            for idx, name in ((0, 'O'), (4, 'a'), (2, 'b'), (1, 'c')):
                self.artists.append(ax.text(cell_P[idx, 0], cell_P[idx, 1], ' ' + name, fontsize=s.label_size,
                                            zorder=21, color=cols[idx], family=s.label_font))
        for i, col in getattr(self, 'highlight', None) or []:
            if i < len(self.anchor_r) and (i >= len(self.visible) or self.visible[i]):
                ring = Circle(self.anchor_xy[i], self.anchor_r[i] + 0.16, fill=False, edgecolor=col,
                              linewidth=2.6, linestyle='--', zorder=30)
                ax.add_patch(ring)
                self.artists.append(ring)
        sb = getattr(self, 'sel_bond', None)
        if sb is not None and max(sb) < len(self.anchor_xy):
            p, q = self.anchor_xy[sb[0]], self.anchor_xy[sb[1]]
            ln = Line2D([p[0], q[0]], [p[1], q[1]], color='#0077ff', alpha=0.55, linewidth=7,
                        solid_capstyle='round', zorder=29)
            ax.add_line(ln)
            self.artists.append(ln)
        for num, i in enumerate(selection, 1):
            if i >= len(self.anchor_r) or (i < len(self.visible) and not self.visible[i]):
                continue
            r = self.anchor_r[i] + 0.12
            ring = Circle(self.anchor_xy[i], r, fill=False, edgecolor='#0077ff', linewidth=2.0, zorder=30)
            ax.add_patch(ring)
            self.artists.append(ring)
            self.artists.append(ax.text(self.anchor_xy[i, 0] - r, self.anchor_xy[i, 1] + r, str(num),
                                        color='#0077ff', fontsize=min(max(s.label_size, 9), 18), fontweight='bold',
                                        zorder=31, ha='right', va='bottom'))

    # ------------------------------------------------------------------ picking
    def pick(self, x, y, tol=0.25):
        if self.oid is not None and self.extent is not None:
            x0, x1, y0, y1 = self.extent
            H, W = self.oid.shape
            i = int((x - x0) / (x1 - x0) * W)
            j = int((y1 - y) / (y1 - y0) * H)
            if 0 <= i < W and 0 <= j < H:
                o = int(self.oid[j, i])
                if o >= 0:
                    return o
        if len(self.anchor_xy) == 0:
            return None
        d = np.hypot(self.anchor_xy[:, 0] - x, self.anchor_xy[:, 1] - y) - self.anchor_r
        d = np.where(self.visible, d, np.inf)
        i = int(np.argmin(d))
        return i if d[i] < tol else None
