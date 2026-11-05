"""customtkinter GUI for the ORTEP viewer (tabs: Structure, Labels, View, Color, Styles, Export)."""
import math
import copy
import json
import os
import sys
from types import SimpleNamespace
import queue
import shutil
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from PIL import Image

from . import __version__
from .canvas_view import SceneView, display_name, label_visible
from .cif_reader import read_cif
from .colorpicker import LiveColorPicker
from .toast import Toaster
from .glview import GL_IMPORT_ERROR, GL_STYLES, GLMolView
from . import geometry_index as gi
from .edits import BOND_STYLES, BOND_WIDTHS, apply_edits, atom_key, bond_key, is_centroid
from .export import (DEFAULT_HEIGHT, DEFAULT_WIDTH, ExportCancelled, export_gif, export_image, export_pov,
                     spin_rotation)
from .model import Model, build_model
from .preview import material_preview
from .raster import render_scene
from .scene import build_scene
from .settings import RenderSettings
from .shelx_reader import read_shelx
from .si import caption as si_caption
from .si import identify_solvents, solvent_phrase
from .styles import (ATOM_STYLES, ELLIPSE_STYLES, FINISH_NAMES, OBJECT_TARGETS, POV_COLORS,
                     TEXTURE_NAMES, StyleTable, color_rgb, hex_to_rgb, rgb_to_hex)
from .view import default_orientation, fit_scale, orthonormalize, rot_x, rot_y, rot_z, view_along

PRESETS = ['POV-Ray (ORTEP-3)', 'Jmol / CPK', 'Monochrome']
SIZE_PRESETS = {'6400 × 4800 (default)': (6400, 4800), '3840 × 2160 (4K 16:9)': (3840, 2160),
                '4800 × 3600': (4800, 3600), '2400 × 1800': (2400, 1800), '1920 × 1080': (1920, 1080),
                'Window size': 'window'}
GIF_SIZE_PRESETS = {'1200 × 900': (1200, 900), '1600 × 1200 (default)': (1600, 1200),
                    '1920 × 1440': (1920, 1440), '2400 × 1800': (2400, 1800), '1920 × 1080 (16:9)': (1920, 1080)}
GIF_DEFAULT_PRESET = '1600 × 1200 (default)'
CONFIG_PATH = os.path.join(os.path.expanduser('~'), '.ortepsauce.json')


def _natkey(text):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', text)]


def load_config():
    for path in (CONFIG_PATH, os.path.join(os.path.expanduser('~'), '.ortepviewer.json')):   # old name
        try:
            with open(path) as fh:
                d = json.load(fh)
                return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            continue
    return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, 'w') as fh:
            json.dump(cfg, fh, indent=1)
    except OSError:
        pass
LABEL_FONTS = ['DejaVu Sans', 'Arial', 'Helvetica', 'Times New Roman', 'Calibri', 'Cambria',
               'Courier New', 'Segoe UI']
LABEL_COLORS = ['Black', 'Gray30', 'Gray50', 'White', 'Navy', 'MidnightBlue', 'Maroon', 'DarkGreen']
BACKGROUNDS = ['White', 'Black', 'Gray90', 'Gray75', 'Gray25', 'LightBlue', 'Wheat']


def load_structures(path):
    """Return list of (name, Structure)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.ins', '.res'):
        return [(os.path.basename(path), read_shelx(path))]
    if ext == '.cif':
        return read_cif(path)
    try:
        return read_cif(path)
    except Exception:  # noqa: BLE001
        return [(os.path.basename(path), read_shelx(path))]


def _thumb_model():
    """Two-atom model (O-N) used for the style thumbnails."""
    m = Model()
    m.labels, m.elements = ['O1', 'N1'], ['O', 'N']
    m.cart = np.array([[-0.85, 0.25, 0.0], [0.85, -0.25, 0.0]])
    rot = rot_z(0.6) @ rot_x(0.5)
    m.ucart = np.array([rot @ np.diag([0.060, 0.030, 0.022]) @ rot.T,
                        rot_x(-0.4) @ np.diag([0.028, 0.040, 0.025]) @ rot_x(0.4)])
    m.aniso = np.array([True, True])
    m.part = np.zeros(2, int)
    m.occ = np.ones(2)
    m.generated = np.zeros(2, bool)
    m.asym_index = np.arange(2)
    m.symop = ['', '']
    m.bonds = np.array([[0, 1]])
    return m


def find_povray():
    for name in ('povray', 'pvengine64', 'pvengine'):
        p = shutil.which(name)
        if p:
            return p
    for p in (r'C:\Program Files\POV-Ray\v3.7\bin\pvengine64.exe',
              r'C:\Program Files\POV-Ray\v3.7\bin\pvengine.exe',
              r'C:\Program Files\POV-Ray\v3.8\bin\pvengine64.exe'):
        if os.path.exists(p):
            return p
    return None


class OrtepApp(ctk.CTk):
    def __init__(self, path=None):
        super().__init__()
        ctk.set_appearance_mode('system')
        self.title(f'ORTEPSauce {__version__}')
        self.geometry('1400x900')
        self.minsize(1000, 650)

        self.s = RenderSettings()
        self.styles = StyleTable()
        self.blocks = []
        self.struct = None
        self.model = None
        self.path = None
        self.R = np.eye(3)
        self.center = np.zeros(3)
        self.scale = 10.0
        self.pan = np.zeros(2)
        self.selection = []
        self._drag = None
        self._pending = None          # None / 'fast' / 'final'
        self._final_job = None
        self.rot_speed = 0.5          # degrees per pixel
        self._ver = 0                 # view/state version: bumped by every change
        self._final_ver = -1          # version the latest full-quality render was started for
        self._results = queue.Queue()
        self._polling = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_canvas()
        self._build_tabs()
        self.status = ctk.CTkLabel(self, text='Open a .cif, .ins or .res file to begin (Ctrl+O).', anchor='w',
                                   font=ctk.CTkFont(family='Courier', size=13))
        self.status.grid(row=1, column=0, columnspan=2, sticky='ew', padx=10, pady=(0, 6))
        self.bottom = ctk.CTkFrame(self, fg_color='transparent')
        self.bottom.grid(row=1, column=1, sticky='e', padx=10, pady=(0, 6))
        self.progress = ctk.CTkProgressBar(self.bottom, width=320)
        self.progress.set(0)
        ctk.CTkButton(self.bottom, text='⌨ Hotkeys (F1)', width=120, command=self.show_hotkeys).pack(side='right')
        self.cancel_btn = ctk.CTkButton(self.bottom, text='✕ Cancel', width=80, fg_color='#a32020',
                                        command=self.cancel_job)
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.toaster = Toaster(self)
        self._exclude_mode = False
        self._wire_mode = False
        self._geo_mode = None
        self.geo_metal = None
        self.geo_ligands = []
        self.geo_highlight = []
        self._exclude_hist = []
        self.sel_bond = None
        self._hk_win = None
        self._ldrag = None
        self._box = None              # shift-drag selection rectangle (data coords)
        self.box_rect = None
        self._box_patch = None
        self._busy = False
        self._jobq = queue.Queue()
        self._undo, self._redo = [], []
        self._commit_job = None
        self._restoring = False
        self.cfg = load_config()
        self._factory = self._snapshot()                 # program defaults, before the user's own
        for name in self.TAB_SPEC:
            saved = (self.cfg.get('tab_defaults') or {}).get(name)
            if saved:
                self._apply_tab(name, saved, quiet=True)
        for v in list(self._state_vars().values()) + list(self.size_vars.values()):
            v.trace_add('write', self._note_change)
        self._committed = self._snapshot()
        # every mouse / key release ends one user action: store it as its own undo step
        self.bind_all('<ButtonRelease>', self._event_boundary, add='+')
        self.bind_all('<KeyRelease>', self._event_boundary, add='+')
        self._bind_hotkeys()
        if path:
            self.after(150, lambda: self.open_file(path))

    # ================================================================== undo / redo of every change
    UNDO_SKIP_VARS = {'block_var', 'ctarget_var', 'starget_var'}

    def _state_vars(self):
        return {k: v for k, v in vars(self).items()
                if isinstance(v, tk.Variable) and k not in self.UNDO_SKIP_VARS}

    def _snapshot(self):
        """Everything the user can change (not the orientation / zoom)."""
        return dict(s=copy.deepcopy(self.s), entries=copy.deepcopy(self.styles.entries),
                    preset=self.styles.preset, vars={k: v.get() for k, v in self._state_vars().items()},
                    sizes={k: v.get() for k, v in getattr(self, 'size_vars', {}).items()}, rot=self.rot_speed)

    def _note_change(self, *_):
        """Called by every redraw and every widget change: the state is compared (and an undo step
        stored) once things have been quiet for 0.4 s, so a slider drag is one step."""
        if getattr(self, '_restoring', True) or '_committed' not in self.__dict__:
            return
        if self._commit_job is not None:
            self.after_cancel(self._commit_job)
        self._commit_job = self.after(400, self._commit)

    def _event_boundary(self, e=None):
        if self._restoring:
            return
        try:
            typing = isinstance(self.focus_get(), (tk.Entry, tk.Text)) and e is not None and \
                str(e.type) in ('KeyRelease', '3')
        except (KeyError, tk.TclError):
            typing = False
        if typing:
            self._note_change()                  # typing: one step per pause, not per letter
        else:
            self.after_idle(self._flush_or_commit)

    def _flush_or_commit(self):
        if self._commit_job is not None:
            self.after_cancel(self._commit_job)
        self._commit()

    def _commit(self):
        self._commit_job = None
        if self._restoring:
            return
        cur = self._snapshot()
        if cur != self._committed:
            self._undo.append(self._committed)
            del self._undo[:-200]
            self._redo.clear()
            self._committed = cur

    def _flush_change(self):
        if self._commit_job is not None:
            self.after_cancel(self._commit_job)
            self._commit()

    def undo(self):
        self._flush_change()
        if not self._undo:
            self.toast('Nothing to undo')
            return
        self._redo.append(self._committed)
        self._apply_snapshot(self._undo.pop())
        self.toast('Undo', 'info')

    def redo(self):
        self._flush_change()
        if not self._redo:
            self.toast('Nothing to redo')
            return
        self._undo.append(self._committed)
        self._apply_snapshot(self._redo.pop())
        self.toast('Redo', 'info')

    def undo_exclude(self):                 # older name, kept for buttons / callers
        self.undo()

    def _reset_history(self):
        if self._commit_job is not None:
            self.after_cancel(self._commit_job)
            self._commit_job = None
        self._undo, self._redo = [], []
        self._committed = self._snapshot()

    def _struct_key(self):
        s = self.s
        return (self.grow_var.get(), self.tol_var.get(), self.pack_var.get(), repr(s.centroids),
                repr(sorted(s.custom_bonds.items())), repr(sorted(s.deleted_bonds)))

    def _sync_sliders(self):
        for key, (sl, val, fmt) in getattr(self, '_sliders', {}).items():
            v = self.rot_speed if key == 'rot_speed' else getattr(self.s, key)
            sl.set(v)
            val.configure(text=fmt.format(float(v)))

    def _apply_snapshot(self, st):
        old_key = self._struct_key()
        self._restoring = True
        try:
            self.s = copy.deepcopy(st['s'])
            self.styles.entries = copy.deepcopy(st['entries'])
            self.styles.preset = st['preset']
            sv = self._state_vars()
            for k, v in st['vars'].items():
                if k in sv and sv[k].get() != v:
                    sv[k].set(v)
            for k, v in st['sizes'].items():
                if k in self.size_vars:
                    self.size_vars[k].set(v)
            self.rot_speed = st['rot']
            self._sync_sliders()
            self._reapply(structural=old_key != self._struct_key())
        finally:
            self._restoring = False
        self._committed = self._snapshot()

    def _reapply(self, structural=False):
        """Bring picture and panels in line with self.s / styles / widget values."""
        if self.gl is not None:
            self.gl.dirty = True
        self.fig.set_facecolor(self.s.background)
        if structural and self.struct is not None:
            self.rebuild()
        else:
            self.on_setting()
        self.on_labels()
        self.on_wire_options()
        self._show_view()
        self._highlight_style()
        self._after_exclusion()
        self._after_wire()
        self._edits_note()
        self._engine_changed()
        try:
            self.on_color_target()
            self.on_style_target()
        except Exception:  # noqa: BLE001 - target lists not filled yet (no structure)
            pass
        self.request_redraw()
        self.update_si()

    # ================================================================== per-tab defaults
    TAB_SPEC = {
        'Structure': dict(vars=['grow_var', 'h_var', 'cell_var', 'pack_var', 'wire_lab_var', 'tol_var', 'q_var',
                                'qn_var', 'wire_r_var', 'cg_r_var'],
                          s=['show_h', 'show_cell', 'show_q', 'q_count', 'wire_labels', 'wire_radius',
                             'centroid_radius']),
        'Labels': dict(vars=['lab_on', 'lab_which', 'lab_font', 'lab_size', 'lab_bold', 'lab_italic', 'lab_color',
                             'lab_halo', 'lab_elem', 'lab_suffix'],
                       s=['labels_on', 'label_which', 'label_font', 'label_size', 'label_bold', 'label_italic',
                          'label_color', 'label_halo', 'label_elem_color', 'label_offset', 'sym_suffix']),
        'View': dict(vars=['outline_var', 'step_var', 'dragq_var', 'srgb_var'],
                     s=['light_azimuth', 'light_elevation', 'fill_light', 'ambient_light', 'outline', 'srgb',
                        'drag_quality'], rot=True),
        'Color': dict(vars=['preset_var', 'bondcol_var', 'bg_var'], s=['background', 'bond_coloring'],
                      style_fields=['color', 'texture']),
        'Styles': dict(vars=['prob_var'], s=['atom_style', 'probability', 'bond_radius', 'hbond_radius', 'h_radius',
                                             'band_width', 'ball_scale', 'stick_radius', 'rod_radius', 'vdw_scale'],
                       sizes=True, style_fields=['ellipse', 'finish']),
        'Export': dict(vars=['size_preset', 'dpi_var', 'shadow_var', 'trans_var', 'gif_size', 'gif_axis', 'gif_dir',
                             'gif_shadow', 'gif_trans', 'gif_matte', 'w_px', 'h_px', 'aa_var', 'engine_var', 'refl_var',
                             'lsize_mode', 'gif_frames', 'gif_deg', 'gif_delay', 'gif_w', 'gif_h', 'gif_grain',
                             'pov_labels'], s=[]),
        'SI': dict(vars=['si_fig', 'si_auto', 'si_merge', 'si_solv', 'geo_caption'], s=[]),
    }

    def _tab_state(self, name):
        """Current values of one tab, as plain JSON-friendly data."""
        spec = self.TAB_SPEC[name]
        d = dict(vars={k: getattr(self, k).get() for k in spec['vars']},
                 s={k: getattr(self.s, k) for k in spec['s']})
        if spec.get('rot'):
            d['rot'] = self.rot_speed
        if spec.get('sizes'):
            d['sizes'] = {k: v.get() for k, v in self.size_vars.items()}
        if spec.get('style_fields'):
            d['styles'] = {k: {f: v[f] for f in spec['style_fields'] if f in v}
                           for k, v in self.styles.entries.items() if not k.startswith('Atom:')}
            d['preset'] = self.styles.preset
        return d

    def _apply_tab(self, name, d, quiet=False, factory=False):
        spec = self.TAB_SPEC[name]
        if not quiet:
            self._flush_change()                  # the previous change stays its own undo step
        old_key = self._struct_key()
        self._restoring = True
        try:
            for k, v in (d.get('vars') or {}).items():
                if k in spec['vars']:
                    getattr(self, k).set(v)
            for k, v in (d.get('s') or {}).items():
                if k in spec['s']:
                    setattr(self.s, k, v)
            if 'rot' in d:
                self.rot_speed = float(d['rot'])
            for k, v in (d.get('sizes') or {}).items():
                if k in self.size_vars:
                    self.size_vars[k].set(v)
                    try:
                        setattr(self.s, k, float(v))
                    except ValueError:
                        pass
            fields = spec.get('style_fields')
            if fields:
                if factory:                  # program colors / finishes for every element and object
                    fresh = StyleTable(d.get('preset', 'POV-Ray (ORTEP-3)'))
                    for k in list(self.styles.entries):
                        if k.startswith('Atom:'):
                            for f in fields:
                                self.styles.entries[k].pop(f, None)
                        else:
                            base = fresh.get(k)
                            for f in fields:
                                if f in base:
                                    self.styles.entries[k][f] = base[f]
                else:
                    for k, v in (d.get('styles') or {}).items():
                        self.styles.entries.setdefault(k, {}).update(v)
                        if k.startswith('El:'):
                            self.styles.element_entry(k[3:])
                if d.get('preset'):
                    self.styles.preset = d['preset']
            self._sync_sliders()
            self.fig.set_facecolor(self.s.background)
            if not quiet:
                self._reapply(structural=old_key != self._struct_key())
        finally:
            self._restoring = False
        if not quiet:
            self._note_change()

    def _defaults_row(self, tab, name):
        fr = ctk.CTkFrame(tab, fg_color='transparent')
        fr.pack(fill='x', side='bottom', padx=4, pady=(2, 4))
        ctk.CTkButton(fr, text='↺ Reset tab to defaults', width=40, fg_color='gray45', hover_color='gray35',
                      command=lambda: self.reset_tab(name)).pack(side='left', expand=True, fill='x', padx=(0, 2))
        ctk.CTkButton(fr, text='★ Save tab as default', width=40, fg_color='gray45', hover_color='gray35',
                      command=lambda: self.save_tab_default(name)).pack(side='left', expand=True, fill='x', padx=(2, 0))

    def reset_tab(self, name):
        saved = (self.cfg.get('tab_defaults') or {}).get(name)
        if saved:
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label='My saved defaults', command=lambda: self._reset_to(name, saved))
            menu.add_command(label='Program defaults', command=lambda: self._reset_to(name, None))
            menu.add_separator()
            menu.add_command(label='Forget my saved defaults for this tab', command=lambda: self.forget_tab_default(name))
            x, y = self.winfo_pointerxy()
            try:
                menu.tk_popup(x, y)
            finally:
                menu.grab_release()
        else:
            self._reset_to(name, None)

    def _reset_to(self, name, saved):
        if saved is None:
            spec = self.TAB_SPEC[name]
            f = self._factory
            d = dict(vars={k: f['vars'][k] for k in spec['vars'] if k in f['vars']},
                     s={k: getattr(f['s'], k) for k in spec['s']}, rot=f['rot'], sizes=f['sizes'],
                     preset='POV-Ray (ORTEP-3)')
            if not spec.get('rot'):
                d.pop('rot')
            self._apply_tab(name, d, factory=True)
            self.toast(f'{name}: program defaults restored  (Ctrl+Z to undo)', 'ok')
        else:
            self._apply_tab(name, saved)
            self.toast(f'{name}: your saved defaults restored  (Ctrl+Z to undo)', 'ok')

    def save_tab_default(self, name):
        self.cfg.setdefault('tab_defaults', {})[name] = self._tab_state(name)
        save_config(self.cfg)
        self.toast(f'{name}: current settings saved as your default (used at every start)', 'ok')

    def forget_tab_default(self, name):
        (self.cfg.get('tab_defaults') or {}).pop(name, None)
        save_config(self.cfg)
        self.toast(f'{name}: back to the program defaults at start')

    # ================================================================== widgets helpers
    def _scroll_tab(self, name):
        f = ctk.CTkScrollableFrame(self.tabs.tab(name), fg_color='transparent')
        f.pack(fill='both', expand=True)
        return f

    @staticmethod
    def _section(parent, text):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=14, weight='bold'),
                     anchor='w').pack(fill='x', padx=6, pady=(12, 3))

    @staticmethod
    def _row(parent, label, factory, label_width=125):
        fr = ctk.CTkFrame(parent, fg_color='transparent')
        fr.pack(fill='x', padx=6, pady=2)
        ctk.CTkLabel(fr, text=label, anchor='w', width=label_width).pack(side='left')
        w = factory(fr)
        w.pack(side='right', fill='x', expand=True)
        return w

    def _option(self, parent, label, var, values, cmd):
        return self._row(parent, label, lambda p: ctk.CTkOptionMenu(p, variable=var, values=values,
                                                                     command=lambda _: cmd()))

    @staticmethod
    def _switch(parent, text, var, cmd):
        sw = ctk.CTkSwitch(parent, text=text, variable=var, command=cmd)
        sw.pack(anchor='w', padx=6, pady=3)
        return sw

    def _entry(self, parent, label, var, cmd, width=80):
        e = self._row(parent, label, lambda p: ctk.CTkEntry(p, textvariable=var, width=width))
        e.bind('<Return>', lambda ev: cmd())
        e.bind('<FocusOut>', lambda ev: cmd())
        return e

    def _slider(self, parent, label, lo, hi, value, cmd, fmt='{:.0f}', steps=None, key=None):
        fr = ctk.CTkFrame(parent, fg_color='transparent')
        fr.pack(fill='x', padx=6, pady=2)
        ctk.CTkLabel(fr, text=label, anchor='w', width=110).pack(side='left')
        val = ctk.CTkLabel(fr, text=fmt.format(value), width=42)
        val.pack(side='right')

        def changed(v):
            val.configure(text=fmt.format(float(v)))
            cmd(float(v))
        sl = ctk.CTkSlider(fr, from_=lo, to=hi, number_of_steps=steps, command=changed)
        sl.set(value)
        sl.pack(side='right', fill='x', expand=True, padx=4)
        if key:
            self.__dict__.setdefault('_sliders', {})[key] = (sl, val, fmt)
        return sl

    @staticmethod
    def _listbox(parent, label, items, height, cmd):
        ctk.CTkLabel(parent, text=label, anchor='w').pack(fill='x', padx=6, pady=(6, 0))
        fr = tk.Frame(parent)
        fr.pack(fill='x', padx=6, pady=2)
        lb = tk.Listbox(fr, height=height, exportselection=False, activestyle='none',
                        font=('Segoe UI', 10), selectbackground='#1f6aa5', selectforeground='white')
        sb = tk.Scrollbar(fr, orient='vertical', command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side='left', fill='x', expand=True)
        sb.pack(side='right', fill='y')
        for it in items:
            lb.insert('end', it)
        lb.bind('<<ListboxSelect>>', lambda e: cmd(lb))
        return lb

    @staticmethod
    def _button(parent, text, cmd):
        b = ctk.CTkButton(parent, text=text, command=cmd)
        b.pack(fill='x', padx=6, pady=3)
        return b

    @staticmethod
    def _button_row(parent, items):
        fr = ctk.CTkFrame(parent, fg_color='transparent')
        fr.pack(fill='x', padx=6, pady=3)
        out = []
        for k, (text, cmd) in enumerate(items):
            b = ctk.CTkButton(fr, text=text, command=cmd, width=40)
            b.pack(side='left', expand=True, fill='x', padx=(0 if k == 0 else 2, 0))
            out.append(b)
        return out

    @staticmethod
    def _note(parent, text):
        lbl = ctk.CTkLabel(parent, text=text, anchor='w', wraplength=290, justify='left',
                           text_color=('gray30', 'gray70'))
        lbl.pack(fill='x', padx=6)
        return lbl

    def _collapsible(self, parent, title, opened=False):
        """Section folded away by default (rarely needed settings)."""
        state = {'open': False}
        btn = ctk.CTkButton(parent, text='▸ ' + title, anchor='w', fg_color='transparent',
                            text_color=('gray10', 'gray90'), hover_color=('gray80', 'gray25'),
                            font=ctk.CTkFont(size=14, weight='bold'))
        btn.pack(fill='x', padx=2, pady=(16, 2))
        body = ctk.CTkFrame(parent, fg_color=('gray90', 'gray18'))

        def toggle():
            state['open'] = not state['open']
            if state['open']:
                body.pack(fill='x', padx=4, pady=(0, 8), after=btn)
            else:
                body.pack_forget()
            btn.configure(text=('▾ ' if state['open'] else '▸ ') + title)
        btn.configure(command=toggle)
        if opened:
            toggle()
        return body

    def _dialog(self, title, geometry=None):
        """Toplevel that stays in front of the main window (transient) and gets the focus."""
        w = ctk.CTkToplevel(self)
        w.title(title)
        if geometry:
            w.geometry(geometry)
        w.transient(self)

        def front():
            try:
                w.lift()
                w.focus_force()
            except tk.TclError:
                pass
        w.after(60, front)
        w.after(300, front)          # CTkToplevel on Windows may be pushed back once after creation
        return w

    # ================================================================== canvas
    def _build_canvas(self):
        self.fig = Figure(figsize=(8, 6), dpi=100, facecolor=self.s.background)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_axis_off()
        self.view = SceneView(self.ax)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().grid(row=0, column=1, sticky='nsew', padx=(4, 8), pady=8)
        c = self.canvas
        c.mpl_connect('button_press_event', self.on_press)
        c.mpl_connect('motion_notify_event', self.on_motion)
        c.mpl_connect('button_release_event', self.on_release)
        c.mpl_connect('scroll_event', self.on_scroll)
        c.mpl_connect('key_press_event', self.on_key)
        c.mpl_connect('resize_event', lambda e: self.request_redraw())
        self.canvas.draw()
        self.gl = None
        self._gl_pending = False
        if GL_IMPORT_ERROR is None and not os.environ.get('ORTEPSAUCE_NO_GL'):
            try:
                self.gl = GLMolView(self, self, width=800, height=600)
                g = self.gl
                g.bind('<ButtonPress>', self._gl_press)
                g.bind('<Motion>', lambda e: self.on_motion(self._gl_ev(e)))
                g.bind('<ButtonRelease>', lambda e: self.on_release(self._gl_ev(e)) if e.num in (1, 2, 3) else None)
                g.bind('<MouseWheel>', lambda e: self.on_scroll(SimpleNamespace(button='up' if e.delta > 0 else 'down')))
                g.bind('<Key>', self._gl_key)
                g.bind('<Configure>', lambda e: self.request_redraw(), add='+')
            except Exception as e:  # noqa: BLE001
                self.gl = None
                self._gl_error = str(e)
        self._show_view()

    # ---- GPU view helpers
    def _gl_active(self):
        return self.gl is not None and self.gl.failed is None and self.s.atom_style in GL_STYLES

    def _show_view(self):
        mpl_w = self.canvas.get_tk_widget()
        if self._gl_active():
            mpl_w.grid_remove()
            self.gl.grid(row=0, column=1, sticky='nsew', padx=(4, 8), pady=8)
        else:
            if self.gl is not None:
                self.gl.grid_remove()
            mpl_w.grid(row=0, column=1, sticky='nsew', padx=(4, 8), pady=8)

    def gl_failed(self, msg):
        self.status.configure(text=f'OpenGL unavailable ({msg[:80]}) - using the software renderer.')
        self._show_view()
        self.request_redraw()

    def _active_view(self):
        return self.gl if self._gl_active() else self.view

    def _gl_ev(self, e):
        H = max(self.gl.winfo_height(), 1)
        xd, yd = self.gl.px_to_data(e.x, e.y)
        alt = 0x20000 if sys.platform == 'win32' else 0x0008
        key = 'control' if (e.state & 0x0004) else ('shift' if (e.state & 0x0001) else
                                                     ('alt' if (e.state & alt) else None))
        return SimpleNamespace(x=e.x, y=H - e.y, button=getattr(e, 'num', None), key=key, xdata=xd, ydata=yd)

    def _gl_press(self, e):
        if e.num in (4, 5):                       # X11 mouse wheel
            self.on_scroll(SimpleNamespace(button='up' if e.num == 4 else 'down'))
            return
        self.on_press(self._gl_ev(e))

    def _gl_key(self, e):
        keys = {'Left': 'left', 'Right': 'right', 'Up': 'up', 'Down': 'down', 'Escape': 'escape',
                'plus': '+', 'equal': '=', 'minus': '-', 'KP_Add': '+', 'KP_Subtract': '-'}
        k = keys.get(e.keysym)
        if k:
            self.on_key(SimpleNamespace(key=k))

    def _gl_refresh(self):
        self._gl_pending = False
        if self._gl_active():
            self.gl.refresh()

    def screen_dpi(self):
        """Pixels per inch used for on-screen label sizes (same rule as matplotlib's Tk backend)."""
        try:
            if sys.platform == 'win32':
                ratio = round(float(self.tk.call('tk', 'scaling')) / (96 / 72), 2)
            elif sys.platform.startswith('linux'):
                ratio = self.winfo_fpixels('1i') / 96
            else:
                ratio = 1.0
        except Exception:  # noqa: BLE001
            ratio = 1.0
        return 100.0 * ratio

    def _canvas_px(self):
        if self._gl_active():
            return max(self.gl.winfo_width(), 2), max(self.gl.winfo_height(), 2)
        return max(int(self.fig.bbox.width), 2), max(int(self.fig.bbox.height), 2)

    # ================================================================== tabs
    def _build_tabs(self):
        self.tabs = ctk.CTkTabview(self, width=360)
        self.tabs.grid(row=0, column=0, sticky='nsw', padx=(8, 4), pady=(0, 8))
        for name in ('Structure', 'Labels', 'View', 'Color', 'Styles', 'Export', 'SI'):
            self.tabs.add(name)
        self._tab_structure(self._scroll_tab('Structure'))
        self._tab_labels(self._scroll_tab('Labels'))
        self._tab_view(self._scroll_tab('View'))
        self._tab_color(self._scroll_tab('Color'))
        self._tab_styles(self._scroll_tab('Styles'))
        self._tab_export(self._scroll_tab('Export'))
        self._tab_si(self._scroll_tab('SI'))
        for name in self.TAB_SPEC:
            self._defaults_row(self.tabs.tab(name), name)

    # ------------------------------------------------------------------ Structure
    def _tab_structure(self, t):
        ctk.CTkButton(t, text='Open structure…  Ctrl+O', command=self.ask_open).pack(fill='x', padx=6, pady=(6, 4))
        self.file_lbl = ctk.CTkLabel(t, text='(no file)', anchor='w', wraplength=290, justify='left')
        self.file_lbl.pack(fill='x', padx=6)
        self.block_var = tk.StringVar(value='')
        self.block_menu = ctk.CTkOptionMenu(t, variable=self.block_var, values=[''],
                                            command=lambda _: self.select_block())
        self._section(t, 'Show')
        self.grow_var = tk.BooleanVar(value=True)
        self._switch(t, 'Complete molecules (symmetry)', self.grow_var, self.rebuild)
        self.h_var = tk.BooleanVar(value=self.s.show_h)
        self._switch(t, 'Hydrogen atoms', self.h_var, self.on_setting)
        self.cell_var = tk.BooleanVar(value=False)
        self._switch(t, 'Unit cell', self.cell_var, self.on_setting)
        self.pack_var = tk.BooleanVar(value=False)
        self._switch(t, 'Pack unit cell', self.pack_var, self.on_pack)

        self._section(t, 'Exclude atoms')
        self.excl_btn = self._button(t, 'Exclude atoms (click)  Ctrl+E', self.toggle_exclude)
        self._button_row(t, [('By name…', self.exclude_by_name), ('Solvent', self.exclude_solvent),
                             ('Restore all', self.restore_excluded)])
        self.excl_lbl = self._note(t, 'No atoms excluded.')

        self._section(t, 'Wire (thin lines)')
        self.wire_btn = self._button(t, 'Wire / unwire selected  Ctrl+W', self.wire_toggle_selected)
        self._button_row(t, [('By name…', self.wire_by_name), ('All but selected', self.wire_all_but_selected),
                             ('Clear', self.clear_wire)])
        self.wire_lab_var = tk.BooleanVar(value=self.s.wire_labels)
        self._switch(t, 'Labels on wire atoms', self.wire_lab_var, self.on_wire_options)
        self.wire_lbl = self._note(t, 'No wire atoms.')

        self._section(t, 'Centroids & bonds')
        self._button_row(t, [('Centroid  C', self.add_centroid), ('Bond…  Ctrl+B', self.bond_dialog)])
        self._button_row(t, [('Delete bond  Del', self.delete_selected_bond),
                             ('Restore bonds', self.restore_bonds)])
        self.edit_lbl = self._note(t, 'Select ring atoms and press C for a centroid. Click a bond and press '
                                      'Delete to remove it. Select 2+ atoms (metal first) and press Ctrl+B to '
                                      'draw solid, dashed or dotted bonds.')

        self._section(t, 'Structure info')
        self.info = ctk.CTkTextbox(t, height=200, wrap='word', font=ctk.CTkFont(family='Courier', size=12))
        self.info.pack(fill='x', padx=6, pady=(0, 8))
        self.info.configure(state='disabled')

        adv = self._collapsible(t, 'Advanced')
        self.tol_var = tk.StringVar(value='0.45')
        self._entry(adv, 'Bond tolerance (Å)', self.tol_var, self.rebuild)
        self.q_var = tk.BooleanVar(value=False)
        self.q_switch = self._switch(adv, 'Q-peaks (.res)', self.q_var, self.on_setting)
        self.qn_var = tk.StringVar(value='20')
        self._entry(adv, 'Strongest Q shown', self.qn_var, self.on_setting)
        self.wire_r_var = tk.StringVar(value=f'{self.s.wire_radius:g}')
        self._entry(adv, 'Wire radius (Å)', self.wire_r_var, self.on_wire_options)
        self.cg_r_var = tk.StringVar(value=f'{self.s.centroid_radius:g}')
        self._entry(adv, 'Centroid radius (Å)', self.cg_r_var, self.on_wire_options)
        self._button(adv, 'Wire atoms by clicking (mode)', self.toggle_wire_mode)
        self._button(adv, 'Remove all centroids and drawn bonds', self.clear_edits)

    # ------------------------------------------------------------------ Labels
    def _tab_labels(self, t):
        s = self.s
        self.lab_on = tk.BooleanVar(value=s.labels_on)
        sw = ctk.CTkSwitch(t, text='Show labels', variable=self.lab_on, command=self.on_labels,
                           font=ctk.CTkFont(size=14, weight='bold'))
        sw.pack(anchor='w', padx=6, pady=(10, 6))
        self.lab_which = tk.StringVar(value=s.label_which)
        self._option(t, 'Label atoms', self.lab_which, ['All', 'Non-H', 'Heavy atoms', 'Metals only'],
                     self.on_labels)
        self._section(t, 'Font')
        self.lab_font = tk.StringVar(value=s.label_font)
        self._option(t, 'Font', self.lab_font, LABEL_FONTS, self.on_labels)
        self.lab_size = tk.StringVar(value=str(int(s.label_size)))
        cb = self._row(t, 'Size (pt)', lambda p: ctk.CTkComboBox(
            p, variable=self.lab_size, command=lambda _: self.on_labels(),
            values=['6', '8', '10', '12', '14', '16', '18', '20', '24', '28', '32', '40', '48', '64', '72', '96']))
        cb.bind('<Return>', lambda e: self.on_labels())
        cb.bind('<FocusOut>', lambda e: self.on_labels())
        self.lab_size_box = cb
        self.lab_bold = tk.BooleanVar(value=s.label_bold)
        self._switch(t, 'Bold', self.lab_bold, self.on_labels)
        self.lab_italic = tk.BooleanVar(value=s.label_italic)
        self._switch(t, 'Italic', self.lab_italic, self.on_labels)
        self.lab_color = tk.StringVar(value='Black')
        self._option(t, 'Color', self.lab_color, LABEL_COLORS + ['Custom…'], self.on_label_color)
        self.lab_halo = tk.BooleanVar(value=s.label_halo)
        self._switch(t, 'Background halo', self.lab_halo, self.on_labels)
        self.lab_elem = tk.BooleanVar(value=self.s.label_elem_color)
        self._switch(t, 'Element symbol in atom color (Fe1)', self.lab_elem, self.on_labels)
        self._slider(t, 'Offset (Å)', 0.0, 0.8, s.label_offset, self._set_label_offset, '{:.2f}', 32,
                     key='label_offset')
        self.lab_suffix = tk.StringVar(value=s.sym_suffix)
        self._entry(t, 'Symmetry suffix', self.lab_suffix, self.on_labels, width=60)
        self._section(t, 'Individual labels')
        ctk.CTkLabel(t, text='Click atoms in the picture to select them, then:', anchor='w',
                     wraplength=290, justify='left').pack(fill='x', padx=6)
        ctk.CTkButton(t, text='Hide labels of selected atoms', command=self.hide_selected_labels
                      ).pack(fill='x', padx=6, pady=3)
        ctk.CTkButton(t, text='Show only selected atoms’ labels', command=self.only_selected_labels
                      ).pack(fill='x', padx=6, pady=3)
        ctk.CTkButton(t, text='Restore all labels', command=self.restore_labels).pack(fill='x', padx=6, pady=3)
        self._section(t, 'Label positions')
        ctk.CTkLabel(t, text='Ctrl + drag a label in the picture to move it.', anchor='w', wraplength=290,
                     justify='left').pack(fill='x', padx=6)
        ctk.CTkButton(t, text='Reset label positions', command=self.reset_label_positions).pack(fill='x', padx=6, pady=3)

    def _set_label_offset(self, v):
        self.s.label_offset = v
        self.redraw_overlay()

    def on_label_color(self):
        v = self.lab_color.get()
        if v == 'Custom…':
            prev = self.s.label_color

            def live(hx):
                self.s.label_color = hx
                self.redraw_overlay()

            def close(hx):
                live(hx or prev)
            init = prev if prev.startswith('#') else rgb_to_hex(color_rgb(prev))
            self._open_picker('Label color', init, live, close)
            return
        else:
            self.s.label_color = v
        self.redraw_overlay()

    def on_labels(self):
        s = self.s
        s.labels_on = self.lab_on.get()
        s.label_which = self.lab_which.get()
        s.label_font = self.lab_font.get()
        try:
            size = float(self.lab_size.get().replace(',', '.').replace('pt', '').strip())
            if not 1 <= size <= 500:
                raise ValueError
            s.label_size = size
        except ValueError:
            self.toast('Label size: type a number between 1 and 500', 'warn')
            self.lab_size.set(f'{s.label_size:g}')
        s.label_bold = self.lab_bold.get()
        s.label_italic = self.lab_italic.get()
        s.label_halo = self.lab_halo.get()
        s.label_elem_color = self.lab_elem.get()
        new_suffix = self.lab_suffix.get()
        if new_suffix != s.sym_suffix and self.model is not None:
            # hidden / moved labels are stored by displayed name: keep them for symmetry atoms
            ren = {self.model.labels[i] + s.sym_suffix: self.model.labels[i] + new_suffix
                   for i in range(self.model.n) if self.model.generated[i]}
            s.hidden_labels = {ren.get(n, n) for n in s.hidden_labels}
            s.label_offsets = {ren.get(n, n): v for n, v in s.label_offsets.items()}
        s.sym_suffix = new_suffix
        self.update_si()
        self.redraw_overlay()

    def hide_selected_labels(self):
        if self.model is None:
            return
        for i in self.selection:
            self.s.hidden_labels.add(display_name(self.model, i, self.s))
        self.redraw_overlay()
        self.toast('Labels of selected atoms hidden')

    def only_selected_labels(self):
        if self.model is None or not self.selection:
            return
        keep = {display_name(self.model, i, self.s) for i in self.selection}
        self.s.hidden_labels = {display_name(self.model, i, self.s) for i in range(self.model.n)} - keep
        self.redraw_overlay()
        self.toast('Only selected labels shown')

    def restore_labels(self):
        self.s.hidden_labels = set()
        self.redraw_overlay()

    # ------------------------------------------------------------------ View
        self.toast('All labels restored', 'ok')

    def _tab_view(self, t):
        ctk.CTkButton(t, text='Reset view', command=self.reset_view).pack(fill='x', padx=6, pady=(8, 3))
        ctk.CTkButton(t, text='Fit to window', command=self.fit_view).pack(fill='x', padx=6, pady=3)
        fr = ctk.CTkFrame(t, fg_color='transparent')
        fr.pack(fill='x', padx=6, pady=3)
        for n in 'abc':
            ctk.CTkButton(fr, text=f'along {n}', width=80,
                          command=lambda n=n: self.view_axis(n)).pack(side='left', expand=True, padx=2)
        fr2 = ctk.CTkFrame(t, fg_color='transparent')
        fr2.pack(fill='x', padx=6, pady=3)
        for txt, rot in (('↻ 90° x', rot_x), ('↻ 90° y', rot_y), ('↻ 90° z', rot_z)):
            ctk.CTkButton(fr2, text=txt, width=80, command=lambda r=rot: self.apply_rotation(r(math.pi / 2))
                          ).pack(side='left', expand=True, padx=2)
        self._section(t, 'Lighting')
        self._slider(t, 'Light from (left/right)', -90, 90, self.s.light_azimuth,
                     lambda v: self._set('light_azimuth', v), '{:.0f}°', 36, key='light_azimuth')
        self._slider(t, 'Light height', -30, 85, self.s.light_elevation,
                     lambda v: self._set('light_elevation', v), '{:.0f}°', 23, key='light_elevation')
        self.outline_var = tk.BooleanVar(value=self.s.outline)
        self._switch(t, 'Dark outlines', self.outline_var, self.on_setting)

        adv = self._collapsible(t, 'Advanced')
        self._slider(adv, 'Rotate speed', 0.1, 1.5, self.rot_speed, self._set_rot_speed, '{:.2f}', 28,
                     key='rot_speed')
        self.step_var = tk.StringVar(value='5')
        self._option(adv, 'Arrow-key step (°)', self.step_var, ['1', '2', '5', '10', '15', '30', '45', '90'],
                     lambda: None)
        self.dragq_var = tk.StringVar(value=self.s.drag_quality)
        self._option(adv, 'While dragging', self.dragq_var, ['Smooth (1/2 res)', 'Faster (1/3 res)',
                                                             'Fastest (1/4 res)', 'Full quality'], self.on_setting)
        self._slider(adv, 'Fill light', 0, 1, self.s.fill_light, lambda v: self._set('fill_light', v),
                     '{:.2f}', 20, key='fill_light')
        self._slider(adv, 'Ambient', 0, 4, self.s.ambient_light, lambda v: self._set('ambient_light', v),
                     '{:.2f}', 40, key='ambient_light')
        self.srgb_var = tk.BooleanVar(value=self.s.srgb)
        self._switch(adv, 'POV-Ray gamma (sRGB)', self.srgb_var, self.on_setting)
        self.render_lbl = self._note(adv, '')
        self.after(2500, self._update_render_label)

    def _update_render_label(self):
        if self.gl is not None and self.gl.ready and self.gl.failed is None:
            try:
                from OpenGL import GL as _GL
                self.gl.tkMakeCurrent()
                name = _GL.glGetString(_GL.GL_RENDERER).decode(errors='replace')
            except Exception:  # noqa: BLE001
                name = 'OpenGL'
            txt = (f'Live view: GPU ({name}) - full quality while rotating. "While dragging" only applies '
                   'to Line drawing / RMSD / MSD styles.')
        elif self.gl is not None and self.gl.failed:
            txt = f'Live view: software renderer (OpenGL failed: {self.gl.failed[:60]})'
        elif self.gl is None:
            txt = 'Live view: software renderer (install PyOpenGL + pyopengltk for GPU rendering)'
        else:
            txt = 'Live view: GPU starts when a structure is shown'
            self.after(2000, self._update_render_label)
        self.render_lbl.configure(text=txt)

    def _set(self, attr, v):
        setattr(self.s, attr, v)
        self.request_redraw(fast=True)

    def _set_rot_speed(self, v):
        self.rot_speed = v

    # ------------------------------------------------------------------ Color
    def _tab_color(self, t):
        self._section(t, 'Color scheme')
        self.preset_var = tk.StringVar(value=self.styles.preset)
        self._option(t, 'Preset', self.preset_var, PRESETS, lambda: None)
        ctk.CTkButton(t, text='Apply preset', command=self.apply_preset).pack(fill='x', padx=6, pady=3)
        self._section(t, 'Modify color')
        self.ctarget_var = tk.StringVar(value='')
        self.ctarget_menu = self._option(t, 'Apply to', self.ctarget_var, ['Bonds'], self.on_color_target)
        fr = ctk.CTkFrame(t, fg_color='transparent')
        fr.pack(fill='x', padx=6, pady=3)
        ctk.CTkLabel(fr, text='Current:', anchor='w').pack(side='left')
        self.swatch = ctk.CTkLabel(fr, text='', width=60, height=22, corner_radius=4, fg_color='#888888')
        self.swatch.pack(side='left', padx=6)
        self.swatch_name = ctk.CTkLabel(fr, text='', anchor='w')
        self.swatch_name.pack(side='left')
        self.cpreview = ctk.CTkLabel(t, text='')
        self.cpreview.pack(pady=4)
        self._selection_buttons(t)
        names = sorted(POV_COLORS, key=str.lower)
        self.color_list = self._listbox(t, 'POV-Ray colors', names, 12, self.on_color_pick)
        for k, nm in enumerate(names):
            r, g, b = POV_COLORS[nm]
            lum = 0.3 * r + 0.59 * g + 0.11 * b
            self.color_list.itemconfig(k, background=rgb_to_hex((r, g, b)),
                                       foreground='black' if lum > 0.45 else 'white')
        ctk.CTkButton(t, text='Custom color…', command=self.custom_color).pack(fill='x', padx=6, pady=3)
        ctk.CTkButton(t, text='Clear per-atom overrides', command=self.clear_overrides).pack(fill='x', padx=6, pady=3)
        self._section(t, 'Bonds & background')
        self.bondcol_var = tk.StringVar(value=self.s.bond_coloring)
        self._option(t, 'Bond coloring', self.bondcol_var, ['Bond texture', 'Split by atom'], self.on_setting)
        self.bg_var = tk.StringVar(value='White')
        self._option(t, 'Background', self.bg_var, BACKGROUNDS + ['Custom…'], self.on_background)

    def _targets(self):
        els = []
        if self.model is not None:
            for e in self.model.elements:
                if e not in els:
                    els.append(e)
        return els + list(OBJECT_TARGETS) + ['Selected atoms', 'All atoms']

    def _refresh_targets(self):
        vals = self._targets()
        self.ctarget_menu.configure(values=vals)
        self.starget_menu.configure(values=vals)
        if self.ctarget_var.get() not in vals:
            self.ctarget_var.set(vals[0])
        if self.starget_var.get() not in vals:
            self.starget_var.set(vals[0])
        self.on_color_target()
        self.on_style_target()

    def _target_keys(self, name):
        """Display target -> list of StyleTable keys."""
        if name in OBJECT_TARGETS:
            return [name]
        if name == 'Selected atoms':
            if self.model is None:
                return []
            return sorted({f'Atom:{self.model.labels[i]}' for i in self.selection})
        if name == 'All atoms':
            return [f'El:{e}' for e in (self._targets()[:-len(OBJECT_TARGETS) - 2])]
        return [f'El:{name}']

    def _current_entry(self, name):
        keys = self._target_keys(name)
        if not keys:
            return {}
        k = keys[0]
        if k.startswith('Atom:') and self.model is not None:
            lab = k[5:]
            el = self.model.elements[self.model.labels.index(lab)]
            return self.styles.atom_entry(lab, el)
        return self.styles.get(k)

    def on_color_target(self):
        ent = self._current_entry(self.ctarget_var.get())
        if not ent:
            self.swatch.configure(fg_color='#888888')
            self.swatch_name.configure(text='(nothing selected)')
            return
        if ent.get('texture', 'None') != 'None':
            from .styles import TEXTURES
            col = TEXTURES[ent['texture']]['color']
            txt = f'texture {ent["texture"]}'
        else:
            col = color_rgb(ent.get('color', 'Gray50'))
            txt = str(ent.get('color'))
        self.swatch.configure(fg_color=rgb_to_hex(col))
        self.swatch_name.configure(text=txt)
        self._update_previews()

    def _selection_buttons(self, t):
        fr = ctk.CTkFrame(t, fg_color='transparent')
        fr.pack(fill='x', padx=6, pady=2)
        ctk.CTkButton(fr, text='Select all of element', width=150,
                      command=self.select_element).pack(side='left', expand=True, fill='x', padx=(0, 2))
        ctk.CTkButton(fr, text='Clear selection', width=110,
                      command=self.clear_selection).pack(side='left', expand=True, fill='x', padx=(2, 0))

    def select_element(self):
        """Select every atom of the element chosen in 'Apply to' (or of the last selected atom)."""
        if self.model is None:
            return
        name = self.tabs.get() == 'Color' and self.ctarget_var.get() or self.starget_var.get()
        el = name if name in self.model.elements else (
            self.model.elements[self.selection[-1]] if self.selection else None)
        if el is None:
            self.status.configure(text='Choose an element in "Apply to" (or click an atom) first.')
            return
        self.selection = [i for i in range(self.model.n) if self.model.elements[i] == el and self._active_view().visible[i]]
        self.toast(f'Selected all {el} atoms ({len(self.selection)})')
        self.update_status()
        self.redraw_overlay()

    def clear_selection(self):
        self.selection = []
        self.update_status()
        self.redraw_overlay()
        self.toast('Selection cleared')

    def _preview_image(self, name):
        if name in OBJECT_TARGETS and name in ('Bonds', 'H bonds'):
            ent, kind = self.styles.get(name), 'bond'
        elif name in ('Equators', 'Cutout faces'):
            ent, kind = dict(self.styles.element_entry('C'), ellipse='CutoutEllipse'), 'atom'
        else:
            ent, kind = self._current_entry(name), 'atom'
            if not ent:
                return None
        try:
            im = material_preview(self.styles, self.s, ent, kind, size=110)
        except Exception:  # noqa: BLE001 - preview is cosmetic
            return None
        return ctk.CTkImage(light_image=im, dark_image=im, size=(110, 110))

    def _update_previews(self):
        for lbl, var in ((getattr(self, 'cpreview', None), self.ctarget_var),
                         (getattr(self, 'spreview', None), getattr(self, 'starget_var', None))):
            if lbl is None or var is None:
                continue
            img = self._preview_image(var.get())
            lbl.configure(image=img, text='' if img else '(no preview)')
            lbl._preview_ref = img

    def _apply_to_target(self, name, **kw):
        keys = self._target_keys(name)
        if not keys:
            self.status.configure(text='No atoms selected - click atoms in the picture first.')
            return
        for k in keys:
            self.styles.set(k, **kw)
        self.request_redraw()
        self._update_previews()

    def on_color_pick(self, lb):
        sel = lb.curselection()
        if not sel:
            return
        self._apply_to_target(self.ctarget_var.get(), color=lb.get(sel[0]), texture='None')
        self.on_color_target()
        self.toast(f'{self.ctarget_var.get()}: {lb.get(sel[0])}')

    def _open_picker(self, title, initial, live, close):
        old = getattr(self, '_picker', None)
        if old is not None and not old.closed:
            old.ok()                    # a picker that is still open keeps its color (no revert)
        self._picker = LiveColorPicker(self, title, initial, live, close)

    def custom_color(self):
        """Live color picker for the 'Apply to' target; Cancel restores the previous colors."""
        name = self.ctarget_var.get()
        keys = self._target_keys(name)
        if not keys:
            self.status.configure(text='No atoms selected - click atoms in the picture first.')
            return
        saved = {k: (dict(self.styles.entries[k]) if k in self.styles.entries else None) for k in keys}
        ent = self._current_entry(name)
        if ent.get('texture', 'None') != 'None':
            from .styles import TEXTURES
            init = rgb_to_hex(TEXTURES[ent['texture']]['color'])
        else:
            init = rgb_to_hex(color_rgb(ent.get('color', 'Gray50')))

        def live(hx):
            for k in keys:
                self.styles.set(k, color=hx, texture='None')
            self.swatch.configure(fg_color=hx)
            self.swatch_name.configure(text=hx)
            self.request_redraw()

        def close(hx):
            if hx is None:
                for k, v in saved.items():
                    if v is None:
                        self.styles.entries.pop(k, None)
                    else:
                        self.styles.entries[k] = v
            else:
                live(hx)
                self.toast(f'{name}: {hx}', 'ok')
            self.request_redraw()
            self.on_color_target()
        self._open_picker(f'Color - {name}', init, live, close)

    def clear_overrides(self):
        self.styles.clear_atom_overrides()
        self.request_redraw()
        self.toast('Per-atom overrides cleared')

    def apply_preset(self):
        self.styles.apply_preset(self.preset_var.get())
        bg = {'Monochrome': 'White'}.get(self.preset_var.get())
        if bg:
            self.bg_var.set(bg)
        self._refresh_targets()
        self.request_redraw()
        self.toast(f'Preset applied: {self.preset_var.get()}', 'ok')

    def on_background(self):
        v = self.bg_var.get()
        if v == 'Custom…':
            prev = self.s.background

            def live(hx):
                self.s.background = hx
                self.fig.set_facecolor(hx)
                self.request_redraw()

            def close(hx):
                live(hx or prev)
                if hx is None:
                    self.bg_var.set('White' if prev.lower() == '#ffffff' else 'Custom…')
            self._open_picker('Background color', prev, live, close)
            return
        else:
            self.s.background = rgb_to_hex(POV_COLORS[v])
        self.fig.set_facecolor(self.s.background)
        self.request_redraw()

    # ------------------------------------------------------------------ Styles
    def _tab_styles(self, t):
        self._section(t, 'Style')
        grid = ctk.CTkFrame(t, fg_color='transparent')
        grid.pack(fill='x', padx=4, pady=2)
        self.style_buttons = {}
        thumbs = self._make_thumbnails()
        for k, name in enumerate(ATOM_STYLES):
            b = ctk.CTkButton(grid, text=name.replace(' (vector)', ''), image=thumbs.get(name), compound='top',
                              width=92, height=92,
                              fg_color='transparent', border_width=2, text_color=('black', 'white'),
                              hover_color=('gray80', 'gray30'), font=ctk.CTkFont(size=10),
                              command=lambda n=name: self.set_style(n))
            b.grid(row=k // 3, column=k % 3, padx=1, pady=2, sticky='nsew')
            self.style_buttons[name] = b
        self._highlight_style()
        self.prob_var = tk.StringVar(value='50 %')
        self._option(t, 'Probability', self.prob_var, ['10 %', '20 %', '30 %', '40 %', '50 %', '60 %', '70 %',
                                                       '80 %', '90 %', '99 %'], self.on_setting)

        self._section(t, 'Modify')
        self.starget_var = tk.StringVar(value='')
        self.starget_menu = self._option(t, 'Apply to', self.starget_var, ['Bonds'], self.on_style_target)
        self.spreview = ctk.CTkLabel(t, text='')
        self.spreview.pack(pady=4)
        self._selection_buttons(t)
        self.ell_list = self._listbox(t, 'Ellipse style', ELLIPSE_STYLES, 3, self.on_ellipse_pick)
        self.fin_list = self._listbox(t, 'Finish', FINISH_NAMES, 8, self.on_finish_pick)
        self.tex_list = self._listbox(t, 'Texture (overrides color + finish)', TEXTURE_NAMES, 8,
                                      self.on_texture_pick)

        adv = self._collapsible(t, 'Advanced: sizes (Å)')
        s = self.s
        self.size_vars = {}
        for attr, label in (('bond_radius', 'Bond radius'), ('hbond_radius', 'Bond-to-H radius'),
                            ('h_radius', 'H sphere radius'), ('band_width', 'Boundary band (rel.)'),
                            ('ball_scale', 'Ball scale (×r_cov)'), ('stick_radius', 'Stick radius'),
                            ('rod_radius', 'Rod radius'), ('vdw_scale', 'vdW scale')):
            v = tk.StringVar(value=f'{getattr(s, attr):g}')
            self.size_vars[attr] = v
            self._entry(adv, label, v, self.on_sizes, width=70)

    def _make_thumbnails(self):
        thumbs = {}
        m = _thumb_model()
        st = RenderSettings(labels_on=False, srgb=True)
        sty = StyleTable()
        sty.set('El:O', ellipse='CutoutEllipse')
        sty.set('El:N', ellipse='BoundaryEllipse')
        fig = Figure(figsize=(0.84, 0.58), dpi=100, facecolor='#bebebe')
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        view = SceneView(ax)
        R = rot_y(0.35) @ rot_x(0.35)
        for name in ATOM_STYLES:
            st.atom_style = name
            st.background = '#bebebe'
            sc = 1.9 if name == 'Van der Waals' else 1.1
            try:
                view.draw(m, None, R, np.zeros(3), sc, (0, 0), st, sty, 84, 58, ss=2)
                fig.canvas.draw()
                im = Image.fromarray(np.asarray(fig.canvas.buffer_rgba())[..., :3].copy())
                thumbs[name] = ctk.CTkImage(light_image=im, dark_image=im, size=(84, 58))
            except Exception:  # noqa: BLE001 - thumbnails are cosmetic
                pass
        return thumbs

    def _highlight_style(self):
        for n, b in self.style_buttons.items():
            b.configure(border_color='#1f6aa5' if n == self.s.atom_style else ('gray75', 'gray30'))

    def set_style(self, name):
        self.s.atom_style = name
        self._show_view()
        self._highlight_style()
        self.request_redraw()
        self.toast(f'Style: {name}')

    @staticmethod
    def _select_in(lb, value):
        lb.selection_clear(0, 'end')
        items = lb.get(0, 'end')
        if value in items:
            k = items.index(value)
            lb.selection_set(k)
            lb.see(k)

    def on_style_target(self):
        name = self.starget_var.get()
        ent = self._current_entry(name)
        is_atom = name not in OBJECT_TARGETS
        self.ell_list.configure(state='normal' if is_atom else 'disabled')
        self._select_in(self.ell_list, ent.get('ellipse', '') if is_atom else '')
        self._select_in(self.fin_list, ent.get('finish', '') if isinstance(ent.get('finish'), str) else '')
        self._select_in(self.tex_list, ent.get('texture', 'None'))
        self._update_previews()

    def on_ellipse_pick(self, lb):
        sel = lb.curselection()
        if sel:
            self._apply_to_target(self.starget_var.get(), ellipse=lb.get(sel[0]))
            self.toast(f'{self.starget_var.get()}: {lb.get(sel[0])}')

    def on_finish_pick(self, lb):
        sel = lb.curselection()
        if sel:
            self._apply_to_target(self.starget_var.get(), finish=lb.get(sel[0]), texture='None')
            self.toast(f'{self.starget_var.get()}: finish {lb.get(sel[0])}')
            self._select_in(self.tex_list, 'None')

    def on_texture_pick(self, lb):
        sel = lb.curselection()
        if sel:
            self._apply_to_target(self.starget_var.get(), texture=lb.get(sel[0]))
            self.toast(f'{self.starget_var.get()}: texture {lb.get(sel[0])}')
            self.on_color_target()

    def on_sizes(self):
        for attr, v in self.size_vars.items():
            try:
                val = float(v.get())
                if val > 0:
                    setattr(self.s, attr, val)
            except ValueError:
                v.set(f'{getattr(self.s, attr):g}')
        self.request_redraw()

    # ------------------------------------------------------------------ Export
        self.toast('Sizes updated')

    def _tab_export(self, t):
        self._section(t, 'Image')
        self.size_preset = tk.StringVar(value='6400 × 4800 (default)')
        self._option(t, 'Size', self.size_preset, list(SIZE_PRESETS), self.on_size_preset)
        self.dpi_var = tk.StringVar(value='600')
        self._option(t, 'Print resolution (dpi)', self.dpi_var, ['300', '600', '1200'], lambda: None)
        self.shadow_var = tk.BooleanVar(value=False)
        self._switch(t, 'Shadows', self.shadow_var, lambda: None)
        self.trans_var = tk.BooleanVar(value=True)
        self._switch(t, 'Transparent background', self.trans_var, lambda: None)
        self.px_lbl = self._note(t, '')
        self.save_btn = self._button(t, 'Save image…  Ctrl+S', self.save_image)

        self._section(t, 'Rotating GIF')
        self.gif_size = tk.StringVar(value=GIF_DEFAULT_PRESET)
        self._option(t, 'Size', self.gif_size, list(GIF_SIZE_PRESETS), self.on_gif_size)
        self.gif_axis = tk.StringVar(value='Vertical')
        self._option(t, 'Spin axis', self.gif_axis, ['Vertical', 'Horizontal', 'In-plane'], lambda: None)
        self.gif_dir = tk.StringVar(value='Clockwise')
        self._option(t, 'Direction', self.gif_dir, ['Clockwise', 'Counter-clockwise'], lambda: None)
        self.spin_btn = self._button(t, '▶ Spin preview  Space', self.toggle_spin)
        self._note(t, 'Drag the molecule while it spins to choose the orientation; the GIF uses it.')
        self.gif_shadow = tk.BooleanVar(value=True)
        self._switch(t, 'Shadows', self.gif_shadow, lambda: None)
        self.gif_trans = tk.BooleanVar(value=True)
        self._switch(t, 'Transparent background', self.gif_trans, lambda: None)
        self.gif_matte = tk.StringVar(value='#ffffff')
        self._entry(t, 'Slide color', self.gif_matte, self._check_matte, width=80)
        self._button(t, 'Pick slide color…', self.pick_matte)
        self.gif_btn = self._button(t, 'Save GIF…  Ctrl+G', self.save_gif)

        adv = self._collapsible(t, 'Advanced')
        ctk.CTkLabel(adv, text='Image', font=ctk.CTkFont(weight='bold'), anchor='w').pack(fill='x', padx=6, pady=(6, 0))
        self.w_px = tk.StringVar(value=str(DEFAULT_WIDTH))
        self.h_px = tk.StringVar(value=str(DEFAULT_HEIGHT))
        self._entry(adv, 'Width (px)', self.w_px, lambda: None, width=80)
        self._entry(adv, 'Height (px)', self.h_px, lambda: None, width=80)
        self._button(adv, 'Match window shape', self.match_window)
        self.aa_var = tk.BooleanVar(value=True)
        self._switch(adv, 'Antialiasing (threshold 0.3)', self.aa_var, lambda: None)
        self.engine_var = tk.StringVar(value='Built-in')
        self._option(adv, 'Renderer', self.engine_var, ['Built-in', 'POV-Ray (ray traced)'], self._engine_changed)
        self.refl_var = tk.BooleanVar(value=True)
        self.refl_switch = self._switch(adv, 'Reflections (POV-Ray only)', self.refl_var, lambda: None)
        self.lsize_mode = tk.StringVar(value='Match screen')
        self._option(adv, 'Label size', self.lsize_mode, ['Match screen', 'As set (pt)'], lambda: None)

        ctk.CTkLabel(adv, text='GIF', font=ctk.CTkFont(weight='bold'), anchor='w').pack(fill='x', padx=6, pady=(10, 0))
        self.gif_frames = tk.StringVar(value='200')
        self._entry(adv, 'Frames', self.gif_frames, lambda: None, width=70)
        self.gif_deg = tk.StringVar(value='360')
        self._entry(adv, 'Total rotation (°)', self.gif_deg, lambda: None, width=70)
        self.gif_delay = tk.StringVar(value='50')
        self._entry(adv, 'Frame delay (ms)', self.gif_delay, lambda: None, width=70)
        self.gif_w = tk.StringVar(value='1600')
        self.gif_h = tk.StringVar(value='1200')
        self._entry(adv, 'Width (px)', self.gif_w, lambda: None, width=70)
        self._entry(adv, 'Height (px)', self.gif_h, lambda: None, width=70)
        self.gif_grain = tk.BooleanVar(value=False)
        self._switch(adv, 'Speckle grain (shimmers)', self.gif_grain, lambda: None)
        self._note(adv, 'Default 200 frames × 50 ms = 20 frames/s, one turn in 10 s. Slide color: the soft '
                        'edges and label halos of a transparent GIF are blended onto it. Save as .png for an '
                        'animated PNG with true color and soft transparent edges.')

        ctk.CTkLabel(adv, text='POV-Ray', font=ctk.CTkFont(weight='bold'), anchor='w').pack(fill='x', padx=6, pady=(10, 0))
        self.povexe = load_config().get('povray') or find_povray()
        self.pov_lbl = self._note(adv, '')
        self._button(adv, 'Browse for POV-Ray program…', self.browse_povray)
        self.pov_labels = tk.BooleanVar(value=True)
        self._switch(adv, 'Labels in .pov (POV-Ray text)', self.pov_labels, lambda: None)
        self._button(adv, 'Save POV-Ray scene (.pov + .ini)…  Ctrl+P', self.save_pov)
        self._show_pov_path()
        self._engine_changed()
        self.after(500, self._update_px_label)

    def on_gif_size(self):
        wh = GIF_SIZE_PRESETS.get(self.gif_size.get())
        if wh:
            self.gif_w.set(str(wh[0]))
            self.gif_h.set(str(wh[1]))
            self.toast(f'GIF size {wh[0]} × {wh[1]}')

    def _check_matte(self):
        import re
        from matplotlib.colors import to_hex
        v = self.gif_matte.get().strip()
        if re.fullmatch(r'#?[0-9a-fA-F]{6}', v):
            hx = '#' + v.lstrip('#').lower()
        elif v in POV_COLORS:
            hx = rgb_to_hex(color_rgb(v))
        else:
            try:
                hx = to_hex(v.lower())
            except ValueError:
                hx = '#ffffff'
                self.toast('Slide color not understood - using white', 'warn')
        self.gif_matte.set(hx)
        return hx

    def pick_matte(self):
        prev = self._check_matte()
        self._open_picker('Slide color (GIF edge matte)', prev, lambda hx: self.gif_matte.set(hx),
                          lambda hx: self.gif_matte.set(hx or prev))

    def _engine_changed(self):
        pov = self.engine_var.get().startswith('POV')
        self.refl_switch.configure(state='normal' if pov else 'disabled')

    def _show_pov_path(self):
        self.pov_lbl.configure(text=f'Program: {self.povexe or "not found - use Browse"}')

    def browse_povray(self):
        p = filedialog.askopenfilename(title='Select POV-Ray (pvengine64.exe / povray)',
                                       filetypes=[('Programs', '*.exe'), ('All files', '*.*')])
        if p:
            self.povexe = p
            cfg = load_config()
            cfg['povray'] = p
            save_config(cfg)
            self._show_pov_path()
            self.toast('POV-Ray program set', 'ok')

    def on_size_preset(self):
        v = SIZE_PRESETS.get(self.size_preset.get())
        if v == 'window':
            W, H = self._canvas_px()
            v = (W, H)
        if v:
            self.w_px.set(str(v[0]))
            self.h_px.set(str(v[1]))

    def _update_px_label(self):
        try:
            w, h, d = int(self.w_px.get()), int(self.h_px.get()), int(self.dpi_var.get())
            pt = self._export_settings(h / d, self._export_scale(w, h)).label_size
            self.px_lbl.configure(text=f'{w} × {h} px = {w / d:.2f} × {h / d:.2f} in at {d} dpi; '
                                       f'labels {pt:.1f} pt')
        except (ValueError, ZeroDivisionError):
            self.px_lbl.configure(text='')
        self.after(700, self._update_px_label)

    def match_window(self):
        W, H = self._canvas_px()
        try:
            w = int(self.w_px.get())
        except ValueError:
            w = DEFAULT_WIDTH
        self.h_px.set(str(int(round(w * H / W))))

    # ------------------------------------------------------------------ SI caption
    def _tab_si(self, t):
        self._section(t, 'Figure caption for the SI')
        self.si_fig = tk.StringVar(value='S1')
        self._entry(t, 'Figure number', self.si_fig, self.update_si, width=90)
        self.si_name = tk.StringVar(value='')
        self._entry(t, 'Compound (X)', self.si_name, self.update_si, width=150)
        self.si_auto = tk.BooleanVar(value=True)
        self._switch(t, 'Update automatically', self.si_auto, self.update_si)
        self.si_merge = tk.BooleanVar(value=True)
        self._switch(t, 'Skip symmetry-equivalent repeats', self.si_merge, self.update_si)
        self.si_solv = tk.BooleanVar(value=True)
        self._switch(t, 'Mention co-crystallized solvent', self.si_solv, self.update_si)
        ctk.CTkLabel(t, text='Select atoms in the picture (click them). Bonds between selected atoms and '
                             'angles between selected bonded atoms are listed in selection order; '
                             'atom names follow the file labels.', wraplength=300, justify='left',
                     anchor='w', text_color=('gray30', 'gray70')).pack(fill='x', padx=6, pady=(4, 2))
        self.si_text = ctk.CTkTextbox(t, height=200, wrap='word', font=ctk.CTkFont(size=13))
        self.si_text.pack(fill='x', padx=6, pady=4)
        self.si_info = ctk.CTkLabel(t, text='', anchor='w', wraplength=300, justify='left',
                                    text_color=('gray30', 'gray70'))
        self.si_info.pack(fill='x', padx=6)
        fr = ctk.CTkFrame(t, fg_color='transparent')
        fr.pack(fill='x', padx=6, pady=4)
        ctk.CTkButton(fr, text='Update', width=100, command=lambda: self.update_si(force=True)
                      ).pack(side='left', expand=True, fill='x', padx=(0, 2))
        ctk.CTkButton(fr, text='Copy to clipboard', width=150, command=self.copy_si
                      ).pack(side='left', expand=True, fill='x', padx=(2, 0))

        self._section(t, 'Geometry index (τ₄, τ₄′, τ₅)')
        self._note(t, 'The metal centre and the atoms bonded to it are found automatically. Use the '
                      'buttons to choose them yourself (e.g. a Cg centroid as one ligand).')
        row = ctk.CTkFrame(t, fg_color='transparent')
        row.pack(fill='x', padx=6, pady=3)
        self.geo_metal_btn = ctk.CTkButton(row, text='Metal center', width=40,
                                           command=lambda: self.toggle_geo_mode('metal'))
        self.geo_metal_btn.pack(side='left', expand=True, fill='x', padx=(0, 2))
        self.geo_lig_btn = ctk.CTkButton(row, text='Ligands', width=40,
                                         command=lambda: self.toggle_geo_mode('ligands'))
        self.geo_lig_btn.pack(side='left', expand=True, fill='x', padx=2)
        ctk.CTkButton(row, text='Auto', width=40, command=self.geo_auto).pack(side='left', expand=True,
                                                                            fill='x', padx=(2, 0))
        self.geo_text = ctk.CTkTextbox(t, height=170, wrap='word', font=ctk.CTkFont(size=13))
        self.geo_text.pack(fill='x', padx=6, pady=4)
        self.geo_caption = tk.BooleanVar(value=False)
        self._switch(t, 'Add the geometry index to the caption', self.geo_caption, lambda: self.update_si(force=True))
        ctk.CTkButton(t, text='Copy geometry index', command=self.copy_geo).pack(fill='x', padx=6, pady=(3, 10))

    def update_si(self, force=False):
        if not hasattr(self, 'si_text') or self.model is None:
            return
        if not (force or self.si_auto.get()):
            return
        m, s = self.model, self.s
        view = self._active_view()
        vis = getattr(view, 'visible', np.ones(m.n, bool))
        gen_vis = s.labels_on and any(
            m.generated[i] and i < len(vis) and vis[i] and label_visible(s, m.elements[i])
            and display_name(m, i, s) not in s.hidden_labels for i in range(m.n))
        text, used_cif, nb, na = si_caption(self.si_fig.get().strip() or 'S1',
                                            self.si_name.get().strip() or self._base(),
                                            s.probability, s.show_h, m, self.struct, self.selection,
                                            suffix=s.sym_suffix or '*', merge_equivalent=self.si_merge.get(),
                                            generated_visible=gen_vis, excluded=self.s.excluded,
                                            hidden_keys=self.s.hidden_keys,
                                            mention_solvent=self.si_solv.get())
        res = self.update_geometry()
        if self.geo_caption.get() and res:
            sent = gi.caption_sentence(res, self._geo_name)
            if sent:
                text = text.rstrip() + ' ' + sent
        self.si_text.delete('1.0', 'end')
        self.si_text.insert('1.0', text)
        if nb + na == 0:
            info = 'No bonds/angles yet: select bonded atoms in the picture.'
        elif used_cif:
            info = f'{nb} bonds, {na} angles. s.u. values taken from the CIF geometry tables.'
        else:
            info = (f'{nb} bonds, {na} angles. No s.u. available (values computed from coordinates) - '
                    'open the final CIF to include s.u. values.')
        sv = identify_solvents(m)
        if sv:
            info += f'  Solvent found: {solvent_phrase(sv)}.'
        self.si_info.configure(text=info)

    # ------------------------------------------------------------------ geometry index
    def _geo_name(self, i):
        return display_name(self.model, i, self.s)

    def geometry_results(self):
        """Manual metal / ligands when chosen, otherwise every metal centre with its bonded atoms."""
        m = self.model
        if m is None:
            return []
        idx = {atom_key(m, i): i for i in range(m.n)}
        man_c = idx.get(self.geo_metal) if self.geo_metal else None
        man_l = [idx[k] for k in self.geo_ligands if k in idx]
        if man_c is not None:
            lig = man_l if self.geo_ligands else gi.neighbours(m, man_c, self.s.excluded)
            return [gi.analyse(m, man_c, lig, self._geo_name)]
        return [gi.analyse(m, c, gi.neighbours(m, c, self.s.excluded), self._geo_name)
                for c in gi.metal_centres(m, self.s.excluded)]

    def update_geometry(self):
        if not hasattr(self, 'geo_text') or self.model is None:
            return []
        res = self.geometry_results()
        if res:
            mode = 'manual' if self.geo_metal else 'automatic'
            body = f'({mode} selection)\n\n' + '\n\n'.join(r['text'] for r in res)
        else:
            body = ('No metal centre with ligands found. Press "Metal center" and click the metal, then '
                    '"Ligands" and click the coordinating atoms.')
        if self._geo_mode == 'metal':
            body = 'Click the metal centre in the picture (Esc to stop).\n\n' + body
        elif self._geo_mode == 'ligands':
            body = 'Click the ligand atoms (click again to remove; Esc to stop).\n\n' + body
        self.geo_text.delete('1.0', 'end')
        self.geo_text.insert('1.0', body)
        return res

    def toggle_geo_mode(self, mode):
        if self.model is None:
            return
        if mode == 'ligands' and not self.geo_metal:
            res = self.geometry_results()
            if len(res) == 1:                      # start from the automatic centre and its ligands
                c = res[0]['centre']
                self.geo_metal = atom_key(self.model, c)
                self.geo_ligands = [atom_key(self.model, j) for j in res[0]['ligands']]
            else:
                self.toast('Choose the metal center first', 'warn')
                mode = 'metal'
        if self._exclude_mode:
            self.toggle_exclude()
        if self._wire_mode:
            self.toggle_wire_mode()
        self._geo_mode = None if self._geo_mode == mode else mode
        self._set_cursor()
        on = ('#c26a00', '#c26a00')
        off = ctk.ThemeManager.theme['CTkButton']['fg_color']
        self.geo_metal_btn.configure(fg_color=on if self._geo_mode == 'metal' else off,
                                     text='Click the metal…' if self._geo_mode == 'metal' else 'Metal center')
        self.geo_lig_btn.configure(fg_color=on if self._geo_mode == 'ligands' else off,
                                   text='Click ligands… (Esc)' if self._geo_mode == 'ligands' else 'Ligands')
        if self._geo_mode:
            self.tabs.set('SI')
            self.toast('Click the metal center' if self._geo_mode == 'metal' else
                       'Click ligand atoms to add / remove them')
        self._geo_highlight()
        self.update_geometry()

    def _geo_click(self, i):
        m = self.model
        k = atom_key(m, i)
        if self._geo_mode == 'metal':
            self.geo_metal = k
            self.geo_ligands = [atom_key(m, j) for j in gi.neighbours(m, i, self.s.excluded)]
            self.toast(f'Metal center: {self._geo_name(i)} ({len(self.geo_ligands)} bonded atoms as ligands)')
            self.toggle_geo_mode('ligands')       # continue straight with the ligands
        elif self._geo_mode == 'ligands':
            if k == self.geo_metal:
                return
            if k in self.geo_ligands:
                self.geo_ligands.remove(k)
            else:
                self.geo_ligands.append(k)
            self._geo_highlight()
        self.update_si(force=True)

    def geo_auto(self):
        self.geo_metal = None
        self.geo_ligands = []
        if self._geo_mode:
            self.toggle_geo_mode(self._geo_mode)
        self._geo_highlight()
        self.update_si(force=True)
        self.toast('Geometry index: automatic metal center and ligands')

    def _geo_highlight(self):
        """Orange ring = metal, green rings = ligands; shown while choosing them."""
        hl = []
        if self._geo_mode and self.model is not None:
            idx = {atom_key(self.model, i): i for i in range(self.model.n)}
            if self.geo_metal in idx:
                hl.append((idx[self.geo_metal], (0.90, 0.45, 0.0)))
            hl += [(idx[k], (0.10, 0.65, 0.25)) for k in self.geo_ligands if k in idx]
        self.geo_highlight = hl
        self.view.highlight = hl
        self.redraw_overlay()

    def copy_geo(self):
        txt = self.geo_text.get('1.0', 'end').strip()
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.toast('Geometry index copied to the clipboard', 'ok')

    def copy_si(self):
        txt = self.si_text.get('1.0', 'end').strip()
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.status.configure(text='SI caption copied to the clipboard.')
        self.toast('SI caption copied to the clipboard', 'ok')

    # ------------------------------------------------------------------ live spin (GIF preview)
    def toggle_spin(self):
        if getattr(self, '_spin_job', None):
            self.stop_spin()
        else:
            self.start_spin()

    def start_spin(self):
        if self.model is None:
            return
        self._spin_last = time.perf_counter()
        self.spin_btn.configure(text='■ Stop spin')
        self.toast('Spin preview: drag to re-orient, Space to stop')
        self._spin_job = self.after(16, self._spin_tick)

    def stop_spin(self):
        job = getattr(self, '_spin_job', None)
        if job:
            self.after_cancel(job)
            self.toast('Spin stopped')
        self._spin_job = None
        if hasattr(self, 'spin_btn'):
            self.spin_btn.configure(text='▶ Spin preview')

    def _spin_tick(self):
        """Turn at the GIF's speed: (total rotation / frames) degrees every frame delay."""
        now = time.perf_counter()
        dt = now - self._spin_last
        self._spin_last = now
        try:
            frames = max(int(self.gif_frames.get()), 1)
            deg = float(self.gif_deg.get())
            delay = max(int(self.gif_delay.get()), 10)
        except ValueError:
            frames, deg, delay = 36, 360.0, 60
        speed = math.radians(deg / frames) / (delay / 1000.0)       # rad / s
        Rd = spin_rotation(self.gif_axis.get(), speed * min(dt, 0.1), self.gif_dir.get())
        self.R = orthonormalize(Rd @ self.R)
        self.request_redraw(fast=True)
        self._spin_job = self.after(16, self._spin_tick)

    # ------------------------------------------------------------------ toasts / hotkeys
    def toast(self, text, kind='info'):
        self.toaster.show(text, kind)

    HOTKEYS = [
        ('Ctrl + O', 'Open structure'), ('Ctrl + S', 'Save image'), ('Ctrl + G', 'Save rotating GIF'),
        ('Ctrl + P', 'Save POV-Ray scene'), ('Ctrl + Shift + C', 'Copy SI caption'),
        ('Ctrl + E', 'Exclude atoms by clicking (toggle)'), ('Delete', 'Delete selected bond / centroid, exclude selected atoms'),
        ('Ctrl + W', 'Wire the selected atoms; wired ones go back to normal (no selection: click mode)'),
        ('C', 'Centroid of the selected atoms (Cg1, Cg2 …)'),
        ('Ctrl + B', 'Bond selected atoms: solid / dashed / dotted'),
        ('Click a bond', 'Select it (Delete removes it)'),
        ('Ctrl + Z / Ctrl + Y', 'Undo / redo any change'), ('Ctrl + H', 'Hydrogen atoms on / off'),
        ('L', 'Labels off / on; with atoms selected: label only those'), ('Ctrl + R', 'Reset view'), ('Ctrl + F', 'Fit to window'),
        ('Space', 'Spin preview on / off'), ('Esc', 'Clear selection / leave exclude or wire mode'),
        ('F1', 'This list'), ('Left drag', 'Rotate'), ('Middle / Alt + drag', 'Spin in the screen plane'),
        ('Shift + drag', 'Box: select everything inside'), ('Right click', 'Hide a molecule / solvent, rotate around an atom'),
        ('Right drag', 'Pan'), ('Wheel, + / -', 'Zoom'), ('Arrow keys', 'Rotate by the arrow-key step'),
        ('Click atoms', 'Select (2-4: distance / angle / torsion)'), ('Ctrl + drag label', 'Move a label'),
    ]

    def _bind_hotkeys(self):
        def guard(fn, plain):
            def h(e):
                w = self.focus_get()
                if plain and isinstance(w, (tk.Entry, tk.Text, tk.Listbox)):
                    return None             # single keys (C, L, Space, Delete) type into the box
                fn()
                return 'break'
            return h
        ctrl = {'o': self.ask_open, 's': self.save_image, 'g': self.save_gif, 'p': self.save_pov,
                'e': self.toggle_exclude, 'w': self.wire_toggle_selected, 'b': self.bond_dialog,
                'z': self.undo, 'y': self.redo, 'h': self._toggle_h, 'l': self.label_key,
                'r': lambda: (self.reset_view(), self.toast('View reset')),
                'f': lambda: (self.fit_view(), self.toast('Fitted to window'))}
        for k, fn in ctrl.items():
            self.bind(f'<Control-{k}>', guard(fn, False))
            if k not in ('z',):                                       # Caps Lock on
                self.bind(f'<Control-{k.upper()}>', guard(fn, False))
        self.bind('<Control-Shift-Z>', guard(self.redo, False))
        self.bind('<Control-Shift-C>', guard(self.copy_si, False))
        self.bind('<Control-C>', guard(self.copy_si, False))
        plain = {'<c>': self.add_centroid, '<C>': self.add_centroid, '<Delete>': self.exclude_selected,
                 '<l>': self.label_key, '<L>': self.label_key, '<space>': self.toggle_spin}
        for k, fn in plain.items():
            self.bind(k, guard(fn, True))
        self.bind('<F1>', guard(self.show_hotkeys, False))

    def show_hotkeys(self):
        """F1 / button: toggles a small window that stays in front of the main window."""
        if self._hk_win is not None:
            try:
                if self._hk_win.winfo_exists():
                    self._hk_win.destroy()
                    self._hk_win = None
                    return
            except tk.TclError:
                pass
        w = self._dialog('Hotkeys')
        w.resizable(False, False)
        self._hk_win = w
        fr = ctk.CTkFrame(w)
        fr.pack(padx=12, pady=12)
        half = (len(self.HOTKEYS) + 1) // 2           # two columns so the window fits the screen
        for n, (k, d) in enumerate(self.HOTKEYS):
            r, c = n % half, 2 * (n // half)
            ctk.CTkLabel(fr, text=k, font=ctk.CTkFont(weight='bold'), anchor='w').grid(
                row=r, column=c, sticky='w', padx=(10 if c == 0 else 24, 10), pady=1)
            ctk.CTkLabel(fr, text=d, anchor='w', wraplength=300, justify='left').grid(
                row=r, column=c + 1, sticky='w', padx=(0, 8), pady=1)
        ctk.CTkButton(w, text='Close  (F1)', command=self.show_hotkeys).pack(pady=(0, 12))
        w.protocol('WM_DELETE_WINDOW', self.show_hotkeys)
        w.bind('<F1>', lambda e: self.show_hotkeys())
        w.bind('<Escape>', lambda e: self.show_hotkeys())

    def _toggle_h(self):
        self.h_var.set(not self.h_var.get())
        self.on_setting()
        self.toast('Hydrogen atoms ' + ('shown' if self.h_var.get() else 'hidden'))

    def on_pack(self):
        """Fill the unit cell with every molecule whose centre lies inside it."""
        if self.struct is None:
            return
        on = self.pack_var.get()
        if on and not self.cell_var.get():
            self.cell_var.set(True)                  # packing is read against the cell edges
        self.status.configure(text='Packing the unit cell …' if on else 'Back to one molecule …')
        self.update_idletasks()
        self.rebuild()
        if self.model is not None and self.model.n:
            self.center = self.model.cart.mean(axis=0)
            self.fit_view(redraw=False)
        self.on_setting()
        self.toast(f'Unit cell packed: {self.model.n} atoms' if on else 'Packing off')

    def label_key(self):
        """L: no atoms selected -> all labels off (or back on); atoms selected -> label only those."""
        if self.model is None:
            return
        s = self.s
        if self.selection:
            keep = {display_name(self.model, i, s) for i in self.selection}
            s.hidden_labels = {display_name(self.model, i, s) for i in range(self.model.n)} - keep
            self.lab_on.set(True)
            self.on_labels()
            self.toast(f'Labels only on the {len(keep)} selected atom(s)')
            return
        if self.lab_on.get():
            self.lab_on.set(False)
            self.on_labels()
            self.toast('All labels off')
        else:
            s.hidden_labels = set()
            self.lab_on.set(True)
            self.on_labels()
            self.toast('All labels on')

    def _toggle_labels(self):
        self.lab_on.set(not self.lab_on.get())
        self.on_labels()
        self.toast('Labels ' + ('on' if self.lab_on.get() else 'off'))

    # ------------------------------------------------------------------ label dragging
    def _pick_label(self, x, y):
        view = self._active_view()
        pos = getattr(view, 'label_positions', [])
        if not pos:
            return None
        W, H = self._canvas_px()
        fh = self.s.label_size * self.screen_dpi() / 72.0 * (2 * self.scale / H)     # font height in A
        best, bd = None, 1e9
        for name, lx, ly in pos:
            w = 0.62 * len(name) * fh
            if lx - 0.3 * fh <= x <= lx + w + 0.3 * fh and ly - 0.3 * fh <= y <= ly + 1.2 * fh:
                d = (x - (lx + w / 2)) ** 2 + (y - (ly + 0.5 * fh)) ** 2
                if d < bd:
                    best, bd = name, d
        if best is None:                      # Ctrl+click on an atom: move its label
            i = view.pick(x, y)
            if i is not None:
                name = display_name(self.model, i, self.s)
                if any(n == name for n, _, _ in pos):
                    best = name
        return best

    def reset_label_positions(self):
        self.s.label_offsets = {}
        self.redraw_overlay()
        self.toast('Label positions reset')

    # ------------------------------------------------------------------ exclusion
    def _set_cursor(self):
        cur = 'crosshair' if (self._exclude_mode or self._wire_mode or self._geo_mode) else ''
        for w in (self.canvas.get_tk_widget(), self.gl):
            if w is not None:
                try:
                    w.configure(cursor=cur)
                except tk.TclError:
                    pass

    def toggle_exclude(self):
        if self._wire_mode:
            self.toggle_wire_mode()
        if self._geo_mode:
            self.toggle_geo_mode(self._geo_mode)
        self._exclude_mode = not self._exclude_mode
        self._set_cursor()
        self.excl_btn.configure(text='Exclude mode ON - click atoms (Esc to stop)' if self._exclude_mode
                                else 'Exclude atoms (click)  Ctrl+E',
                                fg_color='#a32020' if self._exclude_mode else ctk.ThemeManager.theme['CTkButton']['fg_color'])
        self.toast('Exclude mode: click atoms to remove them' if self._exclude_mode else 'Exclude mode off',
                   'warn' if self._exclude_mode else 'info')

    def exclude_labels(self, labels, record=True):
        new = [lab for lab in labels if lab not in self.s.excluded]
        if not new:
            return
        self.s.excluded.update(new)
        if record:
            self._exclude_hist.append(new)
        if self.model is not None:
            self.selection = [i for i in self.selection if self.model.labels[i] not in self.s.excluded]
        self._after_exclusion()
        self.toast('Excluded ' + ', '.join(new[:8]) + (' …' if len(new) > 8 else ''), 'warn')

    def _solvent_labels(self):
        if self.model is None:
            return [], set()
        sv = identify_solvents(self.model)
        return sv, {self.model.labels[i] for _, _, fr in sv for i in fr}

    def exclude_solvent(self):
        sv, labs = self._solvent_labels()
        if not labs:
            self.toast('No known solvent molecules found')
            return
        self.exclude_labels(sorted(labs, key=_natkey))
        self.toast('Solvent excluded: ' + solvent_phrase(sv), 'warn')

    def exclude_selected(self):
        """Delete key: selected bond -> delete it; selected centroids -> remove; atoms -> exclude."""
        if self.model is None:
            return
        if self.sel_bond is not None:
            self.delete_selected_bond()
            return
        if not self.selection:
            self.toast('Select atoms or a bond first (click them), then press Delete')
            return
        cgs = {self.model.labels[i] for i in self.selection if is_centroid(self.model, i)}
        labs = sorted({self.model.labels[i] for i in self.selection if not is_centroid(self.model, i)})
        if cgs:
            old = [dict(c) for c in self.s.centroids if c['name'] in cgs]
            oldb = dict(self.s.custom_bonds)

            def undo():
                self.s.centroids += old
                self.s.custom_bonds = oldb
                self._edits_changed('Centroid restored')
            self.selection = [i for i in self.selection if not is_centroid(self.model, i)]
            self._remove_centroids(cgs)
            self._exclude_hist.append(undo)
        if labs:
            self.exclude_labels(labs)

    def restore_excluded(self):
        self.s.excluded = set()
        self.s.hidden_keys = set()
        self._exclude_hist = []
        self._after_exclusion()
        self.toast('All atoms restored', 'ok')

    def _after_exclusion(self):
        n = len(self.s.excluded)
        txt = ('No atoms excluded.' if n == 0 else
               f'{n} excluded: ' + ', '.join(sorted(self.s.excluded, key=_natkey)[:40]) + (' …' if n > 40 else ''))
        if self.s.hidden_keys:
            txt += f'  {len(self.s.hidden_keys)} atom(s) hidden by right-click.'
        self.excl_lbl.configure(text=txt)
        self.request_redraw()
        self.update_status()

    def exclude_by_name(self):
        if self.struct is None:
            return

        def apply(chosen):
            added = sorted(chosen - self.s.excluded, key=_natkey)
            self.s.excluded = set(chosen)
            if added:
                self._exclude_hist.append(added)
            if self.model is not None:
                self.selection = [i for i in self.selection if self.model.labels[i] not in self.s.excluded]
            self._after_exclusion()
            self.toast(f'{len(chosen)} atom(s) excluded', 'warn' if chosen else 'ok')
        self._name_dialog('Exclude atoms by name', 'Select the atoms to exclude (Ctrl / Shift + click for several):',
                          self.s.excluded, '#a32020', apply)

    def _name_dialog(self, title, prompt, current, sel_color, on_apply):
        labels = sorted({a.label for a in self.struct.atoms}, key=_natkey)
        from .si import disordered_labels
        dis = disordered_labels(self.struct)
        solv_tag = self._solvent_labels()[1]
        elem = {a.label: a.element for a in self.struct.atoms}
        w = self._dialog(title, '400x580')
        ctk.CTkLabel(w, text=prompt, wraplength=330,
                     justify='left').pack(fill='x', padx=10, pady=(10, 4))
        fr = tk.Frame(w)
        fr.pack(fill='both', expand=True, padx=10)
        lb = tk.Listbox(fr, selectmode='extended', exportselection=False, font=('Segoe UI', 11),
                        selectbackground=sel_color, selectforeground='white')
        sb = tk.Scrollbar(fr, orient='vertical', command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        for k, lab in enumerate(labels):
            lb.insert('end', lab + ('   (solvent)' if lab in solv_tag else '') + ('   (disorder?)' if lab in dis else ''))
            if lab in current:
                lb.selection_set(k)
        row = ctk.CTkFrame(w, fg_color='transparent')
        row.pack(fill='x', padx=10, pady=4)

        def sel(pred):
            for k, lab in enumerate(labels):
                if pred(lab):
                    lb.selection_set(k)
        ctk.CTkButton(row, text='+ all H', width=60, command=lambda: sel(lambda l: elem[l] in ('H', 'D'))
                      ).pack(side='left', padx=2)
        ctk.CTkButton(row, text='+ disorder', width=80, command=lambda: sel(lambda l: l in dis)
                      ).pack(side='left', padx=2)
        solv_labs = self._solvent_labels()[1]
        ctk.CTkButton(row, text='+ solvent', width=80, command=lambda: sel(lambda l: l in solv_labs)
                      ).pack(side='left', padx=2)
        ctk.CTkButton(row, text='Clear', width=60, command=lambda: lb.selection_clear(0, 'end')
                      ).pack(side='left', padx=2)

        def apply():
            on_apply({labels[k] for k in lb.curselection()})
            w.destroy()
        btns = ctk.CTkFrame(w, fg_color='transparent')
        btns.pack(fill='x', padx=10, pady=(4, 10))
        ctk.CTkButton(btns, text='Apply', command=apply).pack(side='left', expand=True, fill='x', padx=2)
        ctk.CTkButton(btns, text='Cancel', fg_color='gray50', command=w.destroy).pack(side='left', expand=True,
                                                                                    fill='x', padx=2)
        w.after(50, lambda: (w.lift(), w.focus_force()))

    # ------------------------------------------------------------------ wire
    def toggle_wire_mode(self):
        if self._exclude_mode:
            self.toggle_exclude()
        if self._geo_mode:
            self.toggle_geo_mode(self._geo_mode)
        self._wire_mode = not self._wire_mode
        self._set_cursor()
        self.wire_btn.configure(text='Wire mode ON - click atoms (Esc to stop)' if self._wire_mode
                                else 'Wire / unwire selected  Ctrl+W',
                                fg_color='#1f7a4d' if self._wire_mode else ctk.ThemeManager.theme['CTkButton']['fg_color'])
        self.toast('Wire mode: click atoms to toggle thin-line drawing' if self._wire_mode else 'Wire mode off')

    def set_wire(self, labels, msg=None):
        self.s.wire = set(labels)
        self._after_wire()
        if msg:
            self.toast(msg, 'ok')

    def toggle_wire_atom(self, i):
        lab = self.model.labels[i]
        if lab in self.s.wire:
            self.s.wire.discard(lab)
            self.toast(f'{lab}: normal')
        else:
            self.s.wire.add(lab)
            self.toast(f'{lab}: wire')
        self._after_wire()

    def wire_selected(self):
        if self.model is None or not self.selection:
            self.toast('Select atoms first (click them)')
            return
        labs = {self.model.labels[i] for i in self.selection}
        self.set_wire(self.s.wire | labs, f'{len(labs)} atom(s) drawn as wire')

    def wire_all_but_selected(self):
        if self.model is None or not self.selection:
            self.toast('Select the atoms to keep as ellipsoids first (click them)')
            return
        keep = {self.model.labels[i] for i in self.selection}
        labs = {a.label for a in self.struct.atoms} - keep
        self.selection = []
        self.update_status()
        self.set_wire(labs, f'Everything except {len(keep)} atom(s) drawn as wire')

    def clear_wire(self):
        self.set_wire(set(), 'Wire cleared')

    def on_wire_options(self):
        self.s.wire_labels = self.wire_lab_var.get()
        try:
            r = float(self.wire_r_var.get())
            if r > 0:
                self.s.wire_radius = r
        except ValueError:
            self.wire_r_var.set(f'{self.s.wire_radius:g}')
        try:
            r = float(self.cg_r_var.get())
            if r > 0:
                self.s.centroid_radius = r
        except ValueError:
            self.cg_r_var.set(f'{self.s.centroid_radius:g}')
        self.request_redraw()

    def _after_wire(self):
        n = len(self.s.wire)
        self.wire_lbl.configure(text='No wire atoms.' if n == 0 else
                                f'{n} wire: ' + ', '.join(sorted(self.s.wire, key=_natkey)[:40]) +
                                (' …' if n > 40 else ''))
        self.request_redraw()

    def wire_by_name(self):
        if self.struct is None:
            return
        self._name_dialog('Wire atoms by name', 'Select the atoms to draw as thin wires:', self.s.wire,
                          '#1f7a4d', lambda chosen: self.set_wire(chosen, f'{len(chosen)} atom(s) drawn as wire'))

    def wire_toggle_selected(self):
        """Ctrl+W: selected atoms become wire; if the selection is (mostly) wire already, it goes back to
        normal. Without a selection: click mode."""
        if self.model is None:
            return
        if not self.selection:
            self.toggle_wire_mode()
            return
        labs = {self.model.labels[i] for i in self.selection if not is_centroid(self.model, i)}
        if not labs:
            return
        wired = labs & self.s.wire
        if len(wired) * 2 >= len(labs):
            self.set_wire(self.s.wire - labs, f'{len(labs)} atom(s) back to normal')
        else:
            self.set_wire(self.s.wire | labs, f'{len(labs)} atom(s) drawn as wire')

    # ------------------------------------------------------------------ centroids & bonds
    def _set_sel_bond(self, pair):
        self.sel_bond = pair
        self.view.sel_bond = pair

    def _edits_changed(self, msg=None, kind='ok'):
        self.rebuild()
        self._edits_note()
        if msg:
            self.toast(msg, kind)

    def _edits_note(self):
        n_cg = len(self.s.centroids)
        n_b = len(self.s.custom_bonds)
        n_d = len(self.s.deleted_bonds)
        parts = []
        if n_cg:
            parts.append(f'{n_cg} centroid(s): ' + ', '.join(c['name'] for c in self.s.centroids))
        if n_b:
            parts.append(f'{n_b} drawn/styled bond(s)')
        if n_d:
            parts.append(f'{n_d} deleted bond(s)')
        self.edit_lbl.configure(text='; '.join(parts) if parts else 'No centroids or bond edits.')

    def add_centroid(self):
        m = self.model
        if m is None:
            return
        sel = [i for i in self.selection if not is_centroid(m, i)]
        if len(sel) < 2:
            self.toast('Select the ring atoms first (click them), then press C')
            return
        used = {c['name'] for c in self.s.centroids}
        k = 1
        while f'Cg{k}' in used:
            k += 1
        name = f'Cg{k}'
        cg = dict(name=name, members=[atom_key(m, i) for i in sel])
        self.s.centroids.append(cg)
        self._exclude_hist.append(lambda: self._remove_centroids({name}))
        members = ', '.join(self._name(i) for i in sel)
        self.selection = []
        self._edits_changed(f'{name} = centroid of {members}')

    def _remove_centroids(self, names):
        self.s.centroids = [c for c in self.s.centroids if c['name'] not in names]
        keys = {f'{n}|' for n in names}
        self.s.custom_bonds = {k: v for k, v in self.s.custom_bonds.items() if not (set(k) & keys)}
        self._edits_changed('Removed ' + ', '.join(sorted(names)))

    def _pick_bond(self, x, y):
        """Front-most bond whose drawn cylinder lies under (x, y) (screen Angstrom)."""
        m = self.model
        if m is None or len(m.bonds) == 0:
            return None
        view = self._active_view()
        vis = getattr(view, 'visible', np.ones(m.n, bool))
        X = (m.cart - self.center) @ self.R.T
        a, b = m.bonds[:, 0], m.bonds[:, 1]
        ok = vis[a] & vis[b] if len(vis) == m.n else np.ones(len(a), bool)
        p, q = X[a], X[b]
        d = q[:, :2] - p[:, :2]
        L2 = np.maximum((d * d).sum(1), 1e-12)
        tpar = np.clip(((x - p[:, 0]) * d[:, 0] + (y - p[:, 1]) * d[:, 1]) / L2, 0, 1)
        cx, cy = p[:, 0] + tpar * d[:, 0], p[:, 1] + tpar * d[:, 1]
        dist = np.hypot(cx - x, cy - y)
        tol = max(self.s.bond_radius, 0.05) + 1.5 * (2 * self.scale / self._canvas_px()[1]) * 3
        hit = ok & (dist < tol) & (tpar > 0.02) & (tpar < 0.98)
        if not hit.any():
            return None
        z = p[:, 2] + tpar * (q[:, 2] - p[:, 2])
        k = np.flatnonzero(hit)
        k = k[np.argmax(z[k])]
        return (int(min(a[k], b[k])), int(max(a[k], b[k])))

    def delete_selected_bond(self):
        m = self.model
        if m is None:
            return
        pair = self.sel_bond
        if pair is None and len(self.selection) == 2:
            i, j = sorted(self.selection)
            if any(set(map(int, bb)) == {i, j} for bb in m.bonds):
                pair = (i, j)
        if pair is None:
            self.toast('Click a bond first (it turns blue), then press Delete')
            return
        key = bond_key(m, *pair)
        old_custom = self.s.custom_bonds.pop(key, None)
        self.s.deleted_bonds.add(key)

        def undo():
            self.s.deleted_bonds.discard(key)
            if old_custom is not None:
                self.s.custom_bonds[key] = old_custom
            self._edits_changed('Bond restored')
        self._exclude_hist.append(undo)
        name = f'{self._name(pair[0])}–{self._name(pair[1])}'
        self._set_sel_bond(None)
        self._edits_changed(f'Deleted bond {name}  (Ctrl+Z to undo)', 'warn')

    def restore_bonds(self):
        self.s.deleted_bonds = set()
        self._edits_changed('All deleted bonds restored')

    def clear_edits(self):
        self.s.centroids = []
        self.s.custom_bonds = {}
        self.s.deleted_bonds = set()
        self._edits_changed('Centroids and bond edits removed')

    def bond_dialog(self):
        """Ctrl+B: draw (or restyle) bonds from the first selected atom to each other selected atom."""
        m = self.model
        if m is None:
            return
        if len(self.selection) >= 2:
            first = self.selection[0]
            pairs = [(first, j) for j in self.selection[1:]]
        elif self.sel_bond is not None:
            pairs = [self.sel_bond]
        else:
            self.toast('Select 2 atoms (or the metal first, then several atoms), then press Ctrl+B')
            return
        names = ', '.join(f'{self._name(i)}–{self._name(j)}' for i, j in pairs[:6]) + (' …' if len(pairs) > 6 else '')
        cur = self.s.custom_bonds.get(bond_key(m, *pairs[0]), {})
        w = self._dialog('Bond style', '420x470')
        ctk.CTkLabel(w, text=f'{len(pairs)} bond(s): {names}', wraplength=380, justify='left', anchor='w',
                     font=ctk.CTkFont(weight='bold')).pack(fill='x', padx=12, pady=(12, 6))
        style = tk.StringVar(value=cur.get('style', 'Dashed' if len(pairs) > 1 else 'Solid'))
        width = tk.StringVar(value=cur.get('width', 'Normal'))
        prev = ctk.CTkLabel(w, text='')
        ctk.CTkLabel(w, text='Style', anchor='w').pack(fill='x', padx=12)

        def redraw_prev(*_):
            prev.configure(image=self._bond_preview(style.get(), width.get()))
        ctk.CTkSegmentedButton(w, values=BOND_STYLES, variable=style, command=redraw_prev).pack(fill='x', padx=12, pady=4)
        ctk.CTkLabel(w, text='Thickness', anchor='w').pack(fill='x', padx=12)
        ctk.CTkSegmentedButton(w, values=list(BOND_WIDTHS), variable=width, command=redraw_prev).pack(fill='x', padx=12, pady=4)
        prev.pack(pady=8)
        redraw_prev()
        ctk.CTkLabel(w, text='Cp / η5 rings: select the ring carbons and press C for a centroid, then '
                             'bond metal–Cg (solid or dashed).\nCoordinated arenes / η-ligands: select the '
                             'metal first, then the ring carbons: one bond from the metal to each '
                             '(usually dashed or dotted, thin).', wraplength=390, justify='left', anchor='w',
                     text_color=('gray30', 'gray70')).pack(fill='x', padx=12, pady=4)

        def apply():
            st = dict(style=style.get(), width=width.get())
            old = {}
            for i, j in pairs:
                k = bond_key(m, i, j)
                old[k] = (self.s.custom_bonds.get(k), k in self.s.deleted_bonds)
                self.s.custom_bonds[k] = dict(st)
                self.s.deleted_bonds.discard(k)

            def undo():
                for k, (c, d) in old.items():
                    if c is None:
                        self.s.custom_bonds.pop(k, None)
                    else:
                        self.s.custom_bonds[k] = c
                    if d:
                        self.s.deleted_bonds.add(k)
                self._edits_changed('Bond change undone')
            self._exclude_hist.append(undo)
            w.destroy()
            self._edits_changed(f'{len(pairs)} {st["style"].lower()} bond(s)')

        def remove():
            for i, j in pairs:
                k = bond_key(m, i, j)
                self.s.custom_bonds.pop(k, None)
                self.s.deleted_bonds.add(k)
            w.destroy()
            self._edits_changed(f'{len(pairs)} bond(s) removed', 'warn')
        btns = ctk.CTkFrame(w, fg_color='transparent')
        btns.pack(fill='x', padx=12, pady=(6, 12), side='bottom')
        ctk.CTkButton(btns, text='Apply', command=apply).pack(side='left', expand=True, fill='x', padx=2)
        ctk.CTkButton(btns, text='No bond', fg_color='#a32020', command=remove).pack(side='left', expand=True,
                                                                                   fill='x', padx=2)
        ctk.CTkButton(btns, text='Cancel', fg_color='gray50', command=w.destroy).pack(side='left', expand=True,
                                                                                    fill='x', padx=2)
        w.bind('<Return>', lambda e: apply())
        w.bind('<Escape>', lambda e: w.destroy())

    def _bond_preview(self, style, width):
        from .edits import dash_segments
        from PIL import ImageDraw
        W, H = 300, 60
        im = Image.new('RGB', (W, H), (235, 235, 235))
        dr = ImageDraw.Draw(im)
        px = 70.0                                         # pixels per Angstrom
        r = self.s.bond_radius * BOND_WIDTHS.get(width, 1.0) * px
        for x in (40, W - 40):
            dr.ellipse([x - 16, H / 2 - 16, x + 16, H / 2 + 16], fill=(205, 40, 205) if x == 40 else (60, 60, 60))
        p0, p1 = np.array([56.0 / px, 0, 0]), np.array([(W - 56.0) / px, 0, 0])
        for piece in dash_segments(p0, p1, style, r / px):
            if piece[0] == 'cyl':
                dr.rectangle([piece[1][0] * px, H / 2 - r, piece[2][0] * px, H / 2 + r], fill=(10, 10, 10))
            else:
                c = piece[1][0] * px
                dr.ellipse([c - 1.25 * r, H / 2 - 1.25 * r, c + 1.25 * r, H / 2 + 1.25 * r], fill=(10, 10, 10))
        return ctk.CTkImage(light_image=im, dark_image=im, size=(W, H))

    # ================================================================== file handling
    def ask_open(self):
        path = filedialog.askopenfilename(
            title='Open crystal structure',
            filetypes=[('Structure files', '*.cif *.ins *.res *.CIF *.INS *.RES'), ('CIF', '*.cif'),
                       ('SHELX', '*.ins *.res'), ('All files', '*.*')])
        if path:
            self.open_file(path)

    def open_file(self, path):
        try:
            blocks = load_structures(path)
        except Exception as e:  # noqa: BLE001 - report any parsing problem to the user
            self.toast('Could not read file', 'error')
            messagebox.showerror('Could not read file', f'{os.path.basename(path)}\n\n{e}')
            return
        self.blocks = blocks
        self.path = path
        self.file_lbl.configure(text=os.path.basename(path))
        self.si_name.set(os.path.splitext(os.path.basename(path))[0])
        names = [n or f'block {i + 1}' for i, (n, _) in enumerate(blocks)]
        self.block_menu.configure(values=names)
        self.block_var.set(names[0])
        if len(blocks) > 1:
            self.block_menu.pack(fill='x', padx=6, pady=4, after=self.file_lbl)
        else:
            self.block_menu.pack_forget()
        self._reset_structure_state()
        self._block_idx = 0
        self.select_block()
        self._after_exclusion()
        self._after_wire()
        self._reset_history()                         # undo does not reach into the previous file
        self.toast(f'Opened {os.path.basename(path)}', 'ok')

    def _reset_structure_state(self):
        """Forget everything that belongs to one structure: exclusions, wire, centroids, bond edits,
        hidden / moved labels and per-atom colors (they are keyed by atom label)."""
        self.s.hidden_labels = set()
        self.s.label_offsets = {}
        self.s.excluded = set()
        self.s.hidden_keys = set()
        self._exclude_hist = []
        self.s.wire = set()
        self.s.centroids = []
        self.s.custom_bonds = {}
        self.s.deleted_bonds = set()
        self.styles.clear_atom_overrides()
        self.geo_metal = None
        self.geo_ligands = []
        if self._geo_mode:
            self._geo_mode = None
            self._set_cursor()
        self.geo_highlight = []
        self.view.highlight = []
        self.model = None
        self.selection = []
        self.sel_bond = None
        self.view.sel_bond = None

    def select_block(self):
        names = list(self.block_menu.cget('values'))
        idx = names.index(self.block_var.get()) if self.block_var.get() in names else 0
        if self.model is not None and idx != getattr(self, '_block_idx', 0):
            self._reset_structure_state()            # another compound: edits do not carry over
            self._after_exclusion()
            self._after_wire()
            self.toast(f'Data block: {self.block_var.get()}')
        self._block_idx = idx
        self.struct = self.blocks[idx][1]
        has_q = len(self.struct.qpeaks) > 0
        self.q_switch.configure(state='normal' if has_q else 'disabled')
        if not has_q:
            self.q_var.set(False)
        self.rebuild(reset=True)
        if hasattr(self, '_committed'):
            self._reset_history()

    def rebuild(self, reset=False):
        if self.struct is None:
            return
        try:
            tol = float(self.tol_var.get())
        except ValueError:
            tol = 0.45
            self.tol_var.set('0.45')
        keep = [atom_key(self.model, i) for i in self.selection] if (self.model is not None and not reset) else []
        self.model = build_model(self.struct, complete=self.grow_var.get(), tol=tol, pack=self.pack_var.get())
        for note in apply_edits(self.model, self.s):
            self.model.notes.append(note)
        idx = {atom_key(self.model, i): i for i in range(self.model.n)}
        self.selection = [idx[k] for k in keep if k in idx]
        self._set_sel_bond(None)
        if reset or self.model.n == 0:
            self.reset_view(redraw=False)
        self._refresh_targets()
        self.update_info()
        self.on_setting()

    # ================================================================== view
    def reset_view(self, redraw=True):
        if self.model is None or self.model.n == 0:
            return
        self.center = self.model.cart.mean(axis=0)
        self._pivot = None
        self.R = default_orientation(self.model.cart)
        self.pan = np.zeros(2)
        self.fit_view(redraw)

    def fit_view(self, redraw=True):
        if self.model is None or self.model.n == 0:
            return
        W, H = self._canvas_px()
        pad = 2.2 if self.s.atom_style == 'Van der Waals' else 0.6
        self.pan = np.zeros(2)
        self.scale = fit_scale(self.model, self.R, self.center, aspect=W / H, pad=pad)
        if redraw:
            self.request_redraw()

    def view_axis(self, name):
        if self.struct is None:
            return
        A = self.struct.cell.A
        idx = 'abc'.index(name)
        self.R = view_along(A[:, idx], up_hint=A[:, (idx + 1) % 3])
        self.request_redraw()
        self.toast(f'Viewing along {name}')

    def apply_rotation(self, Rd, fast=False):
        self.R = orthonormalize(Rd @ self.R)
        self.request_redraw(fast=fast)

    def on_setting(self):
        s = self.s
        s.probability = float(self.prob_var.get().split()[0])
        s.show_h = self.h_var.get()
        s.show_cell = self.cell_var.get()
        s.show_q = self.q_var.get()
        try:
            s.q_count = int(self.qn_var.get())
        except ValueError:
            s.q_count = 20
        s.bond_coloring = self.bondcol_var.get()
        s.outline = self.outline_var.get()
        s.srgb = self.srgb_var.get()
        s.drag_quality = self.dragq_var.get()
        self.request_redraw()
        self.update_si()

    # ---- rendering scheduler: fast frames while interacting, one full-quality frame afterwards
    def request_redraw(self, fast=False):
        """fast=True while dragging/zooming (final frame after 220 ms of quiet);
        fast=False for any setting change: an immediate preview, full quality right after."""
        self._note_change()
        self._ver += 1
        if self._gl_active():
            if not fast:
                self.gl.dirty = True
            if not self._gl_pending:
                self._gl_pending = True
                self.after_idle(self._gl_refresh)
            return
        if self.s.atom_style == 'Line drawing (vector)' or self.s.drag_quality == 'Full quality':
            if self._pending is None:
                self._pending = 'final'
                self.after_idle(self._render_pending)
            else:
                self._pending = 'final'
            return
        if self._pending is None:
            self._pending = 'fast'
            self.after_idle(self._render_pending)
        if self._final_job is not None:
            self.after_cancel(self._final_job)
        self._final_job = self.after(220 if fast else 30, self._render_final)

    def _render_pending(self):
        mode = self._pending
        self._pending = None
        if mode == 'fast':
            self._render(fast=True)
        else:
            self._render(fast=False)

    def _render_final(self):
        self._final_job = None
        self._render(fast=False)

    def _render(self, fast=False):
        if self.model is None:
            return
        if fast and self._final_ver == self._ver:
            return          # a full-quality frame for this exact state is already on its way
        if not fast and self.s.atom_style != 'Line drawing (vector)':
            self._render_background()
            return
        W, H = self._canvas_px()
        try:
            self.view.draw(self.model, self.struct, self.R, self.center, self.scale, tuple(self.pan), self.s,
                           self.styles, W, H, selection=self.selection, fast=fast)
        except Exception as e:  # noqa: BLE001
            self.status.configure(text=f'Render error: {e}')
            raise
        self.canvas.draw()

    def redraw_overlay(self):
        """Labels / selection changed but not the picture: no re-render needed."""
        self._note_change()
        if self.model is None:
            return
        if self._gl_active():
            self.request_redraw(fast=True)
            return
        if self.s.atom_style == 'Line drawing (vector)':
            self.request_redraw()
            return
        if len(self.view.visible) != self.model.n:
            self.request_redraw()          # last picture belongs to an older model: draw a new one
            return
        self.view.refresh_overlay(self.model, self.s, self.selection)
        self.canvas.draw_idle()

    def _render_background(self):
        """Full-quality frame computed in a worker thread so the window never freezes;
        a newer frame (e.g. the user starts dragging again) makes the result obsolete."""
        W, H = self._canvas_px()
        gen = self._ver
        self._final_ver = gen
        s = self.s
        scale, pan = self.scale, tuple(self.pan)
        x0, x1 = pan[0] - scale * W / H, pan[0] + scale * W / H
        extent = (x0, x1, pan[1] - scale, pan[1] + scale)
        try:
            scene = build_scene(self.model, self.R, self.center, s, self.styles, cell=self.struct.cell)
        except Exception as e:  # noqa: BLE001
            self.status.configure(text=f'Render error: {e}')
            return
        bgcol = hex_to_rgb(s.background)
        model, selection = self.model, list(self.selection)

        def work():
            try:
                ss = s.antialias if W * H * s.antialias ** 2 <= 4_500_000 else 1
                rgba, oid = render_scene(scene, W, H, scale, pan, s, ss=ss, background=bgcol)
                self._results.put((gen, model, scene, rgba, oid, extent, selection))
            except Exception as e:  # noqa: BLE001
                self._results.put((gen, None, str(e), None, None, None, None))
        threading.Thread(target=work, daemon=True).start()
        if not self._polling:
            self._polling = True
            self.after(15, self._poll_results)

    def _poll_results(self):
        latest = None
        while not self._results.empty():
            latest = self._results.get_nowait()
        if latest is not None:
            gen, model, scene, rgba, oid, extent, selection = latest
            if model is None:
                self.status.configure(text=f'Render error: {scene}')
            elif gen == self._ver and model is self.model:
                self.view.show_raster(model, scene, rgba, oid, extent, self.s, self.selection, styles=self.styles)
                self.canvas.draw()
                if self.status.cget('text').startswith('Rendering'):
                    self.update_status()
        if threading.active_count() > 1 or not self._results.empty():
            self.after(15, self._poll_results)
        else:
            self._polling = False

    # ================================================================== mouse / keys
    def on_press(self, ev):
        (self.gl if self._gl_active() else self.canvas.get_tk_widget()).focus_set()
        if ev.key in ('control', 'ctrl') and getattr(ev, 'xdata', None) is not None and self.model is not None \
                and getattr(ev, 'button', 1) == 1:
            name = self._pick_label(ev.xdata, ev.ydata)
            if name:
                self._ldrag = dict(name=name, x0=ev.xdata, y0=ev.ydata,
                                   off=self.s.label_offsets.get(name, (0.0, 0.0)))
                self._drag = None
                return
        if ev.key == 'shift' and getattr(ev, 'button', 1) == 1 and self.model is not None \
                and getattr(ev, 'xdata', None) is not None:
            self._box = dict(x0=ev.xdata, y0=ev.ydata, x1=ev.xdata, y1=ev.ydata, px0=ev.x, py0=ev.y)
            self._drag = None
            return
        self._drag = dict(x=ev.x, y=ev.y, x0=ev.x, y0=ev.y, button=ev.button, shift=False, moved=False,
                          alt=(ev.key == 'alt'))

    # ---- shift-drag box selection
    def _show_box(self):
        b = self._box
        rect = None if b is None else (min(b['x0'], b['x1']), min(b['y0'], b['y1']),
                                       max(b['x0'], b['x1']), max(b['y0'], b['y1']))
        self.box_rect = rect
        if self._gl_active():
            self.request_redraw(fast=True)
            return
        from matplotlib.patches import Rectangle
        if self._box_patch is not None:
            try:
                self._box_patch.remove()
            except (ValueError, AttributeError):
                pass
            self._box_patch = None
        if rect is not None:
            self._box_patch = Rectangle((rect[0], rect[1]), rect[2] - rect[0], rect[3] - rect[1],
                                        fill=True, facecolor=(0.0, 0.47, 1.0, 0.10), edgecolor='#0077ff',
                                        linewidth=1.4, linestyle='--', zorder=40)
            self.ax.add_patch(self._box_patch)
        self.canvas.draw_idle()

    def _finish_box(self, ev):
        b = self._box
        self._box = None
        self._show_box()
        view = self._active_view()
        m = self.model
        small = ev.x is None or (abs(ev.x - b['px0']) + abs(ev.y - b['py0']) <= 3)
        if small:                                   # shift + click: add / remove one atom
            i = view.pick(b['x0'], b['y0'])
            if i is None:
                return
            idx = [i]
        else:
            x0, x1 = sorted((b['x0'], b['x1']))
            y0, y1 = sorted((b['y0'], b['y1']))
            xy = view.anchor_xy
            vis = view.visible if len(view.visible) == m.n else np.ones(m.n, bool)
            inside = vis & (xy[:, 0] >= x0) & (xy[:, 0] <= x1) & (xy[:, 1] >= y0) & (xy[:, 1] <= y1)
            idx = [int(k) for k in np.flatnonzero(inside)]
            if not idx:
                self.toast('No atoms inside the box')
                return
        if self._exclude_mode:
            self.exclude_labels(sorted({m.labels[i] for i in idx}, key=_natkey))
            return
        if self._wire_mode:
            labs = {m.labels[i] for i in idx if not is_centroid(m, i)}
            self.set_wire(self.s.wire | labs, f'{len(labs)} atom(s) drawn as wire')
            return
        if self._geo_mode == 'ligands':
            for i in idx:
                k = atom_key(m, i)
                if k != self.geo_metal and k not in self.geo_ligands:
                    self.geo_ligands.append(k)
            self._geo_highlight()
            self.update_si(force=True)
            return
        if small and idx[0] in self.selection:
            self.selection.remove(idx[0])
        else:
            self.selection += [i for i in idx if i not in self.selection]
        self._set_sel_bond(None)
        if not small:
            self.toast(f'{len(idx)} atom(s) added to the selection ({len(self.selection)} selected)')
        self.update_status()
        if self.ctarget_var.get() == 'Selected atoms':
            self.on_color_target()
        if self.starget_var.get() == 'Selected atoms':
            self.on_style_target()
        self.redraw_overlay()

    # ---- right-click menu: hide / select a molecule or solvent
    def _fragment_of(self, i):
        from .si import fragments
        for fr in fragments(self.model):
            if i in fr:
                return fr
        return [i]

    def _context_menu(self, ev):
        m = self.model
        view = self._active_view()
        i = view.pick(ev.xdata, ev.ydata) if ev.xdata is not None else None
        if i is None and ev.xdata is not None:
            pair = self._pick_bond(ev.xdata, ev.ydata)
            i = pair[0] if pair else None
        menu = tk.Menu(self, tearoff=0)
        if i is not None:
            fr = self._fragment_of(i)
            vis = view.visible if len(view.visible) == m.n else np.ones(m.n, bool)
            fr_vis = [k for k in fr if vis[k]] or fr
            sv = {tuple(sorted(f)): name for name, _, f in identify_solvents(m)}
            solvent = sv.get(tuple(sorted(fr)))
            counts = {}
            for k in fr:
                e = m.elements[k]
                if e != 'Cg':
                    counts['H' if e == 'D' else e] = counts.get('H' if e == 'D' else e, 0) + 1
            from .si import _hill
            what = f'solvent: {solvent}' if solvent else f'molecule {_hill(counts)}'
            menu.add_command(label=f'{self._name(i)}  –  {what}', state='disabled')
            menu.add_separator()
            menu.add_command(label=f'Hide this {"solvent molecule" if solvent else "molecule"} ({len(fr)} atoms)',
                             command=lambda: self.hide_atoms(fr, 'solvent molecule' if solvent else 'molecule'))
            menu.add_command(label=f'Hide atom {self._name(i)}', command=lambda: self.hide_atoms([i], 'atom'))
            menu.add_command(label='Select this molecule', command=lambda: self._select_atoms(fr_vis))
            menu.add_separator()
            menu.add_command(label=f'Rotate around {self._name(i)}', command=lambda: self.set_rotation_center(i))
            menu.add_command(label=f'Rotate around {self._name(i)} and center it',
                             command=lambda: self.set_rotation_center(i, move=True))
            if solvent:
                menu.add_command(label='Hide all solvent molecules', command=self.exclude_solvent)
        if getattr(self, '_pivot', None) is not None:
            menu.add_separator()
            menu.add_command(label='Rotate around the molecule center again', command=self.reset_rotation_center)
        if self.s.hidden_keys or self.s.excluded:
            if i is not None:
                menu.add_separator()
            menu.add_command(label='Show everything that is hidden', command=self.restore_excluded)
        if menu.index('end') is None:
            menu.add_command(label='Nothing here to hide', state='disabled')
        x, y = self.winfo_pointerxy()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def set_rotation_center(self, i, move=False):
        """Rotate about atom i. move=False keeps the picture where it is (only the pivot changes);
        move=True also brings the atom to the middle of the window."""
        m = self.model
        new = m.cart[i].copy()
        if move:
            self.pan = np.zeros(2)
        else:
            self.pan = self.pan - ((new - self.center) @ self.R.T)[:2]
        self.center = new
        self._pivot = atom_key(m, i)
        if self.gl is not None:
            self.gl.dirty = True
        self.request_redraw()
        self.toast(f'Rotating around {self._name(i)}  (right-click → molecule center to undo)')

    def reset_rotation_center(self):
        if self.model is None:
            return
        new = self.model.cart.mean(axis=0)
        self.pan = self.pan - ((new - self.center) @ self.R.T)[:2]
        self.center = new
        self._pivot = None
        if self.gl is not None:
            self.gl.dirty = True
        self.request_redraw()
        self.toast('Rotating around the molecule center')

    def hide_atoms(self, idx, what='molecule'):
        m = self.model
        keys = {atom_key(m, k) for k in idx} - self.s.hidden_keys
        if not keys:
            return
        self.s.hidden_keys |= keys
        self.selection = [k for k in self.selection if atom_key(m, k) not in self.s.hidden_keys]

        def undo():
            self.s.hidden_keys -= keys
            self._after_exclusion()
            self.toast(f'{what.capitalize()} shown again')
        self._exclude_hist.append(undo)
        self._after_exclusion()
        self.update_si()
        self.toast(f'{what.capitalize()} hidden ({len(keys)} atoms)  –  Ctrl+Z to undo', 'warn')

    def _select_atoms(self, idx):
        self.selection = [k for k in self.selection if k not in idx] + list(idx)
        self.update_status()
        self.redraw_overlay()
        self.toast(f'{len(idx)} atoms selected')

    def on_motion(self, ev):
        if self._box is not None:
            if getattr(ev, 'xdata', None) is not None:
                self._box['x1'], self._box['y1'] = ev.xdata, ev.ydata
                self._show_box()
            return
        ld = self._ldrag
        if ld is not None:
            if getattr(ev, 'xdata', None) is not None:
                self.s.label_offsets[ld['name']] = (ld['off'][0] + ev.xdata - ld['x0'],
                                                    ld['off'][1] + ev.ydata - ld['y0'])
                self.redraw_overlay()
            return
        d = self._drag
        if d is None or ev.x is None:
            return
        dx, dy = ev.x - d['x'], ev.y - d['y']
        d['x'], d['y'] = ev.x, ev.y
        if abs(ev.x - d['x0']) + abs(ev.y - d['y0']) > 3:
            d['moved'] = True
        if not d['moved']:
            return
        sp = math.radians(self.rot_speed)
        btn = d['button']
        if btn == 1 and not d.get('alt'):
            self.R = orthonormalize(rot_y(dx * sp) @ rot_x(-dy * sp) @ self.R)
        elif btn == 2 or btn == 1:                    # middle drag or Alt + drag: spin in the screen plane
            self.R = orthonormalize(rot_z(dx * sp) @ self.R)
        elif btn == 3:
            H = self._canvas_px()[1]
            self.pan -= np.array([dx, dy]) * (2 * self.scale / H)
        self.request_redraw(fast=True)

    def on_release(self, ev):
        if self._box is not None:
            self._finish_box(ev)
            return
        if self._ldrag is not None:
            self.toast(f'Moved label {self._ldrag["name"]}')
            self._ldrag = None
            self.request_redraw()
            return
        d = self._drag
        self._drag = None
        if d is None or self.model is None:
            return
        if d['moved']:
            return
        if d['button'] == 3:
            self._context_menu(ev)
            return
        if d['button'] != 1 or ev.xdata is None:
            return
        i = self._active_view().pick(ev.xdata, ev.ydata)
        if self._geo_mode:
            if i is not None:
                self._geo_click(i)
            return
        if not (self._exclude_mode or self._wire_mode):
            inside = i is not None and np.hypot(*(self._active_view().anchor_xy[i] - (ev.xdata, ev.ydata))) <= \
                self._active_view().anchor_r[i]
            pair = None if inside else self._pick_bond(ev.xdata, ev.ydata)
            if pair is not None:
                self.selection = []
                self._set_sel_bond(None if self.sel_bond == pair else pair)
                if self.sel_bond:
                    d = np.linalg.norm(self.model.cart[pair[0]] - self.model.cart[pair[1]])
                    self.status.configure(text=f'Bond {self._name(pair[0])}–{self._name(pair[1])} = {d:.4f} Å   '
                                               '(Delete removes it, Ctrl+B changes its style)')
                self.redraw_overlay()
                return
            self._set_sel_bond(None)
        if self._exclude_mode:
            if i is not None:
                self.exclude_labels([self.model.labels[i]])
            return
        if self._wire_mode:
            if i is not None:
                self.toggle_wire_atom(i)
            return
        if i is None:
            self.selection = []
        elif i in self.selection:
            self.selection.remove(i)
        else:
            self.selection.append(i)
        self.update_status()
        if self.ctarget_var.get() == 'Selected atoms':
            self.on_color_target()
        if self.starget_var.get() == 'Selected atoms':
            self.on_style_target()
        self.redraw_overlay()

    def on_scroll(self, ev):
        f = 0.9 if ev.button == 'up' else 1 / 0.9
        self.scale = min(max(self.scale * f, 0.5), 500)
        self.request_redraw(fast=True)

    def on_key(self, ev):
        step = math.radians(float(self.step_var.get()))
        rots = {'left': rot_y(-step), 'right': rot_y(step), 'up': rot_x(-step), 'down': rot_x(step)}
        if ev.key in rots:
            self.apply_rotation(rots[ev.key], fast=True)
        elif ev.key == 'escape':
            if self._exclude_mode:
                self.toggle_exclude()
                return
            if self._wire_mode:
                self.toggle_wire_mode()
                return
            if self._geo_mode:
                self.toggle_geo_mode(self._geo_mode)
                return
            self.selection = []
            self._set_sel_bond(None)
            self.update_status()
            self.redraw_overlay()
        elif ev.key in ('+', '='):
            self.scale *= 0.9
            self.request_redraw(fast=True)
        elif ev.key == '-':
            self.scale /= 0.9
            self.request_redraw(fast=True)

    # ================================================================== text
    def _name(self, i):
        return display_name(self.model, i, self.s)

    def update_status(self):
        m = self.model
        sel = self.selection
        P = [m.cart[i] for i in sel]
        if not sel:
            txt = 'Click atoms to select / measure (1 = info, 2 = distance, 3 = angle, 4 = torsion, more = selection).'
        elif len(sel) == 1 and is_centroid(m, sel[0]):
            i = sel[0]
            cg = next((c for c in self.s.centroids if c['name'] == m.labels[i]), None)
            mem = ', '.join(k.split('|')[0] for k in cg['members']) if cg else ''
            txt = f'{m.labels[i]} = centroid of {mem}   (Delete removes it)'
        elif len(sel) == 1:
            i = sel[0]
            f = self.struct.cell.to_frac(m.cart[i])
            ueq = np.trace(m.ucart[i]) / 3
            txt = (f'{self._name(i)} ({m.elements[i]})  xyz = {f[0]:.4f} {f[1]:.4f} {f[2]:.4f}  '
                   f'Ueq = {ueq:.4f} Å²  occ = {m.occ[i]:.3f}  PART {m.part[i]}'
                   + (f'  [{m.symop[i]}]' if m.generated[i] else ''))
        elif len(sel) == 2:
            d = np.linalg.norm(P[0] - P[1])
            txt = f'd({self._name(sel[0])}–{self._name(sel[1])}) = {d:.4f} Å'
        elif len(sel) > 4:
            names = ', '.join(self._name(i) for i in sel[:12]) + (' …' if len(sel) > 12 else '')
            txt = f'{len(sel)} atoms selected: {names}   (click again to deselect, Esc clears all)'
        elif len(sel) == 3:
            v1, v2 = P[0] - P[1], P[2] - P[1]
            ang = math.degrees(math.acos(np.clip(v1 @ v2 / np.linalg.norm(v1) / np.linalg.norm(v2), -1, 1)))
            txt = (f'∠({self._name(sel[0])}–{self._name(sel[1])}–{self._name(sel[2])}) = {ang:.2f}°   '
                   f'({np.linalg.norm(v1):.4f} Å, {np.linalg.norm(v2):.4f} Å)')
        else:
            b0, b1, b2 = P[0] - P[1], P[2] - P[1], P[3] - P[2]
            b1n = b1 / np.linalg.norm(b1)
            v = b0 - (b0 @ b1n) * b1n
            w = b2 - (b2 @ b1n) * b1n
            tor = math.degrees(math.atan2(np.cross(b1n, v) @ w, v @ w))
            txt = f'torsion({"–".join(self._name(i) for i in sel)}) = {tor:.2f}°'
        self.status.configure(text=txt)
        self.update_si()

    def update_info(self):
        st, m = self.struct, self.model
        a, b, c, al, be, ga = st.cell.params
        lines = [f'Title:   {st.title}', f'Formula: {st.formula or "?"}', f'Space group: {st.spacegroup or "?"}',
                 f'a = {a:.4f}  α = {al:.3f}', f'b = {b:.4f}  β = {be:.3f}', f'c = {c:.4f}  γ = {ga:.3f}',
                 f'V = {st.cell.volume:.2f} Å³', f'Atoms (asym.): {len(st.atoms)}   shown: {m.n}',
                 f'Anisotropic: {int(m.aniso.sum())}   bonds: {len(m.bonds)}']
        if st.qpeaks:
            lines.append(f'Q-peaks: {len(st.qpeaks)} (max {max(q.peak_height for q in st.qpeaks):.2f} e/Å³)')
        for w in st.warnings + m.notes:
            lines.append('⚠ ' + w)
        self.info.configure(state='normal')
        self.info.delete('1.0', 'end')
        self.info.insert('1.0', '\n'.join(lines))
        self.info.configure(state='disabled')
        self.update_status()

    # ================================================================== export actions
    def _base(self):
        return os.path.splitext(os.path.basename(self.path or 'structure'))[0]

    def _export_args(self):
        return (self.model, self.struct, self.R, self.center, self.scale, tuple(self.pan), self.s, self.styles)

    def _export_scale(self, w, h):
        """Half-height for an export of w x h pixels that keeps everything visible on screen."""
        W, H = self._canvas_px()
        return self.scale * max(1.0, (W / H) / (w / h))

    def _export_settings(self, height_in, export_scale=None):
        """Copy of the settings with label / line sizes scaled so the exported picture looks like
        the screen (same label size relative to the molecule), unless 'As set' is chosen."""
        s2 = copy.copy(self.s)
        s2.hidden_labels = set(self.s.hidden_labels)
        if self.lsize_mode.get() == 'Match screen':
            H = self._canvas_px()[1]
            f = self.screen_dpi() * height_in * self.scale / (H * (export_scale or self.scale))
            s2.label_size = self.s.label_size * f
            s2.line_width = self.s.line_width * f
            s2.halo_width = self.s.halo_width * f
        return s2

    def _export_args_for(self, height_in, export_scale=None):
        args = list(self._export_args())
        if export_scale is not None:
            args[4] = export_scale
        args[6] = self._export_settings(height_in, export_scale)
        args[7] = self.styles.copy()
        return args

    # ---- background jobs with progress bar
    def _run_job(self, title, func):
        """func(report, cancel) runs in a worker thread; progress bar + Cancel button meanwhile."""
        if self._busy:
            messagebox.showinfo('Busy', 'An export is already running.')
            return
        self._busy = True
        self.progress.set(0)
        self.progress.pack(side='left', padx=(0, 10))
        self.cancel_btn.pack(side='left', padx=(0, 10))
        self.status.configure(text=f'{title} …')
        for b in (self.save_btn, self.gif_btn):
            b.configure(state='disabled')
        cancel = threading.Event()
        self._job_cancel = cancel

        def report(frac, msg=''):
            if cancel.is_set():
                raise ExportCancelled('Export cancelled')
            self._jobq.put(('progress', float(frac), msg))

        def work():
            try:
                res = func(report, cancel)
                self._jobq.put(('done', res, ''))
            except ExportCancelled:
                self._jobq.put(('cancelled', '', ''))
            except Exception as e:  # noqa: BLE001
                self._jobq.put(('error', str(e), ''))
        self._job_thread = threading.Thread(target=work, daemon=True)
        self._job_thread.start()
        self.after(60, self._poll_job)

    def cancel_job(self, wait=False):
        if not self._busy:
            return
        self._job_cancel.set()
        self.status.configure(text='Cancelling …')
        if wait:
            t0 = time.monotonic()
            while self._job_thread.is_alive() and time.monotonic() - t0 < 5.0:
                self._job_thread.join(0.1)

    def on_close(self):
        if self._busy:
            if not messagebox.askyesno('Export running', 'An export is still running. Stop it and quit?'):
                return
            self.cancel_job(wait=True)       # also stops the GIF worker processes at once
        self.stop_spin()
        self.destroy()

    def _poll_job(self):
        done = False
        while not self._jobq.empty():
            kind, val, msg = self._jobq.get_nowait()
            if kind == 'progress':
                self.progress.set(max(0.0, min(1.0, val)))
                if msg:
                    self.status.configure(text=msg)
            elif kind == 'done':
                self.status.configure(text=f'Saved {val}')
                self.toast(f'Saved {os.path.basename(str(val))}', 'ok')
                done = True
            elif kind == 'cancelled':
                self.status.configure(text='Export cancelled')
                self.toast('Export cancelled', 'warn')
                done = True
            else:
                self.status.configure(text='Export failed')
                self.toast('Export failed', 'error')
                messagebox.showerror('Export failed', val)
                done = True
        if done:
            self._busy = False
            self.progress.pack_forget()
            self.cancel_btn.pack_forget()
            for b in (self.save_btn, self.gif_btn):
                b.configure(state='normal')
        else:
            self.after(60, self._poll_job)

    def save_image(self):
        if self.model is None:
            return
        try:
            w, h, dpi = int(self.w_px.get()), int(self.h_px.get()), int(self.dpi_var.get())
        except ValueError:
            messagebox.showerror('Export', 'Width / height must be whole numbers of pixels.')
            return
        engine = self.engine_var.get()
        if engine.startswith('POV') and not self.povexe:
            messagebox.showerror('POV-Ray', 'POV-Ray was not found. Use "Browse for POV-Ray program…".')
            return
        path = filedialog.asksaveasfilename(
            title='Save image', initialfile=f'{self._base()}_ortep.png', defaultextension='.png',
            filetypes=[('PNG', '*.png'), ('TIFF', '*.tif'), ('JPEG', '*.jpg'), ('SVG (labels as vector)', '*.svg'),
                       ('PDF (labels as vector)', '*.pdf')])
        if not path:
            return
        scale = self._export_scale(w, h)
        args = self._export_args_for(h / dpi, scale)
        opts = dict(width_px=w, height_px=h, dpi=dpi, transparent=self.trans_var.get(),
                    antialias=self.aa_var.get(), shadows=self.shadow_var.get(), engine=engine,
                    povray_exe=self.povexe, reflections=self.refl_var.get())
        self._run_job(f'Rendering {w} × {h}', lambda rep, cancel: export_image(path, *args, progress=rep, **opts))

    def save_pov(self):
        if self.model is None:
            return
        path = filedialog.asksaveasfilename(title='Save POV-Ray scene', initialfile=f'{self._base()}.pov',
                                            defaultextension='.pov', filetypes=[('POV-Ray scene', '*.pov')])
        if not path:
            return
        try:
            w, h, dpi = int(self.w_px.get()), int(self.h_px.get()), int(self.dpi_var.get())
        except ValueError:
            w, h, dpi = DEFAULT_WIDTH, DEFAULT_HEIGHT, 600
        scale = self._export_scale(w, h)
        export_pov(path, *self._export_args_for(h / dpi, scale), aspect=w / h,
                   include_labels=self.pov_labels.get(), image_height_in=h / dpi,
                   shadows=True, reflections=self.refl_var.get(), width_px=w, height_px=h,
                   antialias=self.aa_var.get())
        ini = os.path.splitext(path)[0] + '.ini'
        self.status.configure(text=f'Saved {path} and {os.path.basename(ini)} ({w}×{h}, AA 0.3)')
        self.toast(f'Saved {os.path.basename(path)} + .ini', 'ok')

    def save_gif(self):
        if self.model is None:
            return
        try:
            frames, deg = int(self.gif_frames.get()), float(self.gif_deg.get())
            delay, w, h = int(self.gif_delay.get()), int(self.gif_w.get()), int(self.gif_h.get())
        except ValueError:
            messagebox.showerror('GIF', 'GIF settings must be numbers.')
            return
        path = filedialog.asksaveasfilename(title='Save rotating GIF', initialfile=f'{self._base()}_spin.gif',
                                            defaultextension='.gif',
                                            filetypes=[('GIF', '*.gif'), ('Animated PNG (true color)', '*.png')])
        if not path:
            return
        scale = self._export_scale(w, h)
        args = self._export_args_for(h / 100.0, scale)
        self.stop_spin()
        opts = dict(width_px=w, height_px=h, frames=frames, degrees=deg, axis=self.gif_axis.get(),
                    delay_ms=delay, shadows=self.gif_shadow.get(), direction=self.gif_dir.get(),
                    transparent=self.gif_trans.get(), grain=self.gif_grain.get(), matte=self._check_matte())
        self._run_job('Rendering GIF', lambda rep, cancel: export_gif(path, *args, progress=rep, cancel=cancel,
                                                                      **opts))


def main(path=None):
    import logging
    logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
    app = OrtepApp(path)
    app.mainloop()
