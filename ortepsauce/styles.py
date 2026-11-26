"""Rendering styles: POV-Ray named colors, finishes and textures, and the per-element /
per-object style table (mirrors ORTEP-3's Modify panel: EllipseStyle, Color, Finish, Texture).

Finish and texture parameters are copied from POV-Ray 3.7's finish.inc, metals.inc and
textures.inc so the on-screen preview and the exported .pov scene describe the same material.
The preview is a single-bounce Phong approximation (no true reflections / shadows)."""
import copy

from .elements import element_color

POV_COLORS = {
    'Red': (1.0, 0.0, 0.0), 'Green': (0.0, 1.0, 0.0), 'Blue': (0.0, 0.0, 1.0),
    'Yellow': (1.0, 1.0, 0.0), 'Cyan': (0.0, 1.0, 1.0), 'Magenta': (1.0, 0.0, 1.0),
    'White': (1.0, 1.0, 1.0), 'Black': (0.0, 0.0, 0.0), 'Gray05': (0.05, 0.05, 0.05),
    'Gray10': (0.1, 0.1, 0.1), 'Gray15': (0.15, 0.15, 0.15), 'Gray20': (0.2, 0.2, 0.2),
    'Gray25': (0.25, 0.25, 0.25), 'Gray30': (0.3, 0.3, 0.3), 'Gray35': (0.35, 0.35, 0.35),
    'Gray40': (0.4, 0.4, 0.4), 'Gray45': (0.45, 0.45, 0.45), 'Gray50': (0.5, 0.5, 0.5),
    'Gray55': (0.55, 0.55, 0.55), 'Gray60': (0.6, 0.6, 0.6), 'Gray65': (0.65, 0.65, 0.65),
    'Gray70': (0.7, 0.7, 0.7), 'Gray75': (0.75, 0.75, 0.75), 'Gray80': (0.8, 0.8, 0.8),
    'Gray85': (0.85, 0.85, 0.85), 'Gray90': (0.9, 0.9, 0.9), 'Gray95': (0.95, 0.95, 0.95),
    'DimGray': (0.3294, 0.3294, 0.3294), 'DimGrey': (0.3294, 0.3294, 0.3294), 'Gray': (0.7529, 0.7529, 0.7529),
    'Grey': (0.7529, 0.7529, 0.7529), 'LightGray': (0.6588, 0.6588, 0.6588), 'LightGrey': (0.6588, 0.6588, 0.6588),
    'VLightGray': (0.8, 0.8, 0.8), 'VLightGrey': (0.8, 0.8, 0.8), 'Aquamarine': (0.4392, 0.8588, 0.5765),
    'BlueViolet': (0.6235, 0.3725, 0.6235), 'Brown': (0.6471, 0.1647, 0.1647), 'CadetBlue': (0.3725, 0.6235, 0.6235),
    'Coral': (1.0, 0.498, 0.0), 'CornflowerBlue': (0.2588, 0.2588, 0.4353), 'DarkGreen': (0.1843, 0.3098, 0.1843),
    'DarkOliveGreen': (0.3098, 0.3098, 0.1843), 'DarkOrchid': (0.6, 0.1961, 0.8), 'DarkSlateBlue': (0.1196, 0.1373, 0.5569),
    'DarkSlateGray': (0.1843, 0.3098, 0.3098), 'DarkSlateGrey': (0.1843, 0.3098, 0.3098), 'DarkTurquoise': (0.4392, 0.5765, 0.8588),
    'Firebrick': (0.5569, 0.1373, 0.1373), 'ForestGreen': (0.1373, 0.5569, 0.1373), 'Gold': (0.8, 0.498, 0.1961),
    'Goldenrod': (0.8588, 0.8588, 0.4392), 'GreenYellow': (0.5765, 0.8588, 0.4392), 'IndianRed': (0.3098, 0.1843, 0.1843),
    'Khaki': (0.6235, 0.6235, 0.3725), 'LightBlue': (0.749, 0.8471, 0.8471), 'LightSteelBlue': (0.5608, 0.5608, 0.7373),
    'LimeGreen': (0.1961, 0.8, 0.1961), 'Maroon': (0.5569, 0.1373, 0.4196), 'MediumAquamarine': (0.1961, 0.8, 0.6),
    'MediumBlue': (0.1961, 0.1961, 0.8), 'MediumForestGreen': (0.4196, 0.5569, 0.1373), 'MediumGoldenrod': (0.9176, 0.9176, 0.6784),
    'MediumOrchid': (0.5765, 0.4392, 0.8588), 'MediumSeaGreen': (0.2588, 0.4353, 0.2588), 'MediumSlateBlue': (0.498, 0, 1.0),
    'MediumSpringGreen': (0.498, 1.0, 0), 'MediumTurquoise': (0.4392, 0.8588, 0.8588), 'MediumVioletRed': (0.8588, 0.4392, 0.5765),
    'MidnightBlue': (0.1843, 0.1843, 0.3098), 'Navy': (0.1373, 0.1373, 0.5569), 'NavyBlue': (0.1373, 0.1373, 0.5569),
    'Orange': (1.0, 0.5, 0.0), 'OrangeRed': (1.0, 0.25, 0), 'Orchid': (0.8588, 0.4392, 0.8588),
    'PaleGreen': (0.5608, 0.7373, 0.5608), 'Pink': (0.7373, 0.5608, 0.5608), 'Plum': (0.9176, 0.6784, 0.9176),
    'Salmon': (0.4353, 0.2588, 0.2588), 'SeaGreen': (0.1373, 0.5569, 0.4196), 'Sienna': (0.5569, 0.4196, 0.1373),
    'SkyBlue': (0.1961, 0.6, 0.8), 'SlateBlue': (0, 0.498, 1.0), 'SpringGreen': (0, 1.0, 0.498),
    'SteelBlue': (0.1373, 0.4196, 0.5569), 'Tan': (0.8588, 0.5765, 0.4392), 'Thistle': (0.8471, 0.749, 0.8471),
    'Turquoise': (0.6784, 0.9176, 0.9176), 'Violet': (0.3098, 0.1843, 0.3098), 'VioletRed': (0.8, 0.1961, 0.6),
    'Wheat': (0.8471, 0.8471, 0.749), 'YellowGreen': (0.6, 0.8, 0.1961), 'SummerSky': (0.22, 0.69, 0.87),
    'RichBlue': (0.35, 0.35, 0.67), 'Brass': (0.71, 0.65, 0.26), 'Copper': (0.72, 0.45, 0.2),
    'Bronze': (0.55, 0.47, 0.14), 'Bronze2': (0.65, 0.49, 0.24), 'Silver': (0.9, 0.91, 0.98),
    'BrightGold': (0.85, 0.85, 0.1), 'OldGold': (0.81, 0.71, 0.23), 'Feldspar': (0.82, 0.57, 0.46),
    'Quartz': (0.85, 0.85, 0.95), 'NeonPink': (1.0, 0.43, 0.78), 'DarkPurple': (0.53, 0.12, 0.47),
    'NeonBlue': (0.3, 0.3, 1.0), 'CoolCopper': (0.85, 0.53, 0.1), 'MandarinOrange': (0.89, 0.47, 0.2),
    'LightWood': (0.91, 0.76, 0.65), 'MediumWood': (0.65, 0.5, 0.39), 'DarkWood': (0.52, 0.37, 0.26),
    'SpicyPink': (1.0, 0.11, 0.68), 'SemiSweetChoc': (0.42, 0.26, 0.15), 'BakersChoc': (0.36, 0.2, 0.09),
    'Flesh': (0.96, 0.8, 0.69), 'NewTan': (0.92, 0.78, 0.62), 'NewMidnightBlue': (0.0, 0.0, 0.61),
    'VeryDarkBrown': (0.35, 0.16, 0.14), 'DarkBrown': (0.36, 0.25, 0.2), 'DarkTan': (0.59, 0.41, 0.31),
    'GreenCopper': (0.32, 0.49, 0.46), 'DkGreenCopper': (0.29, 0.46, 0.43), 'DustyRose': (0.52, 0.39, 0.39),
    'HuntersGreen': (0.13, 0.37, 0.31), 'Scarlet': (0.55, 0.09, 0.09), 'Med_Purple': (0.73, 0.16, 0.96),
    'Light_Purple': (0.87, 0.58, 0.98), 'Very_Light_Purple': (0.94, 0.81, 0.99),
}

# --------------------------------------------------------------------------- finishes
# POV-Ray defaults: ambient 0.1 diffuse 0.6 brilliance 1 specular 0 roughness 0.05 phong 0
# phong_size 40 reflection 0, not metallic, crand 0.
FINISH_DEFAULT = dict(ambient=0.1, diffuse=0.6, brilliance=1.0, specular=0.0, roughness=0.05,
                      phong=0.0, phong_size=40.0, reflection=0.0, metallic=False, crand=0.0)


def _f(**kw):
    d = dict(FINISH_DEFAULT)
    d.update(kw)
    return d


FINISHES = {
    'Dull': _f(specular=0.5, roughness=0.15),                                    # finish.inc
    'Shiny': _f(specular=1.0, roughness=0.001),                                  # finish.inc
    'Speckled': _f(phong=0.4, phong_size=40, crand=0.3),                         # user's ORTEP-3 file
    'Plastic': _f(specular=0.6, roughness=0.02, phong=0.3, phong_size=60),       # defined in exported .pov
    'Metal': _f(metallic=True, ambient=0.2, diffuse=0.7, brilliance=6, reflection=0.25,
                phong=0.75, phong_size=80),                                      # textures.inc
    'Phong_Dull': _f(phong=0.5, phong_size=1),                                   # finish.inc
    'Phong_Shiny': _f(phong=1.0, phong_size=200),
    'Phong_Glossy': _f(phong=1.0, phong_size=300, reflection=0.13),
    'Metallic_Finish': _f(metallic=True, ambient=0.1, diffuse=0.65, specular=0.85, roughness=0.01,
                          reflection=0.45, brilliance=1.5),                      # textures.inc
    'SilverFinish': _f(metallic=True, ambient=0.25, diffuse=0.65, reflection=0.45, brilliance=6,
                       phong=1.0, phong_size=100),                               # textures.inc
    'F_MetalA': _f(ambient=0.35, brilliance=2, diffuse=0.3, metallic=True, specular=0.8,
                   roughness=1 / 20, reflection=0.1),                            # metals.inc
    'F_MetalB': _f(ambient=0.30, brilliance=3, diffuse=0.4, metallic=True, specular=0.7,
                   roughness=1 / 60, reflection=0.25),
    'F_MetalC': _f(ambient=0.25, brilliance=4, diffuse=0.5, metallic=True, specular=0.8,
                   roughness=1 / 80, reflection=0.5),
    'F_MetalD': _f(ambient=0.15, brilliance=5, diffuse=0.6, metallic=True, specular=0.8,
                   roughness=1 / 100, reflection=0.65),
    'F_MetalE': _f(ambient=0.1, brilliance=6, diffuse=0.7, metallic=True, specular=0.8,
                   roughness=1 / 120, reflection=0.8),
    'Glossy': _f(specular=1.0, roughness=0.0001, reflection=0.13),
    'Luminous': _f(ambient=1.0, diffuse=0.0),
}
FINISH_NAMES = list(FINISHES)
# finishes that are not in the standard POV include files and must be declared in the .pov
CUSTOM_FINISH_POV = {
    'Speckled': 'finish { phong 0.4 phong_size 40 crand 0.3 }',
    'Plastic': 'finish { specular 0.6 roughness 0.02 phong 0.3 phong_size 60 }',
}

# --------------------------------------------------------------------------- textures
# pattern: None | ('granite', color_map) | ('brushed',) | ('waves',) | ('wrinkles',)
_CHROME_F = _f(ambient=0.3, diffuse=0.7, reflection=0.15, brilliance=8, specular=0.8, roughness=0.1)
TEXTURES = {
    'None': None,
    'Brass_Texture': dict(color=(0.71, 0.65, 0.26), finish='Metal'),
    'Gold_Texture': dict(color=(0.85, 0.85, 0.10), finish='Metal'),
    'Bronze_Texture': dict(color=(0.55, 0.47, 0.14), finish='Metal'),
    'Copper_Texture': dict(color=(0.72, 0.45, 0.20), finish='Metal'),
    'Silver_Texture': dict(color=(0.90, 0.91, 0.98), finish='Metal'),
    'Polished_Chrome': dict(color=(0.2, 0.2, 0.2),
                            finish=_f(ambient=0.1, diffuse=0.7, brilliance=6, reflection=0.6,
                                      phong=0.8, phong_size=120)),
    'Polished_Brass': dict(color=(0.578, 0.422, 0.195),
                           finish=_f(metallic=True, ambient=0.1, diffuse=0.8, brilliance=6,
                                     reflection=0.4, phong=0.8, phong_size=120)),
    'New_Brass': dict(color=(0.70, 0.56, 0.37),
                      finish=_f(ambient=0.35, diffuse=1.0, brilliance=15, phong=0.41, phong_size=5)),
    'Spun_Brass': dict(color=(0.70, 0.56, 0.37),
                       finish=_f(ambient=0.35, diffuse=1.0, brilliance=15, phong=0.41, phong_size=5),
                       pattern=('waves',)),
    'Brushed_Aluminum': dict(color=(0.658824, 0.658824, 0.658824), finish=_CHROME_F, pattern=('brushed',)),
    'Silver1': dict(color=(0.94, 0.93, 0.83), finish='SilverFinish'),
    'Silver2': dict(color=(0.94, 0.93, 0.86), finish='SilverFinish'),
    'Silver3': dict(color=(0.94, 0.93, 0.90), finish='SilverFinish'),
    'Brass_Valley': dict(color=(0.82, 0.57, 0.46),
                         finish=_f(metallic=True, brilliance=6, reflection=0.75, phong=0.75),
                         pattern=('granite', [(0.3, (0.82, 0.57, 0.46)), (0.3, (0, 0, 0)),
                                              (0.6, (0.85, 0.85, 0.95)), (0.6, (0.82, 0.57, 0.46)),
                                              (1.0, (0.85, 0.85, 0.95))])),
    'Rust': dict(color=(0.89, 0.51, 0.28), finish=_f(ambient=0.2, diffuse=0.4),
                 pattern=('granite', [(0.0, (0.89, 0.51, 0.28)), (0.4, (0.70, 0.13, 0.00)),
                                      (0.5, (0.69, 0.41, 0.08)), (0.6, (0.49, 0.31, 0.28)),
                                      (1.0, (0.89, 0.51, 0.28))])),
    'Rusty_Iron': dict(color=(0.42, 0.20, 0.20), finish=_f(ambient=0.2, diffuse=0.6),
                       pattern=('granite', [(0.0, (0.42, 0.20, 0.20)), (0.5, (0.50, 0.50, 0.02)),
                                            (0.6, (0.60, 0.20, 0.20)), (0.6, (0.30, 0.20, 0.20)),
                                            (1.0, (0.30, 0.20, 0.20))])),
    'Soft_Silver': dict(color=(0.94, 0.93, 0.83),
                        finish=_f(metallic=True, ambient=0.2, diffuse=0.35, specular=0.85,
                                  roughness=0.01, reflection=0.45, brilliance=1.5)),
    'New_Penny': dict(color=(0.6, 0.45, 0.4), finish='Metallic_Finish'),
    'Tinny_Brass': dict(color=(0.70, 0.56, 0.37), finish='Metallic_Finish'),
    'Gold_Nugget': dict(color=(0.5, 0.35, 0.25), finish='Metallic_Finish'),
    'Aluminum': dict(color=(0.55, 0.5, 0.45), finish='Metallic_Finish'),
    'Bright_Bronze': dict(color=(0.36, 0.28, 0.20), finish='Metallic_Finish'),
    'Chrome_Metal': dict(color=(0.658824, 0.658824, 0.658824), finish=_CHROME_F),
}
TEXTURE_NAMES = list(TEXTURES)

ELLIPSE_STYLES = ['PlainEllipse', 'BoundaryEllipse', 'CutoutEllipse']
ATOM_STYLES = ['ORTEP ellipsoids', 'Van der Waals', 'RMSD surface', 'Ball and Stick', 'Rods',
               'MSD surface', 'Line drawing (vector)', 'ORTEP-3 classic']
VECTOR_STYLES = ('Line drawing (vector)', 'ORTEP-3 classic')   # drawn as true vector paths

# --------------------------------------------------------------------------- defaults
# From the user's ORTEP-3 / POV-Ray texture block.
POV_ELEMENT_DEFAULTS = {
    'C': ('Gray20', 'Speckled'), 'H': ('White', 'Shiny'), 'D': ('White', 'Shiny'),
    'Fe': ('#ce28ce', 'Shiny'), 'Ti': ('#ce28ce', 'Shiny'), 'Zr': ('#ce28ce', 'Shiny'),
    'Cg': ('Gray50', 'Shiny'),
    'N': ('#005dff', 'Speckled'), 'O': ('Red', 'Speckled'), 'Ag': ('LightSteelBlue', 'Shiny'),
    'F': ('YellowGreen', 'Shiny'), 'B': ('Pink', 'Shiny'), 'P': ('BrightGold', 'Shiny'),
    'U': ('ForestGreen', 'Speckled'), 'K': ('DarkOrchid', 'Shiny'), 'I': ('Violet', 'Shiny'),
    'Si': ('Plum', 'Shiny'), 'Br': ('Scarlet', 'Shiny'), 'Cl': ('MediumSeaGreen', 'Shiny'),
    'Se': ('MediumSeaGreen', 'Shiny'), 'S': ('Yellow', 'Shiny'), 'Te': ('MediumWood', 'Shiny'),
}
OBJECT_TARGETS = {          # name -> (color, finish)
    'Bonds': ('#060606', 'Shiny'),
    'H bonds': ('White', 'Metal'),        # bonds to hydrogen
    'Equators': ('White', 'Shiny'),       # boundary ellipses
    'Cutout faces': ('SteelBlue', 'Shiny'),
}
NONMETALS = {'H', 'D', 'He', 'B', 'C', 'N', 'O', 'F', 'Ne', 'Si', 'P', 'S', 'Cl', 'Ar', 'Ge', 'As',
             'Se', 'Br', 'Kr', 'Sb', 'Te', 'I', 'Xe', 'At', 'Rn', 'Cg'}


def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return '#' + ''.join(f'{int(round(max(0, min(1, c)) * 255)):02x}' for c in rgb)


def color_rgb(c):
    """Color given as POV name, '#rrggbb' or rgb tuple -> rgb tuple (0-1)."""
    if isinstance(c, (tuple, list)):
        return tuple(float(x) for x in c)
    if c in POV_COLORS:
        return POV_COLORS[c]
    if isinstance(c, str) and c.startswith('#'):
        return hex_to_rgb(c)
    return (0.5, 0.5, 0.5)


def resolve_finish(f):
    return dict(FINISHES[f]) if isinstance(f, str) else dict(f)


class StyleTable:
    """Holds color / finish / texture / ellipse style per target.
    Targets: 'El:<sym>', 'Atom:<label>' (asymmetric-unit label, applies to symmetry copies),
    'Bonds', 'H bonds', 'Equators', 'Cutout faces'."""

    def __init__(self, preset='POV-Ray (ORTEP-3)'):
        self.entries = {}
        self.preset = preset
        self.apply_preset(preset)

    def apply_preset(self, preset):
        self.preset = preset
        keep_atoms = {k: v for k, v in self.entries.items() if k.startswith('Atom:')}
        self.entries = {}
        for name, (col, fin) in OBJECT_TARGETS.items():
            self.entries[name] = dict(color=col, finish=fin, texture='None')
        if preset == 'Monochrome':
            self.entries['Bonds'] = dict(color='White', finish='Dull', texture='None')
            self.entries['H bonds'] = dict(color='White', finish='Dull', texture='None')
            self.entries['Cutout faces'] = dict(color='Gray20', finish='Dull', texture='None')
        self.entries.update(keep_atoms)

    def element_entry(self, el):
        key = f'El:{el}'
        if key not in self.entries:
            if self.preset == 'Monochrome':
                col, fin = 'White', 'Dull'
            elif self.preset == 'Jmol / CPK':
                col, fin = element_color(el), 'Shiny'
            else:
                col, fin = POV_ELEMENT_DEFAULTS.get(el, (element_color(el), 'Shiny'))
            style = 'BoundaryEllipse' if el in NONMETALS else 'CutoutEllipse'
            self.entries[key] = dict(color=col, finish=fin, texture='None', ellipse=style)
        return self.entries[key]

    def atom_entry(self, label, el):
        """Effective entry for an atom (atom override on top of its element)."""
        e = dict(self.element_entry(el))
        e.update(self.entries.get(f'Atom:{label}', {}))
        return e

    def set(self, target, **kw):
        if target.startswith('El:'):
            self.element_entry(target[3:])
        ent = self.entries.setdefault(target, {})
        ent.update(kw)

    def get(self, target):
        if target.startswith('El:'):
            return self.element_entry(target[3:])
        return self.entries.get(target, {})

    def clear_atom_overrides(self):
        for k in [k for k in self.entries if k.startswith('Atom:')]:
            del self.entries[k]

    def material(self, entry):
        """Entry -> material dict(color rgb, finish dict, pattern) for the renderers."""
        tex = TEXTURES.get(entry.get('texture', 'None'))
        if tex:
            return dict(color=tex['color'], finish=resolve_finish(tex['finish']),
                        pattern=tex.get('pattern'), name=entry.get('texture'),
                        pov=dict(texture=entry.get('texture')))
        return dict(color=color_rgb(entry.get('color', 'Gray50')),
                    finish=resolve_finish(entry.get('finish', 'Shiny')), pattern=None, name=None,
                    pov=dict(texture=None, color=entry.get('color', 'Gray50'),
                             finish=entry.get('finish', 'Shiny')))

    def copy(self):
        return copy.deepcopy(self)
