"""Core crystallographic data model: unit cell, symmetry operators, atoms."""
import math
import re
from dataclasses import dataclass, field

import numpy as np


# ----------------------------------------------------------------------------
# Unit cell
# ----------------------------------------------------------------------------
class Cell:
    def __init__(self, a, b, c, alpha, beta, gamma):
        self.params = (a, b, c, alpha, beta, gamma)
        al, be, ga = (math.radians(x) for x in (alpha, beta, gamma))
        ca, cb, cg = math.cos(al), math.cos(be), math.cos(ga)
        sa, sb, sg = math.sin(al), math.sin(be), math.sin(ga)
        self.volume = a * b * c * math.sqrt(max(1e-12, 1 - ca**2 - cb**2 - cg**2 + 2 * ca * cb * cg))
        V = self.volume
        # fractional -> Cartesian (a along x, b in the xy plane)
        self.A = np.array([
            [a, b * cg, c * cb],
            [0.0, b * sg, c * (ca - cb * cg) / sg],
            [0.0, 0.0, V / (a * b * sg)],
        ])
        self.Ainv = np.linalg.inv(self.A)
        # reciprocal lengths a*, b*, c*
        self.recip = np.array([b * c * sa / V, a * c * sb / V, a * b * sg / V])
        self.N = np.diag(self.recip)

    def to_cart(self, frac):
        return np.asarray(frac) @ self.A.T

    def to_frac(self, cart):
        return np.asarray(cart) @ self.Ainv.T

    def ustar_from_uij(self, u):
        """u = (U11, U22, U33, U23, U13, U12) in the CIF/SHELX convention -> U* (3x3)."""
        U = uij_matrix(u)
        return self.N @ U @ self.N

    def ucart_from_ustar(self, ustar):
        return self.A @ ustar @ self.A.T

    def ueq(self, u):
        return float(np.trace(self.ucart_from_ustar(self.ustar_from_uij(u))) / 3.0)


def uij_matrix(u):
    u11, u22, u33, u23, u13, u12 = u
    return np.array([[u11, u12, u13], [u12, u22, u23], [u13, u23, u33]], dtype=float)


# ----------------------------------------------------------------------------
# Symmetry operators
# ----------------------------------------------------------------------------
_TERM = re.compile(r'([+-]?)\s*([0-9]*\.?[0-9]*(?:/[0-9]*\.?[0-9]+)?)\s*\*?\s*([xyz]?)')


def _num(s):
    if '/' in s:
        n, d = s.split('/')
        return float(n) / float(d)
    return float(s)


def parse_symop(text):
    """Parse 'x,-y+1/2,z+1/2' style operator -> (R 3x3, t 3)."""
    s = text.strip().strip("'\"").lower().replace(' ', '')
    parts = s.split(',')
    if len(parts) != 3:
        raise ValueError(f'Cannot parse symmetry operator: {text!r}')
    R = np.zeros((3, 3))
    t = np.zeros(3)
    for row, part in enumerate(parts):
        for m in _TERM.finditer(part):
            sign, num, var = m.groups()
            if not num and not var:
                continue
            sgn = -1.0 if sign == '-' else 1.0
            if var:
                coef = _num(num) if num else 1.0
                R[row, 'xyz'.index(var)] += sgn * coef
            else:
                t[row] += sgn * _num(num)
    return R, t


CENTERING_VECTORS = {
    1: [],                                                  # P
    2: [(0.5, 0.5, 0.5)],                                   # I
    3: [(2 / 3, 1 / 3, 1 / 3), (1 / 3, 2 / 3, 2 / 3)],      # R (obverse)
    4: [(0, 0.5, 0.5), (0.5, 0, 0.5), (0.5, 0.5, 0)],       # F
    5: [(0, 0.5, 0.5)],                                     # A
    6: [(0.5, 0, 0.5)],                                     # B
    7: [(0.5, 0.5, 0)],                                     # C
}


def expand_shelx_symmetry(symm_ops, latt):
    """Build the full list of operators from SHELX SYMM cards + LATT code."""
    ops = [(np.eye(3), np.zeros(3))] + list(symm_ops)
    if latt > 0:  # centrosymmetric
        ops = ops + [(-R, -t) for R, t in ops]
    full = list(ops)
    for v in CENTERING_VECTORS.get(abs(latt), []):
        full += [(R, t + np.array(v)) for R, t in ops]
    return unique_ops(full)


def unique_ops(ops):
    out = []
    seen = set()
    for R, t in ops:
        key = (tuple(np.round(R, 6).ravel()), tuple(np.round(np.mod(t, 1.0), 4) % 1.0))
        if key not in seen:
            seen.add(key)
            out.append((R, t))
    return out


# ----------------------------------------------------------------------------
# Atom / structure containers
# ----------------------------------------------------------------------------
@dataclass
class Atom:
    label: str
    element: str
    frac: np.ndarray
    occupancy: float = 1.0
    part: int = 0
    uiso: float = None          # isotropic U (Angstrom^2); also Ueq for aniso atoms
    uani: tuple = None          # (U11, U22, U33, U23, U13, U12)
    is_qpeak: bool = False
    peak_height: float = 0.0
    residue: str = ''


@dataclass
class Structure:
    title: str
    cell: Cell
    symops: list
    atoms: list
    qpeaks: list = field(default_factory=list)
    spacegroup: str = ''
    formula: str = ''
    source: str = ''
    warnings: list = field(default_factory=list)
    geom_bonds: list = field(default_factory=list)    # (label1, label2, value text) from CIF
    geom_angles: list = field(default_factory=list)   # (label1, label2 (centre), label3, value text)
