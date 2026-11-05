"""Display model: symmetry completion of fragments, Cartesian ADPs and bond detection."""
import numpy as np

from .elements import covalent_radius


class Model:
    """Flat, Cartesian representation of what is shown on screen."""

    def __init__(self):
        self.labels = []
        self.elements = []
        self.cart = np.zeros((0, 3))
        self.ucart = np.zeros((0, 3, 3))
        self.aniso = np.zeros(0, bool)
        self.part = np.zeros(0, int)
        self.occ = np.zeros(0)
        self.generated = np.zeros(0, bool)
        self.asym_index = np.zeros(0, int)
        self.bonds = np.zeros((0, 2), int)
        self.q_labels = []
        self.q_cart = np.zeros((0, 3))
        self.q_height = np.zeros(0)
        self.symop = []
        self.notes = []

    @property
    def n(self):
        return len(self.labels)

    def is_h(self):
        return np.array([e in ('H', 'D') for e in self.elements], bool)


def _bond_cutoff_matrix(el_a, el_b, tol):
    ra = np.array([covalent_radius(e) for e in el_a])
    rb = np.array([covalent_radius(e) for e in el_b])
    cut = ra[:, None] + rb[None, :] + tol
    ha = np.array([e in ('H', 'D') for e in el_a])
    hb = np.array([e in ('H', 'D') for e in el_b])
    cut[ha[:, None] & hb[None, :]] = 0.0          # never bond H...H
    return cut


def _parts_compatible(pa, pb):
    pa = pa[:, None]
    pb = pb[None, :]
    return (pa == 0) | (pb == 0) | (pa == pb)


def build_model(struct, complete=True, tol=0.45, max_atoms=4000, pack=False):
    """pack: fill the unit cell - every molecule whose centre lies inside the cell (0 <= x, y, z < 1),
    completed by symmetry when complete=True."""
    cell = struct.cell
    A = cell.A
    atoms = struct.atoms
    N = len(atoms)
    model = Model()
    if N == 0:
        model.notes.append('No atoms in structure.')
        return model

    F = np.array([a.frac for a in atoms], float)
    el = [a.element for a in atoms]
    part = np.array([a.part for a in atoms], int)
    ustar = np.zeros((N, 3, 3))
    is_aniso = np.zeros(N, bool)
    for i, a in enumerate(atoms):
        if a.uani is not None:
            ustar[i] = cell.ustar_from_uij(a.uani)
            is_aniso[i] = True

    # polymeric structures would grow forever; allow up to 8 copies of the asymmetric unit
    max_atoms = min(max_atoms, max(8 * N, 300))
    if pack:
        max_atoms = max(max_atoms, min(max(16 * N * max(len(struct.symops), 1), 2000), 12000))
    cut_aa = _bond_cutoff_matrix(el, el, tol)
    compat_aa = _parts_compatible(part, part)

    # Each displayed atom: (asym index, op index, fractional coords)
    sites_idx = list(range(N))
    sites_op = [0] * N
    sites_frac = [F[i].copy() for i in range(N)]
    sites_gen = [False] * N
    keys = {(i, tuple(np.round(F[i], 3))) for i in range(N)}

    ops = struct.symops
    truncated = False
    if pack and len(ops) > 0:
        # seeds: every symmetry image of every atom, moved into the cell
        sites_idx, sites_op, sites_frac, sites_gen, keys = [], [], [], [], set()
        for g, (Rg, tg) in enumerate(ops):
            ident = np.allclose(Rg, np.eye(3)) and np.allclose(tg - np.round(tg), 0)
            img = F @ Rg.T + tg
            wrapped = img - np.floor(img + 1e-5)
            for j in range(N):
                key = (j, tuple(np.round(wrapped[j], 3)))
                if key in keys:
                    continue
                keys.add(key)
                sites_idx.append(j)
                sites_op.append(g)
                sites_frac.append(wrapped[j])
                sites_gen.append(not (ident and np.allclose(wrapped[j], F[j], atol=1e-4)))
    if complete and len(ops) > 0:
        frontier = list(range(len(sites_idx)))
        images = [F @ R.T + t for R, t in ops]
        iteration = 0
        while frontier and not truncated:
            iteration += 1
            S = np.array([sites_frac[k] for k in frontier])
            s_idx = np.array([sites_idx[k] for k in frontier])
            new = []
            for g, Fg in enumerate(images):
                diff = Fg[None, :, :] - S[:, None, :]            # (M, N, 3)
                shift = np.round(diff)
                d = (diff - shift) @ A.T
                dist = np.linalg.norm(d, axis=2)
                ok = (dist < cut_aa[s_idx]) & (dist > 0.1) & compat_aa[s_idx]
                for m, j in zip(*np.nonzero(ok)):
                    f = Fg[j] - shift[m, j]
                    key = (int(j), tuple(np.round(f, 3)))
                    if key in keys:
                        continue
                    keys.add(key)
                    sites_idx.append(int(j))
                    sites_op.append(g)
                    sites_frac.append(f)
                    sites_gen.append(True)
                    new.append(len(sites_idx) - 1)
                    if len(sites_idx) >= max_atoms:
                        truncated = True
                        break
                if truncated:
                    break
            frontier = new
            if iteration > 60:
                truncated = True
        if truncated:
            model.notes.append(f'Growth stopped at {len(sites_idx)} atoms (polymeric structure?).')
    if pack and len(ops) > 0 and complete and len(sites_idx):
        # keep each molecule once: the copy whose centre lies inside the cell
        fr_all = np.array(sites_frac)
        cart_all = fr_all @ A.T
        b = find_bonds(cart_all, [el[i] for i in sites_idx], part[np.array(sites_idx)], tol)
        parent = list(range(len(sites_idx)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for a_, b_ in b:
            ra, rb = find(int(a_)), find(int(b_))
            if ra != rb:
                parent[ra] = rb
        groups = {}
        for k in range(len(sites_idx)):
            groups.setdefault(find(k), []).append(k)
        keep = []
        for members in groups.values():
            c = fr_all[members].mean(axis=0)
            if np.all(c >= -1e-4) and np.all(c < 1 - 1e-4):
                keep += members
        if keep:
            keep.sort()
            sites_idx = [sites_idx[k] for k in keep]
            sites_op = [sites_op[k] for k in keep]
            sites_frac = [sites_frac[k] for k in keep]
            sites_gen = [sites_gen[k] for k in keep]

    if pack and len(sites_idx) > 1:
        # remove copies of the same atom that coincide (special positions, rounding at 3 decimals)
        fr_all = np.array(sites_frac)
        cart_all = fr_all @ A.T
        idx_arr = np.array(sites_idx)
        drop = set()
        for j in np.unique(idx_arr):
            ks = np.flatnonzero(idx_arr == j)
            if len(ks) < 2:
                continue
            P = cart_all[ks]
            d = np.linalg.norm(P[:, None] - P[None], axis=2)
            for a_ in range(len(ks)):
                if ks[a_] in drop:
                    continue
                for b_ in np.flatnonzero(d[a_, a_ + 1:] < 0.05) + a_ + 1:
                    drop.add(ks[b_])
        if drop:
            keep = [k for k in range(len(sites_idx)) if k not in drop]
            sites_idx = [sites_idx[k] for k in keep]
            sites_op = [sites_op[k] for k in keep]
            sites_frac = [sites_frac[k] for k in keep]
            sites_gen = [sites_gen[k] for k in keep]

    n = len(sites_idx)
    fr = np.array(sites_frac)
    model.cart = fr @ A.T
    model.asym_index = np.array(sites_idx, int)
    model.generated = np.array(sites_gen, bool)
    model.elements = [el[i] for i in sites_idx]
    model.labels = [atoms[i].label for i in sites_idx]
    model.symop = [struct_op_text(ops[g][0], ops[g][1], sites_frac[k] - F[i] @ ops[g][0].T - ops[g][1])
                   if sites_gen[k] else '' for k, (i, g) in enumerate(zip(sites_idx, sites_op))]
    model.part = part[model.asym_index]
    model.occ = np.array([atoms[i].occupancy for i in sites_idx])
    model.aniso = is_aniso[model.asym_index].copy()
    model.ucart = np.zeros((n, 3, 3))
    npd = []
    for k, (i, g) in enumerate(zip(sites_idx, sites_op)):
        if is_aniso[i]:
            R = ops[g][0] if (ops and sites_gen[k]) else np.eye(3)    # asym. unit: as given
            us = R @ ustar[i] @ R.T
            uc = cell.ucart_from_ustar(us)
            if np.linalg.eigvalsh(uc).min() <= 1e-6:
                model.aniso[k] = False
                uc = np.eye(3) * max(abs(np.trace(uc) / 3.0), 0.005)
                if not sites_gen[k]:
                    npd.append(atoms[i].label)
            model.ucart[k] = uc
        else:
            model.ucart[k] = np.eye(3) * max(atoms[i].uiso or 0.05, 1e-4)
    if npd:
        model.notes.append('Non-positive-definite ADPs drawn as spheres: ' + ', '.join(npd))

    model.bonds = find_bonds(model.cart, model.elements, model.part, tol)
    if len(model.bonds) and (model.part < 0).any():
        # SHELX negative PART: an atom is never bonded to symmetry copies of the same disorder part
        a, b = model.bonds[:, 0], model.bonds[:, 1]
        bad = (model.part[a] < 0) & (model.part[a] == model.part[b]) & \
              (model.generated[a] != model.generated[b])
        model.bonds = model.bonds[~bad]

    # Q-peaks
    if struct.qpeaks:
        model.q_labels = [q.label for q in struct.qpeaks]
        model.q_cart = np.array([q.frac for q in struct.qpeaks]) @ A.T
        model.q_height = np.array([q.peak_height for q in struct.qpeaks])
    return model


def struct_op_text(R, t, shift):
    """Human-readable operator, e.g. '-x+1, -y, -z+1'."""
    from fractions import Fraction
    out = []
    tt = t + np.round(shift)
    for row in range(3):
        s = ''
        for c, v in zip('xyz', R[row]):
            if abs(v) < 1e-6:
                continue
            s += ('-' if v < 0 else '+') + ('' if abs(abs(v) - 1) < 1e-6 else f'{abs(v):g}') + c
        if abs(tt[row]) > 1e-6:
            fr = Fraction(tt[row]).limit_denominator(12)
            s += ('-' if fr < 0 else '+') + str(abs(fr))
        out.append(s.lstrip('+') or '0')
    return ', '.join(out)


def find_bonds(cart, elements, part, tol, chunk=1500):
    n = len(cart)
    if n < 2:
        return np.zeros((0, 2), int)
    pairs = []
    for s in range(0, n, chunk):
        e = min(n, s + chunk)
        d = np.linalg.norm(cart[s:e, None, :] - cart[None, :, :], axis=2)
        cut = _bond_cutoff_matrix(elements[s:e], elements, tol)
        ok = (d < cut) & (d > 0.1) & _parts_compatible(part[s:e], part)
        ii, jj = np.nonzero(ok)
        ii = ii + s
        keep = ii < jj
        pairs.append(np.stack([ii[keep], jj[keep]], axis=1))
    return np.concatenate(pairs) if pairs else np.zeros((0, 2), int)
