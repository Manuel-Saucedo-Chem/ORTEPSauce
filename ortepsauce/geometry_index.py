"""Coordination-geometry indices of a metal centre.

tau4  (Houser 2007):        (360 - (a + b)) / 141                     0 square planar ... 1 tetrahedral
tau4' (Okuniewski 2015):    (b - a)/(360 - t) + (180 - b)/(180 - t),  t = 109.5 (tetrahedral angle)
tau5  (Addison 1984):       (b - a) / 60                              0 square pyramidal ... 1 trig. bipyramidal
a, b: the two largest L-M-L angles (b >= a)."""
import itertools
import math

import numpy as np

from .styles import NONMETALS

THETA = math.degrees(math.acos(-1.0 / 3.0))          # 109.47 deg
NOT_CENTRE = NONMETALS | {'Cg', 'He', 'Ne', 'Ar', 'Kr', 'Xe', 'Rn'}

# reference values for the ideal shapes (tau4, tau4')
IDEAL4 = [('square planar', 0.00, 0.00), ('seesaw', 0.43, 0.24), ('trigonal pyramidal', 0.85, 0.85),
          ('tetrahedral', 1.00, 1.00)]


def tau4(a, b):
    return (360.0 - (a + b)) / (360.0 - 2 * THETA)


def tau4p(a, b):
    a, b = min(a, b), max(a, b)
    return (b - a) / (360.0 - THETA) + (180.0 - b) / (180.0 - THETA)


def tau5(a, b):
    a, b = min(a, b), max(a, b)
    return (b - a) / 60.0


def angle(model, i, j, k):
    v1, v2 = model.cart[i] - model.cart[j], model.cart[k] - model.cart[j]
    c = float(v1 @ v2 / (np.linalg.norm(v1) * np.linalg.norm(v2)))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def neighbours(model, i, excluded=(), metals=False):
    """Atoms bonded to i (excluded atoms left out). Metal-metal contacts are not counted as ligands
    unless metals=True."""
    excl = set(excluded)
    out = []
    for a, b in model.bonds:
        a, b = int(a), int(b)
        j = b if a == i else (a if b == i else None)
        if j is None or model.labels[j] in excl or j in out:
            continue
        if not metals and model.elements[j] not in NOT_CENTRE:
            continue
        out.append(j)
    return out


def metal_centres(model, excluded=()):
    """One instance per metal label (prefer the asymmetric-unit copy) that has >= 2 ligands."""
    excl = set(excluded)
    best = {}
    for i in range(model.n):
        el, lab = model.elements[i], model.labels[i]
        if el in NOT_CENTRE or lab in excl:
            continue
        cn = len(neighbours(model, i, excl))
        if cn < 2:
            continue
        cur = best.get(lab)
        if cur is None or (model.generated[cur] and not model.generated[i]):
            best[lab] = i
    return list(best.values())


def analyse(model, centre, ligands, name=None):
    """Dict with coordination number, the two largest angles and the indices that apply."""
    name = name or (lambda i: model.labels[i])
    lig = [j for j in ligands if j != centre]
    res = dict(centre=centre, ligands=lig, cn=len(lig), angles=[], values={}, text='')
    if len(lig) < 2:
        res['text'] = f'{name(centre)}: needs at least 2 ligands (has {len(lig)}).'
        return res
    angs = sorted(((angle(model, j, centre, k), j, k) for j, k in itertools.combinations(lig, 2)), reverse=True)
    res['angles'] = angs
    if len(angs) < 2:
        ang, j, k = angs[0]
        res['text'] = (f'{name(centre)}  (CN 2: {name(j)}, {name(k)})\n  {name(j)}–{name(centre)}–{name(k)} = '
                       f'{ang:.1f}°   (τ₄ needs 4 ligands, τ₅ needs 5)')
        return res
    b, a = angs[0][0], angs[1][0]
    lig_txt = ', '.join(name(j) for j in lig)
    big = (f'largest angles {name(angs[0][1])}–{name(centre)}–{name(angs[0][2])} = {b:.1f}°, '
           f'{name(angs[1][1])}–{name(centre)}–{name(angs[1][2])} = {a:.1f}°')
    head = f'{name(centre)}  (CN {len(lig)}: {lig_txt})'
    if len(lig) == 4:
        t4, t4p = tau4(a, b), tau4p(a, b)
        res['values'] = {'τ₄': t4, 'τ₄′': t4p}
        shape = min(IDEAL4, key=lambda s: (s[1] - t4) ** 2 + (s[2] - t4p) ** 2)[0]
        res['text'] = (f'{head}\n  τ₄ = {t4:.2f}   τ₄′ = {t4p:.2f}   → closest to {shape}\n  ({big})\n'
                       '  τ₄, τ₄′: 0 = square planar, 1 = tetrahedral; seesaw ≈ 0.43 / 0.24, '
                       'trigonal pyramidal ≈ 0.85 / 0.85')
    elif len(lig) == 5:
        t5 = tau5(a, b)
        res['values'] = {'τ₅': t5}
        shape = 'square pyramidal' if t5 < 0.5 else 'trigonal bipyramidal'
        res['text'] = (f'{head}\n  τ₅ = {t5:.2f}   → closer to {shape}\n  ({big})\n'
                       '  τ₅: 0 = square pyramidal, 1 = trigonal bipyramidal')
    else:
        res['text'] = (f'{head}\n  τ₄ / τ₄′ are defined for 4 ligands and τ₅ for 5 – this centre has '
                       f'{len(lig)}. Use "Ligands" to choose them if bonds are missing or extra.\n  ({big})')
    return res


def caption_sentence(results, name):
    """'Geometry indices: τ₄ = 0.93 and τ₄′ = 0.92 (Fe1).'"""
    parts = []
    for r in results:
        if r['values']:
            vals = ' and '.join(f'{k} = {v:.2f}' for k, v in r['values'].items())
            parts.append(f'{vals} ({name(r["centre"])})')
    if not parts:
        return ''
    return 'Geometry ' + ('index' if len(parts) == 1 and len(results[0]['values']) == 1 else 'indices') + \
        ': ' + '; '.join(parts) + '.'
