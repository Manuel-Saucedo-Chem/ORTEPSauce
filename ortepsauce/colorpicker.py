"""Live color picker: the structure updates while you drag in the picker (unlike the native
Windows dialog, which only reports the color after OK)."""
import colorsys
import tkinter as tk

import customtkinter as ctk
import numpy as np
from PIL import Image, ImageTk

SV = 220      # size of the saturation/value square
HUE_W = 22


def _hex(rgb):
    return '#' + ''.join(f'{int(round(max(0, min(1, c)) * 255)):02x}' for c in rgb)


def _rgb(hexstr):
    h = hexstr.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class LiveColorPicker(ctk.CTkToplevel):
    def __init__(self, master, title, initial, on_change, on_close):
        """initial: '#rrggbb'; on_change(hex) is called live; on_close(hex or None) when the
        window closes (None = cancelled)."""
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.on_change = on_change
        self.on_close = on_close
        self.initial = initial
        r, g, b = _rgb(initial)
        self.h, self.s, self.v = colorsys.rgb_to_hsv(r, g, b)
        self._job = None
        self._lock = False
        self.closed = False

        body = ctk.CTkFrame(self, fg_color='transparent')
        body.pack(padx=10, pady=10)
        self.sv = tk.Canvas(body, width=SV, height=SV, highlightthickness=0, cursor='crosshair')
        self.sv.grid(row=0, column=0, rowspan=6)
        self.hue = tk.Canvas(body, width=HUE_W, height=SV, highlightthickness=0, cursor='sb_v_double_arrow')
        self.hue.grid(row=0, column=1, rowspan=6, padx=(6, 10))
        self._hue_img = ImageTk.PhotoImage(self._hue_bar())
        self.hue.create_image(0, 0, anchor='nw', image=self._hue_img)
        self.hue_mark = self.hue.create_rectangle(0, 0, HUE_W, 3, outline='black', width=2)
        self.sv_img_id = self.sv.create_image(0, 0, anchor='nw')
        self.sv_mark = self.sv.create_oval(0, 0, 10, 10, outline='white', width=2)
        for ev in ('<Button-1>', '<B1-Motion>'):
            self.sv.bind(ev, self._sv_click)
            self.hue.bind(ev, self._hue_click)

        sw = ctk.CTkFrame(body, fg_color='transparent')
        sw.grid(row=0, column=2, sticky='w')
        ctk.CTkLabel(sw, text='old').grid(row=0, column=0)
        ctk.CTkLabel(sw, text='new').grid(row=0, column=1)
        self.old_sw = ctk.CTkLabel(sw, text='', width=60, height=34, fg_color=initial, corner_radius=4)
        self.old_sw.grid(row=1, column=0, padx=2)
        self.new_sw = ctk.CTkLabel(sw, text='', width=60, height=34, fg_color=initial, corner_radius=4)
        self.new_sw.grid(row=1, column=1, padx=2)

        self.sliders = {}
        self.vals = {}
        for k, name in enumerate(('R', 'G', 'B')):
            fr = ctk.CTkFrame(body, fg_color='transparent')
            fr.grid(row=1 + k, column=2, sticky='ew')
            ctk.CTkLabel(fr, text=name, width=16).pack(side='left')
            sl = ctk.CTkSlider(fr, from_=0, to=255, number_of_steps=255, width=160,
                               command=lambda v, n=name: self._slider(n, v))
            sl.pack(side='left', padx=4)
            val = ctk.CTkLabel(fr, text='0', width=32)
            val.pack(side='left')
            self.sliders[name], self.vals[name] = sl, val
        fr = ctk.CTkFrame(body, fg_color='transparent')
        fr.grid(row=4, column=2, sticky='w', pady=4)
        ctk.CTkLabel(fr, text='Hex', width=30).pack(side='left')
        self.hex_var = tk.StringVar(value=initial)
        e = ctk.CTkEntry(fr, textvariable=self.hex_var, width=90)
        e.pack(side='left', padx=4)
        e.bind('<Return>', self._hex_entered)
        e.bind('<FocusOut>', self._hex_entered)
        btns = ctk.CTkFrame(body, fg_color='transparent')
        btns.grid(row=5, column=2, sticky='se')
        ctk.CTkButton(btns, text='OK', width=80, command=self.ok).pack(side='left', padx=3)
        ctk.CTkButton(btns, text='Cancel', width=80, fg_color='gray50', command=self.cancel).pack(side='left', padx=3)
        self.protocol('WM_DELETE_WINDOW', self.cancel)
        self.bind('<Escape>', lambda e: self.cancel())
        self._refresh(notify=False)
        self.after(50, self._bring_up)

    def _bring_up(self):
        try:
            self.lift()
            self.focus_force()
            self.attributes('-topmost', True)
            self.after(200, lambda: self.attributes('-topmost', False))
        except tk.TclError:
            pass

    # ---------------------------------------------------------------- drawing
    @staticmethod
    def _hue_bar():
        h = np.linspace(0, 1, SV, endpoint=False)
        cols = np.array([colorsys.hsv_to_rgb(x, 1, 1) for x in h])
        arr = (np.repeat(cols[:, None, :], HUE_W, axis=1) * 255).astype(np.uint8)
        return Image.fromarray(arr)

    def _sv_square(self):
        s = np.linspace(0, 1, SV)[None, :]
        v = np.linspace(1, 0, SV)[:, None]
        base = np.array(colorsys.hsv_to_rgb(self.h, 1, 1))
        rgb = v[..., None] * ((1 - s[..., None]) + s[..., None] * base[None, None, :])
        return Image.fromarray((rgb * 255).astype(np.uint8))

    def _refresh(self, notify=True, redraw_square=True):
        rgb = colorsys.hsv_to_rgb(self.h, self.s, self.v)
        hx = _hex(rgb)
        if redraw_square:
            self._sv_img = ImageTk.PhotoImage(self._sv_square())
            self.sv.itemconfigure(self.sv_img_id, image=self._sv_img)
        x, y = self.s * (SV - 1), (1 - self.v) * (SV - 1)
        self.sv.coords(self.sv_mark, x - 5, y - 5, x + 5, y + 5)
        self.sv.itemconfigure(self.sv_mark, outline='white' if self.v < 0.6 else 'black')
        hy = self.h * (SV - 1)
        self.hue.coords(self.hue_mark, 0, hy - 2, HUE_W, hy + 2)
        self._lock = True
        for name, c in zip('RGB', rgb):
            self.sliders[name].set(round(c * 255))
            self.vals[name].configure(text=str(int(round(c * 255))))
        self._lock = False
        self.hex_var.set(hx)
        self.new_sw.configure(fg_color=hx)
        if notify:
            self._notify(hx)

    def _notify(self, hx):
        # throttle: at most one live update per ~40 ms
        self._pending = hx
        if self._job is None:
            self._job = self.after(40, self._flush)

    def _flush(self):
        self._job = None
        try:
            self.on_change(self._pending)
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- events
    def _sv_click(self, e):
        self.s = min(max(e.x / (SV - 1), 0), 1)
        self.v = min(max(1 - e.y / (SV - 1), 0), 1)
        self._refresh(redraw_square=False)

    def _hue_click(self, e):
        self.h = min(max(e.y / (SV - 1), 0), 0.999)
        self._refresh()

    def _slider(self, name, v):
        if self._lock:
            return
        rgb = [self.sliders[n].get() / 255.0 for n in 'RGB']
        h, s, v2 = colorsys.rgb_to_hsv(*rgb)
        if s > 0 and v2 > 0:
            self.h = h
        self.s, self.v = s, v2
        self._refresh()

    def _hex_entered(self, e=None):
        txt = self.hex_var.get().strip()
        if not txt.startswith('#'):
            txt = '#' + txt
        try:
            r, g, b = _rgb(txt)
        except ValueError:
            return
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        if s > 0 and v > 0:
            self.h = h
        self.s, self.v = s, v
        self._refresh()

    def ok(self):
        if self.closed:
            return
        self.closed = True
        hx = _hex(colorsys.hsv_to_rgb(self.h, self.s, self.v))
        if self._job is not None:
            self.after_cancel(self._job)
        self.destroy()
        self.on_close(hx)

    def cancel(self):
        if self.closed:                 # already closed with OK/Cancel: never revert again
            return
        self.closed = True
        if self._job is not None:
            self.after_cancel(self._job)
        self.destroy()
        self.on_close(None)
