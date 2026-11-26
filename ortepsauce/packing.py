"""Mercury-style growing of the displayed model: bonded neighbours across symmetry (polymer
expansion), whole molecules, and short intermolecular contacts.

New atoms are described as sites (asym index, operator index, (na, nb, nc)): fractional position
F[asym] @ R.T + t + (na, nb, nc). They are stored in RenderSettings.extra_sites and added by
model.build_model, so they survive rebuilding and undo."""
import numpy as np

from .elements import covalent_radius, vdw_radius
from .model import _bond_cutoff_matrix, _parts_compatible

_NEIGH = np.array([[a, b, c] for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)], float)


def _asym(struct):
    F = np.array([a.frac for a in struct.atoms], float)
    el = [a.element for a in struct.atoms]
    part = np.array([a.part for a in struct.atoms], int)
    return F, el, part


def _model_keys(model, struct):
    """{(asym index, rounded frac)} of the atoms already shown."""
    Ainv = np.linalg.inv(struct.cell.A)
    fr = model.cart @ Ainv.T
    out = set()
    for k in range(model.n):
        j = int(model.asym_index[k])
        if j >= 0:
            out.add((j, tuple(np.round(fr[k], 3))))
    return out, fr


def _images_near(struct, frac, max_d, el_src=None, part_src=0, kind='bond', tol=0.45, contact_tol=0.0):
    """Symmetry images of every asymmetric-unit atom near the fractional point `frac`.
    Returns [(j, g, shift(3,), f(3,), dist)]."""
    F, el, part = _asym(struct)
    A = struct.cell.A
    out = []
    for g, (Rg, tg) in enumerate(struct.symops):
        img = F @ Rg.T + tg                                    # (N, 3)
        base = np.round(img - frac)                            # nearest copy
        for nb in _NEIGH:
            f = img - base + nb                                 # (N, 3)
            d = np.linalg.norm((f - frac) @ A.T, axis=1)
            for j in np.flatnonzero((d < max_d) & (d > 0.1)):
                if kind == 'bond':
                    cut = _bond_cutoff_matrix([el_src], [el[j]], tol)[0, 0]
                    if d[j] >= cut or not _parts_compatible(np.array([part_src]), np.array([part[j]]))[0, 0]:
                        continue
                shift = f[j] - (F[j] @ Rg.T + tg)
                out.append((int(j), int(g), np.round(shift).astype(int), f[j].copy(), float(d[j])))
    return out


def _site(j, g, shift):
    return (int(j), int(g), tuple(int(x) for x in shift))


def bonded_neighbours(struct, model, idx, tol=0.45):
    """Sites bonded to the model atoms idx that are not shown yet (one polymer step)."""
    have, fr = _model_keys(model, struct)
    out, seen = [], set()
    for i in idx:
        j0 = int(model.asym_index[i])
        if j0 < 0:
            continue
        for j, g, sh, f, d in _images_near(struct, fr[i], 3.6, model.elements[i], int(model.part[i]),
                                           'bond', tol):
            key = (j, tuple(np.round(f, 3)))
            if key in have or key in seen:
                continue
            seen.add(key)
            out.append(_site(j, g, sh))
    return out


def complete_from(struct, seeds=(), model=None, start=(), tol=0.45, max_new=3000):
    """Grow whole molecules from seed sites and / or the model atoms `start`.
    Returns (new sites not shown yet, truncated). Breadth first, so a capped polymer grows evenly
    around the seeds."""
    F, el, part = _asym(struct)
    ops = struct.symops
    have, fr = (set(), None)
    if model is not None:
        have, fr = _model_keys(model, struct)
    frontier, out, seen = [], [], set()
    for (j, g, sh) in seeds:
        f = F[j] @ ops[g][0].T + ops[g][1] + np.array(sh, float)
        key = (j, tuple(np.round(f, 3)))
        if key not in seen:
            seen.add(key)
            if key not in have:
                out.append(_site(j, g, sh))
            frontier.append((j, f))
    for i in start:
        j = int(model.asym_index[i])
        if j >= 0:
            key = (j, tuple(np.round(fr[i], 3)))
            seen.add(key)
            frontier.append((j, fr[i]))
    truncated = False
    while frontier and not truncated:
        nxt = []
        for j0, f0 in frontier:
            for j, g, sh, f, d in _images_near(struct, f0, 3.6, el[j0], int(part[j0]), 'bond', tol):
                key = (j, tuple(np.round(f, 3)))
                if key in seen:
                    continue
                seen.add(key)
                if key not in have:
                    out.append(_site(j, g, sh))
                nxt.append((j, f))
                if len(out) >= max_new:
                    truncated = True
                    break
            if truncated:
                break
        frontier = nxt
    return out, truncated


def site_frac(struct, site):
    F, _, _ = _asym(struct)
    j, g, sh = site
    Rg, tg = struct.symops[g]
    return F[j] @ Rg.T + tg + np.array(sh, float)


def model_index_by_site(struct, model):
    """{(asym index, rounded frac): model index}"""
    Ainv = np.linalg.inv(struct.cell.A)
    fr = model.cart @ Ainv.T
    return {(int(model.asym_index[k]), tuple(np.round(fr[k], 3))): k
            for k in range(model.n) if int(model.asym_index[k]) >= 0}


def short_contacts(struct, model, idx, contact_tol=0.0, include_h=False, fragment_of=None):
    """Intermolecular contacts of the model atoms idx shorter than the sum of the van der Waals radii
    + contact_tol. Returns [(i, site, j_model_or_None, distance)]: j_model is the atom index when the
    partner is already shown, else None (site is then the partner's site)."""
    have, fr = _model_keys(model, struct)
    key_to_model = {}
    for k in range(model.n):
        j = int(model.asym_index[k])
        if j >= 0:
            key_to_model[(j, tuple(np.round(fr[k], 3)))] = k
    F, el, part = _asym(struct)
    out, seen = [], set()
    for i in idx:
        if int(model.asym_index[i]) < 0 or (model.elements[i] in ('H', 'D') and not include_h):
            continue
        ri = vdw_radius(model.elements[i])
        same = set(fragment_of(i)) if fragment_of else set()
        for j, g, sh, f, d in _images_near(struct, fr[i], ri + 2.4 + contact_tol, kind='contact'):
            if el[j] in ('H', 'D') and not include_h:
                continue
            if d > ri + vdw_radius(el[j]) + contact_tol:
                continue
            cut = covalent_radius(model.elements[i]) + covalent_radius(el[j]) + 0.45
            if d < cut:
                continue                                   # bonded, not a contact
            key = (j, tuple(np.round(f, 3)))
            jm = key_to_model.get(key)
            if jm is not None and jm in same:
                continue                                   # same molecule
            pair = (i, key)
            if pair in seen or (jm is not None and (jm, None) in seen):
                continue
            seen.add(pair)
            out.append((i, _site(j, g, sh), jm, d))
    out.sort(key=lambda x: x[3])
    return out
