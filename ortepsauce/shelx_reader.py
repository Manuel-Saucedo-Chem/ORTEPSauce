"""Reader for SHELX .ins / .res files (atoms, ADPs, free variables, riding H, Q-peaks)."""
import re

import numpy as np

from .elements import normalize_symbol
from .structure import Atom, Cell, Structure, expand_shelx_symmetry, parse_symop

# Instructions that are never atom names (first 4 characters are significant in SHELX)
SHELX_COMMANDS = set("""
ABIN ACTA AFIX ANIS ANSC ANSR BASF BIND BLOC BOND BUMP CELL CGLS CHIV CONF CONN DAMP DANG
DEFS DELU DFIX DISP EADP END EQIV EXTI EXYZ FEND FLAT FMAP FRAG FREE FVAR GRID HFIX HKLF
HTAB ISOR LATT LAUE LIST L.S. MERG MORE MOVE MPLA NCSY NEUT OMIT PART PLAN PRIG REM RESI
RIGU RTAB SADI SAME SFAC SHEL SIMU SIZE SPEC STIR SUMP SWAT SYMM TEMP TITL TWIN TWST UNIT
WGHT WIGL WPDB XNPD ZERR BEDE LONE CHIV DISP SADM ABIN EGEN
""".split())


def _logical_lines(text):
    """Join '=' continuation lines, strip '!' comments, keep REM lines separate."""
    out = []
    buf = ''
    for raw in text.splitlines():
        line = raw.rstrip()
        if not buf and line[:4].upper() == 'REM ' or line.upper() == 'REM':
            out.append(line)
            continue
        if '!' in line:
            line = line.split('!', 1)[0].rstrip()
        if line.endswith('='):
            buf += line[:-1] + ' '
            continue
        buf += line
        out.append(buf)
        buf = ''
    if buf:
        out.append(buf)
    return out


def _resolve(p, fvars):
    """Apply SHELX free-variable / fixing conventions to a parameter value."""
    if abs(p) <= 5.0:
        return p
    m = int((abs(p) + 5.0) // 10)
    q = p - 10.0 * m if p > 0 else p + 10.0 * m
    if m <= 1:
        return q
    fv = fvars[m - 1] if m - 1 < len(fvars) else 1.0
    return q * fv if p > 0 else q * (fv - 1.0)


def _is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def read_shelx(path):
    with open(path, 'r', encoding='latin-1') as fh:
        text = fh.read()

    title = ''
    cell = None
    latt = 1
    symm = []
    sfac = []
    fvars = []
    part = 0
    part_sof = None
    residue = ''
    atoms = []
    qpeaks = []
    warnings = []
    last_ueq = 0.05        # Ueq of the last non-H atom (for riding Uiso)
    after_hklf = False

    for line in _logical_lines(text):
        toks = line.split()
        if not toks:
            continue
        key = toks[0].upper()
        k4 = key[:4]
        if k4 == 'REM':
            continue
        if k4 == 'TITL':
            title = line[4:].strip()
        elif k4 == 'CELL':
            nums = [float(x) for x in toks[1:8]]
            cell = Cell(*nums[1:7])
        elif k4 == 'LATT':
            latt = int(float(toks[1]))
        elif k4 == 'SYMM':
            symm.append(parse_symop(line[4:].strip()))
        elif k4 == 'SFAC':
            args = toks[1:]
            if len(args) >= 2 and _is_number(args[1]):
                sfac.append(normalize_symbol(args[0]) or args[0])  # long form, one element
            else:
                sfac.extend(normalize_symbol(a) or a for a in args)
        elif k4 == 'FVAR':
            fvars.extend(float(x) for x in toks[1:])
        elif k4 == 'PART':
            part = int(float(toks[1])) if len(toks) > 1 else 0
            part_sof = float(toks[2]) if len(toks) > 2 else None
        elif k4 == 'RESI':
            residue = ' '.join(toks[1:3]) if len(toks) > 1 else ''
            if len(toks) > 1 and toks[1].upper() == '0':
                residue = ''
        elif k4 in ('HKLF', 'END'):
            after_hklf = True
            part = 0
        elif k4 in SHELX_COMMANDS or key in SHELX_COMMANDS:
            continue
        else:
            # Candidate atom line: Name SFAC x y z [sof [U11 or Uiso [U22 U33 U23 U13 U12]]]
            if len(toks) < 5 or not all(_is_number(t) for t in toks[1:]):
                continue
            name = toks[0]
            is_q = bool(re.fullmatch(r'Q\d+', name, re.IGNORECASE))
            if after_hklf and not is_q:
                continue
            nums = [float(t) for t in toks[1:]]
            sf = int(nums[0])
            xyz = np.array([_resolve(v, fvars) for v in nums[1:4]])
            sof_raw = nums[4] if len(nums) > 4 else (part_sof if part_sof is not None else 11.0)
            occ = _resolve(sof_raw, fvars)
            if is_q:
                height = nums[6] if len(nums) > 6 else 0.0
                qpeaks.append(Atom(label=name, element='Q', frac=xyz, is_qpeak=True,
                                   peak_height=height, uiso=0.05))
                continue
            if sf < 1 or sf > len(sfac):
                warnings.append(f'{name}: SFAC index {sf} out of range')
                el = normalize_symbol(name) or 'C'
            else:
                el = sfac[sf - 1]
            if cell is None:
                raise ValueError('Atom found before CELL instruction.')
            atom = Atom(label=name, element=el, frac=xyz, occupancy=occ, part=part, residue=residue)
            if len(nums) >= 11:
                u = [_resolve(v, fvars) for v in nums[5:11]]
                atom.uani = (u[0], u[1], u[2], u[3], u[4], u[5])
                atom.uiso = cell.ueq(atom.uani)
            else:
                uval = nums[5] if len(nums) > 5 else 0.05
                if -5.0 < uval < -0.5:      # riding: -1.2 / -1.5 x Ueq of previous non-H atom
                    atom.uiso = abs(uval) * last_ueq
                else:
                    atom.uiso = _resolve(uval, fvars)
            if el not in ('H', 'D'):
                last_ueq = atom.uiso
            atoms.append(atom)

    if cell is None:
        raise ValueError('No CELL instruction found.')
    symops = expand_shelx_symmetry(symm, latt)
    counts = {}
    for a in atoms:
        counts[a.element] = counts.get(a.element, 0) + 1
    formula = ' '.join(f'{e}{n}' for e, n in counts.items())
    sg = f'LATT {latt}, {len(symops)} symmetry operators'
    return Structure(title=title or path, cell=cell, symops=symops, atoms=atoms,
                     qpeaks=qpeaks, spacegroup=sg, formula=f'(asym. unit) {formula}',
                     source=path, warnings=warnings)
