# ORTEPSauce 1.0.1

ORTEP-style viewer for small-molecule crystal structures from **.cif**, **.ins** and **.res** files,
with POV-Ray-style shaded rendering, high-resolution image export, POV-Ray scene export, rotating
GIFs, SI figure captions and coordination-geometry indices (τ₄, τ₄′, τ₅).
(Formerly "ORTEP Viewer" 0.1-1.9.)

## How to cite
Saucedo Cañas, M. A.; Fortier, S. ORTEPSauce [Computer software]; Zenodo, 2026.
DOI: [10.5281/zenodo.24170231](https://doi.org/10.5281/zenodo.24170231)
(also under the **❝ Citation** button in the program)

## Run (Windows cmd)
    cd /d C:\Users\manue\Downloads\ORTEPSauce_V1.0.1
    py -m pip install -r ortepsauce\requirements.txt
    py -m ortepsauce                       :: GUI
    py -m ortepsauce structure.cif         :: GUI with a file
    py -m ortepsauce x.res --export x.png                        :: 6400 x 4800, AA
    py -m ortepsauce x.cif --export x.gif                        :: 1600 x 1200, 200 frames
    py -m ortepsauce x.cif --export x.pov             :: POV-Ray scene

## Run on Linux / macOS
ORTEPSauce is plain Python, so the same code runs on Linux and macOS (the .exe is only for Windows).
Python 3.9+ with Tk is needed (Ubuntu/Debian: `sudo apt install python3-tk`; macOS: the python.org
installer includes Tk).

    cd ~/Downloads/ORTEPSauce_V1.0.1
    python3 -m venv .venv && source .venv/bin/activate      # optional
    python3 -m pip install -r ortepsauce/requirements.txt
    python3 -m ortepsauce                                    # GUI
    python3 -m ortepsauce x.cif --export x.svg --style "ORTEP-3 classic"

If OpenGL is not available the software renderer is used automatically
(`ORTEPSAUCE_NO_GL=1` forces it).

## Make a stand-alone .exe (Windows)
In the extracted folder (next to the `ortepsauce` folder) double-click **build_exe.bat**, or in cmd:

    cd /d C:\Users\manue\Downloads\ORTEPSauce_V1.0.1
    build_exe.bat

Result: `dist\ORTEPSauce\ORTEPSauce.exe`. Keep the whole `dist\ORTEPSauce` folder together.


## Publishing a new version (so that everyone gets it automatically)
1. Raise `__version__` in `ortepsauce/__init__.py` (1.0.1 → 1.0.2 …).
2. Double-click **make_release.bat** (builds the .exe, then makes `ORTEPSauce_V<ver>_Windows.zip`,
   `ORTEPSauce_V<ver>.zip` and `ortepsauce_version.json`).
3. GitHub → Releases → *Draft a new release*, tag `v<ver>` (e.g. `v1.0.2`), attach both zips, publish
   (Zenodo archives it as before). Optionally upload `ortepsauce_version.json` to the web page repo.
Copies of ORTEPSauce 1.0.1 or newer then offer *Install update*. (v1.0.0 has to be replaced by hand
once.)
## First start, tutorial, updates
* The **📖 Tutorial** (bottom right) opens by itself the first time: labels, selecting, colors,
  saving your own defaults, the SI caption, styles and export.
* **⚙ Settings & updates** (bottom right):
  * *Check now / Install update* – looks at the latest GitHub release of Manuel-Saucedo-Chem/ORTEPSauce
    (or ortepsauce_version.json on the web page), downloads it, checks its SHA-256 and installs it.
    The .exe closes, is replaced and starts again (_internal is replaced, other files next to the .exe
    are kept); the Python version replaces the `ortepsauce` folder and keeps the old one as
    `ortepsauce_backup_<version>`. An automatic check runs at most once a day (can be switched off).
  * **Your defaults are never touched by an update**: they live in ~/.ortepsauce.json in your user
    folder, not in the program folder.
  * *Lab settings file* – set up every tab, **Export lab settings file…** and share it (e-mail, Teams,
    a shared or cloud folder). Others use **Import lab settings file…** once: the chosen tabs are
    applied and saved as their defaults, and the file is *followed* – when its owner changes it,
    ORTEPSauce offers the new version at the next start. A file named `ortepsauce_lab_settings.json`
    placed next to ORTEPSauce.exe (or the `ortepsauce` folder) is offered automatically at the first start.

## Labels
Labels start **off**. Click an atom (Shift + drag for a box, double click for the whole molecule)
and press **L** to label it; L again on labelled atoms removes them; L with nothing selected turns
all labels on / off. **Ctrl + drag** a label to move it.

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
  Line drawing (vector), **ORTEP-3 classic** (vector: white ellipsoids with element-colored outlines,
  principal ellipses, octant shaded with parallel lines, riding H as short sticks, thin black
  bonds, plain Arial labels); probability; *Modify*: Ellipse style (PlainEllipse / BoundaryEllipse /
  CutoutEllipse), Finish and Texture per target; bond / H / band / ball / rod sizes.
* **Export** – PNG/TIFF/JPEG/SVG/PDF/EPS at any size and dpi (antialiased, optional transparency);
  POV-Ray .pov (optionally rendered directly if POV-Ray is installed); rotating GIF.

## Mouse / keys
double-click an atom: select its whole molecule · right-click with atoms selected: edit only the bonds
among them, select whole molecules, show only the selected molecules / atoms, hide, invert ·
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
| packing.py | growing, completing, short contacts |
| buried_volume.py | %V_bur |
| citations.py | literature references used in captions |
| appsettings.py / updates.py | settings window, lab settings files, updates |

## SI tab: geometry index, buried volume, references
* **τ₄ / τ₄′ / τ₅** of the metal centre (automatic, or choose the metal and ligands).
* **%V_bur** (percent buried volume, grid method as in SambVca): sphere around the metal (radius 3.5 Å),
  Bondi radii × 1.17, mesh 0.10 Å, H atoms left out by default – all adjustable. Whole complex, or one
  ligand (double click it, *Ligand = selection*); for a ligand also the four quadrants. Checked against
  the exact volume of a single sphere (within 0.01 %) and against the morfeus library on two structures
  (within 0.5 %); compare with SambVca for your own conventions before publishing.
* The caption includes τ and %V_bur by default (values only; the %V_bur settings are shown in the SI tab).
* **References** (off by default): switching them on adds numbered references [1], [2] … with the full
  ACS-style list below the caption. The texts are in `ortepsauce/citations.py` (one place to correct).

## Packing, polymers, contacts (Mercury-style)
Structure tab → *Packing, molecules & contacts*:
* **Range** a / b / c from–to + **Pack this range** (e.g. a 0–2, b 0–2, c 0–1). *Whole molecules*
  keeps each molecule whose centre is inside the range; *Atoms in range* packs every atom inside it
  (polymers / networks; chosen automatically when molecules cannot be completed). Capped at 30 000 atoms.
* **Molecules…** – list of all molecules (formula, atoms, solvent, shown / hidden): select, show only,
  hide, show, short contacts.
* **Grow bonds +1** – atoms bonded to the selection across symmetry (polymer expansion, one step per
  click; the new atoms become the selection). **Complete molecule** – whole molecules.
* **Short contacts** – neighbouring molecules closer than the sum of the van der Waals radii + the
  typed value, drawn as thin dashed lines with the distance (switch the numbers off with
  *Distances on contact lines*). **Remove grown** – back to normal.
* **H add** – with hydrogens off, click atoms to show only their H atoms (crosshair cursor, Esc stops).
* Command line: `--pack-range 0 2 0 2 0 1 --pack-mode "Atoms in range"`.

## Vector export (SVG / PDF / EPS)
With **Line drawing** or **ORTEP-3 classic** every ellipsoid, bond and label is a vector object; labels
are real text (editable in Illustrator / Inkscape) when the halo is off (ORTEP-3 classic switches it
off). The shaded styles are embedded as an image inside SVG / PDF / EPS, with vector labels.

## Disorder
Structure → Exclude atoms → **By name…** (and Wire → By name…): type how the two disorder parts are
labelled – C21 / C21* (major empty, minor `*`), C55A / C55B (major `A`, minor `B`), C1 / C1' … – and
press **+ major part** or **+ minor part**. ORTEPSauce guesses the endings from the file; with both
empty the PART numbers are used (PART 1 = major). Hydrogen atoms follow the PART of their part.

## Changelog
**ORTEPSauce 1.0.1** (first update after the v1.0.0 release; development builds 1.1–1.6)
* **❝ Citation** button and a tutorial page on how to cite ORTEPSauce.
* References checked against the publishers' records: %V_bur now cites Poater et al. 2008 (the paper
  SambVca asks users to cite), SambVca 2009 and 2.1, Bondi; τ₄′ cites the 2015 and 2018 papers.
* New program icon (window, taskbar, .exe), made by make_icon.py from icon_source.png.
* Saved SI defaults from older versions that still held the old program values are moved to the new
  ones (geometry index and %V_bur in the caption, references off); values chosen on purpose are kept.
* RMSD and MSD surfaces are drawn on the graphics card (smooth rotation; exports unchanged).
* Line drawing / ORTEP-3 classic: light preview while dragging (outlines and bonds, no labels), the
  full drawing when the mouse stops; faster vector drawing for large structures.
* SI caption: geometry index and %V_bur on by default, references off by default; the %V_bur
  sentence gives just the value.
* SI tab: percent buried volume %V_bur (whole complex or one ligand, quadrants), optional sentence in
  the caption.
* References for τ₄, τ₄′, τ₅ and %V_bur, numbered in the caption and listed below it; Copy all references.
* Updates are downloaded from GitHub and installed from *Settings & updates* (SHA-256 checked);
  the user's defaults are kept. make_release.bat makes the release files.
* Lab settings files: export the settings of every tab, share them, import / follow them.
* *Packing, molecules & contacts* (with *Pack unit cell*) moved below *Centroids & bonds*.
* Packing over any range of cells, whole molecules or atoms in range (polymers, networks).
* Molecules list window; grow bonded atoms step by step (polymers); complete molecules; short
  contacts with dashed lines and distances; all also in the right-click menu.
* Bond dialog (Ctrl+B): option to write the distance on a bond, e.g. a dashed Cl···Cg contact.
* H add button: crosshair mode that shows the H atoms of the clicked / selected atoms.
* "Labels: click an atom and press L" pop-up when a file is opened.
* ORTEP-3 classic: solid black bonds (thinner to metals) and denser octant shading, as in ORTEP-3.
* Update check (button + quiet daily check) and a built-in tutorial that opens on the first start.
* Labels off when a file is opened; clear "select atoms + L" hint; L adds / removes labels of the
  selected atoms and reminds you that Ctrl + drag moves labels.
* New **ORTEP-3 classic** vector style (white ellipsoids, colored outlines, hatched octants, H sticks).
* Double click selects a whole molecule / fragment.
* Right-click menu for the selection: edit only the bonds among the selected atoms, select whole
  molecules, show only the selected molecules / atoms, hide, invert (Mercury-style picking).
* Exclude / wire by name: type the label endings of the major and minor disorder parts.
* SI caption: bonds are written metal first (Fe1–N1, Fe1–O1).
* EPS / PostScript export; text stays editable text in SVG / PDF / EPS.
* .exe: SVG / PDF / EPS export fixed ("No module named matplotlib.backends.backend_pdf").
* Linux / macOS instructions.

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
