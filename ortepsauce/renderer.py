"""ORTEP-style renderer: depth-sorted 2D projection drawn with matplotlib paths.

Ellipsoids are drawn the classic ORTEP way: the projected outline (exact for an
orthographic view), the front halves of the three principal ellipses and a shaded
front octant. Because everything is a vector path, output is resolution independent
(PNG at any DPI, SVG, PDF).
"""
import math

import numpy as np
from matplotlib.collections import PathCollection
from matplotlib.colors import to_rgba
from matplotlib.path import Path

from .edits import BOND_WIDTHS, dash_segments
from .elements import QPEAK_COLOR
from .settings import RenderSettings  # noqa: F401  (re-exported)


def _P(verts, closed=False):
    """Path helper. matplotlib ignores the last vertex of a closed path, so repeat the first."""
    verts = np.asarray(verts, float)
    if closed:
        return Path(np.vstack([verts, verts[:1]]), closed=True)
    return Path(verts)


def probability_scale(p):
    """Radius scale k such that P(chi^2_3 <= k^2) = p (e.g. 50 % -> 1.5382)."""
    def cdf(x):
        return math.erf(math.sqrt(x / 2)) - math.sqrt(2 * x / math.pi) * math.exp(-x / 2)
    lo, hi = 0.0, 50.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return math.sqrt(0.5 * (lo + hi))


def _darken(rgba, f):
    r, g, b, a = rgba
    return (r * f, g * f, b * f, a)


_NONE = (0, 0, 0, 0)
_BLACK = (0, 0, 0, 1)


class OrtepRenderer:
    def __init__(self, settings=None, styles=None):
        from .styles import StyleTable
        self.s = settings or RenderSettings()
        self.styles = styles or StyleTable()
        # filled on each draw, used for picking
        self.screen_xy = np.zeros((0, 2))
        self.screen_r = np.zeros(0)
        self.visible = np.zeros(0, bool)

    # ------------------------------------------------------------------
    def _atom_colors(self, el, label=''):
        m = self.styles.material(self.styles.atom_entry(label, el))
        base = tuple(m['color']) + (1.0,)
        cut = self.styles.material(self.styles.get('Cutout faces'))['color']
        dark = _darken(base, 0.55) if self.styles.preset != 'Monochrome' else tuple(cut) + (1.0,)
        return base, dark

    def draw(self, ax, model, R, center, cell=None):
        """Add the vector ORTEP drawing to `ax` (labels / selection are drawn by overlay.py).
        R: 3x3 rotation (rows = screen x, y, z toward viewer); center: rotation centre (Cart.)
        Returns (projected centres, projected radii, visible mask)."""
        s = self.s
        k = probability_scale(s.probability / 100.0)

        n = model.n
        is_h = model.is_h() if n else np.zeros(0, bool)
        visible = np.ones(n, bool)
        if not s.show_h:
            visible &= ~is_h
        if getattr(s, 'excluded', None):
            visible &= np.array([lab not in s.excluded for lab in model.labels], bool)
        if getattr(s, 'hidden_keys', None):
            visible &= np.array([f'{model.labels[k]}|{model.symop[k]}' not in s.hidden_keys
                                 for k in range(len(model.labels))], bool)
        self.visible = visible
        wire_set = getattr(s, 'wire', None) or set()
        wire = np.array([lab in wire_set for lab in model.labels], bool) if n else np.zeros(0, bool)

        X = (model.cart - center) @ R.T if n else np.zeros((0, 3))
        zspan = max(np.abs(X[:, 2]).max() if n else 1.0, 1.0)

        items = []   # (depth, suborder, path, face, edge, lw, ls)
        radii_screen = np.zeros(n)
        u_rot = np.zeros((n, 3, 3))
        u_inv = np.zeros((n, 3, 3))
        sphere_r = np.zeros(n)

        tt = np.linspace(0, 2 * np.pi, 61)
        circle = np.stack([np.cos(tt), np.sin(tt)], axis=1)

        for i in range(n):
            if not visible[i]:
                continue
            c = X[i]
            face, dark = self._atom_colors(model.elements[i], model.labels[i])
            if wire[i]:
                radii_screen[i] = getattr(s, 'wire_radius', 0.025)
                continue
            if model.elements[i] == 'Cg':
                r = getattr(s, 'centroid_radius', 0.09)
                sphere_r[i] = radii_screen[i] = r
                items.append((c[2], 0, _P(c[:2] + r * circle, closed=True), face, _BLACK, s.line_width * 0.6, '-'))
                continue
            if is_h[i]:
                r = s.h_radius
                sphere_r[i] = r
                radii_screen[i] = r
                items.append((c[2], 0, _P(c[:2] + r * circle, closed=True), face, _BLACK, s.line_width * 0.7, '-'))
                continue
            U = R @ model.ucart[i] @ R.T
            u_rot[i] = U
            if not model.aniso[i]:
                r = k * math.sqrt(max(U[0, 0], 1e-6))
                sphere_r[i] = r
                radii_screen[i] = r
                items.append((c[2], 0, _P(c[:2] + r * circle, closed=True), face, _BLACK, s.line_width, '-'))
                continue
            u_inv[i] = np.linalg.inv(U)
            # projected outline: marginal 2x2 covariance
            C2 = (k * k) * U[:2, :2]
            w, v = np.linalg.eigh(C2)
            w = np.sqrt(np.clip(w, 1e-8, None))
            outline = c[:2] + (circle * w) @ v.T
            radii_screen[i] = w.max()
            items.append((c[2], 0, _P(outline, closed=True), face, _BLACK, s.line_width, '-'))

            lam, vec = np.linalg.eigh(U)
            axes = (k * np.sqrt(np.clip(lam, 1e-8, None)))[None, :] * vec   # columns = semi-axes
            if s.octant:
                sg = np.where(axes[2] >= 0, 1.0, -1.0)
                ca = axes * sg[None, :]
                q = np.linspace(0, np.pi / 2, 16)
                pts = []
                for a_, b_ in ((0, 1), (1, 2), (2, 0)):
                    arc = np.outer(np.cos(q), ca[:, a_]) + np.outer(np.sin(q), ca[:, b_])
                    pts.append(arc[:-1])
                poly = c[:2] + np.concatenate(pts)[:, :2]
                items.append((c[2], 1, _P(poly, closed=True), dark, _BLACK, s.line_width * 0.6, '-'))
            if s.principal:
                for a_, b_ in ((0, 1), (1, 2), (2, 0)):
                    ea, eb = axes[:, a_], axes[:, b_]
                    phi = math.atan2(eb[2], ea[2])
                    t = np.linspace(phi - np.pi / 2, phi + np.pi / 2, 31)
                    arc = np.outer(np.cos(t), ea) + np.outer(np.sin(t), eb)
                    items.append((c[2], 2, _P(c[:2] + arc[:, :2]), _NONE, _BLACK, s.line_width * 0.6, '-'))

        # ---- bonds
        bond_rgba = [tuple(self.styles.material(self.styles.get(t))['color']) + (1.0,)
                     for t in ('Bonds', 'H bonds')]
        for i, j in model.bonds:
            if not (visible[i] and visible[j]):
                continue
            a, b = X[i], X[j]
            d = b - a
            L = np.linalg.norm(d)
            if L < 1e-6:
                continue
            u = d / L
            if wire[i] or wire[j]:
                ra = 0.0 if wire[i] else self._exit_radius(i, u, k, model, is_h, sphere_r, u_inv)
                rb = 0.0 if wire[j] else self._exit_radius(j, -u, k, model, is_h, sphere_r, u_inv)
                if ra + rb >= L - 0.02:
                    continue
                pa, pb = a + ra * u, b - rb * u
                mid = 0.5 * (pa + pb)
                for p_, q_, at in ((pa, mid, i), (mid, pb, j)):
                    col = self._atom_colors(model.elements[at], model.labels[at])[0]
                    items.append((0.5 * (p_[2] + q_[2]), 0, _P(np.array([p_[:2], q_[:2]])), _NONE, col,
                                  s.line_width * 1.2, '-'))
                continue
            ra = self._exit_radius(i, u, k, model, is_h, sphere_r, u_inv)
            rb = self._exit_radius(j, -u, k, model, is_h, sphere_r, u_inv)
            if ra + rb >= L - 0.02:
                continue
            pa = a + ra * u
            pb = b - rb * u
            mid = 0.5 * (pa + pb)
            ci = self._atom_colors(model.elements[i], model.labels[i])[0]
            cj = self._atom_colors(model.elements[j], model.labels[j])[0]
            xh = is_h[i] or is_h[j]
            if s.bond_coloring != 'Split by atom':
                ci = cj = bond_rgba[1] if xh else bond_rgba[0]
            br = s.hbond_radius if xh else s.bond_radius
            bst = (getattr(model, 'bond_style', {}) or {}).get((min(i, j), max(i, j)))
            if bst and (bst.get('style', 'Solid') != 'Solid' or bst.get('width', 'Normal') != 'Normal'):
                br *= BOND_WIDTHS.get(bst.get('width', 'Normal'), 1.0)
                col = bond_rgba[1] if xh else bond_rgba[0]
                for piece in dash_segments(pa, pb, bst.get('style', 'Solid'), br):
                    if piece[0] == 'cyl':
                        self._bond_poly(items, piece[1], piece[2], br, col, zspan)
                    else:
                        q = piece[1]
                        items.append((q[2], 0, _P(q[:2] + 1.25 * br * circle, closed=True), col, col, 0.3, '-'))
                continue
            if ci == cj:
                self._bond_poly(items, pa, pb, br, ci, zspan)
            else:
                self._bond_poly(items, pa, mid, br, ci, zspan)
                self._bond_poly(items, mid, pb, br, cj, zspan)

        # ---- Q-peaks
        q_draw = []
        if s.show_q and len(model.q_labels):
            Q = (model.q_cart - center) @ R.T
            order = np.argsort(-model.q_height)[:max(0, int(s.q_count))]
            qface = to_rgba(QPEAK_COLOR)
            for qi in order:
                c = Q[qi]
                items.append((c[2], 0, _P(c[:2] + 0.13 * circle, closed=True), qface, _BLACK, s.line_width * 0.5, '-'))
                q_draw.append((qi, c))
                if n:
                    dist = np.linalg.norm(X - c, axis=1)
                    for j in np.nonzero((dist < 1.7) & (dist > 0.3) & visible & ~is_h)[0]:
                        seg = _P(np.array([c[:2], X[j, :2]]))
                        items.append((0.5 * (c[2] + X[j, 2]), -1, seg, _NONE, to_rgba('#8060a0'), 0.8, '--'))

        # ---- unit cell
        if s.show_cell and cell is not None:
            corners = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], float)
            P = (corners @ cell.A.T - center) @ R.T
            edges = [(0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3), (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7)]
            col = {(0, 4): '#d62728', (0, 2): '#2ca02c', (0, 1): '#1f77b4'}
            for e in edges:
                seg = _P(P[list(e), :2])
                items.append((P[list(e), 2].mean(), -1, seg, _NONE, to_rgba(col.get(e, '#555555')),
                              1.4 if e in col else 0.8, '-'))
        # ---- assemble in painter's order
        items.sort(key=lambda t: (t[0], t[1]))
        if items:
            pc = PathCollection([t[2] for t in items],
                                facecolors=[t[3] for t in items],
                                edgecolors=[t[4] for t in items],
                                linewidths=[t[5] for t in items],
                                linestyles=[t[6] for t in items],
                                joinstyle='round', capstyle='round')
            pc.set_transform(ax.transData)
            ax.add_collection(pc, autolim=False)

        self.q_draw = q_draw
        self.screen_xy = X[:, :2] if n else np.zeros((0, 2))
        self.screen_r = radii_screen
        return self.screen_xy, radii_screen, visible

    # ------------------------------------------------------------------
    @staticmethod
    def set_limits(ax, scale, pan):
        bbox = ax.get_window_extent()
        aspect = bbox.width / max(bbox.height, 1)
        ax.set_xlim(pan[0] - scale * aspect, pan[0] + scale * aspect)
        ax.set_ylim(pan[1] - scale, pan[1] + scale)

    def _exit_radius(self, i, u, k, model, is_h, sphere_r, u_inv):
        if is_h[i] or not model.aniso[i]:
            return sphere_r[i]
        return k / math.sqrt(max(u @ u_inv[i] @ u, 1e-8))

    def _bond_poly(self, items, p0, p1, radius, color, zspan):
        d = p1[:2] - p0[:2]
        L = np.hypot(*d)
        if L < 1e-4:
            return
        nrm = np.array([-d[1], d[0]]) / L
        w0 = radius * (1 + self.s.bond_taper * p0[2] / zspan)
        w1 = radius * (1 + self.s.bond_taper * p1[2] / zspan)
        poly = np.array([p0[:2] + w0 * nrm, p1[:2] + w1 * nrm, p1[:2] - w1 * nrm, p0[:2] - w0 * nrm])
        items.append((0.5 * (p0[2] + p1[2]), 0, _P(poly, closed=True), color, _BLACK, self.s.line_width * 0.8, '-'))

    def pick(self, x, y, tol=0.25):
        """Return the index of the atom under screen point (x, y) in Angstrom, or None."""
        if len(self.screen_xy) == 0:
            return None
        d = np.hypot(self.screen_xy[:, 0] - x, self.screen_xy[:, 1] - y)
        d = np.where(self.visible, d - self.screen_r, np.inf)
        i = int(np.argmin(d))
        return i if d[i] < tol else None
