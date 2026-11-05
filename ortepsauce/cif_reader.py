"""Minimal but robust CIF 1.1 / 2.0 reader for small-molecule structures."""
import math
import re

import numpy as np

from .elements import normalize_symbol
from .structure import Atom, Cell, Structure, parse_symop, unique_ops

_TOKEN = re.compile(r"""'(?:[^']|'(?=\S))*'(?=\s|$)|"(?:[^"]|"(?=\S))*"(?=\s|$)|\S+""")


def _tokens(text):
    """Yield (value, is_tag_candidate) tokens. Quoted strings / text fields are never tags."""
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.startswith(';'):
            buf = [line[1:]]
            i += 1
            while i < n and not lines[i].startswith(';'):
                buf.append(lines[i])
                i += 1
            i += 1
            yield '\n'.join(buf).strip(), False
            continue
        for m in _TOKEN.finditer(line):
            tok = m.group(0)
            if tok.startswith('#'):
                break
            if (tok[0] == "'" and tok[-1] == "'" and len(tok) >= 2) or \
               (tok[0] == '"' and tok[-1] == '"' and len(tok) >= 2):
                yield tok[1:-1], False
            else:
                yield tok, True
        i += 1


def _norm_tag(tag):
    return tag.lower().replace('.', '_')


def parse_cif_blocks(text):
    """Return list of (block_name, items dict, loops list). loops = list of dict(tag -> list)."""
    blocks = []
    cur = None
    toks = list(_tokens(text))
    i = 0
    n = len(toks)
    while i < n:
        tok, bare = toks[i]
        low = tok.lower() if bare else ''
        if bare and low.startswith('data_'):
            cur = {'name': tok[5:], 'items': {}, 'loops': []}
            blocks.append(cur)
            i += 1
        elif bare and low == 'loop_':
            i += 1
            tags = []
            while i < n and toks[i][1] and toks[i][0].startswith('_'):
                tags.append(_norm_tag(toks[i][0]))
                i += 1
            values = []
            while i < n:
                v, b = toks[i]
                if b and (v.startswith('_') or v.lower() in ('loop_', 'stop_')
                          or v.lower().startswith('data_') or v.lower().startswith('save_')
                          or v.lower().startswith('global_')):
                    break
                values.append(v)
                i += 1
            if cur is None:
                cur = {'name': '', 'items': {}, 'loops': []}
                blocks.append(cur)
            if tags:
                ncol = len(tags)
                loop = {t: values[k::ncol] for k, t in enumerate(tags)}
                cur['loops'].append(loop)
        elif bare and tok.startswith('_'):
            tag = _norm_tag(tok)
            val = toks[i + 1][0] if i + 1 < n else ''
            if cur is None:
                cur = {'name': '', 'items': {}, 'loops': []}
                blocks.append(cur)
            cur['items'][tag] = val
            i += 2
        else:
            i += 1  # save_/global_/stray tokens
    return blocks


def cif_float(v, default=None):
    if v is None:
        return default
    v = v.strip()
    if v in ('.', '?', ''):
        return default
    v = re.sub(r'\(.*\)$', '', v)
    try:
        return float(v)
    except ValueError:
        return default


def _get(block, *tags):
    for t in tags:
        if t in block['items']:
            return block['items'][t]
    return None


def _find_loop(block, tag):
    for loop in block['loops']:
        if tag in loop:
            return loop
    return None


def block_has_atoms(block):
    return _find_loop(block, '_atom_site_fract_x') is not None


def read_cif(path):
    """Return list of (block_name, Structure) for every data block containing atoms."""
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        text = fh.read()
    out = []
    for blk in parse_cif_blocks(text):
        if block_has_atoms(blk):
            out.append((blk['name'], structure_from_block(blk, path)))
    if not out:
        raise ValueError('No data block with atomic coordinates (_atom_site_fract_x) found.')
    return out


def structure_from_block(blk, path=''):
    warnings = []
    vals = [cif_float(_get(blk, t)) for t in
            ('_cell_length_a', '_cell_length_b', '_cell_length_c',
             '_cell_angle_alpha', '_cell_angle_beta', '_cell_angle_gamma')]
    if any(v is None for v in vals[:3]):
        raise ValueError('Cell lengths missing from CIF block.')
    vals = [v if v is not None else 90.0 for v in vals]
    cell = Cell(*vals)

    # --- symmetry
    symops = []
    for tag in ('_space_group_symop_operation_xyz', '_symmetry_equiv_pos_as_xyz'):
        loop = _find_loop(blk, tag)
        if loop:
            for s in loop[tag]:
                try:
                    symops.append(parse_symop(s))
                except ValueError as e:
                    warnings.append(str(e))
            break
    if not symops:
        warnings.append('No symmetry operators found; using P1.')
        symops = [(np.eye(3), np.zeros(3))]
    symops = unique_ops(symops)

    # --- atoms
    loop = _find_loop(blk, '_atom_site_fract_x')
    nat = len(loop['_atom_site_fract_x'])

    def col(tag, default=None):
        c = loop.get(tag)
        return c if c is not None else [default] * nat

    labels = col('_atom_site_label', None)
    types = col('_atom_site_type_symbol', None)
    xs, ys, zs = col('_atom_site_fract_x'), col('_atom_site_fract_y'), col('_atom_site_fract_z')
    uiso = col('_atom_site_u_iso_or_equiv')
    biso = col('_atom_site_b_iso_or_equiv')
    occ = col('_atom_site_occupancy')
    dg = col('_atom_site_disorder_group')
    flags = col('_atom_site_calc_flag')

    atoms = []
    for k in range(nat):
        if flags[k] and flags[k].lower() == 'dum':
            continue
        label = labels[k] if labels[k] is not None else f'X{k + 1}'
        el = normalize_symbol(types[k]) if types[k] not in (None, '.', '?') else None
        if el is None:
            el = normalize_symbol(label) or 'C'
        f = np.array([cif_float(xs[k], 0.0), cif_float(ys[k], 0.0), cif_float(zs[k], 0.0)])
        u = cif_float(uiso[k])
        if u is None:
            b = cif_float(biso[k])
            u = b / (8 * math.pi**2) if b is not None else (0.025 if el not in ('H', 'D') else 0.03)
        part = 0
        if dg[k] not in (None, '.', '?'):
            try:
                part = int(dg[k])
            except ValueError:
                part = 1
        atoms.append(Atom(label=label, element=el, frac=f,
                          occupancy=cif_float(occ[k], 1.0), part=part, uiso=u))

    # --- anisotropic displacement parameters
    by_label = {a.label: a for a in atoms}
    aloop = _find_loop(blk, '_atom_site_aniso_label')
    if aloop:
        use_b = '_atom_site_aniso_u_11' not in aloop and '_atom_site_aniso_b_11' in aloop
        pre = '_atom_site_aniso_b_' if use_b else '_atom_site_aniso_u_'
        conv = 1.0 / (8 * math.pi**2) if use_b else 1.0
        cols = [aloop.get(pre + s) for s in ('11', '22', '33', '23', '13', '12')]
        if all(c is not None for c in cols):
            for k, lab in enumerate(aloop['_atom_site_aniso_label']):
                a = by_label.get(lab)
                if a is None:
                    continue
                u = [cif_float(c[k]) for c in cols]
                if any(v is None for v in u):
                    continue
                a.uani = tuple(v * conv for v in u)

    formula = (_get(blk, '_chemical_formula_sum') or '').strip()
    sg = (_get(blk, '_space_group_name_h-m_alt', '_symmetry_space_group_name_h-m') or '').strip()
    geom_bonds, geom_angles = [], []
    gb = _find_loop(blk, '_geom_bond_distance')
    if gb and '_geom_bond_atom_site_label_1' in gb:
        for a, b, v in zip(gb['_geom_bond_atom_site_label_1'], gb['_geom_bond_atom_site_label_2'],
                           gb['_geom_bond_distance']):
            geom_bonds.append((a, b, v))
    ga = _find_loop(blk, '_geom_angle')
    if ga and '_geom_angle_atom_site_label_1' in ga:
        for a, b, c, v in zip(ga['_geom_angle_atom_site_label_1'], ga['_geom_angle_atom_site_label_2'],
                              ga['_geom_angle_atom_site_label_3'], ga['_geom_angle']):
            geom_angles.append((a, b, c, v))
    return Structure(geom_bonds=geom_bonds, geom_angles=geom_angles, title=blk['name'], cell=cell, symops=symops, atoms=atoms,
                     spacegroup=sg, formula=formula, source=path, warnings=warnings)
