"""Small transient notifications ("toasts") in the bottom-right corner of the main window."""
import customtkinter as ctk

COLORS = {'info': ('#2b2b2b', '#f0f0f0'), 'ok': ('#1e6b34', '#ffffff'), 'warn': ('#8a5a00', '#ffffff'),
          'error': ('#a32020', '#ffffff')}


class Toaster:
    def __init__(self, root):
        self.root = root
        self.items = []

    def show(self, text, kind='info', ms=2600):
        try:
            bg, fg = COLORS.get(kind, COLORS['info'])
            w = ctk.CTkToplevel(self.root)
            w.overrideredirect(True)
            try:
                w.attributes('-topmost', True)
                w.attributes('-alpha', 0.94)
            except Exception:  # noqa: BLE001
                pass
            lbl = ctk.CTkLabel(w, text=text, fg_color=bg, text_color=fg, corner_radius=8,
                               font=ctk.CTkFont(size=13), wraplength=380, justify='left', padx=14, pady=8)
            lbl.pack()
            self.items.append(w)
            self._layout()
            w.after(ms, lambda: self._close(w))
        except Exception:  # noqa: BLE001 - toasts are cosmetic, never break the app
            pass

    def _close(self, w):
        if w in self.items:
            self.items.remove(w)
        try:
            w.destroy()
        except Exception:  # noqa: BLE001
            pass
        self._layout()

    def _layout(self):
        try:
            self.root.update_idletasks()
            rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
            rw, rh = self.root.winfo_width(), self.root.winfo_height()
            y = ry + rh - 50
            for w in reversed(self.items[-5:]):
                w.update_idletasks()
                ww, wh = w.winfo_reqwidth(), w.winfo_reqheight()
                y -= wh + 8
                w.geometry(f'+{rx + rw - ww - 24}+{y}')
            for w in self.items[:-5]:
                w.withdraw()
        except Exception:  # noqa: BLE001
            pass
