"""Percent buried volume (%V_bur) around a metal centre, computed on a grid as in SambVca.

%V_bur = 100 · (grid points of a sphere around the metal that lie inside any ligand atom) / (all points).
Defaults follow the usual SambVca settings: sphere radius 3.5 Å, Bondi radii scaled by 1.17,
mesh 0.10 Å, hydrogen atoms left out, sphere centred on the metal (crystal-structure position).
Quadrants: z from the metal towards the donor atom(s) of the ligand, x towards the first neighbour
of the (first) donor atom; quadrant values are %V_bur of each quarter of the sphere."""
import numpy as np

from .elements import VDW_RADII

# Bondi (1964) radii; elements Bondi did not list fall back on the program's vdW table (Alvarez 2013)
BONDI = {'H': 1.20, 'D': 1.20, 'He': 1.40, 'C': 1.70, 'N': 1.55, 'O': 1.52, 'F': 1.47, 'Ne': 1.54,
         'Si': 2.10, 'P': 1.80, 'S': 1.80, 'Cl': 1.75, 'Ar': 1.88, 'As': 1.85, 'Se': 1.90, 'Br': 1.85,
         'Kr': 2.02, 'Te': 2.06, 'I': 1.98, 'Xe': 2.16, 'Li': 1.82, 'Na': 2.27, 'Mg': 1.73, 'K': 2.75,
         'Ni': 1.63, 'Cu': 1.40, 'Zn': 1.39, 'Ga': 1.87, 'Pd': 1.63, 'Ag': 1.72, 'Cd': 1.58, 'In': 1.93,
         'Sn': 2.17, 'Pt': 1.75, 'Au': 1.66, 'Hg': 1.55, 'Tl': 1.96, 'Pb': 2.02, 'U': 1.86}


def radius(el):
    return BONDI.get(el, VDW_RADII.get(el, 2.0))


_GRID_CACHE = {}


def _grid(R, mesh):
    key = (round(R, 4), round(mesh, 4))
    g = _GRID_CACHE.get(key)
    if g is None:
        n = int(np.ceil(R / mesh))
        ax = np.arange(-n, n + 1) * mesh
        X, Y, Z = np.meshgrid(ax, ax, ax, indexing='ij')
        P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
        g = P[np.einsum('ij,ij->i', P, P) <= R * R]
        _GRID_CACHE.clear()
        _GRID_CACHE[key] = g
    return g


def buried_volume(metal_xyz, xyz, elements, R=3.5, scale=1.17, mesh=0.10, z_dir=None, x_dir=None):
    """xyz: (n, 3) Cartesian coordinates of the ligand atoms (metal and unwanted atoms already left out).
    Returns dict(percent, free, quadrants (or None), n_atoms, n_points)."""
    P = _grid(R, mesh)
    xyz = np.asarray(xyz, float).reshape(-1, 3) - np.asarray(metal_xyz, float)
    r = np.array([radius(e) * scale for e in elements])
    buried = np.zeros(len(P), bool)
    used = 0
    for c, rr in zip(xyz, r):
        if np.linalg.norm(c) > R + rr:
            continue                                     # entirely outside the sphere
        used += 1
        sel = np.all(np.abs(P - c) <= rr, axis=1)        # bounding box first, then the exact test
        idx = np.flatnonzero(sel)
        d = P[idx] - c
        buried[idx[np.einsum('ij,ij->i', d, d) <= rr * rr]] = True
    pct = 100.0 * buried.mean() if len(P) else 0.0
    quads = None
    if z_dir is not None and x_dir is not None:
        z = np.asarray(z_dir, float)
        z /= np.linalg.norm(z)
        x = np.asarray(x_dir, float) - np.dot(x_dir, z) * z
        if np.linalg.norm(x) > 1e-6:
            x /= np.linalg.norm(x)
            y = np.cross(z, x)
            px, py = P @ x, P @ y
            quads = {}
            for name, m in (('NE', (px >= 0) & (py >= 0)), ('NW', (px < 0) & (py >= 0)),
                            ('SW', (px < 0) & (py < 0)), ('SE', (px >= 0) & (py < 0))):
                quads[name] = 100.0 * buried[m].mean() if m.any() else 0.0
    return dict(percent=pct, free=100.0 - pct, quadrants=quads, n_atoms=used, n_points=len(P),
                R=R, scale=scale, mesh=mesh)
