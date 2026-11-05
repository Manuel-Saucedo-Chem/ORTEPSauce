"""All user-adjustable display settings in one place."""
from dataclasses import dataclass, field


@dataclass
class RenderSettings:
    # --- structure / content
    probability: float = 50.0          # ellipsoid probability level (%)
    show_h: bool = False
    show_q: bool = False
    q_count: int = 20
    show_cell: bool = False
    complete: bool = True               # complete molecules by symmetry
    bond_tol: float = 0.45              # Angstrom added to the sum of covalent radii
    # --- style
    atom_style: str = 'ORTEP ellipsoids'
    bond_coloring: str = 'Bond texture'     # 'Bond texture' or 'Split by atom'
    bond_radius: float = 0.060              # Angstrom
    hbond_radius: float = 0.035             # bonds to H
    h_radius: float = 0.150                 # fixed H sphere radius
    band_width: float = 0.06                # boundary-ellipse half width (fraction of semi-axis)
    ball_scale: float = 0.40                # ball radius = scale x covalent radius
    stick_radius: float = 0.10
    rod_radius: float = 0.14
    vdw_scale: float = 1.0
    # --- line drawing (vector) style
    octant: bool = True
    principal: bool = True
    bond_taper: float = 0.25
    line_width: float = 0.9
    # --- lighting / quality
    light_azimuth: float = -35.0            # degrees, negative = from the left
    light_elevation: float = 35.0
    fill_light: float = 0.35
    ambient_light: float = 1.6              # multiplies every finish's ambient
    outline: bool = False
    srgb: bool = True                       # sRGB output encoding, as POV-Ray 3.7
    antialias: int = 2                      # supersampling for still images
    drag_quality: str = 'Smooth (1/2 res)'  # preview while dragging, or 'Full quality'
    background: str = '#ffffff'
    # --- labels
    labels_on: bool = True
    label_which: str = 'Non-H'              # 'All', 'Non-H', 'Heavy atoms', 'Metals only'
    label_size: float = 16.0
    label_font: str = 'Arial'
    label_bold: bool = True
    label_italic: bool = True
    label_color: str = '#000000'
    label_offset: float = 0.10              # Angstrom beyond the atom surface
    label_halo: bool = True
    label_elem_color: bool = True           # element symbol in the atom color ('Fe' pink + '1')
    halo_width: float = 2.5                 # points
    sym_suffix: str = "*"
    hidden_labels: set = field(default_factory=set)   # display names hidden by the user
    label_offsets: dict = field(default_factory=dict)  # display name -> (dx, dy) screen Angstrom (Ctrl+drag)
    excluded: set = field(default_factory=set)         # asymmetric-unit labels not drawn
    hidden_keys: set = field(default_factory=set)      # single atoms hidden by right-click ('label|symop')
    # --- wire (thin-line) parts of the molecule
    wire: set = field(default_factory=set)             # asymmetric-unit labels drawn as thin wires
    wire_radius: float = 0.025                         # Angstrom
    wire_labels: bool = False                          # label wire atoms too
    # --- user edits (see edits.py)
    centroids: list = field(default_factory=list)      # [{'name': 'Cg1', 'members': [atom keys]}]
    deleted_bonds: set = field(default_factory=set)    # bond keys
    custom_bonds: dict = field(default_factory=dict)   # bond key -> {'style', 'width'}
    centroid_radius: float = 0.09                      # Angstrom
    # --- animation
    grain: bool = True                                 # crand grain of Speckled etc. (off for GIF frames)
