"""Settings & updates window: check for / install updates, lab settings files shared by a research
group, and where the user's own defaults live. Mixed into OrtepApp (gui.py)."""
import datetime
import glob
import hashlib
import json
import os
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import __version__

LAB_FORMAT = 'ORTEPSauce lab settings'
LAB_DEFAULT_NAME = 'ortepsauce_lab_settings.json'
# never written into a lab file (machine- or person-specific)
LAB_SKIP_VARS = {'block_var', 'ctarget_var', 'starget_var'}


def _cfg_io():
    from .gui import CONFIG_PATH, save_config
    return CONFIG_PATH, save_config


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        h.update(fh.read())
    return h.hexdigest()


def read_lab_file(path):
    with open(path, encoding='utf-8') as fh:
        d = json.load(fh)
    if not isinstance(d, dict) or d.get('format') != LAB_FORMAT or not isinstance(d.get('tabs'), dict):
        raise ValueError('This is not an ORTEPSauce lab settings file.')
    return d


class SettingsMixin:
    # ================================================================== startup
    def startup_checks(self):
        from .updates import pop_status
        st = pop_status()
        if st.startswith('OK'):
            self.toast(f'ORTEPSauce was updated to {st[3:].strip() or __version__}. '
                       'Your defaults and lab settings were kept.', 'ok', ms=6000)
        elif st.startswith('FAILED'):
            messagebox.showwarning('Update', 'The last update could not copy the new files (a file was in use or '
                                             'the folder is protected). ORTEPSauce is unchanged; please try again '
                                             'or download the new version from the web page.')
        self._check_lab_file()

    # ================================================================== updates
    def check_updates(self, manual=False, on_result=None):
        """Look for a newer version in a background thread. Automatic checks run at most once a day
        and only say something when there is a new version."""
        _, save_config = _cfg_io()
        if not manual:
            if not self.cfg.get('check_updates', True):
                return
            if time.time() - float(self.cfg.get('last_update_check', 0) or 0) < 86400:
                return
        if getattr(self, '_upd_running', False):
            return
        self._upd_running = True
        box = {}

        def work():
            from .updates import check_for_update
            try:
                box['res'] = check_for_update()
            except Exception as e:  # noqa: BLE001
                box['err'] = e

        th = threading.Thread(target=work, daemon=True)
        th.start()
        if manual and on_result is None:
            self.toast('Checking for updates …')

        def poll():
            if th.is_alive():
                self.after(200, poll)
                return
            self._upd_running = False
            self.cfg['last_update_check'] = time.time()
            save_config(self.cfg)
            self._upd_info = box.get('res')
            if on_result is not None:
                on_result(box)
            else:
                self._update_result(box, manual)
        self.after(200, poll)

    def _update_result(self, box, manual):
        from .updates import DOWNLOAD_PAGE
        _, save_config = _cfg_io()
        res = box.get('res')
        if res is None:
            if manual:
                self.toast('Could not reach the update server. The latest version is always on\n'
                           + DOWNLOAD_PAGE, 'warn', ms=6000)
            return
        if not res['newer']:
            if manual:
                self.toast(f'You have the latest version (ORTEPSauce {__version__}).', 'ok')
            return
        if not manual and self.cfg.get('skip_version') == res['latest']:
            return
        w = self._dialog('Update available', '470x380')
        ctk.CTkLabel(w, text=f'ORTEPSauce {res["latest"]} is available', font=ctk.CTkFont(size=17, weight='bold')
                     ).pack(padx=14, pady=(14, 2), anchor='w')
        ctk.CTkLabel(w, text=f'You have version {__version__}. Installing keeps your defaults, colors and lab '
                             'settings.', anchor='w', wraplength=440, justify='left').pack(padx=14, anchor='w')
        notes = ctk.CTkTextbox(w, height=150, wrap='word')
        notes.pack(fill='both', expand=True, padx=14, pady=8)
        notes.insert('1.0', res.get('notes') or 'See the release page for what is new.')
        notes.configure(state='disabled')
        auto = tk.BooleanVar(value=bool(self.cfg.get('check_updates', True)))

        def set_auto():
            self.cfg['check_updates'] = bool(auto.get())
            save_config(self.cfg)
        ctk.CTkCheckBox(w, text='Check for updates automatically (once a day)', variable=auto, command=set_auto
                        ).pack(padx=14, anchor='w')
        row = ctk.CTkFrame(w, fg_color='transparent')
        row.pack(fill='x', padx=14, pady=10)

        def skip():
            self.cfg['skip_version'] = res['latest']
            save_config(self.cfg)
            w.destroy()
        ctk.CTkButton(row, text='Install update', fg_color='#1f7a4d',
                      command=lambda: (w.destroy(), self.install_update(res))
                      ).pack(side='left', expand=True, fill='x', padx=2)
        ctk.CTkButton(row, text='Release page', command=lambda: webbrowser.open(res.get('url') or DOWNLOAD_PAGE)
                      ).pack(side='left', expand=True, fill='x', padx=2)
        ctk.CTkButton(row, text='Skip version', fg_color='gray50', command=skip
                      ).pack(side='left', expand=True, fill='x', padx=2)
        ctk.CTkButton(row, text='Later', fg_color='gray50', command=w.destroy
                      ).pack(side='left', expand=True, fill='x', padx=2)

    def install_update(self, info):
        from .updates import DOWNLOAD_PAGE, install_kind, run_update
        kind = install_kind()
        if kind is None:
            if messagebox.askyesno('Update', 'This copy of ORTEPSauce cannot replace its own files (for example '
                                             'it is in a protected folder). Open the download page instead?'):
                webbrowser.open(info.get('url') or DOWNLOAD_PAGE)
            return
        if not info['assets'].get('windows' if kind == 'exe' else 'source'):
            if messagebox.askyesno('Update', 'This release has no file for automatic installation. '
                                             'Open the release page instead?'):
                webbrowser.open(info.get('url') or DOWNLOAD_PAGE)
            return
        msg = (f'Download and install ORTEPSauce {info["latest"]}?\n\n'
               'Your saved defaults, colors and lab settings are kept (they are stored in your user folder, '
               'not in the program folder).\n\n'
               + ('ORTEPSauce will close, update itself and start again.' if kind == 'exe'
                  else 'The current version is kept as a backup folder (ortepsauce_backup_…).'))
        if not messagebox.askyesno('Install update', msg):
            return
        self._run_job(f'Updating to {info["latest"]}', lambda rep, cancel: run_update(info, rep, cancel),
                      on_done=self._update_installed, what='Update')

    def _update_installed(self, res):
        from .updates import launch_exe_update, pip_install_requirements, restart_source
        if res['kind'] == 'exe':
            self.status.configure(text='Installing the update – ORTEPSauce restarts in a moment …')
            launch_exe_update(res['bat'])
            self.after(400, self._quit_for_update)
            return
        note = ''
        if res.get('requirements_changed'):
            self.status.configure(text='Installing new Python packages …')
            self.update_idletasks()
            ok, out = pip_install_requirements()
            note = '' if ok else ('\n\nNew packages could not be installed automatically. Run:\n'
                                  'py -m pip install -r ortepsauce\\requirements.txt')
        self.status.configure(text=f'Updated to ORTEPSauce {res["version"]}')
        if messagebox.askyesno('Update installed', f'ORTEPSauce {res["version"]} is installed.' + note +
                               '\n\nRestart now?'):
            restart_source([self.path] if getattr(self, 'path', None) else [])
            self._quit_for_update()

    def _quit_for_update(self):
        _, save_config = _cfg_io()
        save_config(self.cfg)
        try:
            self.stop_spin()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()

    # ================================================================== lab settings file
    def lab_settings_data(self, name=''):
        tabs = {}
        for t in self.TAB_SPEC:
            st = self._tab_state(t)
            st['vars'] = {k: v for k, v in st.get('vars', {}).items() if k not in LAB_SKIP_VARS}
            tabs[t] = st
        return {'format': LAB_FORMAT, 'format_version': 1, 'program_version': __version__,
                'name': name or 'Lab settings', 'created': datetime.date.today().isoformat(), 'tabs': tabs}

    def export_lab_settings(self, name=''):
        path = filedialog.asksaveasfilename(
            title='Save lab settings file', initialfile=LAB_DEFAULT_NAME, defaultextension='.json',
            filetypes=[('ORTEPSauce lab settings', '*.json')])
        if not path:
            return
        data = self.lab_settings_data(name)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, indent=1, default=list)
        self.toast(f'Lab settings saved: {os.path.basename(path)}\nShare this file; others use '
                   '"Import lab settings file…".', 'ok', ms=6000)
        return path

    def import_lab_settings(self, path=None, tabs=None, ask=True, follow=True):
        """Apply a lab settings file: the chosen tabs are applied now and saved as the user's defaults."""
        _, save_config = _cfg_io()
        if path is None:
            path = filedialog.askopenfilename(title='Open lab settings file',
                                              filetypes=[('ORTEPSauce lab settings', '*.json'), ('All files', '*.*')])
            if not path:
                return
        try:
            data = read_lab_file(path)
        except (OSError, ValueError) as e:
            messagebox.showerror('Lab settings', str(e))
            return
        avail = [t for t in self.TAB_SPEC if t in data['tabs']]

        def apply(chosen, save_defaults, keep_following):
            for t in chosen:
                self._apply_tab(t, data['tabs'][t])
                if save_defaults:
                    self.cfg.setdefault('tab_defaults', {})[t] = data['tabs'][t]
            if keep_following:
                self.cfg['lab_file'] = dict(path=os.path.abspath(path), sha=_sha(path), name=data.get('name', ''),
                                            tabs=list(chosen))
            save_config(self.cfg)
            self.toast(f'Lab settings "{data.get("name", "")}" applied to: {", ".join(chosen)}', 'ok', ms=5000)
            self._refresh_settings_window()

        if not ask:
            apply([t for t in (tabs or avail) if t in avail], True, follow)
            return
        w = self._dialog('Import lab settings', '440x520')
        ctk.CTkLabel(w, text=data.get('name', 'Lab settings'), font=ctk.CTkFont(size=17, weight='bold'),
                     anchor='w').pack(fill='x', padx=14, pady=(14, 0))
        ctk.CTkLabel(w, text=f'Made with ORTEPSauce {data.get("program_version", "?")} on {data.get("created", "?")}',
                     anchor='w', text_color='gray50').pack(fill='x', padx=14)
        ctk.CTkLabel(w, text='Use these tabs from the file:', anchor='w').pack(fill='x', padx=14, pady=(10, 2))
        chk = {}
        for t in avail:
            v = tk.BooleanVar(value=True)
            chk[t] = v
            ctk.CTkCheckBox(w, text=t, variable=v).pack(anchor='w', padx=24, pady=2)
        save_v = tk.BooleanVar(value=True)
        follow_v = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(w, text='Save them as my defaults (used at every start)', variable=save_v
                        ).pack(anchor='w', padx=14, pady=(10, 2))
        ctk.CTkCheckBox(w, text='Keep following this file: offer its changes at start\n'
                                '(useful on a shared / cloud folder)', variable=follow_v
                        ).pack(anchor='w', padx=14, pady=2)
        row = ctk.CTkFrame(w, fg_color='transparent')
        row.pack(fill='x', padx=14, pady=12, side='bottom')
        ctk.CTkButton(row, text='Apply', command=lambda: (w.destroy(), apply(
            [t for t, v in chk.items() if v.get()], save_v.get(), follow_v.get()))
                      ).pack(side='left', expand=True, fill='x', padx=2)
        ctk.CTkButton(row, text='Cancel', fg_color='gray50', command=w.destroy
                      ).pack(side='left', expand=True, fill='x', padx=2)

    def _find_lab_file_next_to_program(self):
        from .updates import install_dir
        d = install_dir()
        for pat in (LAB_DEFAULT_NAME, '*ortepsauce*settings*.json', '*lab_settings*.json'):
            for p in sorted(glob.glob(os.path.join(d, pat))):
                try:
                    read_lab_file(p)
                    return p
                except (OSError, ValueError):
                    continue
        return None

    def _check_lab_file(self):
        """At start: offer a changed lab file that is being followed, or a lab file found next to the
        program (e.g. copied into the shared ORTEPSauce folder)."""
        _, save_config = _cfg_io()
        lf = self.cfg.get('lab_file') or {}
        p = lf.get('path')
        if p:
            if not os.path.exists(p):
                return
            try:
                sha = _sha(p)
                data = read_lab_file(p)
            except (OSError, ValueError):
                return
            if sha == lf.get('sha') or sha == self.cfg.get('lab_file_declined'):
                return
            ans = messagebox.askyesnocancel(
                'Lab settings', f'The lab settings file "{data.get("name", os.path.basename(p))}" was changed '
                                f'(by its owner, {data.get("created", "")}).\n\nApply the new settings?\n\n'
                                'Yes = apply and save as my defaults\nNo = not this version\n'
                                'Cancel = ask again next time')
            if ans:
                self.import_lab_settings(p, tabs=lf.get('tabs'), ask=False)
            elif ans is False:
                self.cfg['lab_file_declined'] = sha
                save_config(self.cfg)
            return
        if self.cfg.get('lab_file_offer_done'):
            return
        found = self._find_lab_file_next_to_program()
        if found:
            self.cfg['lab_file_offer_done'] = True
            save_config(self.cfg)
            if messagebox.askyesno('Lab settings', f'A lab settings file was found next to ORTEPSauce:\n'
                                                   f'{os.path.basename(found)}\n\nUse it?'):
                self.import_lab_settings(found)

    def stop_following_lab_file(self):
        _, save_config = _cfg_io()
        self.cfg.pop('lab_file', None)
        save_config(self.cfg)
        self._refresh_settings_window()
        self.toast('No longer following the lab settings file (your current defaults stay).')

    def forget_all_defaults(self):
        _, save_config = _cfg_io()
        if not messagebox.askyesno('Defaults', 'Forget all your saved defaults on every tab? (The program '
                                               'defaults are used at the next start.)'):
            return
        self.cfg.pop('tab_defaults', None)
        save_config(self.cfg)
        self.toast('Saved defaults forgotten. Use ↺ Reset tab to defaults to see the program defaults now.')

    # ================================================================== the window
    def show_settings(self):
        w = getattr(self, '_set_win', None)
        if w is not None:
            try:
                if w.winfo_exists():
                    w.lift()
                    return
            except tk.TclError:
                pass
        from .updates import install_kind
        config_path, save_config = _cfg_io()
        w = self._dialog('Settings & updates', '540x720')
        self._set_win = w
        body = ctk.CTkScrollableFrame(w, fg_color='transparent')
        body.pack(fill='both', expand=True, padx=6, pady=6)

        def section(text):
            ctk.CTkLabel(body, text=text, font=ctk.CTkFont(size=16, weight='bold'), anchor='w'
                         ).pack(fill='x', padx=8, pady=(12, 2))

        def note(text):
            lbl = ctk.CTkLabel(body, text=text, anchor='w', justify='left', wraplength=480,
                               text_color=('gray30', 'gray70'))
            lbl.pack(fill='x', padx=8, pady=1)
            return lbl

        # ---- updates
        section('Updates')
        kind = install_kind()
        where = {'exe': 'program (.exe)', 'source': 'Python version'}.get(kind, 'read-only copy')
        note(f'You have ORTEPSauce {__version__} ({where}).')
        self._upd_lbl = note('Press "Check now" to look for a new version.')
        row = ctk.CTkFrame(body, fg_color='transparent')
        row.pack(fill='x', padx=8, pady=4)
        self._upd_install_btn = ctk.CTkButton(row, text='Install update', state='disabled', fg_color='gray60',
                                              command=lambda: self.install_update(self._upd_info))

        def got(box):
            res = box.get('res')
            try:
                if res is None:
                    self._upd_lbl.configure(text='Could not reach GitHub or the web page. Check the internet '
                                                 'connection, or download from the web page.')
                elif res['newer']:
                    self._upd_lbl.configure(text=f'ORTEPSauce {res["latest"]} is available (from {res["source"]}).')
                    self._upd_install_btn.configure(state='normal', fg_color='#1f7a4d')
                else:
                    self._upd_lbl.configure(text=f'You have the latest version ({__version__}).')
            except tk.TclError:
                pass
        ctk.CTkButton(row, text='Check now', command=lambda: (
            self._upd_lbl.configure(text='Checking …'), self.check_updates(manual=True, on_result=got))
                      ).pack(side='left', expand=True, fill='x', padx=2)
        self._upd_install_btn.pack(side='left', expand=True, fill='x', padx=2)
        from .updates import RELEASES_PAGE
        ctk.CTkButton(row, text='Release page', fg_color='gray45', command=lambda: webbrowser.open(RELEASES_PAGE)
                      ).pack(side='left', expand=True, fill='x', padx=2)
        auto = tk.BooleanVar(value=bool(self.cfg.get('check_updates', True)))

        def set_auto():
            self.cfg['check_updates'] = bool(auto.get())
            save_config(self.cfg)
        ctk.CTkCheckBox(body, text='Check automatically once a day', variable=auto, command=set_auto
                        ).pack(anchor='w', padx=8, pady=4)
        note('Updates replace only the program files. Your defaults, colors and lab settings are never changed.')

        # ---- lab settings
        section('Lab settings file')
        note('Share one set of defaults with your group: set up every tab (colors, styles, labels, export '
             'size …), export the file and send it, or put it in a shared folder. Others import it once; '
             'it is kept through every update. A file called ortepsauce_lab_settings.json placed next to '
             'ORTEPSauce is offered automatically at start.')
        name_v = tk.StringVar(value=(self.cfg.get('lab_file') or {}).get('name', '') or self.cfg.get('lab_name', ''))
        r = ctk.CTkFrame(body, fg_color='transparent')
        r.pack(fill='x', padx=8, pady=4)
        ctk.CTkLabel(r, text='Group name').pack(side='left')
        ctk.CTkEntry(r, textvariable=name_v, width=300).pack(side='left', padx=8, fill='x', expand=True)
        row2 = ctk.CTkFrame(body, fg_color='transparent')
        row2.pack(fill='x', padx=8, pady=4)

        def export():
            self.cfg['lab_name'] = name_v.get().strip()
            save_config(self.cfg)
            self.export_lab_settings(name_v.get().strip())
        ctk.CTkButton(row2, text='Export lab settings file…', command=export
                      ).pack(side='left', expand=True, fill='x', padx=2)
        ctk.CTkButton(row2, text='Import lab settings file…', command=lambda: self.import_lab_settings()
                      ).pack(side='left', expand=True, fill='x', padx=2)
        self._lab_lbl = note('')
        self._lab_stop = ctk.CTkButton(body, text='Stop following the lab file', fg_color='gray45',
                                       command=self.stop_following_lab_file)
        self._lab_stop.pack(fill='x', padx=10, pady=4)

        # ---- own defaults
        section('Your defaults')
        note(f'Saved with "★ Save tab as default" in:\n{config_path}')
        ctk.CTkButton(body, text='Forget all my saved defaults', fg_color='gray45', command=self.forget_all_defaults
                      ).pack(fill='x', padx=10, pady=4)
        ctk.CTkButton(w, text='Close', command=w.destroy).pack(pady=(0, 10))
        self._refresh_settings_window()

    def _refresh_settings_window(self):
        lbl = getattr(self, '_lab_lbl', None)
        if lbl is None:
            return
        try:
            lf = self.cfg.get('lab_file') or {}
            if lf.get('path'):
                lbl.configure(text=f'Following: {lf.get("name") or os.path.basename(lf["path"])}\n{lf["path"]}\n'
                                   f'Tabs: {", ".join(lf.get("tabs") or [])}')
                self._lab_stop.configure(state='normal')
            else:
                lbl.configure(text='No lab settings file in use.')
                self._lab_stop.configure(state='disabled')
        except tk.TclError:
            pass

    @staticmethod
    def _frozen():
        return getattr(sys, 'frozen', False)
