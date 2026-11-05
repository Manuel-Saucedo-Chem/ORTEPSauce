"""Turns a Model + view + settings + style table into renderer-independent 3D primitives
(in the rotated screen frame: x right, y up, z toward the viewer, Angstrom units).
Used by both the on-screen raster renderer and the POV-Ray exporter."""
import math

import numpy as np

from .edits import BOND_WIDTHS, dash_segments
from .elements import covalent_radius, vdw_radius
from .renderer import probability_scale


class Scene:
    def __init__(self):
        self.prims = []          # list of dicts
        self.materials = []      # list of material dicts (see StyleTable.material) + 'key'
        self._mat_index = {}
        self.anchor_xy = np.zeros((0, 2))   # projected atom centres
        self.anchor_r = np.zeros(0)         # projected radius (for label offsets / picking)
        self.visible = np.zeros(0, bool)
        self.wire = np.zeros(0, bool)
        self.q_xy = []                       # (index, xy) of drawn Q-peaks
        self.cell_corners = None             # 8x3 screen coords when the cell is shown

    def mat(self, key, material):
        if key not in self._mat_index:
            m = dict(material)
            m['key'] = key
            self._mat_index[key] = len(self.materials)
            self.materials.append(m)
        return self._mat_index[key]


def _ident(text):
    return ''.join(ch if ch.isalnum() else '_' for ch in text)


def _entry_key(entry):
    return tuple(sorted((k, str(v)) for k, v in entry.items() if k != 'ellipse'))


def build_scene(model, R, center, settings, styles, cell=None):
    s = settings
    sc = Scene()
    n = model.n
    k = probability_scale(s.probability / 100.0)
    X = (model.cart - center) @ R.T if n else np.zeros((0, 3))
    is_h = model.is_h() if n else np.zeros(0, bool)
    visible = np.ones(n, bool)
    if not s.show_h:
        visible &= ~is_h
    if getattr(s, 'excluded', None):
        visible &= np.array([lab not in s.excluded for lab in model.labels], bool)
    if getattr(s, 'hidden_keys', None):
        visible &= np.array([f'{model.labels[k]}|{model.symop[k]}' not in s.hidden_keys
                             for k in range(len(model.labels))], bool)
    sc.visible = visible
    wire_set = getattr(s, 'wire', None) or set()
    wire = np.array([lab in wire_set for lab in model.labels], bool) if n else np.zeros(0, bool)
    wr = float(getattr(s, 'wire_radius', 0.025))
    sc.wire = wire
    sc.anchor_xy = X[:, :2].copy()
    sc.anchor_r = np.zeros(n)

    style = s.atom_style
    band_m = sc.mat('Equators', styles.material(styles.get('Equators')))
    cut_m = sc.mat('Cutout faces', styles.material(styles.get('Cutout faces')))

    atom_mats = []
    cache = {}
    for i in range(n):
        el, lab = model.elements[i], model.labels[i]
        hit = cache.get((lab, el))
        if hit is None:
            ent = styles.atom_entry(lab, el)
            material = styles.material(ent)
            own = {k: v for k, v in styles.entries.get(f'Atom:{lab}', {}).items() if k != 'ellipse'}
            material['pov_name'] = 'Texture_' + _ident(lab if own else el)
            hit = (sc.mat(('atom',) + _entry_key(ent), material), ent)
            cache[(lab, el)] = hit
        atom_mats.append(hit)

    draw_bonds = style not in ('Van der Waals',)
    for i in range(n):
        if not visible[i]:
            continue
        c = X[i]
        mi, ent = atom_mats[i]
        if model.elements[i] == 'Cg':
            r = float(getattr(s, 'centroid_radius', 0.09))
            sc.prims.append(dict(type='ellipsoid', c=c, V=np.eye(3), a=np.full(3, r), style='PlainEllipse',
                                 mat=mi, band=band_m, cut=cut_m, oid=i))
            sc.anchor_r[i] = r
            continue
        if wire[i]:
            # thin line look: only a joint sphere as wide as the wire, bonds carry the color
            sc.prims.append(dict(type='ellipsoid', c=c, V=np.eye(3), a=np.full(3, wr), style='PlainEllipse',
                                 mat=mi, band=band_m, cut=cut_m, oid=i))
            sc.anchor_r[i] = wr
            continue
        if style == 'Van der Waals':
            r = vdw_radius(model.elements[i]) * s.vdw_scale
            sc.prims.append(dict(type='ellipsoid', c=c, V=np.eye(3), a=np.full(3, r), style='PlainEllipse',
                                 mat=mi, band=band_m, cut=cut_m, oid=i))
            sc.anchor_r[i] = r
            continue
        if style == 'Ball and Stick':
            r = s.ball_scale * covalent_radius(model.elements[i])
            sc.prims.append(dict(type='ellipsoid', c=c, V=np.eye(3), a=np.full(3, r), style='PlainEllipse',
                                 mat=mi, band=band_m, cut=cut_m, oid=i))
            sc.anchor_r[i] = r
            continue
        if style == 'Rods':
            r = s.rod_radius
            sc.prims.append(dict(type='ellipsoid', c=c, V=np.eye(3), a=np.full(3, r), style='PlainEllipse',
                                 mat=mi, band=band_m, cut=cut_m, oid=i))
            sc.anchor_r[i] = r
            continue
        if is_h[i]:
            r = s.h_radius
            sc.prims.append(dict(type='ellipsoid', c=c, V=np.eye(3), a=np.full(3, r), style='PlainEllipse',
                                 mat=mi, band=band_m, cut=cut_m, oid=i))
            sc.anchor_r[i] = r
            continue
        U = R @ model.ucart[i] @ R.T
        if style in ('RMSD surface', 'MSD surface') and model.aniso[i]:
            lam = np.linalg.eigvalsh(U)
            ueq = float(np.trace(U) / 3)
            kind = 'rmsd' if style == 'RMSD surface' else 'msd'
            rmax = k * math.sqrt(lam.max()) if kind == 'rmsd' else k * lam.max() / math.sqrt(ueq)
            sc.prims.append(dict(type='surface', c=c, U=U, kind=kind, k=k, ueq=ueq, rmax=rmax, mat=mi, oid=i))
            sc.anchor_r[i] = rmax
            continue
        if model.aniso[i]:
            lam, V = np.linalg.eigh(U)
            a = k * np.sqrt(np.clip(lam, 1e-8, None))
            est = ent.get('ellipse', 'BoundaryEllipse')
        else:
            V = np.eye(3)
            a = np.full(3, k * math.sqrt(max(U[0, 0], 1e-6)))
            est = 'PlainEllipse'
        sc.prims.append(dict(type='ellipsoid', c=c, V=V, a=a, style=est, mat=mi, band=band_m, cut=cut_m, oid=i))
        M = (V * a ** 2) @ V.T
        sc.anchor_r[i] = math.sqrt(max(M[0, 0], M[1, 1]))

    # ---- bonds
    if draw_bonds or wire.any() or getattr(model, 'bond_style', None):
        bond_m = sc.mat('Bonds', styles.material(styles.get('Bonds')))
        hbond_m = sc.mat('H bonds', styles.material(styles.get('H bonds')))
        split = s.bond_coloring == 'Split by atom' or style in ('Rods',)
        bstyle = getattr(model, 'bond_style', {}) or {}
        for bi, (i, j) in enumerate(model.bonds):
            if not (visible[i] and visible[j]):
                continue
            p0, p1 = X[i], X[j]
            bst = bstyle.get((min(i, j), max(i, j)))
            if bst and (bst.get('style', 'Solid') != 'Solid' or bst.get('width', 'Normal') != 'Normal'):
                xh = is_h[i] or is_h[j]
                base = wr if (wire[i] or wire[j]) else (s.hbond_radius if xh else s.bond_radius)
                if style == 'Rods':
                    base = s.rod_radius
                elif style == 'Ball and Stick':
                    base = s.stick_radius
                r = base * BOND_WIDTHS.get(bst.get('width', 'Normal'), 1.0)
                m_ = hbond_m if xh else bond_m
                for piece in dash_segments(p0, p1, bst.get('style', 'Solid'), r):
                    if piece[0] == 'cyl':
                        sc.prims.append(dict(type='cylinder', p0=piece[1], p1=piece[2], r=r, mat=m_, oid=-1))
                    else:
                        sc.prims.append(dict(type='ellipsoid', c=piece[1], V=np.eye(3), a=np.full(3, 1.25 * r),
                                             style='PlainEllipse', mat=m_, band=band_m, cut=cut_m, oid=-1))
                continue
            if wire[i] or wire[j]:
                mid = 0.5 * (p0 + p1)
                sc.prims.append(dict(type='cylinder', p0=p0, p1=mid, r=wr, mat=atom_mats[i][0], oid=-1))
                sc.prims.append(dict(type='cylinder', p0=mid, p1=p1, r=wr, mat=atom_mats[j][0], oid=-1))
                continue
            if not draw_bonds:
                continue
            xh = is_h[i] or is_h[j]
            if style == 'Rods':
                r = s.rod_radius
            elif style == 'Ball and Stick':
                r = s.stick_radius * (0.7 if xh else 1.0)
            else:
                r = s.hbond_radius if xh else s.bond_radius
            p0, p1 = X[i], X[j]
            if split:
                mid = 0.5 * (p0 + p1)
                sc.prims.append(dict(type='cylinder', p0=p0, p1=mid, r=r, mat=atom_mats[i][0], oid=-1))
                sc.prims.append(dict(type='cylinder', p0=mid, p1=p1, r=r, mat=atom_mats[j][0], oid=-1))
            else:
                sc.prims.append(dict(type='cylinder', p0=p0, p1=p1, r=r, mat=hbond_m if xh else bond_m, oid=-1))

    # ---- Q-peaks
    if s.show_q and len(model.q_labels):
        qm = sc.mat('Q-peaks', dict(color=(0.78, 0.64, 0.86), finish=dict(
            ambient=0.1, diffuse=0.6, brilliance=1, specular=0.6, roughness=0.02, phong=0, phong_size=40,
            reflection=0, metallic=False, crand=0), pattern=None, name=None))
        Q = (model.q_cart - center) @ R.T
        for qi in np.argsort(-model.q_height)[:max(0, int(s.q_count))]:
            sc.prims.append(dict(type='ellipsoid', c=Q[qi], V=np.eye(3), a=np.full(3, 0.13),
                                 style='PlainEllipse', mat=qm, band=band_m, cut=cut_m, oid=-2))
            sc.q_xy.append((int(qi), Q[qi, :2]))

    # ---- unit cell
    if s.show_cell and cell is not None:
        corners = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], float)
        P = (corners @ cell.A.T - center) @ R.T
        sc.cell_corners = P
        cols = {(0, 4): (0.84, 0.15, 0.16), (0, 2): (0.17, 0.63, 0.17), (0, 1): (0.12, 0.47, 0.71)}
        flat = dict(ambient=0.6, diffuse=0.4, brilliance=1, specular=0, roughness=0.05, phong=0,
                    phong_size=40, reflection=0, metallic=False, crand=0)
        for e in [(0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3), (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7)]:
            col = cols.get(e, (0.35, 0.35, 0.35))
            m = sc.mat(('cell', col), dict(color=col, finish=flat, pattern=None, name=None))
            sc.prims.append(dict(type='cylinder', p0=P[e[0]], p1=P[e[1]], r=0.025 if e in cols else 0.015,
                                 mat=m, oid=-3))
    return sc
