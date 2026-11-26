"""Supporting-information figure caption: selected bond lengths and angles with s.u. values
taken from the CIF geometry tables (_geom_bond / _geom_angle) when available."""
import math
import re

import numpy as np

EN = '–'   # en dash


def _num(text):
    try:
        return float(re.sub(r'\(.*\)$', '', text.strip()))
    except ValueError:
        return None


def _cif_match(entries, value, tol):
    best, bd = None, tol
    for txt in entries:
        v = _num(txt)
        if v is None:
            continue
        d = abs(v - value)
        if d <= bd:
            best, bd = txt, d
    if best is None:
        return None
    if '(' not in best and best.endswith('.0'):
        best = best[:-2]                       # e.g. symmetry-fixed 180.0 -> 180
    return best


def _is_metal(el):
    from .styles import NONMETALS
    return el not in NONMETALS and el not in ('Cg', 'Q')


def selected_geometry(model, struct, selection, suffix='*', merge_equivalent=True):
    """Bonds and angles among the selected atoms (in selection order).
    Returns (bonds, angles, used_cif) with items (names..., value_text, generated_flags)."""
    sel = list(selection)
    pos = {i: k for k, i in enumerate(sel)}
    selset = set(sel)
    nb = {i: set() for i in sel}
    for a, b in model.bonds:
        a, b = int(a), int(b)
        if a in selset and b in selset:
            nb[a].add(b)
            nb[b].add(a)

    def name(i):
        return model.labels[i] + (suffix if model.generated[i] else '')

    cif_b = {}
    for l1, l2, v in getattr(struct, 'geom_bonds', []) or []:
        cif_b.setdefault(frozenset((l1, l2)), []).append(v)
    cif_a = {}
    for l1, l2, l3, v in getattr(struct, 'geom_angles', []) or []:
        cif_a.setdefault((l2, frozenset((l1, l3))), []).append(v)
    used_cif = False

    bonds, seen = [], set()
    for a in sel:
        for b in sorted(nb[a], key=lambda i: pos[i]):
            if pos[b] <= pos[a]:
                continue
            d = float(np.linalg.norm(model.cart[a] - model.cart[b]))
            txt = _cif_match(cif_b.get(frozenset((model.labels[a], model.labels[b])), []), d, 0.0025)
            used_cif |= txt is not None
            txt = txt or f'{d:.3f}'
            key = (frozenset((model.labels[a], model.labels[b])), txt)
            if merge_equivalent and key in seen:
                continue
            seen.add(key)
            # central metal first, then the ligand atom (Fe1–O1, not O1–Fe1)
            first, second = a, b
            if _is_metal(model.elements[b]) and not _is_metal(model.elements[a]):
                first, second = b, a
            bonds.append((name(first), name(second), txt))

    angles, seen = [], set()
    for c in sel:
        ends = sorted(nb[c], key=lambda i: pos[i])
        for x in range(len(ends)):
            for y in range(x + 1, len(ends)):
                a, b = ends[x], ends[y]
                v1, v2 = model.cart[a] - model.cart[c], model.cart[b] - model.cart[c]
                cosv = float(v1 @ v2 / (np.linalg.norm(v1) * np.linalg.norm(v2)))
                ang = math.degrees(math.acos(max(-1.0, min(1.0, cosv))))
                txt = _cif_match(cif_a.get((model.labels[c], frozenset((model.labels[a], model.labels[b]))), []),
                                 ang, 0.06)
                used_cif |= txt is not None
                if txt is None:
                    txt = f'{ang:.1f}'
                key = (model.labels[c], frozenset((model.labels[a], model.labels[b])), txt)
                if merge_equivalent and key in seen:
                    continue
                seen.add(key)
                angles.append((name(a), name(c), name(b), txt))
    return bonds, angles, used_cif


_DIS = re.compile(r"^([A-Za-z]{1,2}\d+)([A-Za-z]|'+)$")


def disordered_labels(struct):
    """Labels that look disordered: partial occupancy, a non-zero PART, or label families such as
    C23A / C23B (or C23 / C23') that share a base name."""
    out = set()
    groups = {}
    for a in struct.atoms:
        if (a.occupancy is not None and abs(a.occupancy - 1.0) > 0.01) or a.part:
            out.add(a.label)
        m = _DIS.match(a.label) if a.element not in ('H', 'D') else None   # H24A/B/C is normal naming
        if m:
            groups.setdefault(m.group(1).upper(), []).append(a.label)
    labels = {a.label.upper() for a in struct.atoms}
    for base, labs in groups.items():
        if len(labs) > 1 or base in labels:
            out.update(labs)
            out.update(a.label for a in struct.atoms if a.label.upper() == base and a.element not in ('H', 'D'))
    return out


def guess_disorder_suffixes(struct):
    """Guess the label suffixes of the two disorder parts: ('', '*') for C21 / C21*,
    ('A', 'B') for C55A / C55B (the part with the higher mean occupancy is the major one)."""
    labs = [a.label for a in struct.atoms]
    lset = set(labs)
    heavy = [a for a in struct.atoms if a.element not in ('H', 'D')]
    for tail in ('*', "'", '"', '_2', '_b'):
        if sum(1 for a in heavy if a.label.endswith(tail) and a.label[:-len(tail)] in lset) >= 1:
            return '', tail
    occ = {}
    for a in heavy:
        m = _DIS.match(a.label)
        if m and m.group(2).isalpha():
            occ.setdefault(m.group(2).upper(), []).append(a.occupancy if a.occupancy is not None else 1.0)
    pairs = [(x, y) for x, y in (('A', 'B'), ('B', 'C'), ('A', 'C')) if x in occ and y in occ]
    if pairs:
        x, y = pairs[0]
        if sum(occ[y]) / len(occ[y]) > sum(occ[x]) / len(occ[x]) + 1e-3:
            x, y = y, x
        return x, y
    return '', ''


def disorder_parts(struct, major, minor):
    """Labels of the major and minor disorder parts, given the suffixes the user types
    (major may be empty: C21 / C21*). H atoms follow the PART number of their part."""
    major, minor = (major or '').strip(), (minor or '').strip()
    atoms = {a.label: a for a in struct.atoms}
    flagged = disordered_labels(struct)
    maj, mnr = set(), set()
    if not minor and not major:
        # no naming scheme: fall back on the PART numbers (PART 1 = major, PART 2, 3 … = minor)
        pos = sorted({a.part for a in struct.atoms if a.part and a.part > 0})
        if len(pos) >= 2:
            maj = {a.label for a in struct.atoms if a.part == pos[0]}
            mnr = {a.label for a in struct.atoms if a.part in pos[1:]}
        return maj, mnr

    def base_of(lab, suf):
        if suf:
            return lab[:-len(suf)] if lab.endswith(suf) and len(lab) > len(suf) else None
        return lab
    for lab, a in atoms.items():
        if a.element in ('H', 'D'):
            continue
        b = base_of(lab, minor) if minor else None
        if b is not None and (b + major in atoms or lab in flagged):
            mnr.add(lab)
            if b + major in atoms:
                maj.add(b + major)
            continue
        b = base_of(lab, major) if major else None
        if b is not None and (minor and b + minor in atoms or lab in flagged and major):
            maj.add(lab)
    # hydrogen atoms: by PART number, or by the same suffix rule
    def parts(labs):
        return {atoms[l].part for l in labs if atoms[l].part}
    pmaj, pmnr = parts(maj), parts(mnr)
    for lab, a in atoms.items():
        if a.element not in ('H', 'D'):
            continue
        if a.part and a.part in pmnr and a.part not in pmaj:
            mnr.add(lab)
        elif a.part and a.part in pmaj and a.part not in pmnr:
            maj.add(lab)
        elif minor and minor not in 'ABCD' and lab.endswith(minor):
            mnr.add(lab)
    return maj, mnr


def caption(figure, compound, probability, show_h, model, struct, selection, suffix='*',
            merge_equivalent=True, generated_visible=False, excluded=(), mention_solvent=True,
            hidden_keys=(), shown_h=()):
    bonds, angles, used_cif = selected_geometry(model, struct, selection, suffix, merge_equivalent)
    sel_gen = any(model.generated[i] for i in selection)
    parts = [f'Figure {figure}. Solid-state molecular structure of {compound} at '
             f'{probability:g}% ellipsoid probability.']
    if sel_gen or generated_visible:
        parts.append(f'Atoms with {suffix} were generated by symmetry.')
    dis_excluded = bool(set(excluded) & disordered_labels(struct)) if excluded else False
    solv = identify_solvents(model) if mention_solvent else []
    excl = set(excluded)
    hk = set(hidden_keys)
    hidden_solv = [x for x in solv if all(model.labels[i] in excl or (model.elements[i] in ('H', 'D') and not show_h)
                                          or f'{model.labels[i]}|{model.symop[i]}' in hk for i in x[2])]
    shown_solv = [x for x in solv if x not in hidden_solv]
    omitted = []
    if not show_h:
        omitted.append('hydrogen atoms' + (f' (except {", ".join(shown_h)})' if shown_h else ''))
    if dis_excluded:
        omitted.append('disordered parts')
    if hidden_solv:
        omitted.append('co-crystallized solvent (' + solvent_phrase(hidden_solv) + ')')
    if omitted:
        txt = omitted[0] if len(omitted) == 1 else ', '.join(omitted[:-1]) + ' and ' + omitted[-1]
        verb = 'are' if (len(omitted) > 1 or not omitted[0].startswith('co-')) else 'is'
        parts.append(txt[0].upper() + txt[1:] + f' {verb} omitted for clarity.')
    if shown_solv:
        p = solvent_phrase(shown_solv)
        parts.append(f'Co-crystallized solvent ({p}) is shown.')
    items = [f'{a}{EN}{b} = {v}' for a, b, v in bonds] + [f'{a}{EN}{b}{EN}{c} = {v}' for a, b, c, v in angles]
    if items:
        parts.append('Selected bond lengths (Å) and angles (deg): ' + ', '.join(items) + '.')
    return ' '.join(parts), used_cif, len(bonds), len(angles)


# --------------------------------------------------------------------------- solvents
# Hill-order formula (with H) -> name.  Heavy-atom-only keys are generated automatically so that
# solvents refined without hydrogen atoms (e.g. water) are recognised too.
SOLVENTS = {
    'CH2Cl2': 'dichloromethane', 'CHCl3': 'chloroform', 'CCl4': 'carbon tetrachloride',
    'C4H8O': 'tetrahydrofuran', 'C4H10O': 'diethyl ether', 'C7H8': 'toluene', 'C6H6': 'benzene',
    'C6H14': 'hexane', 'C5H12': 'pentane', 'C7H16': 'heptane', 'C6H12': 'cyclohexane',
    'C2H3N': 'acetonitrile', 'C2H6OS': 'dimethyl sulfoxide', 'C3H7NO': 'N,N-dimethylformamide',
    'CH4O': 'methanol', 'C2H6O': 'ethanol', 'H2O': 'water', 'C3H6O': 'acetone',
    'C4H10O2': '1,2-dimethoxyethane', 'C4H8O2': '1,4-dioxane', 'C5H5N': 'pyridine',
    'C6H5F': 'fluorobenzene', 'C6H4F2': '1,2-difluorobenzene', 'C6H5Cl': 'chlorobenzene',
    'C6H4Cl2': '1,2-dichlorobenzene', 'C2H4Cl2': '1,2-dichloroethane', 'C8H10': 'xylene',
    'C5H10': 'cyclopentane', 'C6H18OSi2': 'hexamethyldisiloxane',
    'C3H8O': '2-propanol', 'CS2': 'carbon disulfide', 'C7H5F3': 'trifluorotoluene',
}

_NUMBER_WORDS = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six'}


def _hill(counts):
    keys = sorted(counts)
    out = ''
    if 'C' in counts:
        order = ['C'] + (['H'] if 'H' in counts else []) + sorted(k for k in keys if k not in ('C', 'H'))
    else:
        order = keys
    for k in order:
        out += k + (str(counts[k]) if counts[k] > 1 else '')
    return out


def _formula_counts(f):
    out = {}
    for el, n in re.findall(r'([A-Z][a-z]?)(\d*)', f):
        out[el] = out.get(el, 0) + (int(n) if n else 1)
    return out


_HEAVY = {}
for _f, _n in list(SOLVENTS.items()):
    c = _formula_counts(_f)
    c.pop('H', None)
    if c:
        _HEAVY.setdefault(_hill(c), _n)


def fragments(model):
    """Connected fragments (lists of atom indices) of the displayed model."""
    parent = list(range(model.n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    styles = getattr(model, 'bond_style', {}) or {}
    for a, b in model.bonds:
        a, b = int(a), int(b)
        if styles.get((min(a, b), max(a, b)), {}).get('contact'):
            continue                                  # a drawn contact does not join two molecules
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    groups = {}
    for i in range(model.n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def identify_solvents(model):
    """[(name, formula, [atom indices])] for small fragments that match a known solvent."""
    frs = fragments(model)
    if len(frs) < 2:
        return []
    biggest = max(frs, key=len)
    out = []
    for fr in frs:
        if fr is biggest:
            continue                                    # the main molecule
        heavy = [i for i in fr if model.elements[i] not in ('H', 'D')]
        if not heavy or len(heavy) > 12:
            continue
        counts = {}
        for i in fr:
            e = 'H' if model.elements[i] == 'D' else model.elements[i]
            counts[e] = counts.get(e, 0) + 1
        f_all = _hill(counts)
        name = SOLVENTS.get(f_all)
        if name is None:
            hc = dict(counts)
            hc.pop('H', None)
            name = _HEAVY.get(_hill(hc))
            if name is None:
                continue
            f_all = _hill(hc)
        out.append((name, f_all, fr))
    return out


def solvent_phrase(solv):
    """[(name, ...)] -> 'two molecules of dichloromethane and one molecule of toluene'."""
    counts = {}
    for name, *_ in solv:
        counts[name] = counts.get(name, 0) + 1
    parts = []
    for name, n in counts.items():
        parts.append(f'{_NUMBER_WORDS.get(n, str(n))} molecule{"s" if n > 1 else ""} of {name}')
    if len(parts) > 1:
        return ', '.join(parts[:-1]) + ' and ' + parts[-1]
    return parts[0] if parts else ''
