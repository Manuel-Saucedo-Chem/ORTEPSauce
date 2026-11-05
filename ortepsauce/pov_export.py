"""Write the current scene as a POV-Ray 3.7 scene file (.pov).

Coordinates are the rotated screen frame in Angstrom with z flipped (POV-Ray is left-handed),
seen by an orthographic camera, so the POV-Ray picture matches the on-screen view."""
import math

import numpy as np

from .raster import light_vectors
from .styles import CUSTOM_FINISH_POV, POV_COLORS

_FLIP = np.diag([1.0, 1.0, -1.0])


def _v(p):
    return f'<{p[0]:.5f}, {p[1]:.5f}, {-p[2]:.5f}>'


def _color(c):
    if isinstance(c, str) and c in POV_COLORS:
        return f'color {c}'
    if isinstance(c, str) and c.startswith('#'):
        h = c.lstrip('#')
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return f'color rgb <{r:.4f}, {g:.4f}, {b:.4f}>'
    r, g, b = c
    return f'color rgb <{r:.4f}, {g:.4f}, {b:.4f}>'


def _finish(f):
    if isinstance(f, str):
        return f
    keys = ['ambient', 'diffuse', 'brilliance', 'specular', 'roughness', 'phong', 'phong_size',
            'reflection', 'crand']
    parts = [f'{k} {f[k]:g}' for k in keys if k in f]
    if f.get('metallic'):
        parts.append('metallic')
    return ' '.join(parts)


def _texture_body(m):
    pov = m.get('pov')
    if pov and pov.get('texture'):
        return f'{pov["texture"]}'
    if pov:
        fin = pov['finish']
        fin_txt = f'finish {{ {fin} }}' if isinstance(fin, str) else f'finish {{ {_finish(fin)} }}'
        return f'pigment {{ {_color(pov["color"])} }} {fin_txt}'
    return f'pigment {{ {_color(m["color"])} }} finish {{ {_finish(m["finish"])} }}'


_OBJECT_NAMES = {'Bonds': 'Bond_Texture', 'H bonds': 'HBond_Texture',
                 'Equators': 'Equator_Texture', 'Cutout faces': 'Cutout_Texture'}


def write_pov(path, scene, settings, scale, aspect, pan=(0.0, 0.0), labels=None, image_height_in=6.0,
              title='', shadows=True, reflections=True):
    """labels: optional list of (text, x, y) in screen Angstrom to place as flat text objects."""
    s = settings
    names = []
    used = set()
    for mi, m in enumerate(scene.materials):
        key = m.get('key')
        if isinstance(key, str) and key in _OBJECT_NAMES:
            nm = _OBJECT_NAMES[key]
        elif m.get('pov_name'):
            nm = m['pov_name']
        else:
            nm = f'Texture_M{mi}'
        base, k = nm, 2
        while nm in used:
            nm = f'{base}_{k}'
            k += 1
        used.add(nm)
        names.append(nm)

    out = []
    w = out.append
    w(f'// ORTEPSauce POV-Ray scene {title}')
    w('// Render e.g.:  povray +W2400 +H1800 +A0.1 +FN scene.pov')
    w('#version 3.7;')
    w('#include "colors.inc"')
    w('#include "finish.inc"')
    w('#include "textures.inc"')
    w('#include "metals.inc"')
    a = s.ambient_light
    trace = '' if reflections else ' max_trace_level 1'
    w(f'global_settings {{ assumed_gamma 1.0 ambient_light rgb <{a:g}, {a:g}, {a:g}>{trace} }}')
    if not reflections:
        w('// reflections disabled (max_trace_level 1)')
    bg = s.background.lstrip('#')
    bgc = tuple(int(bg[i:i + 2], 16) / 255 for i in (0, 2, 4))
    w(f'background {{ color rgb <{bgc[0]:.4f}, {bgc[1]:.4f}, {bgc[2]:.4f}> }}')
    w('')
    w('// ---------------------------------------------------------------- camera / lights')
    h = 2 * scale
    w(f'camera {{ orthographic location <{pan[0]:.4f}, {pan[1]:.4f}, -1000> '
      f'look_at <{pan[0]:.4f}, {pan[1]:.4f}, 0> right x*{h * aspect:.5f} up y*{h:.5f} }}')
    for L, inten in light_vectors(s.light_azimuth, s.light_elevation, s.fill_light):
        p = np.array(L) * 1000
        w(f'light_source {{ <{p[0]:.2f}, {p[1]:.2f}, {-p[2]:.2f}> color rgb {inten:g} '
          f'parallel point_at <0, 0, 0>{"" if shadows else " shadowless"} }}')
    w('')
    w('// ---------------------------------------------------------------- finishes / sizes')
    for nm, body in CUSTOM_FINISH_POV.items():
        w(f'#ifndef ({nm}) #declare {nm} = {body} #end')
    w(f'#declare H_Radius         = {s.h_radius:.3f};   // Angstrom')
    w(f'#declare HBond_Radius     = {s.hbond_radius:.3f};')
    w(f'#declare Bond_Radius      = {s.bond_radius:.3f};')
    w(f'#declare Band_Width       = {s.band_width:.3f};   // boundary ellipse half width (fraction of axis)')
    w('#declare Band_Lift        = 0.004;')
    w('')
    w('// ---------------------------------------------------------------- textures')
    for nm, m in zip(names, scene.materials):
        w(f'#declare {nm:<18}= texture {{ {_texture_body(m)} }}')
    w('')
    w('// ---------------------------------------------------------------- ellipsoid styles (unit sphere)')
    w('#macro Plain_Ellipsoid(T) sphere { 0, 1 texture { T } } #end')
    w('#macro Boundary_Ellipsoid(T)')
    w('  union {')
    w('    sphere { 0, 1 texture { T } }')
    w('    intersection {')
    w('      sphere { 0, 1 + Band_Lift }')
    w('      union { box { <-Band_Width, -2, -2>, <Band_Width, 2, 2> }')
    w('              box { <-2, -Band_Width, -2>, <2, Band_Width, 2> }')
    w('              box { <-2, -2, -Band_Width>, <2, 2, Band_Width> } }')
    w('      texture { Equator_Texture } } }')
    w('#end')
    w('#macro Cutout_Ellipsoid(T, S)')
    w('  difference { Boundary_Ellipsoid(T) box { <0, 0, 0>, 1.1 * S texture { Cutout_Texture } } }')
    w('#end')
    w('')
    w('// ---------------------------------------------------------------- objects')
    for p in scene.prims:
        t = p['type']
        if t == 'ellipsoid':
            T = names[p['mat']]
            V = _FLIP @ p['V']
            aa = p['a']
            c = p['c']
            if p['style'] == 'PlainEllipse' and np.allclose(aa, aa[0]):
                w(f'sphere {{ {_v(c)}, {aa[0]:.5f} texture {{ {T} }} }}')
                continue
            mat = ', '.join(f'{V[r, col]:.6f}' for col in range(3) for r in range(3))
            if p['style'] == 'CutoutEllipse':
                sg = np.where(p['V'][2] >= 0, 1, -1)
                body = f'Cutout_Ellipsoid({T}, <{sg[0]}, {sg[1]}, {sg[2]}>)'
            elif p['style'] == 'BoundaryEllipse':
                body = f'Boundary_Ellipsoid({T})'
            else:
                body = f'Plain_Ellipsoid({T})'
            w(f'object {{ {body} scale <{aa[0]:.5f}, {aa[1]:.5f}, {aa[2]:.5f}> '
              f'matrix <{mat}, {c[0]:.5f}, {c[1]:.5f}, {-c[2]:.5f}> }}')
        elif t == 'cylinder':
            if np.linalg.norm(p['p1'] - p['p0']) < 1e-6:
                continue
            w(f'cylinder {{ {_v(p["p0"])}, {_v(p["p1"])}, {p["r"]:.4f} texture {{ {names[p["mat"]]} }} }}')
        elif t == 'surface':
            U = _FLIP @ p['U'] @ _FLIP
            q = (f'({U[0, 0]:.6f}*x*x + {U[1, 1]:.6f}*y*y + {U[2, 2]:.6f}*z*z + '
                 f'{2 * U[0, 1]:.6f}*x*y + {2 * U[0, 2]:.6f}*x*z + {2 * U[1, 2]:.6f}*y*z)'
                 f'/(x*x + y*y + z*z + 1e-9)')
            if p['kind'] == 'rmsd':
                fn = f'sqrt(x*x + y*y + z*z) - {p["k"]:.5f}*sqrt({q})'
            else:
                fn = f'sqrt(x*x + y*y + z*z) - {p["k"] / math.sqrt(p["ueq"]):.5f}*{q}'
            c = p['c']
            w(f'isosurface {{ function {{ {fn} }} contained_by {{ sphere {{ 0, {p["rmax"] * 1.05:.4f} }} }} '
              f'threshold 0 max_gradient 4 texture {{ {names[p["mat"]]} }} translate {_v(c)} }}')
    if labels:
        zfront = -(max([abs(p['c'][2]) for p in scene.prims if 'c' in p] + [5]) + 2)
        size = 2 * scale * s.label_size / (image_height_in * 72.0)
        font = 'timrom.ttf'
        w('')
        w('// ---------------------------------------------------------------- labels (flat text)')
        for text, x, y in labels:
            safe = text.replace('"', "'")
            w(f'text {{ ttf "{font}" "{safe}" 0.01, 0 pigment {{ color rgb 0 }} '
              f'finish {{ ambient 1 diffuse 0 }} scale {size:.4f} translate <{x:.4f}, {y:.4f}, {zfront:.3f}> }}')
    with open(path, 'w') as fh:
        fh.write('\n'.join(out) + '\n')
    return path


def write_ini(path, pov_path, width, height, antialias=True, threshold=0.3, output=None, alpha=False):
    """POV-Ray .ini with the render settings (defaults: 6400 x 4800, AA 0.3)."""
    lines = ['; ORTEPSauce render settings', f'Input_File_Name="{pov_path}"',
             f'Width={int(width)}', f'Height={int(height)}',
             f'Antialias={"On" if antialias else "Off"}', f'Antialias_Threshold={threshold:g}',
             'Output_File_Type=N', f'Output_Alpha={"On" if alpha else "Off"}']
    if output:
        lines.append(f'Output_File_Name="{output}"')
    with open(path, 'w') as fh:
        fh.write('\n'.join(lines) + '\n')
    return path


def run_povray(exe, pov_path, out_png, width, height, antialias=True, threshold=0.3, alpha=False,
               progress=None):
    """Render with POV-Ray. Windows pvengine runs its own window (no progress available);
    the console 'povray' reports progress on stderr."""
    import os
    import re
    import subprocess
    args = [f'+I{pov_path}', f'+O{out_png}', f'+W{int(width)}', f'+H{int(height)}', '+FN']
    args += [f'+A{threshold:g}'] if antialias else ['-A']
    if alpha:
        args.append('+UA')
    is_gui = 'pvengine' in os.path.basename(exe).lower()
    cwd = os.path.dirname(pov_path) or None
    if is_gui:
        cmd = [exe, '/EXIT', '/NR', '/RENDER', pov_path] + args[1:] + ['-D']
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        ok = os.path.exists(out_png)
        return ok, (r.stderr or r.stdout or '')[-400:]
    cmd = [exe] + args + ['-D', '+V']
    p = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, cwd=cwd)
    buf = b''
    tail = b''
    pat = re.compile(rb'Rendered (\d+) of (\d+) pixels')
    while True:
        chunk = p.stderr.read(256)
        if not chunk:
            break
        buf = (buf + chunk)[-4096:]
        tail = (tail + chunk)[-2000:]
        m = None
        for m in pat.finditer(buf):
            pass
        if m and progress:
            progress(int(m.group(1)) / max(int(m.group(2)), 1))
    p.wait()
    return p.returncode == 0 and os.path.exists(out_png), tail.decode(errors='replace')[-400:]
