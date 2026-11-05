"""Entry point:  python -m ortepsauce [file] [--export out.png|.tif|.svg|.pdf|.gif|.pov ...]"""
import argparse
import sys

from .styles import ATOM_STYLES


def cli():
    p = argparse.ArgumentParser(prog='ortepsauce', description='ORTEPSauce - ORTEP-style crystal structure viewer')
    p.add_argument('file', nargs='?', help='.cif, .ins or .res file')
    p.add_argument('--export', metavar='OUT',
                   help='render without the GUI; format from extension (png, tif, jpg, svg, pdf, gif, pov)')
    p.add_argument('--dpi', type=int, default=600)
    p.add_argument('--size', type=int, nargs=2, default=None, metavar=('W', 'H'),
                   help='size in pixels (default 6400 4800; GIF 1600 1200)')
    p.add_argument('--prob', type=float, default=50.0, help='ellipsoid probability in %% (default 50)')
    p.add_argument('--style', default='ORTEP ellipsoids', choices=ATOM_STYLES)
    p.add_argument('--preset', default='POV-Ray (ORTEP-3)', choices=['POV-Ray (ORTEP-3)', 'Jmol / CPK', 'Monochrome'])
    p.add_argument('--no-labels', action='store_true')
    p.add_argument('--no-h', action='store_true', help='hide hydrogen atoms')
    p.add_argument('--asym', action='store_true', help='do not complete molecules by symmetry')
    p.add_argument('--pack', action='store_true', help='fill the unit cell with complete molecules')
    p.add_argument('--block', type=int, default=0, help='CIF data block index (default 0)')
    p.add_argument('--frames', type=int, default=200, help='GIF frames (default 200)')
    p.add_argument('--opaque', action='store_true', help='solid background (default: transparent)')
    p.add_argument('--shadows', action='store_true', help='cast shadows in the final render')
    p.add_argument('--povray', metavar='EXE', help='render with POV-Ray (shadows + reflections) using this executable')
    p.add_argument('--no-aa', action='store_true', help='switch antialiasing off')
    a = p.parse_args()

    if a.export:
        if not a.file:
            p.error('--export needs an input file')
        from .gui_free import render_file
        render_file(a.file, a.export, dpi=a.dpi, size=a.size, prob=a.prob, labels=not a.no_labels,
                    show_h=not a.no_h, style=a.style, preset=a.preset, complete=not a.asym,
                    block=a.block, transparent=not a.opaque, frames=a.frames, shadows=a.shadows,
                    engine='POV-Ray' if a.povray else 'Built-in', povray_exe=a.povray, antialias=not a.no_aa, pack=a.pack,
                    progress=lambda f, m: print(f'\r{f:5.0%}  {m:<40}', end='', flush=True))
        print()
        print(f'Saved {a.export}')
        return
    from .gui import main
    main(a.file)


if __name__ == '__main__':
    sys.exit(cli())
