"""Software renderer for shaded (POV-Ray-like) pictures.

Orthographic z-buffer with analytic ray intersections (ellipsoids incl. boundary bands and
cut-out octants, cylinders, RMSD/MSD star surfaces), followed by deferred Phong/Blinn shading
using POV-Ray finish parameters. Pure numpy - no OpenGL needed, identical on every platform,
and any output resolution."""
import copy
import math

import numpy as np


# ---------------------------------------------------------------------------- noise
def _hash3(ix, iy, iz):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791)
    h = (h ^ (h >> 13)) * 1274126177
    return ((h ^ (h >> 16)) & 0xFFFF).astype(np.float32) / 65535.0


def value_noise(p):
    """Smooth 3D value noise in [0,1]; p: (n,3)."""
    f = np.floor(p)
    t = p - f
    t = t * t * (3 - 2 * t)
    i = f.astype(np.int64)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = ((t[:, 0] if dx else 1 - t[:, 0]) * (t[:, 1] if dy else 1 - t[:, 1])
                     * (t[:, 2] if dz else 1 - t[:, 2]))
                out = out + w * _hash3(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz)
    return out


def turbulence(p, octaves=5):
    v = np.zeros(len(p), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        v += amp * np.abs(value_noise(p * (2 ** o)) * 2 - 1)
        tot += amp
        amp *= 0.5
    return v / tot


def _color_map(v, cmap):
    v = np.clip(v, 0, 1)
    out = np.empty((len(v), 3), np.float32)
    out[:] = cmap[-1][1]
    pos = [c[0] for c in cmap]
    cols = [np.array(c[1], np.float32) for c in cmap]
    for a in range(len(cmap) - 1):
        lo, hi = pos[a], pos[a + 1]
        sel = (v >= lo) & (v < hi)
        if not sel.any():
            continue
        if hi - lo < 1e-9:
            out[sel] = cols[a + 1]
        else:
            f = ((v[sel] - lo) / (hi - lo))[:, None]
            out[sel] = cols[a] * (1 - f) + cols[a + 1] * f
    out[v < pos[0]] = cols[0]
    return out


# ---------------------------------------------------------------------------- renderer
class Raster:
    def __init__(self, width, height, x0, y0, px, depth_only=False):
        """Pixel grid of width x height; (x0, y0) = top-left corner in screen Angstrom,
        px = Angstrom per pixel. depth_only: z-buffer only (used for shadow maps)."""
        self.W, self.H = int(width), int(height)
        self.px = px
        self.x0, self.y0 = x0, y0
        self.xs = (self.x0 + (np.arange(self.W) + 0.5) * self.px).astype(np.float64)
        self.ys = (self.y0 - (np.arange(self.H) + 0.5) * self.px).astype(np.float64)
        self.depth = np.full((self.H, self.W), -np.inf, np.float32)
        self.normal = None if depth_only else np.zeros((self.H, self.W, 3), np.float32)
        self.loc = None if depth_only else np.zeros((self.H, self.W, 3), np.float32)
        self.mat = np.full((self.H, self.W), -1, np.int32)
        self.oid = np.full((self.H, self.W), -1, np.int32)

    # -- batched primitives (vectorised over all pixels of many primitives at once)
    def _windows(self, xmin, xmax, ymin, ymax):
        i0 = np.clip(np.floor((xmin - self.x0) / self.px).astype(np.int64), 0, self.W)
        i1 = np.clip(np.floor((xmax - self.x0) / self.px).astype(np.int64) + 2, 0, self.W)
        j0 = np.clip(np.floor((self.y0 - ymax) / self.px).astype(np.int64), 0, self.H)
        j1 = np.clip(np.floor((self.y0 - ymin) / self.px).astype(np.int64) + 2, 0, self.H)
        w = np.maximum(i1 - i0, 0)
        h = np.maximum(j1 - j0, 0)
        return i0, j0, w, h

    @staticmethod
    def _chunks(counts, limit=1_500_000):
        """Split primitive indices into groups whose pixel totals stay below `limit`."""
        out, cur, tot = [], [], 0
        for k, c in enumerate(counts):
            if c == 0:
                continue
            if cur and tot + c > limit:
                out.append(np.array(cur))
                cur, tot = [], 0
            cur.append(k)
            tot += c
        if cur:
            out.append(np.array(cur))
        return out

    def _expand(self, idx, i0, j0, w, h):
        """Pixel list for primitives idx -> (prim index per pixel, col, row)."""
        cnt = (w * h)[idx]
        pid = np.repeat(idx, cnt)
        starts = np.repeat(np.cumsum(cnt) - cnt, cnt)
        local = np.arange(cnt.sum()) - starts
        ww = w[pid]
        col = i0[pid] + local % ww
        row = j0[pid] + local // ww
        return pid, col, row

    def _commit_batch(self, row, col, z, n, mat, loc, oid):
        if len(z) == 0:
            return
        p = row * self.W + col
        order = np.lexsort((z, p))
        ps = p[order]
        last = np.ones(len(ps), bool)
        last[:-1] = ps[1:] != ps[:-1]
        sel = order[last]
        dflat = self.depth.reshape(-1)
        ok = z[sel] > dflat[p[sel]]
        sel = sel[ok]
        q = p[sel]
        dflat[q] = z[sel]
        if self.normal is not None:
            self.normal.reshape(-1, 3)[q] = n[sel]
            self.loc.reshape(-1, 3)[q] = loc[sel]
        self.mat.reshape(-1)[q] = mat[sel]
        self.oid.reshape(-1)[q] = oid[sel]

    def ellipsoids(self, C, V, A, style, mat, band, cut, oid, band_width=0.06):
        """C (n,3) centres, V (n,3,3) principal axes as columns, A (n,3) semi-axes,
        style (n,) 0 plain / 1 boundary / 2 cutout; mat/band/cut/oid (n,) ints."""
        if len(C) == 0:
            return
        M = np.einsum('nij,nj,nkj->nik', V, A ** 2, V)
        ex, ey = np.sqrt(M[:, 0, 0]), np.sqrt(M[:, 1, 1])
        i0, j0, w, h = self._windows(C[:, 0] - ex, C[:, 0] + ex, C[:, 1] - ey, C[:, 1] + ey)
        B = np.transpose(V, (0, 2, 1)) / A[:, :, None]          # rows: V[:, i] / a_i
        Wz = B[:, :, 2]
        sgn_all = np.where(V[:, 2, :] >= 0, 1.0, -1.0)            # octant toward the viewer
        for idx in self._chunks(w * h):
            pid, col, row = self._expand(idx, i0, j0, w, h)
            dx = self.xs[col] - C[pid, 0]
            dy = self.ys[row] - C[pid, 1]
            u0 = B[pid, :, 0] * dx[:, None] + B[pid, :, 1] * dy[:, None]
            wv = Wz[pid]
            ww = (wv * wv).sum(1)
            uw = (u0 * wv).sum(1)
            disc = uw * uw - ww * ((u0 * u0).sum(1) - 1.0)
            keep = disc > 0
            if not keep.any():
                continue
            pid, col, row, u0, wv, ww, uw, disc = (a[keep] for a in (pid, col, row, u0, wv, ww, uw, disc))
            t = (-uw + np.sqrt(disc)) / ww
            uf = u0 + t[:, None] * wv
            Ap = A[pid]
            Vp = V[pid]
            nrm = np.einsum('nij,nj->ni', Vp, uf / Ap)
            nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
            z = C[pid, 2] + t
            loc = uf
            st = style[pid]
            m = mat[pid].copy()
            bnd = (st >= 1) & (np.abs(uf).min(1) < band_width)
            m[bnd] = band[pid[bnd]]
            valid = np.ones(len(pid), bool)
            cutmask = st == 2
            if cutmask.any():
                sg = sgn_all[pid]
                inoct = cutmask & np.all(sg * uf > 0, axis=1)
                if inoct.any():
                    io = np.flatnonzero(inoct)
                    u0i, wvi, ti = u0[io], wv[io], t[io]
                    with np.errstate(divide='ignore', invalid='ignore'):
                        tt = -u0i / wvi
                    tt = np.where((np.abs(wvi) > 1e-12) & (tt < ti[:, None] - 1e-9), tt, -np.inf)
                    which = tt.argmax(1)
                    te = tt[np.arange(len(io)), which]
                    ue = u0i + te[:, None] * wvi
                    inside = (ue * ue).sum(1) <= 1.0 + 1e-9
                    valid[io[~inside]] = False
                    fi = io[inside]
                    wf = which[inside]
                    nf = Vp[fi, :, wf] * sg[fi, wf][:, None]
                    nrm[fi] = nf
                    z[fi] = C[pid[fi], 2] + te[inside]
                    loc = loc.copy()
                    loc[fi] = ue[inside]
                    m[fi] = cut[pid[fi]]
            v = valid
            self._commit_batch(row[v], col[v], z[v].astype(np.float32), nrm[v], m[v], loc[v], oid[pid[v]])

    def cylinders(self, P0, P1, R, mat, oid):
        if len(P0) == 0:
            return
        ax = P1 - P0
        L = np.linalg.norm(ax, axis=1)
        good = L > 1e-6
        a = np.zeros_like(ax)
        a[good] = ax[good] / L[good, None]
        A2 = 1.0 - a[:, 2] ** 2
        good &= A2 > 1e-6
        xmin = np.minimum(P0[:, 0], P1[:, 0]) - R
        xmax = np.maximum(P0[:, 0], P1[:, 0]) + R
        ymin = np.minimum(P0[:, 1], P1[:, 1]) - R
        ymax = np.maximum(P0[:, 1], P1[:, 1]) + R
        i0, j0, w, h = self._windows(xmin, xmax, ymin, ymax)
        w = np.where(good, w, 0)
        for idx in self._chunks(w * h):
            pid, col, row = self._expand(idx, i0, j0, w, h)
            ap = a[pid]
            fx = self.xs[col] - P0[pid, 0]
            fy = self.ys[row] - P0[pid, 1]
            fz = -P0[pid, 2]
            fa = fx * ap[:, 0] + fy * ap[:, 1] + fz * ap[:, 2]
            g0z = fz - fa * ap[:, 2]
            g0g0 = fx * fx + fy * fy + fz * fz - fa * fa
            A2p = A2[pid]
            rp = R[pid]
            disc = g0z * g0z - A2p * (g0g0 - rp * rp)
            zz = (-g0z + np.sqrt(np.maximum(disc, 0))) / A2p
            tpar = fa + zz * ap[:, 2]
            hit = (disc > 0) & (tpar >= 0) & (tpar <= L[pid])
            if not hit.any():
                continue
            k = hit
            px = fx[k] - tpar[k] * ap[k, 0]
            py = fy[k] - tpar[k] * ap[k, 1]
            pz = fz[k] + zz[k] - tpar[k] * ap[k, 2]
            n = np.stack([px, py, pz], 1) / rp[k, None]
            loc = np.stack([tpar[k], px, py], 1)
            self._commit_batch(row[k], col[k], zz[k].astype(np.float32), n, mat[pid[k]], loc, oid[pid[k]])

    # -- helpers
    def _window(self, xmin, xmax, ymin, ymax):
        i0 = max(int((xmin - self.x0) / self.px), 0)
        i1 = min(int((xmax - self.x0) / self.px) + 2, self.W)
        j0 = max(int((self.y0 - ymax) / self.px), 0)
        j1 = min(int((self.y0 - ymin) / self.px) + 2, self.H)
        if i0 >= i1 or j0 >= j1:
            return None
        return j0, j1, i0, i1

    def _commit(self, win, hit, z, n, mat, loc, oid):
        j0, j1, i0, i1 = win
        d = self.depth[j0:j1, i0:i1]
        upd = hit & (z > d)
        if not upd.any():
            return
        d[upd] = z[upd]
        if self.normal is not None:
            self.normal[j0:j1, i0:i1][upd] = n[upd]
            self.loc[j0:j1, i0:i1][upd] = loc[upd]
        mview = self.mat[j0:j1, i0:i1]
        mview[upd] = mat[upd] if isinstance(mat, np.ndarray) else mat
        self.oid[j0:j1, i0:i1][upd] = oid

    # -- star-shaped RMSD / MSD surfaces (ray-marched per primitive)
    def surface(self, c, U, kind, k, ueq, rmax, mat, oid, samples=28):
        win = self._window(c[0] - rmax, c[0] + rmax, c[1] - rmax, c[1] + rmax)
        if win is None:
            return
        j0, j1, i0, i1 = win
        dx = np.broadcast_to((self.xs[i0:i1] - c[0])[None, :], (j1 - j0, i1 - i0))
        dy = np.broadcast_to((self.ys[j0:j1] - c[1])[:, None], (j1 - j0, i1 - i0))
        cand = dx * dx + dy * dy < rmax * rmax
        if not cand.any():
            return
        X, Y = dx[cand], dy[cand]
        msd_scale = k / math.sqrt(ueq)

        def F(zz):
            d2 = X * X + Y * Y + zz * zz + 1e-12
            q = (U[0, 0] * X * X + U[1, 1] * Y * Y + U[2, 2] * zz * zz
                 + 2 * (U[0, 1] * X * Y + U[0, 2] * X * zz + U[1, 2] * Y * zz)) / d2
            r = k * np.sqrt(np.maximum(q, 0)) if kind == 'rmsd' else msd_scale * q
            return np.sqrt(d2) - r

        zs = np.linspace(rmax, -rmax, samples)
        prev = F(np.full_like(X, zs[0]))
        found = np.zeros(len(X), bool)
        zhi = np.full(len(X), zs[0])
        zlo = np.full(len(X), zs[0])
        for zz in zs[1:]:
            cur = F(np.full_like(X, zz))
            new = (~found) & (cur < 0) & (prev >= 0)
            zlo[new] = zz
            zhi[new] = zz + (zs[0] - zs[1])
            found |= new
            prev = cur
        if not found.any():
            return
        X, Y, zlo, zhi = X[found], Y[found], zlo[found], zhi[found]
        Xs, Ys = X, Y            # F() sees the reduced X, Y through the closure
        for _ in range(12):
            zm = 0.5 * (zlo + zhi)
            fm = F(zm)
            inside = fm < 0
            zlo = np.where(inside, zm, zlo)
            zhi = np.where(inside, zhi, zm)
        z = 0.5 * (zlo + zhi)
        # numerical normal
        e = 1e-3
        d = np.stack([Xs, Ys, z], -1)

        def Fp(p):
            d2 = (p * p).sum(-1) + 1e-12
            q = np.einsum('ni,ij,nj->n', p, U, p) / d2
            r = k * np.sqrt(np.maximum(q, 0)) if kind == 'rmsd' else msd_scale * q
            return np.sqrt(d2) - r
        grad = np.stack([(Fp(d + e * np.eye(3)[ax]) - Fp(d - e * np.eye(3)[ax])) for ax in range(3)], -1)
        grad /= np.maximum(np.linalg.norm(grad, axis=-1, keepdims=True), 1e-12)
        idx = np.argwhere(cand)[found]
        H, W = j1 - j0, i1 - i0
        hit = np.zeros((H, W), bool)
        hit[idx[:, 0], idx[:, 1]] = True
        zz = np.zeros((H, W), np.float32)
        zz[idx[:, 0], idx[:, 1]] = c[2] + z
        nn = np.zeros((H, W, 3), np.float32)
        nn[idx[:, 0], idx[:, 1]] = grad
        ll = np.zeros((H, W, 3), np.float32)
        ll[idx[:, 0], idx[:, 1]] = d / max(rmax, 1e-6)
        self._commit(win, hit, zz, nn, mat, ll, oid)

    # -- shading
    def shade(self, materials, lights, ambient_light=1.0, background=(1, 1, 1), outline=False, quick=False,
              shadow_maps=None, grain=True):
        H, W = self.H, self.W
        img = np.empty((H * W, 3), np.float32)
        img[:] = background
        V = np.array([0, 0, 1.0], np.float32)
        bg = np.array(background, np.float32)
        fm = self.mat.ravel()
        cov = np.flatnonzero(fm >= 0)
        order = cov[np.argsort(fm[cov], kind='stable')]
        bounds = np.searchsorted(fm[order], np.arange(len(materials) + 1))
        nflat = self.normal.reshape(-1, 3)
        lflat = self.loc.reshape(-1, 3)
        for mi, m in enumerate(materials):
            sel = order[bounds[mi]:bounds[mi + 1]]
            if len(sel) == 0:
                continue
            N = nflat[sel]
            loc = lflat[sel]
            f = m['finish']
            base = np.empty((len(N), 3), np.float32)
            base[:] = m['color']
            pat = None if quick else m.get('pattern')
            if pat:
                if pat[0] == 'granite':
                    base = _color_map(turbulence(loc * 3.0 + 7.3), pat[1])
                elif pat[0] == 'brushed':
                    streak = value_noise(np.stack([loc[:, 0] * 2, loc[:, 1] * 400, loc[:, 2] * 400], -1))
                    N = N + 0.25 * (streak[:, None] - 0.5) * np.array([0, 1, 0], np.float32)
                elif pat[0] == 'waves':
                    rr = np.linalg.norm(loc[:, :2], axis=1)
                    N = N + 0.15 * np.sin(rr * 60)[:, None] * np.array([1, 0, 0], np.float32)
                elif pat[0] == 'wrinkles':
                    N = N + 0.3 * (np.stack([value_noise(loc * 10 + o) for o in (0, 3.1, 6.7)], -1) - 0.5)
                N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
            ndv = np.clip(N @ V, 0, 1)
            col = base * (f['ambient'] * ambient_light)
            spec_col = base if f['metallic'] else np.ones_like(base)
            if shadow_maps:
                rows, cols = np.divmod(sel, W)
                P = np.stack([self.xs[cols], self.ys[rows], self.depth.reshape(-1)[sel].astype(np.float64)], 1)
            for li, (L, intensity) in enumerate(lights):
                if shadow_maps and shadow_maps[li] is not None:
                    intensity = intensity * shadow_maps[li].visibility(P)
                ndl = np.clip(N @ L, 0, 1)
                if f['diffuse'] > 0:
                    col = col + base * (f['diffuse'] * intensity * ndl ** f['brilliance'])[:, None]
                if f['specular'] > 0:
                    Hh = L + V
                    Hh = Hh / np.linalg.norm(Hh)
                    ndh = np.clip(N @ Hh, 0, 1)
                    col = col + spec_col * (f['specular'] * intensity * ndh ** (1.0 / max(f['roughness'], 1e-4)))[:, None]
                if f['phong'] > 0:
                    Rl = 2 * ndl[:, None] * N - L
                    rdv = np.clip(Rl @ V, 0, 1)
                    col = col + spec_col * (f['phong'] * intensity * rdv ** f['phong_size'] * (ndl > 0))[:, None]
            if f['reflection'] > 0:
                # POV-Ray reflects the scene; with nothing else around the reflected ray mostly sees
                # the background, so the reflection term is ~ reflection x background color
                Rv = 2 * ndv[:, None] * N - V
                env = (0.8 + 0.2 * np.clip(0.5 + 0.5 * Rv[:, 1], 0, 1))[:, None] * bg[None, :]
                col = col + f['reflection'] * env
            if f['crand'] > 0 and not quick and grain:
                # POV-Ray crand: subtract a random amount per sample (grainy surface)
                q = np.floor(loc * 600.0).astype(np.int64)
                rnd = _hash3(q[:, 0], q[:, 1], q[:, 2])
                col = col * (1.0 - 2.0 * f['crand'] * (rnd - 0.15))[:, None]   # calibrated vs POV-Ray 3.7
            elif f['crand'] > 0 and not quick:
                # grain off (animations: per-sample noise shimmers from frame to frame) - keep the same
                # average brightness as the grainy surface (mean of rnd = 0.5)
                col = col * (1.0 - 0.7 * f['crand'])
            img[sel] = np.clip(col, 0, 1)
        img = img.reshape(H, W, 3)
        if outline:
            o = self.oid
            dep = self.depth
            edge = np.zeros((H, W), bool)
            for sh in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                o2 = np.roll(o, sh, (0, 1))
                d2 = np.roll(dep, sh, (0, 1))
                edge |= (self.mat >= 0) & (o2 != o) & (d2 < dep - 0.05)
            img[edge] *= 0.15
        return img

    def coverage(self):
        return (self.mat >= 0).astype(np.float32)


def light_vectors(azimuth, elevation, fill):
    az, el = math.radians(azimuth), math.radians(elevation)
    key = np.array([math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)], np.float32)
    key /= np.linalg.norm(key)
    lights = [(key, 1.0)]
    if fill > 0:
        f = np.array([-key[0] * 0.8, -0.2, 1.0], np.float32)
        lights.append((f / np.linalg.norm(f), float(fill)))
    return lights


_SRGB_LUT = None


def _box_down(a, ss):
    """Average ss x ss blocks (much faster than reshape().mean() for float32 images)."""
    acc = a[0::ss, 0::ss].astype(np.float32)
    for i in range(ss):
        for j in range(ss):
            if i or j:
                acc += a[i::ss, j::ss]
    return acc * (1.0 / (ss * ss))


def _encode(img, srgb):
    """float linear 0..1 -> uint8, optionally sRGB-encoded (lookup table, fast)."""
    global _SRGB_LUT
    idx = (np.clip(img, 0, 1) * 4095 + 0.5).astype(np.uint16)
    if not srgb:
        return (idx >> 4).astype(np.uint8)
    if _SRGB_LUT is None:
        x = np.arange(4096) / 4095.0
        y = np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)
        _SRGB_LUT = (y * 255 + 0.5).astype(np.uint8)
    return _SRGB_LUT[idx]


_STYLE_CODE = {'PlainEllipse': 0, 'BoundaryEllipse': 1, 'CutoutEllipse': 2}


def _rasterize(scene, settings, W, H, x0, y0, px, ras=None):
    ras = ras or Raster(W, H, x0, y0, px)
    ells = [p for p in scene.prims if p['type'] == 'ellipsoid']
    cyls = [p for p in scene.prims if p['type'] == 'cylinder']
    if ells:
        ras.ellipsoids(np.array([p['c'] for p in ells], float), np.array([p['V'] for p in ells], float),
                       np.array([p['a'] for p in ells], float),
                       np.array([_STYLE_CODE.get(p['style'], 0) for p in ells]),
                       np.array([p['mat'] for p in ells]), np.array([p['band'] for p in ells]),
                       np.array([p['cut'] for p in ells]), np.array([p['oid'] for p in ells]),
                       band_width=settings.band_width)
    if cyls:
        ras.cylinders(np.array([p['p0'] for p in cyls], float), np.array([p['p1'] for p in cyls], float),
                      np.array([p['r'] for p in cyls], float), np.array([p['mat'] for p in cyls]),
                      np.array([p['oid'] for p in cyls]))
    for p in scene.prims:
        if p['type'] == 'surface':
            ras.surface(p['c'], p['U'], p['kind'], p['k'], p['ueq'], p['rmax'], p['mat'], p['oid'])
    lights = light_vectors(settings.light_azimuth, settings.light_elevation, settings.fill_light)
    return ras, lights


class _PrimScene:
    def __init__(self, prims):
        self.prims = prims


class ShadowMap:
    """Shadow map for a parallel light (as POV-Ray's `parallel` light sources): the scene is
    z-buffered as seen from the light; a point is lit when nothing lies between it and the light."""

    def __init__(self, scene, settings, L, res=2048):
        z = np.asarray(L, float)
        z = z / np.linalg.norm(z)
        up = np.array([0.0, 1.0, 0.0]) if abs(z[1]) < 0.95 else np.array([1.0, 0.0, 0.0])
        x = np.cross(up, z)
        x /= np.linalg.norm(x)
        y = np.cross(z, x)
        self.Rl = Rl = np.array([x, y, z])
        prims, pts = [], []
        for p in scene.prims:
            q = dict(p)
            if p['type'] == 'ellipsoid':
                q['c'] = Rl @ p['c']
                q['V'] = Rl @ p['V']
                q['style'] = 'PlainEllipse'      # (the small cut-out octant is ignored for shadows)
                pts.append((q['c'], float(np.max(p['a']))))
            elif p['type'] == 'cylinder':
                if p.get('oid', 0) == -3:
                    continue                      # unit-cell edges cast no shadow
                q['p0'], q['p1'] = Rl @ p['p0'], Rl @ p['p1']
                pts.append((q['p0'], p['r']))
                pts.append((q['p1'], p['r']))
            elif p['type'] == 'surface':
                q['c'] = Rl @ p['c']
                q['U'] = Rl @ p['U'] @ Rl.T
                pts.append((q['c'], p['rmax']))
            prims.append(q)
        if not pts:
            self.depth = None
            return
        P = np.array([c for c, _ in pts])
        r = np.array([rr for _, rr in pts])
        lo = (P[:, :2] - r[:, None]).min(0) - 0.2
        hi = (P[:, :2] + r[:, None]).max(0) + 0.2
        ext = float((hi - lo).max())
        self.px = ext / res
        self.x0, self.y0 = lo[0], lo[1] + ext
        ras = Raster(res, res, self.x0, self.y0, self.px, depth_only=True)
        sub = copy.copy(settings)
        _rasterize(_PrimScene(prims), sub, res, res, self.x0, self.y0, self.px, ras=ras)
        self.depth = ras.depth
        self.res = res
        self.bias = 3.0 * self.px + 0.01

    def visibility(self, P):
        """P (n,3) screen-frame points -> fraction lit (3x3 percentage-closer filtering)."""
        if self.depth is None or len(P) == 0:
            return np.ones(len(P), np.float32)
        Q = P @ self.Rl.T
        fi = (Q[:, 0] - self.x0) / self.px - 0.5
        fj = (self.y0 - Q[:, 1]) / self.px - 0.5
        lit = np.zeros(len(P), np.float32)
        for dj in (-1, 0, 1):
            for di in (-1, 0, 1):
                i = np.clip(np.round(fi + di).astype(np.int64), 0, self.res - 1)
                j = np.clip(np.round(fj + dj).astype(np.int64), 0, self.res - 1)
                d = self.depth[j, i]
                lit += (Q[:, 2] >= d - self.bias) | ~np.isfinite(d)
        return lit / 9.0


def make_shadow_maps(scene, settings, res=2048):
    return [ShadowMap(scene, settings, L, res) for L, _ in
            light_vectors(settings.light_azimuth, settings.light_elevation, settings.fill_light)]


def render_scene(scene, width, height, scale, pan, settings, ss=1, background=(1, 1, 1), transparent=False,
                 tile_pixels=4_000_000, quick=False, shadows=False, progress=None):
    """Render a Scene. Returns (rgba uint8 HxWx4, oid HxW).
    Large outputs are rendered in horizontal strips to bound memory.
    Output is sRGB encoded like POV-Ray 3.7 (assumed_gamma 1.0) unless settings.srgb is False."""
    W, H = int(width), int(height)
    WS, HS = W * ss, H * ss
    px = 2.0 * scale / HS
    x0 = pan[0] - WS / 2 * px
    ytop = pan[1] + HS / 2 * px
    rows = max(ss, (tile_pixels // max(WS, 1)) // ss * ss)
    out = np.empty((H, W, 4), np.uint8)
    oid_parts = []
    smaps = None
    if shadows:
        if progress:
            progress(0.0, 'Shadow maps …')
        res = int(min(4096, max(1024, 1.2 * max(WS, HS))))
        smaps = make_shadow_maps(scene, settings, res)
    n_strips = max(1, -(-HS // rows))
    for k, r0 in enumerate(range(0, HS, rows)):
        if progress:
            progress(k / n_strips, f'Rendering strip {k + 1}/{n_strips} …')
        hs = min(rows, HS - r0)
        ras, lights = _rasterize(scene, settings, WS, hs, x0, ytop - r0 * px, px)
        img = ras.shade(scene.materials, lights, settings.ambient_light, background, settings.outline, quick,
                        shadow_maps=smaps, grain=getattr(settings, 'grain', True))
        alpha = ras.coverage()
        oid = ras.oid
        if ss > 1:
            img = _box_down(img, ss)
            alpha = _box_down(alpha, ss)
            oid = oid[ss // 2::ss, ss // 2::ss]
        if transparent:
            # un-premultiply the background so edges carry no background halo
            a3 = np.maximum(alpha, 1e-4)[..., None]
            img = np.clip((img - (1 - alpha[..., None]) * np.asarray(background, np.float32)) / a3, 0, 1)
        o0 = r0 // ss
        o1 = o0 + img.shape[0]
        out[o0:o1, :, :3] = _encode(img, getattr(settings, 'srgb', True))
        out[o0:o1, :, 3] = (alpha * 255 + 0.5).astype(np.uint8) if transparent else 255
        oid_parts.append(oid)
    if progress:
        progress(1.0, 'Rendered')
    return out, np.concatenate(oid_parts, 0)
