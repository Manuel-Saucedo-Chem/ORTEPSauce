"""Built-in tutorial window (opens by itself the first time ORTEPSauce starts)."""
import tkinter as tk

import customtkinter as ctk

# (title, tab to show or None, text)
PAGES = [
    ('Welcome to ORTEPSauce', 'Structure',
     'Open a .cif, .res or .ins file with Ctrl+O (or the "Open structure…" button).\n\n'
     '•  Left drag: rotate        •  Wheel: zoom        •  Right drag: pan\n'
     '•  Middle drag (or Alt + drag): spin in the screen plane\n'
     '•  Ctrl+Z / Ctrl+Y undo and redo every change.\n'
     '•  F1 shows all hotkeys at any time.\n\n'
     'Use Next ▸ to go through the main features. You can reopen this tutorial any time with the '
     '📖 Tutorial button at the bottom right.'),
    ('Labels', 'Labels',
     'Labels start OFF so a freshly opened structure is not cluttered.\n\n'
     '1.  Click an atom to select it (Shift + drag a box to select many, double click to select a '
     'whole molecule).\n'
     '2.  Press  L  → the selected atoms get labels. Press L again on labelled atoms to remove them.\n'
     '3.  L with nothing selected turns all labels on / off.\n'
     '4.  Ctrl + drag a label to move it around. "Reset label positions" puts them back.\n\n'
     'In the Labels tab you set the font, size (type any number), bold / italic, color, halo, '
     'the element symbol in the atom color and the suffix of symmetry-generated atoms (Fe1*).'),
    ('Selecting, hiding and bonds', 'Structure',
     '•  Double click an atom: selects the whole molecule / fragment.\n'
     '•  Right click with atoms selected: edit only the bonds among the selected atoms, show only '
     'the selected molecules, hide or invert the selection.\n'
     '•  Right click an atom: hide that molecule or solvent, rotate around the atom.\n'
     '•  Ctrl+B: bond style (solid, dashed, dotted, thin…) from the first selected atom to the others.\n'
     '•  C: centroid (Cg) of the selected atoms, e.g. for Cp rings.\n'
     '•  H add (Structure tab): with hydrogens off, click an atom to show only its H atoms '
     '(e.g. a hydride or an N–H). Click again to hide them, Esc to stop.\n\n'
     'Disorder: Structure tab → Exclude atoms → By name…  Type the label ending of each part '
     '(C21 / C21*: major empty, minor *;  C55A / C55B: major A, minor B) and press "+ minor part" '
     'to select the whole disordered part at once, then Apply.'),
    ('Packing, polymers and contacts', 'Structure',
     'Structure tab → "Packing, molecules & contacts":\n\n'
     '•  Range: type how many cells to pack along a, b, c (e.g. a 0 → 2) and press "Pack this range". '
     '"Whole molecules" keeps every molecule whose centre is inside; "Atoms in range" is for polymers '
     'and networks (chains are cut at the edges).\n'
     '•  Molecules…: a list of every molecule with tick marks – select, show only, hide or show them.\n'
     '•  Grow bonds +1: adds the atoms bonded to the selected atoms across symmetry; press again to '
     'extend a polymer one step at a time.\n'
     '•  Short contacts: adds the neighbouring molecules closer than the sum of the vdW radii (+ the '
     'value you type) and draws dashed lines with the distance.\n'
     '•  Remove grown: back to the normal picture.'),
    ('Colors', 'Color',
     '1.  Pick a scheme under Preset and press "Apply preset".\n'
     '2.  "Apply to" chooses what you recolor: an element (Fe, N, C …), the bonds, bonds to H, '
     'the cut-out octant faces … or "Selected atoms" for the atoms you clicked.\n'
     '3.  Click a POV-Ray color in the list, or "Custom color…" for any color (hex values work).\n'
     '4.  Bond coloring and background are at the bottom of the tab.\n\n'
     'To keep your colors for every new structure press  ★ Save tab as default  at the bottom of '
     'the Color tab (see the next page).'),
    ('Saving your own defaults', 'Color',
     'Every tab has two buttons at the bottom:\n\n'
     '•  ★ Save tab as default – the current settings of that tab (colors, styles, label font, '
     'export size …) are used every time ORTEPSauce starts.\n'
     '•  ↺ Reset tab to defaults – back to your saved defaults, or to the program defaults. The '
     'same menu can forget your saved defaults.\n\n'
     'Defaults are stored per tab in the file .ortepsauce.json in your user folder, so you can '
     'save, for example, your colors without changing the label settings. Updates never change them.\n\n'
     'Same settings for the whole group: ⚙ Settings & updates → "Export lab settings file…" and share '
     'the file; everyone else uses "Import lab settings file…" once.'),
    ('Supporting information (SI tab)', 'SI',
     '1.  Select atoms in the picture: click the metal first, then its ligand atoms (or Shift + drag '
     'a box around the metal center).\n'
     '2.  The caption lists the bond lengths and angles between the selected atoms, with the '
     's.u. values taken from the CIF geometry tables. Bonds are written metal first (Fe1–N1).\n'
     '3.  Type the figure number and the compound name / number; choose whether symmetry repeats '
     'are skipped and whether solvent is mentioned.\n'
     '4.  "Copy to clipboard" and paste into your SI document.\n\n'
     'Geometry index: press "Auto" (or choose the metal center and the ligands) to get τ₄, τ₄′ or '
     'τ₅, and switch it on to add it to the caption.\n'
     'Buried volume: %V_bur of the whole complex, or of one ligand (double click it, then "Ligand = '
     'selection"). References for τ₄ / τ₄′ / τ₅ / %V_bur are added to the caption automatically.'),
    ('Styles and export', 'Export',
     '•  Styles tab: ORTEP ellipsoids, ball and stick, … and two vector styles: "Line drawing" and '
     '"ORTEP-3 classic" (white ellipsoids, element-colored outlines, hatched octants, H as sticks).\n'
     '•  Ctrl+S saves the picture: PNG / TIFF / JPEG for the shaded styles; with a vector style '
     'SVG, PDF and EPS keep every line and label editable (e.g. in Illustrator or Inkscape).\n'
     '•  Ctrl+G saves a rotating GIF, Ctrl+P a POV-Ray scene.\n\n'
     'Use "⚙ Settings & updates" at the bottom to update ORTEPSauce.'),
    ('How to cite ORTEPSauce', None,
     'If ORTEPSauce helped with figures, SI captions or analysis in your work, please cite it:\n\n'
     '    Saucedo Cañas, M. A.; Fortier, S. ORTEPSauce [Computer software]; Zenodo, 2026. '
     'DOI: 10.5281/zenodo.24170231\n\n'
     'The "❝ Citation" button at the bottom right copies this reference and opens the DOI page.\n\n'
     'When you report τ₄ / τ₄′ / τ₅ or %V_bur, also cite the original papers – switch on '
     '"Add references to the caption" in the SI tab, or use "Copy all references".\n\n'
     'That is all – enjoy ORTEPSauce!'),
]


class Tutorial:
    def __init__(self, app, page=0, on_close=None):
        self.app = app
        self.on_close = on_close
        self.page = page
        w = self.w = ctk.CTkToplevel(app)
        w.title('ORTEPSauce tutorial')
        from .gui import set_window_icon
        set_window_icon(w)
        w.geometry('600x500')
        w.minsize(520, 440)
        try:
            w.transient(app)
        except tk.TclError:
            pass
        self.title = ctk.CTkLabel(w, text='', font=ctk.CTkFont(size=20, weight='bold'), anchor='w')
        self.title.pack(fill='x', padx=18, pady=(16, 2))
        self.step = ctk.CTkLabel(w, text='', text_color='gray50', anchor='w')
        self.step.pack(fill='x', padx=18)
        self.body = ctk.CTkTextbox(w, wrap='word', font=ctk.CTkFont(size=14), activate_scrollbars=True)
        self.body.pack(fill='both', expand=True, padx=16, pady=8)
        bar = ctk.CTkFrame(w, fg_color='transparent')
        bar.pack(fill='x', padx=16, pady=(0, 6))
        self.prev_btn = ctk.CTkButton(bar, text='◂ Back', width=90, command=lambda: self.go(-1))
        self.prev_btn.pack(side='left')
        self.goto_btn = ctk.CTkButton(bar, text='', width=150, fg_color='gray45', hover_color='gray35',
                                      command=self.show_tab)
        self.goto_btn.pack(side='left', padx=8)
        self.next_btn = ctk.CTkButton(bar, text='Next ▸', width=90, command=lambda: self.go(1))
        self.next_btn.pack(side='right')
        low = ctk.CTkFrame(w, fg_color='transparent')
        low.pack(fill='x', padx=16, pady=(0, 12))
        self.startup = tk.BooleanVar(value=bool(app.cfg.get('tutorial_at_startup', False)))
        ctk.CTkCheckBox(low, text='Show this tutorial every time ORTEPSauce starts', variable=self.startup
                        ).pack(side='left')
        ctk.CTkButton(low, text='Close', width=80, fg_color='gray50', command=self.close).pack(side='right')
        w.protocol('WM_DELETE_WINDOW', self.close)
        w.bind('<Escape>', lambda e: self.close())
        w.bind('<Right>', lambda e: self.go(1))
        w.bind('<Left>', lambda e: self.go(-1))
        self.render()
        w.after(80, lambda: (w.lift(), w.focus_force()))

    def render(self):
        title, tab, text = PAGES[self.page]
        self.title.configure(text=title)
        self.step.configure(text=f'Step {self.page + 1} of {len(PAGES)}')
        self.body.configure(state='normal')
        self.body.delete('1.0', 'end')
        self.body.insert('1.0', text)
        self.body.configure(state='disabled')
        self.prev_btn.configure(state='normal' if self.page > 0 else 'disabled')
        last = self.page == len(PAGES) - 1
        self.next_btn.configure(text='Finish ✓' if last else 'Next ▸')
        if tab:
            self.goto_btn.configure(text=f'Show the {tab} tab', state='normal', command=self.show_tab)
        elif title.startswith('How to cite') and hasattr(self.app, 'show_citation'):
            self.goto_btn.configure(text='❝ Citation window', state='normal', command=self.app.show_citation)
        else:
            self.goto_btn.configure(text='', state='disabled')
        self.show_tab()

    def show_tab(self):
        tab = PAGES[self.page][1]
        if tab:
            try:
                self.app.tabs.set(tab)
            except Exception:  # noqa: BLE001
                pass

    def go(self, d):
        if self.page + d >= len(PAGES):
            self.close()
            return
        self.page = max(0, min(len(PAGES) - 1, self.page + d))
        self.render()

    def close(self):
        try:
            self.app.cfg['tutorial_seen'] = True
            self.app.cfg['tutorial_at_startup'] = bool(self.startup.get())
            if self.on_close:
                self.on_close()
        finally:
            try:
                self.w.destroy()
            except tk.TclError:
                pass

    def exists(self):
        try:
            return bool(self.w.winfo_exists())
        except tk.TclError:
            return False
