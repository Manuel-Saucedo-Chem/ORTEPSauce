# ORTEPSauce V1.0

ORTEP-style viewer for small-molecule crystal structures from **.cif**, **.ins** and **.res** files,
with POV-Ray-style shaded rendering, high-resolution image export, POV-Ray scene export, rotating
GIFs, SI figure captions and coordination-geometry indices (τ₄, τ₄′, τ₅).
(Formerly "ORTEP Viewer" 0.1-1.9.)

## Run (Windows cmd)
    cd /d C:\Users\manue\Downloads\ORTEPSauce_V1.0
    py -m pip install -r ortepsauce\requirements.txt
    py -m ortepsauce                       :: GUI
    py -m ortepsauce structure.cif         :: GUI with a file
    py -m ortepsauce x.res --export x.png                        :: 6400 x 4800, AA
    py -m ortepsauce x.cif --export x.gif                        :: 1600 x 1200, 200 frames
    py -m ortepsauce x.cif --export x.pov             :: POV-Ray scene

## Make a stand-alone .exe (Windows)
In the extracted folder (next to the `ortepsauce` folder) double-click **build_exe.bat**, or in cmd:

    cd /d C:\Users\manue\Downloads\ORTEPSauce_V1.0
    build_exe.bat

Result: `dist\ORTEPSauce\ORTEPSauce.exe`. Keep the whole `dist\ORTEPSauce` folder together.

## Undo, defaults
* **Ctrl+Z / Ctrl+Y** (or Ctrl+Shift+Z) undo / redo any change: settings on every tab, colors, styles,
  exclusions, hidden molecules, wire, centroids, bonds, labels. Each click / key press is one step; a
  slider drag or a typed number is one step. Opening a file starts a new history.
* Every tab has **↺ Reset tab to defaults** and **★ Save tab as default** at the bottom. Saved defaults
  (in ~/.ortepsauce.json) are used at every start; Reset then offers your saved defaults or the
  program defaults.

## Tabs
* **Structure** – open file / CIF data block, complete molecules by symmetry, bond tolerance,
  hydrogens, unit cell, Q-peaks, exclude atoms, *Wire (thin lines)* for busy parts, structure info.
* **Labels** – *Show labels* on/off, which atoms (All / Non-H / Heavy atoms / Metals only), font, size,
  bold/italic, color, halo, offset, symmetry suffix; hide labels of selected atoms, show only selected,
  restore all.
* **View** – reset / fit, view along a, b, c, 90° turns, rotate speed, arrow-key step, drag quality,
  light direction, fill and ambient light, outlines, POV-Ray gamma.
* **Color** – presets (POV-Ray ORTEP-3 / Jmol / Monochrome); color per element, bonds, bonds to H,
  equators, cut-out faces or the selected atoms, from the full POV-Ray colors.inc list or a custom
  color; bond coloring; background.
* **Styles** – ORTEP ellipsoids, Van der Waals, RMSD surface, Ball and Stick, Rods, MSD surface,
  Line drawing (vector); probability; *Modify*: Ellipse style (PlainEllipse / BoundaryEllipse /
  CutoutEllipse), Finish and Texture per target; bond / H / band / ball / rod sizes.
* **Export** – PNG/TIFF/JPEG/SVG/PDF at any size and dpi (antialiased, optional transparency);
  POV-Ray .pov (optionally rendered directly if POV-Ray is installed); rotating GIF.

## Mouse / keys
left-drag rotate · middle- or Alt-drag spin in plane · shift-drag box selection · right-click: hide a molecule / solvent, rotate around an atom · right-drag pan · wheel or +/- zoom ·
arrow keys rotate · click 1–4 atoms for info / distance / angle / torsion (also selects atoms for
per-atom color, style and label changes) · Esc clears · Ctrl+O open · Ctrl+S save image.

## Rendering notes
* Shaded styles use a numpy z-buffer renderer with exact ray intersections and POV-Ray finish
  parameters copied from POV-Ray 3.7's finish.inc / metals.inc / textures.inc. Compared with a real
  POV-Ray render of the exported scene it matches closely, but has no cast shadows or true
  reflections, and texture patterns (granite, brushed, ...) are approximations.
* Output is sRGB-encoded like POV-Ray 3.7 with `assumed_gamma 1.0` (switch off under View).
* Sizes are in Angstrom (bond 0.06, bond-to-H 0.035, H sphere 0.15). The radii in ORTEP-3's .pov
  files are in ORTEP-3's own plot units, so they are not copied numerically.
* While dragging, a reduced-resolution preview is drawn; the full-quality frame is computed in a
  background thread and replaces it when ready.

## Files
| file | role |
|---|---|
| cif_reader.py / shelx_reader.py | parsers -> `Structure` |
| structure.py | Cell, symmetry operators, Atom/Structure classes |
| model.py | symmetry growth, Cartesian ADPs, bonds |
| styles.py | POV-Ray colors, finishes, textures; per-element / per-object style table |
| settings.py | all display settings |
| scene.py | model + view + styles -> 3D primitives (shared by preview and POV export) |
| raster.py | shaded renderer |
| renderer.py | vector line-drawing ORTEP |
| canvas_view.py | draws a frame + labels into matplotlib (GUI, export, GIF) |
| export.py / pov_export.py | image, GIF and POV-Ray export |
| gui.py | customtkinter app |

## Changelog
**ORTEPSauce V1.0** (continues ORTEP Viewer 1.9)
* Renamed to ORTEPSauce (`py -m ortepsauce`, ORTEPSauce.exe, settings in ~/.ortepsauce.json; the
  POV-Ray path from the old ~/.ortepviewer.json is picked up).
* GIF defaults: 200 frames, 360°, 50 ms, 1600 × 1200 (one turn in 10 s at 20 frames/s), no grain.
* Label size: type any number (1-500 pt) or pick from the list.
* Full undo / redo of every change (Ctrl+Z, Ctrl+Y / Ctrl+Shift+Z).
* Per-tab Reset to defaults / Save as default buttons (colors included).
* Ctrl+W: selected atoms become wire; if the selection is (mostly) wire already it goes back to
  normal. Ctrl shortcuts now also work while the cursor is in a text box, and with Caps Lock on.
* Selection numbers keep a readable size when labels are very large.

**1.9**
* Right-click an atom: hide that molecule or solvent molecule (only that copy; Ctrl+Z brings it back,
  Restore all shows everything), hide one atom, select the molecule, rotate around that atom
  (picture stays put) or rotate around it and center it; right-click again to go back to the
  molecule center. Hidden solvent is reported as omitted in the SI caption.
* Shift + drag draws a box and selects every visible atom inside it (adds to the selection; in
  exclude / wire / ligand mode it acts on the boxed atoms). Shift + click adds / removes one atom.
* Spin in the screen plane: middle drag or Alt + drag (Shift + drag is now the box).

**1.8**
* build_exe.bat + ortepviewer_launcher.py + make_icon.py: builds a stand-alone ORTEP Viewer.exe
  with PyInstaller (multiprocessing support for the parallel GIF export, program icon).

**1.7**
* SI tab: geometry indices τ₄ (Houser 2007), τ₄′ (Okuniewski 2015) and τ₅ (Addison 1984). The metal
  centre(s) and the atoms bonded to them are found automatically (metal–metal contacts are not
  counted as ligands); *Metal center* and *Ligands* buttons turn the cursor into a crosshair to pick
  them by hand (orange ring = metal, green rings = ligands; a Cg centroid can be a ligand), *Auto*
  goes back. Optional sentence for the caption ("Geometry indices: τ₄ = 0.07 and τ₄′ = 0.07 (Pd1).").

**1.6**
* Structure tab: *Pack unit cell* (under *Unit cell*) fills the cell with every molecule whose centre
  lies inside it, completed by symmetry; the cell is switched on with it. CLI: --pack.
* L: no atoms selected - all labels off (press again: all labels back on); atoms selected - only
  those atoms are labelled. Ctrl+L does the same.
* Hotkeys window in two columns so it fits on the screen.

**1.5** (based on the 1.1 interface)
* Back to the 1.1 window (customtkinter); the Qt interface of 1.2-1.4 was removed.
* Bug fixes carried over from the review: per-atom colors, exclusions, wire, centroids, bond edits
  and label edits no longer carry over to the next file or to another data block of a multi-block
  CIF; asymmetric-unit ellipsoids no longer depend on the order of the CIF symmetry operators;
  changing the symmetry suffix keeps hidden / moved labels of symmetry atoms; the software view no
  longer crashes when labels are redrawn before a new picture is ready; selection rings are not
  drawn for hidden atoms.
* Exports have a Cancel button; closing the window during a GIF export stops the worker
  processes at once instead of rendering every remaining frame in the background.

**1.1**
* Centroids: select ring atoms and press **C** -> dummy atom Cg1, Cg2 ... (drawn as a small sphere,
  labelled, selectable, measurable, listed in the SI caption, Delete removes it).
* Bonds: click a bond to select it (blue), **Delete** removes it (Ctrl+Z undoes). **Ctrl+B** with two
  or more atoms selected (metal first) draws bonds from the first atom to the others - Solid, Dashed or
  Dotted, Normal / Thin / Hairline - or restyles existing ones (e.g. M–Cg for Cp rings, dashed M–C
  bonds for coordinated arenes). Edits are kept when the model is rebuilt; Restore bonds / Remove all.
* **Ctrl+W** turns the selected atoms into wire; if they are all wire already they become normal again
  (no selection: click mode).
* Zr defaults to the Fe / Ti color (#ce28ce).
* Hotkeys window stays in front of the main window; F1 or the button opens and closes it.
* Cleaner tabs: rarely used numbers (bond tolerance, Q-peaks, wire / centroid radius, sizes, rotate
  speed, arrow step, drag quality, fill / ambient light, gamma, image width / height, antialiasing,
  renderer, reflections, label-size mode, GIF frames / rotation / delay / pixels / grain, POV-Ray)
  moved into folded **Advanced** sections at the bottom of each tab.

**1.0**
* Wire (thin lines): draw chosen parts of the molecule as thin element-colored wires so the core
  stands out (Structure tab): click mode (Ctrl+W), by name (with + H / + disorder / + solvent),
  selected atoms, everything except the selection, clear; wire radius; labels on wire atoms off by
  default. Works in the live view, image/GIF export, line drawing and POV-Ray scenes.
* Ti defaults to the Fe color (#ce28ce).
* GIF quality: Speckled grain is left out of GIF frames (it changed randomly from frame to frame and
  shimmered; average brightness kept the same) - switch *Speckle grain in GIF* to keep it.
  *Slide color (edge matte)*: soft edges and label halos are blended onto the color of the slide the
  GIF goes on (no white rim on dark slides). Palette built only from the molecule's pixels of
  8 frames (median cut + k-means). Size presets; default 1600 × 1200.
* Command line: label halo and line widths now scale with the dpi (no white gap such as "C 19" at
  600 dpi).

**0.9**
* Transparent background is the default for image and GIF export (CLI: --opaque for a solid one).
* Smooth GIF defaults: 120 frames (3° steps), 50 ms (20 frames/s, 6 s per turn), 1200 × 900,
  shadows on; frames are rendered in parallel on all CPU cores. Saving as .png writes an animated
  PNG (true color, soft transparent edges).
* Solvent detection (CH2Cl2, CHCl3, THF, Et2O, toluene, benzene, hexane, pentane, MeCN, DMSO,
  DMF, MeOH, EtOH, water, acetone, DME, dioxane, pyridine, fluoro/chloro-benzenes, ...):
  SI caption says "Co-crystallized solvent (one molecule of dichloromethane) is shown." or adds it
  to the "... are omitted for clarity." sentence when excluded. Structure tab: Exclude solvent
  molecules; Exclude by name: "+ solvent".

**0.8**
* Label defaults: Arial 16 pt, bold, italic, element symbol in the atom color.
* "colour" -> "color" throughout.
* Ctrl + drag moves labels (Labels tab: Reset label positions).
* Structure tab: Exclude atoms (click, crosshair cursor), Exclude by name… (list with "+ all H" and
  "+ disorder" helpers), Restore all; Delete excludes the selected atoms, Ctrl+Z undoes.
* SI caption: when excluded atoms look disordered (A/B or ' label families, partial occupancy,
  non-zero PART) the caption says "Hydrogen atoms and disordered parts are omitted for clarity."
  (or "Disordered parts are omitted for clarity." when H are shown).
* Hotkeys button (F1) and toast notifications for actions.
* GIF defaults: 72 frames (5° steps), 175 ms delay, 1024 × 768, shadows on; one palette for the
  whole animation (no color flicker).

**0.7**
* Labels tab: "Element symbol in atom color" (e.g. Fe in the Fe color, the number in the label color);
  works on screen and in all exports.
* Defaults: Fe #ce28ce, N #005dff, C Gray20, bonds #060606.
* Fixed: opening the custom color picker again no longer reverts colors chosen earlier.
* Rotating GIF: spin direction (clockwise / counter-clockwise about a screen axis) and a live
  "Spin preview"; drag the molecule while it spins to choose the orientation - the GIF starts from
  the current view and spins the same way.

**0.6**
* Live color picker (Color tab "Custom color…", custom background, custom label color):
  the structure updates while you drag; Cancel restores the previous colors.
* Carbon default color is Gray35.

**0.5**
* GPU live view (OpenGL via PyOpenGL + pyopengltk): ellipsoids, cut-outs, bands and bonds are
  ray-cast per pixel in shaders with the same finish model as the export renderer, so rotation is
  full quality at full resolution. Falls back to the software renderer automatically
  (set ORTEPVIEWER_NO_GL=1 to force the fallback).
* New SI tab: figure caption with selected bond lengths and angles (s.u. from the CIF
  _geom_bond / _geom_angle tables when present), symmetry and hydrogen sentences added
  automatically; copy to clipboard.
* Hydrogen atoms hidden by default; symmetry-generated atoms are marked with * by default.
* SHELX negative PART: atoms are no longer bonded to symmetry copies of the same part.

**0.4**
* Drag preview: half resolution with smooth upscaling by default (View → While dragging:
  Smooth ½ / Faster ⅓ / Fastest ¼ / Full quality).
* Export defaults: 6400 × 4800 px, antialiasing on (POV-Ray Antialias_Threshold 0.3; built-in 2×2
  supersampling), 600 dpi print resolution. Sizes are now entered in pixels, with presets.
* Final-export options: Shadows (built-in shadow mapping or POV-Ray) and Reflections
  (POV-Ray renderer). Renderer choice: Built-in or POV-Ray (ray traced); POV-Ray renders are
  overlaid with the same labels as the screen.
* Progress bar for image and GIF export (exports run in the background).
* .pov export also writes a matching .ini (Width, Height, Antialias, Antialias_Threshold).
* POV-Ray program location can be set with Browse (remembered in ~/.ortepviewer.json).
* CLI: --size W H in pixels, --shadows, --povray EXE, --no-aa.

**0.3**
* Any number of atoms can be selected (2–4 still give distance / angle / torsion);
  "Select all of element" and "Clear selection" buttons in Color and Styles.
* Every change (style, color, finish, texture, sizes, lighting) redraws immediately;
  fixed a race that could leave the low-resolution preview on screen.
* Material preview in Color and Styles shows the current color / finish / texture.
* Finishes recalibrated against POV-Ray 3.7 (reflection brightens toward the background,
  Speckled crand graininess).
* Exported images / GIFs / POV labels match the on-screen label size relative to the molecule
  (Export → Label size: Match screen, or As set (pt)).
* Full-quality frames on very large (HiDPI) windows skip supersampling to stay fast.

**0.2** tabs, shaded POV-style renderer, styles / finishes / textures, POV-Ray and GIF export.
**0.1** CIF / SHELX reader and line-drawing ORTEP viewer.
