"""Element data: covalent radii (Cordero et al., Dalton Trans. 2008) and display colors."""

# Covalent radii in Angstrom. Where Cordero lists low/high-spin values the mean is used.
COVALENT_RADII = {
    'H': 0.31, 'D': 0.31, 'He': 0.28, 'Li': 1.28, 'Be': 0.96, 'B': 0.84, 'C': 0.76,
    'N': 0.71, 'O': 0.66, 'F': 0.57, 'Ne': 0.58, 'Na': 1.66, 'Mg': 1.41, 'Al': 1.21,
    'Si': 1.11, 'P': 1.07, 'S': 1.05, 'Cl': 1.02, 'Ar': 1.06, 'K': 2.03, 'Ca': 1.76,
    'Sc': 1.70, 'Ti': 1.60, 'V': 1.53, 'Cr': 1.39, 'Mn': 1.50, 'Fe': 1.42, 'Co': 1.38,
    'Ni': 1.24, 'Cu': 1.32, 'Zn': 1.22, 'Ga': 1.22, 'Ge': 1.20, 'As': 1.19, 'Se': 1.20,
    'Br': 1.20, 'Kr': 1.16, 'Rb': 2.20, 'Sr': 1.95, 'Y': 1.90, 'Zr': 1.75, 'Nb': 1.64,
    'Mo': 1.54, 'Tc': 1.47, 'Ru': 1.46, 'Rh': 1.42, 'Pd': 1.39, 'Ag': 1.45, 'Cd': 1.44,
    'In': 1.42, 'Sn': 1.39, 'Sb': 1.39, 'Te': 1.38, 'I': 1.39, 'Xe': 1.40, 'Cs': 2.44,
    'Ba': 2.15, 'La': 2.07, 'Ce': 2.04, 'Pr': 2.03, 'Nd': 2.01, 'Pm': 1.99, 'Sm': 1.98,
    'Eu': 1.98, 'Gd': 1.96, 'Tb': 1.94, 'Dy': 1.92, 'Ho': 1.92, 'Er': 1.89, 'Tm': 1.90,
    'Yb': 1.87, 'Lu': 1.87, 'Hf': 1.75, 'Ta': 1.70, 'W': 1.62, 'Re': 1.51, 'Os': 1.44,
    'Ir': 1.41, 'Pt': 1.36, 'Au': 1.36, 'Hg': 1.32, 'Tl': 1.45, 'Pb': 1.46, 'Bi': 1.48,
    'Po': 1.40, 'At': 1.50, 'Rn': 1.50, 'Fr': 2.60, 'Ra': 2.21, 'Ac': 2.15, 'Th': 2.06,
    'Pa': 2.00, 'U': 1.96, 'Np': 1.90, 'Pu': 1.87, 'Am': 1.80, 'Cm': 1.69,
}

# Colors (roughly the Jmol/CPK scheme, slightly darkened where pure white/yellow
# would vanish on a white background).
ELEMENT_COLORS = {
    'H': '#FFFFFF', 'D': '#FFFFFF', 'He': '#D9FFFF', 'Li': '#CC80FF', 'Be': '#C2FF00',
    'B': '#FFB5B5', 'C': '#7f7f7f', 'N': '#3050F8', 'O': '#FF0D0D', 'F': '#90E050',
    'Ne': '#B3E3F5', 'Na': '#AB5CF2', 'Mg': '#8AFF00', 'Al': '#BFA6A6', 'Si': '#F0C8A0',
    'P': '#FF8000', 'S': '#E6C619', 'Cl': '#1FF01F', 'Ar': '#80D1E3', 'K': '#8F40D4',
    'Ca': '#3DFF00', 'Sc': '#E6E6E6', 'Ti': '#BFC2C7', 'V': '#A6A6AB', 'Cr': '#8A99C7',
    'Mn': '#9C7AC7', 'Fe': '#E06633', 'Co': '#F090A0', 'Ni': '#50D050', 'Cu': '#C88033',
    'Zn': '#7D80B0', 'Ga': '#C28F8F', 'Ge': '#668F8F', 'As': '#BD80E3', 'Se': '#FFA100',
    'Br': '#A62929', 'Kr': '#5CB8D1', 'Rb': '#702EB0', 'Sr': '#00FF00', 'Y': '#94FFFF',
    'Zr': '#94E0E0', 'Nb': '#73C2C9', 'Mo': '#54B5B5', 'Tc': '#3B9E9E', 'Ru': '#248F8F',
    'Rh': '#0A7D8C', 'Pd': '#006985', 'Ag': '#C0C0C0', 'Cd': '#FFD98F', 'In': '#A67573',
    'Sn': '#668080', 'Sb': '#9E63B5', 'Te': '#D47A00', 'I': '#940094', 'Xe': '#429EB0',
    'Cs': '#57178F', 'Ba': '#00C900', 'La': '#70D4FF', 'Ce': '#FFFFC7', 'Pr': '#D9FFC7',
    'Nd': '#C7FFC7', 'Pm': '#A3FFC7', 'Sm': '#8FFFC7', 'Eu': '#61FFC7', 'Gd': '#45FFC7',
    'Tb': '#30FFC7', 'Dy': '#1FFFC7', 'Ho': '#00FF9C', 'Er': '#00E675', 'Tm': '#00D452',
    'Yb': '#00BF38', 'Lu': '#00AB24', 'Hf': '#4DC2FF', 'Ta': '#4DA6FF', 'W': '#2194D6',
    'Re': '#267DAB', 'Os': '#266696', 'Ir': '#175487', 'Pt': '#D0D0E0', 'Au': '#FFD123',
    'Hg': '#B8B8D0', 'Tl': '#A6544D', 'Pb': '#575961', 'Bi': '#9E4FB5', 'Po': '#AB5C00',
    'At': '#754F45', 'Rn': '#428296', 'Fr': '#420066', 'Ra': '#007D00', 'Ac': '#70ABFA',
    'Th': '#00BAFF', 'Pa': '#00A1FF', 'U': '#008FFF', 'Np': '#0080FF', 'Pu': '#006BFF',
    'Am': '#545CF2', 'Cm': '#785CE3',
}

DEFAULT_RADIUS = 1.50
DEFAULT_COLOR = '#FF1493'
QPEAK_COLOR = '#C8A2C8'

_SYMBOLS_UPPER = {s.upper(): s for s in COVALENT_RADII}


def normalize_symbol(text):
    """Return a properly capitalised element symbol from a label or type string
    such as 'C12A', 'Ti1', 'O2-', 'FE', 'Cl1'. Returns None if nothing matches."""
    if not text:
        return None
    letters = ''
    for ch in text.strip():
        if ch.isalpha():
            letters += ch
        else:
            break
    if not letters:
        return None
    up = letters.upper()
    # 1) properly cased two-letter symbol ('Ti1', 'Cl2')
    if len(letters) >= 2 and letters[0].isupper() and letters[1].islower() \
            and letters[:2] in COVALENT_RADII:
        return letters[:2]
    # 2) whole token is an upper-case element symbol ('FE', 'CL') - typical of type columns
    if up in _SYMBOLS_UPPER and len(up) <= 2:
        return _SYMBOLS_UPPER[up]
    # 3) single-letter element ('C12A', 'N1')
    if up[0] in _SYMBOLS_UPPER:
        return _SYMBOLS_UPPER[up[0]]
    if len(up) >= 2 and up[:2] in _SYMBOLS_UPPER:
        return _SYMBOLS_UPPER[up[:2]]
    return None


def covalent_radius(el):
    return COVALENT_RADII.get(el, DEFAULT_RADIUS)


def element_color(el):
    return ELEMENT_COLORS.get(el, DEFAULT_COLOR)


# Van der Waals radii (Angstrom), Bondi 1964 / Alvarez 2013 where Bondi has none.
VDW_RADII = {
    'H': 1.20, 'D': 1.20, 'He': 1.40, 'Li': 1.82, 'Be': 1.53, 'B': 1.92, 'C': 1.70, 'N': 1.55,
    'O': 1.52, 'F': 1.47, 'Ne': 1.54, 'Na': 2.27, 'Mg': 1.73, 'Al': 1.84, 'Si': 2.10, 'P': 1.80,
    'S': 1.80, 'Cl': 1.75, 'Ar': 1.88, 'K': 2.75, 'Ca': 2.31, 'Sc': 2.15, 'Ti': 2.11, 'V': 2.07,
    'Cr': 2.06, 'Mn': 2.05, 'Fe': 2.04, 'Co': 2.00, 'Ni': 1.63, 'Cu': 1.40, 'Zn': 1.39, 'Ga': 1.87,
    'Ge': 2.11, 'As': 1.85, 'Se': 1.90, 'Br': 1.85, 'Kr': 2.02, 'Rb': 3.03, 'Sr': 2.49, 'Y': 2.32,
    'Zr': 2.23, 'Nb': 2.18, 'Mo': 2.17, 'Ru': 2.13, 'Rh': 2.10, 'Pd': 1.63, 'Ag': 1.72, 'Cd': 1.58,
    'In': 1.93, 'Sn': 2.17, 'Sb': 2.06, 'Te': 2.06, 'I': 1.98, 'Xe': 2.16, 'Cs': 3.43, 'Ba': 2.68,
    'La': 2.43, 'Hf': 2.23, 'Ta': 2.22, 'W': 2.18, 'Re': 2.16, 'Os': 2.16, 'Ir': 2.13, 'Pt': 1.75,
    'Au': 1.66, 'Hg': 1.55, 'Tl': 1.96, 'Pb': 2.02, 'Bi': 2.07, 'Th': 2.45, 'U': 1.86,
}


def vdw_radius(el):
    return VDW_RADII.get(el, 2.0)
