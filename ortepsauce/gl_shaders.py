"""GLSL sources shared by the OpenGL views: screen-aligned quads that ray-cast exact ellipsoids
(boundary bands, cut-out octant) and cylinders with the POV-Ray finish model of raster.py."""
import numpy as np

MAXM = 96          # max number of materials passed as uniforms

_COMMON_FS = """
uniform vec3 uCol[%(M)d];
uniform vec4 uFa[%(M)d];   // ambient, diffuse, brilliance, specular
uniform vec4 uFb[%(M)d];   // roughness, phong, phong_size, reflection
uniform vec2 uFc[%(M)d];   // metallic, crand
uniform vec3 uL0; uniform vec3 uL1; uniform float uI0; uniform float uI1;
uniform float uAmbient; uniform vec3 uBg; uniform float uSrgb; uniform float uDepthScale;

float hash3(vec3 q) {
    return fract(sin(dot(q, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
}

vec3 lightOne(vec3 n, vec3 L, float I, vec3 base, vec4 fa, vec4 fb, vec3 specCol) {
    vec3 V = vec3(0.0, 0.0, 1.0);
    float ndl = max(dot(n, L), 0.0);
    vec3 c = vec3(0.0);
    if (fa.y > 0.0) c += base * (fa.y * I * pow(ndl, fa.z));
    if (fa.w > 0.0) {
        vec3 H = normalize(L + V);
        c += specCol * (fa.w * I * pow(max(dot(n, H), 0.0), 1.0 / max(fb.x, 1e-4)));
    }
    if (fb.y > 0.0 && ndl > 0.0) {
        vec3 R = 2.0 * ndl * n - L;
        c += specCol * (fb.y * I * pow(max(R.z, 0.0), fb.z));
    }
    return c;
}

vec3 shade(vec3 n, float matf, vec3 loc) {
    int m = int(matf + 0.5);
    vec3 base = uCol[m];
    vec4 fa = uFa[m]; vec4 fb = uFb[m]; vec2 fc = uFc[m];
    vec3 specCol = fc.x > 0.5 ? base : vec3(1.0);
    vec3 col = base * (fa.x * uAmbient);
    col += lightOne(n, uL0, uI0, base, fa, fb, specCol);
    col += lightOne(n, uL1, uI1, base, fa, fb, specCol);
    if (fb.w > 0.0) {
        vec3 Rv = 2.0 * n.z * n - vec3(0.0, 0.0, 1.0);
        col += fb.w * uBg * (0.8 + 0.2 * clamp(0.5 + 0.5 * Rv.y, 0.0, 1.0));
    }
    if (fc.y > 0.0) {
        float h = hash3(floor(loc * 600.0));
        col *= 1.0 - 2.0 * fc.y * (h - 0.15);
    }
    col = clamp(col, 0.0, 1.0);
    if (uSrgb > 0.5) {
        vec3 lo = 12.92 * col;
        vec3 hi = 1.055 * pow(col, vec3(1.0 / 2.4)) - 0.055;
        col = mix(lo, hi, step(vec3(0.0031308), col));
    }
    return col;
}
""" % {'M': MAXM}

_ELL_VS = """
#version 120
attribute vec2 aCorner; attribute vec3 aCenter;
attribute vec3 aA0; attribute vec3 aA1; attribute vec3 aA2;
attribute vec3 aB0; attribute vec3 aB1; attribute vec3 aB2;
attribute vec4 aInfo;
uniform mat3 uR; uniform vec2 uPan; uniform vec2 uHalf;
varying vec2 vXY; varying vec3 vC; varying mat3 vBinv; varying vec4 vInfo;
void main() {
    vec3 c = uR * aCenter;
    mat3 A = uR * mat3(aA0, aA1, aA2);
    mat3 M = A * transpose(A);
    vec2 e = vec2(sqrt(M[0][0]), sqrt(M[1][1])) * 1.03 + vec2(1e-3);
    vXY = c.xy + aCorner * e;
    vC = c;
    vBinv = transpose(mat3(aB0, aB1, aB2)) * transpose(uR);
    vInfo = aInfo;
    gl_Position = vec4((vXY - uPan) / uHalf, 0.0, 1.0);
}
"""

_ELL_FS = """
#version 120
""" + _COMMON_FS + """
uniform float uBand;
varying vec2 vXY; varying vec3 vC; varying mat3 vBinv; varying vec4 vInfo;
void main() {
    vec3 u0 = vBinv * vec3(vXY - vC.xy, 0.0);
    vec3 w = vBinv[2];
    float ww = dot(w, w);
    float uw = dot(u0, w);
    float disc = uw * uw - ww * (dot(u0, u0) - 1.0);
    if (disc <= 0.0) discard;
    float t = (-uw + sqrt(disc)) / ww;
    vec3 uf = u0 + t * w;
    vec3 n = normalize(transpose(vBinv) * uf);
    float style = vInfo.x;
    float mat = vInfo.y;
    vec3 loc = uf;
    vec3 au = abs(uf);
    if (style > 0.5 && min(au.x, min(au.y, au.z)) < uBand) mat = vInfo.z;
    if (style > 1.5) {
        vec3 r0 = vec3(vBinv[0][0], vBinv[1][0], vBinv[2][0]);
        vec3 r1 = vec3(vBinv[0][1], vBinv[1][1], vBinv[2][1]);
        vec3 r2 = vec3(vBinv[0][2], vBinv[1][2], vBinv[2][2]);
        vec3 sg = vec3(r0.z >= 0.0 ? 1.0 : -1.0, r1.z >= 0.0 ? 1.0 : -1.0, r2.z >= 0.0 ? 1.0 : -1.0);
        if (sg.x * uf.x > 0.0 && sg.y * uf.y > 0.0 && sg.z * uf.z > 0.0) {
            float te = -1e9; int wi = -1;
            if (abs(w.x) > 1e-9) { float tt = -u0.x / w.x; if (tt < t - 1e-6 && tt > te) { te = tt; wi = 0; } }
            if (abs(w.y) > 1e-9) { float tt = -u0.y / w.y; if (tt < t - 1e-6 && tt > te) { te = tt; wi = 1; } }
            if (abs(w.z) > 1e-9) { float tt = -u0.z / w.z; if (tt < t - 1e-6 && tt > te) { te = tt; wi = 2; } }
            if (wi < 0) discard;
            vec3 ue = u0 + te * w;
            if (dot(ue, ue) > 1.0 + 1e-6) discard;
            vec3 row = wi == 0 ? r0 * sg.x : (wi == 1 ? r1 * sg.y : r2 * sg.z);
            n = normalize(row);
            t = te; loc = ue; mat = vInfo.w;
        }
    }
    float z = vC.z + t;
    gl_FragDepth = clamp(0.5 - z * uDepthScale, 0.0, 1.0);
    gl_FragColor = vec4(shade(n, mat, loc), 1.0);
}
"""

_CYL_VS = """
#version 120
attribute vec2 aCorner; attribute vec3 aP0; attribute vec3 aP1; attribute vec2 aInfo;
uniform mat3 uR; uniform vec2 uPan; uniform vec2 uHalf;
varying vec2 vXY; varying vec3 vP0; varying vec3 vP1; varying vec2 vInfo;
void main() {
    vec3 p0 = uR * aP0; vec3 p1 = uR * aP1;
    vec2 d = p1.xy - p0.xy;
    float L = length(d);
    vec2 dir = L > 1e-6 ? d / L : vec2(1.0, 0.0);
    vec2 perp = vec2(-dir.y, dir.x);
    float r = aInfo.x * 1.05 + 1e-3;
    float s = 0.5 * (aCorner.x + 1.0);
    vec2 base = mix(p0.xy - dir * r, p1.xy + dir * r, s);
    vXY = base + perp * aCorner.y * r;
    vP0 = p0; vP1 = p1; vInfo = aInfo;
    gl_Position = vec4((vXY - uPan) / uHalf, 0.0, 1.0);
}
"""

_CYL_FS = """
#version 120
""" + _COMMON_FS + """
varying vec2 vXY; varying vec3 vP0; varying vec3 vP1; varying vec2 vInfo;
void main() {
    vec3 ax = vP1 - vP0;
    float L = length(ax);
    if (L < 1e-6) discard;
    vec3 a = ax / L;
    float A2 = 1.0 - a.z * a.z;
    if (A2 < 1e-6) discard;
    float r = vInfo.x;
    vec3 f = vec3(vXY - vP0.xy, -vP0.z);
    float fa = dot(f, a);
    float g0z = f.z - fa * a.z;
    float g0g0 = dot(f, f) - fa * fa;
    float disc = g0z * g0z - A2 * (g0g0 - r * r);
    if (disc <= 0.0) discard;
    float z = (-g0z + sqrt(disc)) / A2;
    float tp = fa + z * a.z;
    if (tp < 0.0 || tp > L) discard;
    vec3 p = f + vec3(0.0, 0.0, z) - tp * a;
    vec3 n = p / r;
    gl_FragDepth = clamp(0.5 - z * uDepthScale, 0.0, 1.0);
    gl_FragColor = vec4(shade(normalize(n), vInfo.y, vec3(tp, p.x, p.y)), 1.0);
}
"""

_STYLE = {'PlainEllipse': 0.0, 'BoundaryEllipse': 1.0, 'CutoutEllipse': 2.0}
_QUAD = np.array([[-1, -1], [1, -1], [1, 1], [-1, -1], [1, 1], [-1, 1]], np.float32)
GL_STYLES = ('ORTEP ellipsoids', 'Van der Waals', 'Ball and Stick', 'Rods')



def srgb(c):
    c = np.clip(np.asarray(c, float), 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)
