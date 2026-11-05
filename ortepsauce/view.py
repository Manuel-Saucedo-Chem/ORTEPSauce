"""View/orientation helpers and off-screen image export."""
import math

import numpy as np


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def default_orientation(cart):
    """Largest spread horizontal, second vertical, view down the smallest-spread axis."""
    if len(cart) < 3:
        return np.eye(3)
    X = cart - cart.mean(axis=0)
    w, v = np.linalg.eigh(X.T @ X)
    R = v[:, ::-1].T            # rows: largest, middle, smallest
    if np.linalg.det(R) < 0:
        R[2] *= -1
    return R


def view_along(direction, up_hint=None):
    """Rotation that looks down `direction` (direction points toward the viewer)."""
    z = np.asarray(direction, float)
    z = z / np.linalg.norm(z)
    up = np.array([0, 1.0, 0]) if up_hint is None else np.asarray(up_hint, float)
    if abs(np.dot(up, z)) > 0.95:
        up = np.array([1.0, 0, 0])
    x = np.cross(up, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return np.array([x, y, z])


def fit_scale(model, R, center, aspect=4 / 3, margin=1.08, pad=0.6):
    """Half-height (Angstrom) of the view so the whole model fits a window of given w/h aspect.
    pad: extra Angstrom around atom centres (use ~2 for space-filling styles)."""
    if model.n == 0:
        return 5.0
    X = (model.cart - center) @ R.T
    ext = max((np.abs(X[:, 0]).max() + pad) / aspect, np.abs(X[:, 1]).max() + pad)
    return max(ext * margin, 2.0)


def orthonormalize(R):
    u, _, vt = np.linalg.svd(R)
    return u @ vt
