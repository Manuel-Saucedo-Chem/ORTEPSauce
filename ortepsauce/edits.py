"""User edits on top of the automatically built model: centroids (dummy atoms Cg1, Cg2 ...),
deleted bonds and user-drawn / restyled bonds (solid, dashed, dotted).

Atoms are identified by 'label|symmetry operator' so the edits survive rebuilding the model
(bond tolerance, symmetry completion, ...)."""
import numpy as np

BOND_STYLES = ['Solid', 'Dashed', 'Dotted']
BOND_WIDTHS = {'Normal': 1.0, 'Thin': 0.55, 'Hairline': 0.3}
CENTROID = 'Cg'


def atom_key(model, i):
    return f'{model.labels[i]}|{model.symop[i]}'


def bond_key(model, i, j):
    a, b = atom_key(model, i), atom_key(model, j)
    return (a, b) if a <= b else (b, a)


def is_centroid(model, i):
    return model.elements[i] == CENTROID


def _append_atom(model, label, cart):
    model.labels.append(label)
    model.elements.append(CENTROID)
    model.symop.append('')
    model.cart = np.vstack([model.cart, cart[None, :]])
    model.ucart = np.concatenate([model.ucart, (np.eye(3) * 1e-4)[None]])
    model.aniso = np.append(model.aniso, False)
    model.part = np.append(model.part, 0)
    model.occ = np.append(model.occ, 1.0)
    model.generated = np.append(model.generated, False)
    model.asym_index = np.append(model.asym_index, -1)


def apply_edits(model, s):
    """Add centroids, remove deleted bonds, add / restyle user bonds. Sets model.bond_style:
    {(i, j) with i < j: {'style': 'Dashed', 'width': 'Thin'}}. Returns notes about edits that
    could not be applied (atoms not present in this model)."""
    notes = []
    model.bond_style = {}
    keys = {atom_key(model, i): i for i in range(model.n)}
    for cg in getattr(s, 'centroids', []):
        idx = [keys.get(k) for k in cg['members']]
        if any(i is None for i in idx) or len(idx) < 2:
            notes.append(f"{cg['name']}: member atoms not in the current model")
            continue
        _append_atom(model, cg['name'], model.cart[idx].mean(axis=0))
        keys[f"{cg['name']}|"] = model.n - 1
    deleted = getattr(s, 'deleted_bonds', set())
    bonds = [tuple(sorted((int(a), int(b)))) for a, b in model.bonds]
    if deleted:
        bonds = [b for b in bonds if bond_key(model, *b) not in deleted]
    present = set(bonds)
    for (ka, kb), st in getattr(s, 'custom_bonds', {}).items():
        a, b = keys.get(ka), keys.get(kb)
        if a is None or b is None:
            continue
        pair = (min(a, b), max(a, b))
        if pair not in present:
            bonds.append(pair)
            present.add(pair)
        model.bond_style[pair] = dict(st)
    model.bonds = np.array(bonds, int).reshape(-1, 2)
    return notes


def dash_segments(p0, p1, style, r):
    """Pieces of a dashed / dotted bond: list of ('cyl', a, b) or ('dot', c)."""
    d = p1 - p0
    L = float(np.linalg.norm(d))
    if L < 1e-6:
        return []
    u = d / L
    if style == 'Dashed':
        dash, gap = max(0.14, 3.5 * r), max(0.09, 2.2 * r)
        n = max(1, int((L + gap) // (dash + gap)))
        dash = (L - (n - 1) * gap) / n               # stretch so both ends are dashes
        out, t = [], 0.0
        for _ in range(n):
            out.append(('cyl', p0 + u * t, p0 + u * (t + dash)))
            t += dash + gap
        return out
    if style == 'Dotted':
        step = max(0.10, 3.2 * r)
        n = max(2, int(round(L / step)) + 1)
        return [('dot', p0 + u * (L * k / (n - 1))) for k in range(n)]
    return [('cyl', p0, p1)]
