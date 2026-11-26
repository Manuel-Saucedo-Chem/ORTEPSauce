"""GPU (OpenGL) interactive view.

Every atom / bond is drawn as a screen-aligned quad whose fragment shader ray-casts the exact
ellipsoid (with boundary bands and the cut-out octant) or cylinder - the same analytic geometry
and POV-Ray finish model as the export renderer (raster.py), but on the graphics card, so the
molecule rotates at full quality and full resolution. Labels are drawn as textures.

If OpenGL is unavailable the GUI falls back to the software renderer."""
import ctypes
import math

import numpy as np

try:
    from OpenGL import GL
    from pyopengltk import OpenGLFrame
    GL_IMPORT_ERROR = None
except Exception as _e:  # noqa: BLE001
    GL = None
    OpenGLFrame = object
    GL_IMPORT_ERROR = str(_e)

from .canvas_view import atom_label_visible, display_name, label_runs
from .raster import light_vectors
from .scene import build_scene
from .styles import color_rgb, hex_to_rgb

from .gl_shaders import (GL_STYLES, MAXM, _CYL_FS, _CYL_VS, _ELL_FS, _ELL_VS, _MESH_FS, _MESH_VS,  # noqa: F401
                         _QUAD, _STYLE, star_surface_mesh)
from .gl_shaders import srgb as _srgb


class GLMolView(OpenGLFrame):
    def __init__(self, master, app, **kw):
        super().__init__(master, **kw)
        self.app = app
        self.ready = False
        self.failed = None
        self.dirty = True
        self.prog_e = self.prog_c = None
        self.vbo_e = self.vbo_c = None
        self.n_e = self.n_c = 0
        self.prog_m = self.vbo_m = self.ibo_m = None
        self.n_m = 0
        self.scene = None
        self.tex_cache = {}
        self.fbo = None
        self.fbo_size = (0, 0)
        self.ssaa = 2
        self.anchor_xy = np.zeros((0, 2))
        self.anchor_r = np.zeros(0)
        self.anchor_z = np.zeros(0)
        self.visible = np.zeros(0, bool)
        self.label_positions = []
        self.width = self.height = 1
        self.animate = 0

    # ------------------------------------------------------------------ GL setup
    def initgl(self):
        try:
            GL.glViewport(0, 0, max(self.winfo_width(), 1), max(self.winfo_height(), 1))
            if self.prog_e is None:
                self.prog_e = self._program(_ELL_VS, _ELL_FS)
                self.prog_c = self._program(_CYL_VS, _CYL_FS)
                self.vbo_e = GL.glGenBuffers(1)
                self.vbo_c = GL.glGenBuffers(1)
            if self.prog_m is None:
                try:                     # RMSD / MSD surfaces as triangle meshes
                    self.prog_m = self._program(_MESH_VS, _MESH_FS)
                    self.vbo_m = GL.glGenBuffers(1)
                    self.ibo_m = GL.glGenBuffers(1)
                except Exception:  # noqa: BLE001 - surfaces then use the software view
                    self.prog_m = None
            self.ready = True
        except Exception as e:  # noqa: BLE001
            self.failed = str(e)
            self.ready = False
            self.after(10, lambda: self.app.gl_failed(self.failed))

    @staticmethod
    def _program(vs, fs):
        def comp(src, kind):
            sh = GL.glCreateShader(kind)
            GL.glShaderSource(sh, src)
            GL.glCompileShader(sh)
            if not GL.glGetShaderiv(sh, GL.GL_COMPILE_STATUS):
                raise RuntimeError(GL.glGetShaderInfoLog(sh).decode(errors='replace'))
            return sh
        p = GL.glCreateProgram()
        GL.glAttachShader(p, comp(vs, GL.GL_VERTEX_SHADER))
        GL.glAttachShader(p, comp(fs, GL.GL_FRAGMENT_SHADER))
        GL.glLinkProgram(p)
        if not GL.glGetProgramiv(p, GL.GL_LINK_STATUS):
            raise RuntimeError(GL.glGetProgramInfoLog(p).decode(errors='replace'))
        return p

    # ------------------------------------------------------------------ scene upload
    def _upload(self):
        app = self.app
        model, s = app.model, app.s
        self.scene = sc = build_scene(model, np.eye(3), app.center, s, app.styles,
                                      cell=app.struct.cell if app.struct else None)
        ells = [p for p in sc.prims if p['type'] == 'ellipsoid']
        cyls = [p for p in sc.prims if p['type'] == 'cylinder']
        surfs = [p for p in sc.prims if p['type'] == 'surface']
        self.n_m = 0
        if surfs and self.prog_m is not None:
            level = 4 if len(surfs) <= 150 else 3            # 2562 / 642 vertices per atom
            verts, idx, off = [], [], 0
            for p in surfs:
                P, N, F = star_surface_mesh(p['c'], p['U'], p['kind'], p['k'], p['ueq'], level)
                verts.append(np.concatenate([P, N, np.full((len(P), 1), p['mat'])], 1))
                idx.append(F + off)
                off += len(P)
            vdata = np.ascontiguousarray(np.concatenate(verts), np.float32)
            idata = np.ascontiguousarray(np.concatenate(idx).ravel(), np.uint32)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_m)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, vdata.nbytes, vdata, GL.GL_STATIC_DRAW)
            GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ibo_m)
            GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, idata.nbytes, idata, GL.GL_STATIC_DRAW)
            GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, 0)
            self.n_m = len(idata)
        if ells:
            rows = []
            for p in ells:
                A = p['V'] * p['a'][None, :]
                B = np.linalg.inv(A)
                info = [_STYLE.get(p['style'], 0.0), p['mat'], p['band'], p['cut']]
                rows.append(np.concatenate([p['c'], A[:, 0], A[:, 1], A[:, 2], B[0], B[1], B[2], info]))
            per = np.array(rows, np.float32)                       # (n, 25)
            data = np.concatenate([np.tile(_QUAD, (len(per), 1)), np.repeat(per, 6, axis=0)], 1)
            data = np.ascontiguousarray(data, np.float32)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_e)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_STATIC_DRAW)
        self.n_e = 6 * len(ells)
        if cyls:
            per = np.array([np.concatenate([p['p0'], p['p1'], [p['r'], p['mat']]]) for p in cyls], np.float32)
            data = np.concatenate([np.tile(_QUAD, (len(per), 1)), np.repeat(per, 6, axis=0)], 1)
            data = np.ascontiguousarray(data, np.float32)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_c)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_STATIC_DRAW)
        self.n_c = 6 * len(cyls)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        # per-atom 2nd moment for projected radii / picking
        n = model.n
        self.atom_M = np.zeros((n, 3, 3))
        for p in ells:
            if 0 <= p['oid'] < n:
                A = p['V'] * p['a'][None, :]
                self.atom_M[p['oid']] = A @ A.T
        for p in surfs:
            if 0 <= p['oid'] < n:
                self.atom_M[p['oid']] = np.eye(3) * p['rmax'] ** 2
        self.zmax = float(np.abs(model.cart - app.center).max() + 10.0) if n else 10.0
        mats = sc.materials[:MAXM]
        self.mat_arrays = (
            np.array([m['color'] for m in mats], np.float32),
            np.array([[m['finish']['ambient'], m['finish']['diffuse'], m['finish']['brilliance'],
                       m['finish']['specular']] for m in mats], np.float32),
            np.array([[m['finish']['roughness'], m['finish']['phong'], m['finish']['phong_size'],
                       m['finish']['reflection']] for m in mats], np.float32),
            np.array([[1.0 if m['finish']['metallic'] else 0.0, m['finish']['crand']] for m in mats],
                     np.float32))
        self.dirty = False

    def _attribs(self, prog, layout, stride):
        offs = 0
        locs = []
        for name, size in layout:
            loc = GL.glGetAttribLocation(prog, name)
            if loc >= 0:
                GL.glEnableVertexAttribArray(loc)
                GL.glVertexAttribPointer(loc, size, GL.GL_FLOAT, False, stride, ctypes.c_void_p(offs))
                locs.append(loc)
            offs += 4 * size
        return locs

    def _set_uniforms(self, prog, half, pan):
        app = self.app
        s = app.s
        u = lambda n: GL.glGetUniformLocation(prog, n)  # noqa: E731
        GL.glUniformMatrix3fv(u('uR'), 1, True, np.asarray(app.R, np.float32))
        GL.glUniform2f(u('uPan'), pan[0], pan[1])
        GL.glUniform2f(u('uHalf'), half[0], half[1])
        cols, fa, fb, fc = self.mat_arrays
        if len(cols):
            GL.glUniform3fv(u('uCol'), len(cols), cols)
            GL.glUniform4fv(u('uFa'), len(fa), fa)
            GL.glUniform4fv(u('uFb'), len(fb), fb)
            GL.glUniform2fv(u('uFc'), len(fc), fc)
        lights = light_vectors(s.light_azimuth, s.light_elevation, s.fill_light)
        L0, I0 = lights[0]
        L1, I1 = lights[1] if len(lights) > 1 else (lights[0][0], 0.0)
        GL.glUniform3f(u('uL0'), *map(float, L0))
        GL.glUniform3f(u('uL1'), *map(float, L1))
        GL.glUniform1f(u('uI0'), float(I0))
        GL.glUniform1f(u('uI1'), float(I1))
        GL.glUniform1f(u('uAmbient'), float(s.ambient_light))
        GL.glUniform3f(u('uBg'), *hex_to_rgb(s.background))
        GL.glUniform1f(u('uSrgb'), 1.0 if s.srgb else 0.0)
        GL.glUniform1f(u('uDepthScale'), 0.5 / self.zmax)
        loc = u('uBand')
        if loc >= 0:
            GL.glUniform1f(loc, float(s.band_width))

    # ------------------------------------------------------------------ FBO for supersampling
    def _ensure_fbo(self, W, H):
        if self.ssaa <= 1:
            return False
        size = (W * self.ssaa, H * self.ssaa)
        if self.fbo is not None and self.fbo_size == size:
            return True
        try:
            if self.fbo is not None:
                GL.glDeleteFramebuffers(1, [self.fbo])
                GL.glDeleteRenderbuffers(2, self.rbos)
            self.fbo = GL.glGenFramebuffers(1)
            self.rbos = GL.glGenRenderbuffers(2)
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbo)
            GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, self.rbos[0])
            GL.glRenderbufferStorage(GL.GL_RENDERBUFFER, GL.GL_RGBA8, *size)
            GL.glFramebufferRenderbuffer(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_RENDERBUFFER,
                                         self.rbos[0])
            GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, self.rbos[1])
            GL.glRenderbufferStorage(GL.GL_RENDERBUFFER, GL.GL_DEPTH_COMPONENT24, *size)
            GL.glFramebufferRenderbuffer(GL.GL_FRAMEBUFFER, GL.GL_DEPTH_ATTACHMENT, GL.GL_RENDERBUFFER,
                                         self.rbos[1])
            ok = GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER) == GL.GL_FRAMEBUFFER_COMPLETE
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
            if not ok:
                raise RuntimeError('incomplete framebuffer')
            self.fbo_size = size
            return True
        except Exception:  # noqa: BLE001 - no FBO support: draw without supersampling
            self.ssaa = 1
            self.fbo = None
            try:
                GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
            except Exception:  # noqa: BLE001
                pass
            return False

    # ------------------------------------------------------------------ drawing
    def redraw(self):
        if not self.ready or self.app.model is None:
            GL.glClearColor(1, 1, 1, 1)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)
            return
        app = self.app
        s = app.s
        W, H = max(self.winfo_width(), 1), max(self.winfo_height(), 1)
        if self.dirty or self.scene is None:
            self._upload()
        scale, pan = app.scale, tuple(app.pan)
        half = (scale * W / H, scale)
        bg = _srgb(hex_to_rgb(s.background)) if s.srgb else np.array(hex_to_rgb(s.background))

        use_fbo = self._ensure_fbo(W, H)
        if use_fbo:
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbo)
            GL.glViewport(0, 0, W * self.ssaa, H * self.ssaa)
        else:
            GL.glViewport(0, 0, W, H)
        GL.glClearColor(float(bg[0]), float(bg[1]), float(bg[2]), 1.0)
        GL.glClearDepth(1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LESS)
        GL.glDisable(GL.GL_BLEND)
        GL.glDisable(GL.GL_CULL_FACE)

        if self.n_e:
            GL.glUseProgram(self.prog_e)
            self._set_uniforms(self.prog_e, half, pan)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_e)
            locs = self._attribs(self.prog_e, [('aCorner', 2), ('aCenter', 3), ('aA0', 3), ('aA1', 3), ('aA2', 3),
                                               ('aB0', 3), ('aB1', 3), ('aB2', 3), ('aInfo', 4)], 27 * 4)
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, self.n_e)
            for loc in locs:
                GL.glDisableVertexAttribArray(loc)
        if self.n_m:
            GL.glUseProgram(self.prog_m)
            self._set_uniforms(self.prog_m, half, pan)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_m)
            GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ibo_m)
            locs = self._attribs(self.prog_m, [('aPos', 3), ('aNrm', 3), ('aMat', 1)], 7 * 4)
            GL.glDrawElements(GL.GL_TRIANGLES, self.n_m, GL.GL_UNSIGNED_INT, None)
            for loc in locs:
                GL.glDisableVertexAttribArray(loc)
            GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, 0)
        if self.n_c:
            GL.glUseProgram(self.prog_c)
            self._set_uniforms(self.prog_c, half, pan)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_c)
            locs = self._attribs(self.prog_c, [('aCorner', 2), ('aP0', 3), ('aP1', 3), ('aInfo', 2)], 10 * 4)
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, self.n_c)
            for loc in locs:
                GL.glDisableVertexAttribArray(loc)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glUseProgram(0)
        if use_fbo:
            GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, self.fbo)
            GL.glBindFramebuffer(GL.GL_DRAW_FRAMEBUFFER, 0)
            GL.glBlitFramebuffer(0, 0, W * self.ssaa, H * self.ssaa, 0, 0, W, H,
                                 GL.GL_COLOR_BUFFER_BIT, GL.GL_LINEAR)
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
            GL.glViewport(0, 0, W, H)
        self._update_anchors()
        self._overlay(W, H, scale, pan)
        GL.glFlush()

    def _update_anchors(self):
        app = self.app
        m = app.model
        X = (m.cart - app.center) @ app.R.T
        self.anchor_xy = X[:, :2]
        self.anchor_z = X[:, 2]
        Mr = np.einsum('ij,njk,lk->nil', app.R, self.atom_M, app.R)
        self.anchor_r = np.sqrt(np.maximum(np.maximum(Mr[:, 0, 0], Mr[:, 1, 1]), 0))
        self.visible = self.scene.visible if self.scene is not None else np.ones(m.n, bool)

    # ------------------------------------------------------------------ overlay (labels, rings)
    def _to_px(self, x, y, W, H, scale, pan):
        px = 2 * scale / H
        return (x - (pan[0] - scale * W / H)) / px, (y - (pan[1] - scale)) / px

    def _text_texture(self, text, size_px, color, bold, italic, family, halo_px, halo_col):
        key = (text, size_px, color, bold, italic, family, halo_px, halo_col)
        hit = self.tex_cache.get(key)
        if hit:
            return hit
        from matplotlib import font_manager
        from PIL import Image, ImageDraw, ImageFont
        try:
            fp = font_manager.FontProperties(family=family, weight='bold' if bold else 'normal',
                                             style='italic' if italic else 'normal')
            font = ImageFont.truetype(font_manager.findfont(fp), max(int(round(size_px)), 4))
        except Exception:  # noqa: BLE001
            font = ImageFont.load_default()
        runs = text if isinstance(text, tuple) else ((text, color),)
        full = ''.join(t for t, _ in runs)
        sw = int(round(halo_px / 2))
        d0 = ImageDraw.Draw(Image.new('RGBA', (4, 4)))
        x0, y0, x1, y1 = d0.textbbox((0, 0), full, font=font, stroke_width=sw)
        asc, desc = font.getmetrics() if hasattr(font, 'getmetrics') else (y1, 0)
        w, h = x1 - x0 + 2, asc + desc + 2 * sw + 2
        im = Image.new('RGBA', (max(w, 1), max(h, 1)), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)

        def rgba(c):
            return tuple(int(round(v * 255)) for v in c) + (255,)
        oy = 1 + sw if sw > 0 else 1
        if sw > 0:                                   # halo for the whole string first
            stroke = rgba(halo_col)
            d.text((1 - x0, oy), full, font=font, fill=stroke, stroke_width=sw, stroke_fill=stroke)
        xo = 1 - x0
        for t, c in runs:                            # then each colored run
            d.text((xo, oy), t, font=font, fill=rgba(c))
            xo += font.getlength(t) if hasattr(font, 'getlength') else d0.textlength(t, font=font)
        data = np.asarray(im.transpose(Image.FLIP_TOP_BOTTOM)).astype(np.float32)
        data[..., :3] *= data[..., 3:4] / 255.0            # premultiplied alpha: no dark fringes
        data = np.ascontiguousarray(np.round(data).astype(np.uint8))
        tid = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tid)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, im.width, im.height, 0, GL.GL_RGBA,
                        GL.GL_UNSIGNED_BYTE, data)
        hit = (tid, im.width, im.height, desc + sw + 1)
        if len(self.tex_cache) > 3000:
            self.clear_textures()
        self.tex_cache[key] = hit
        return hit

    def clear_textures(self):
        if self.tex_cache:
            try:
                GL.glDeleteTextures([v[0] for v in self.tex_cache.values()])
            except Exception:  # noqa: BLE001
                pass
        self.tex_cache = {}

    def _draw_text(self, text, x, y, size_pt, color, bold=False, italic=False, family='DejaVu Sans',
                   halo=False, halo_col=(1, 1, 1), align='left'):
        dpi = self.app.screen_dpi()
        size_px = size_pt * dpi / 72.0
        halo_px = self.app.s.halo_width * dpi / 72.0 if halo else 0
        tid, w, h, base = self._text_texture(text, round(size_px, 1), tuple(color), bold, italic, family,
                                             round(halo_px, 1), tuple(halo_col))
        if align == 'right':
            x -= w
        y -= base * 0.5
        x, y = round(x), round(y)                           # pixel-aligned: crisp text
        GL.glBindTexture(GL.GL_TEXTURE_2D, tid)
        GL.glBegin(GL.GL_QUADS)
        GL.glTexCoord2f(0, 0); GL.glVertex2f(x, y)            # noqa: E702
        GL.glTexCoord2f(1, 0); GL.glVertex2f(x + w, y)        # noqa: E702
        GL.glTexCoord2f(1, 1); GL.glVertex2f(x + w, y + h)    # noqa: E702
        GL.glTexCoord2f(0, 1); GL.glVertex2f(x, y + h)        # noqa: E702
        GL.glEnd()

    def _overlay(self, W, H, scale, pan):
        app = self.app
        s, m = app.s, app.model
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPushMatrix()
        GL.glLoadIdentity()
        GL.glOrtho(0, W, 0, H, -1, 1)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glPushMatrix()
        GL.glLoadIdentity()
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)      # premultiplied alpha
        GL.glEnable(GL.GL_TEXTURE_2D)
        GL.glColor4f(1, 1, 1, 1)
        px_per_A = H / (2 * scale)
        self.label_positions = []
        if s.labels_on:
            fc = color_rgb(s.label_color)
            bg = hex_to_rgb(s.background)
            is_h = m.is_h()
            for i in range(m.n):
                if not self.visible[i] or not atom_label_visible(s, m, i):
                    continue
                name = display_name(m, i, s)
                if name in s.hidden_labels:
                    continue
                off = 0.7 * self.anchor_r[i] + s.label_offset
                dx, dy = s.label_offsets.get(name, (0.0, 0.0))
                ax_, ay_ = self.anchor_xy[i, 0] + off + dx, self.anchor_xy[i, 1] + off + dy
                self.label_positions.append((name, ax_, ay_))
                x, y = self._to_px(ax_, ay_, W, H, scale, pan)
                runs = label_runs(m, i, s, app.styles, name)
                txt = runs[0][0] if len(runs) == 1 and tuple(runs[0][1]) == tuple(fc) else \
                    tuple((t, tuple(c)) for t, c in runs)
                self._draw_text(txt, x, y, s.label_size * (0.8 if is_h[i] else 1.0), fc, s.label_bold,
                                s.label_italic, s.label_font, s.label_halo, bg)
            if self.scene is not None:
                for qi, c in self.scene.q_xy:
                    q = (app.model.q_cart[qi] - app.center) @ app.R.T
                    x, y = self._to_px(q[0] + 0.12, q[1] + 0.12, W, H, scale, pan)
                    self._draw_text(m.q_labels[qi], x, y, s.label_size * 0.75, (0.42, 0.30, 0.58),
                                    family=s.label_font)
        if getattr(s, 'contact_labels', True):
            fc2 = color_rgb(s.label_color)
            for (i, j), st in (getattr(m, 'bond_style', None) or {}).items():
                if not st.get('dist') or max(i, j) >= len(self.anchor_xy):
                    continue
                if max(i, j) < len(self.visible) and not (self.visible[i] and self.visible[j]):
                    continue
                d = float(np.linalg.norm(m.cart[i] - m.cart[j]))
                p = 0.5 * (self.anchor_xy[i] + self.anchor_xy[j])
                x, y = self._to_px(p[0], p[1], W, H, scale, pan)
                self._draw_text(f'{d:.2f} Å', x, y, s.label_size * 0.8, fc2, False, False, s.label_font,
                                s.label_halo, hex_to_rgb(s.background))
        if self.scene is not None and self.scene.cell_corners is not None and app.struct is not None:
            corners = np.array([[a, b, c] for a in (0, 1) for b in (0, 1) for c in (0, 1)], float)
            P = (corners @ app.struct.cell.A.T - app.center) @ app.R.T
            cols = {4: (0.84, 0.15, 0.16), 2: (0.17, 0.63, 0.17), 1: (0.12, 0.47, 0.71), 0: (0.2, 0.2, 0.2)}
            for idx, name in ((0, 'O'), (4, 'a'), (2, 'b'), (1, 'c')):
                x, y = self._to_px(P[idx, 0], P[idx, 1], W, H, scale, pan)
                self._draw_text(' ' + name, x, y, s.label_size, cols[idx], family=s.label_font)
        GL.glDisable(GL.GL_TEXTURE_2D)
        sb = getattr(app, 'sel_bond', None)
        if sb is not None and max(sb) < len(self.anchor_xy):
            GL.glLineWidth(7.0)
            GL.glColor4f(0.0, 0.47 * 0.55, 1.0 * 0.55, 0.55)          # premultiplied
            GL.glBegin(GL.GL_LINES)
            for k in sb:
                GL.glVertex2f(*self._to_px(self.anchor_xy[k, 0], self.anchor_xy[k, 1], W, H, scale, pan))
            GL.glEnd()
        # shift-drag selection box
        br = getattr(app, 'box_rect', None)
        if br is not None:
            (x0, y0), (x1, y1) = (self._to_px(br[0], br[1], W, H, scale, pan), self._to_px(br[2], br[3], W, H, scale, pan))
            GL.glColor4f(0.0, 0.47 * 0.12, 0.12, 0.12)              # premultiplied fill
            GL.glBegin(GL.GL_QUADS)
            for vx, vy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                GL.glVertex2f(vx, vy)
            GL.glEnd()
            GL.glLineWidth(1.5)
            GL.glColor4f(0.0, 0.47, 1.0, 1.0)
            GL.glEnable(GL.GL_LINE_STIPPLE)
            GL.glLineStipple(1, 0x0F0F)
            GL.glBegin(GL.GL_LINE_LOOP)
            for vx, vy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                GL.glVertex2f(vx, vy)
            GL.glEnd()
            GL.glDisable(GL.GL_LINE_STIPPLE)
        # metal / ligand rings of the geometry-index picker
        GL.glLineWidth(3.0)
        for i, col in getattr(app, 'geo_highlight', None) or []:
            if i >= len(self.anchor_r) or not self.visible[i]:
                continue
            r = (self.anchor_r[i] + 0.16) * px_per_A
            cx, cy = self._to_px(self.anchor_xy[i, 0], self.anchor_xy[i, 1], W, H, scale, pan)
            GL.glColor4f(col[0], col[1], col[2], 1.0)
            GL.glBegin(GL.GL_LINES)
            for k in range(0, 48, 2):                 # dashed circle
                for kk in (k, k + 1):
                    a = 2 * math.pi * kk / 48
                    GL.glVertex2f(cx + r * math.cos(a), cy + r * math.sin(a))
            GL.glEnd()
        # selection rings
        GL.glLineWidth(2.0)
        for num, i in enumerate(app.selection, 1):
            if i >= len(self.anchor_r) or not self.visible[i]:
                continue
            r = (self.anchor_r[i] + 0.12) * px_per_A
            cx, cy = self._to_px(self.anchor_xy[i, 0], self.anchor_xy[i, 1], W, H, scale, pan)
            GL.glColor4f(0.0, 0.47, 1.0, 1.0)
            GL.glBegin(GL.GL_LINE_LOOP)
            for k in range(48):
                a = 2 * math.pi * k / 48
                GL.glVertex2f(cx + r * math.cos(a), cy + r * math.sin(a))
            GL.glEnd()
        GL.glEnable(GL.GL_TEXTURE_2D)
        GL.glColor4f(1, 1, 1, 1)
        for num, i in enumerate(app.selection, 1):
            if i >= len(self.anchor_r) or not self.visible[i]:
                continue
            r = (self.anchor_r[i] + 0.12) * px_per_A
            cx, cy = self._to_px(self.anchor_xy[i, 0], self.anchor_xy[i, 1], W, H, scale, pan)
            self._draw_text(str(num), cx - r * 0.7, cy + r * 0.7, min(max(s.label_size, 9), 18), (0.0, 0.47, 1.0), bold=True,
                            align='right')
        GL.glDisable(GL.GL_TEXTURE_2D)
        GL.glDisable(GL.GL_BLEND)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glPopMatrix()
        GL.glMatrixMode(GL.GL_MODELVIEW)

    # ------------------------------------------------------------------ helpers for the app
    def px_to_data(self, ex, ey):
        app = self.app
        W, H = max(self.winfo_width(), 1), max(self.winfo_height(), 1)
        p = 2 * app.scale / H
        return app.pan[0] - app.scale * W / H + (ex + 0.5) * p, app.pan[1] + app.scale - (ey + 0.5) * p

    def pick(self, x, y, tol=0.25):
        if len(self.anchor_xy) == 0:
            return None
        d = np.hypot(self.anchor_xy[:, 0] - x, self.anchor_xy[:, 1] - y)
        inside = (d <= self.anchor_r) & self.visible
        if inside.any():
            idx = np.flatnonzero(inside)
            return int(idx[np.argmax(self.anchor_z[idx])])        # front-most atom under the cursor
        dd = np.where(self.visible, d - self.anchor_r, np.inf)
        i = int(np.argmin(dd))
        return i if dd[i] < tol else None

    def refresh(self):
        if self.ready and self.winfo_ismapped():
            self._display()

    def read_pixels(self):
        """For tests: current front buffer as RGB array."""
        W, H = self.winfo_width(), self.winfo_height()
        self.tkMakeCurrent()
        data = GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
        return np.frombuffer(data, np.uint8).reshape(H, W, 3)[::-1]
