"""Fake shadows for GPUs that can't afford shadow maps.
  * contact AO  : soft dark ring on the ground around every obstacle
  * cast shadows: each obstacle's real planar projection along the sun direction (one mesh, one draw call)
  * blob shadows: stretched soft ellipse under each enemy"""
import math

from panda3d.core import (CardMaker, Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat,
                          GeomVertexWriter, TransparencyAttrib)

import textures as T


def _hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


class _Mesh:
    def __init__(self):
        self.vd = GeomVertexData("shadows", GeomVertexFormat.getV3c4(), Geom.UHStatic)
        self.vw, self.cw = GeomVertexWriter(self.vd, "vertex"), GeomVertexWriter(self.vd, "color")
        self.tris = GeomTriangles(Geom.UHStatic)

    def vert(self, x, y, z, a):
        i = self.vw.getWriteRow()
        self.vw.addData3(x, y, z); self.cw.addData4(0, 0, 0, a)
        return i

    def fan(self, poly, z, alpha):
        cx = sum(p[0] for p in poly) / len(poly); cy = sum(p[1] for p in poly) / len(poly)
        c = self.vert(cx, cy, z, alpha)
        ids = [self.vert(x, y, z, alpha) for x, y in poly]
        for i in range(len(ids)):
            self.tris.addVertices(c, ids[i], ids[(i + 1) % len(ids)])

    def ring(self, cx, cy, hx, hy, margin, a_in, z):
        inner = [(cx - hx, cy - hy), (cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy)]
        outer = [(cx - hx - margin, cy - hy - margin), (cx + hx + margin, cy - hy - margin),
                 (cx + hx + margin, cy + hy + margin), (cx - hx - margin, cy + hy + margin)]
        ii = [self.vert(x, y, z, a_in) for x, y in inner]
        oo = [self.vert(x, y, z, 0.0) for x, y in outer]
        for k in range(4):
            n = (k + 1) % 4
            self.tris.addVertices(ii[k], ii[n], oo[n]); self.tris.addVertices(ii[k], oo[n], oo[k])

    def node(self, parent):
        g = Geom(self.vd); g.addPrimitive(self.tris)
        gn = GeomNode("fake_shadows"); gn.addGeom(g)
        np_ = parent.attachNewNode(gn)
        np_.setTransparency(TransparencyAttrib.MAlpha)
        np_.setDepthWrite(False); np_.setLightOff(); np_.setTwoSided(True); np_.setBin("transparent", 5)
        return np_


def build_contact_shadows(parent, obstacles, sun, projected=True):
    n = math.sqrt(sum(c * c for c in sun))
    sx, sy, sz = (c / n for c in sun)
    m = _Mesh()
    for cx, cy, hx, hy, hz, kind in obstacles:
        if kind != "pole":
            m.ring(cx, cy, hx, hy, 1.4 if kind == "building" else 0.8, 0.30 if kind == "building" else 0.20, 0.022)
        if not projected:
            continue
        top = 2 * hz
        pts = []
        for dx in (-hx, hx):
            for dy in (-hy, hy):
                for z in (0.0, top):
                    pts.append((cx + dx - sx / sz * z, cy + dy - sy / sz * z))
        poly = _hull(pts)
        if len(poly) < 3:
            continue
        gx = sum(p[0] for p in poly) / len(poly); gy = sum(p[1] for p in poly) / len(poly)
        soft = []
        for x, y in poly:                              # penumbra: polygon pushed 0.35 m outwards
            d = math.hypot(x - gx, y - gy) or 1.0
            soft.append((x + (x - gx) / d * 0.35, y + (y - gy) / d * 0.35))
        m.fan(soft, 0.026, 0.08)
        m.fan(poly, 0.030, 0.14)
    return m.node(parent)


def make_blob(parent):
    """Soft ellipse laid on the ground; caller sets pos/heading/scale each frame."""
    root = parent.attachNewNode("blob_shadow")
    cm = CardMaker("b"); cm.setFrame(-0.5, 0.5, -0.5, 0.5)
    c = root.attachNewNode(cm.generate())
    c.setP(-90); c.setZ(0.035); c.setTexture(T.blob())
    root.setTransparency(TransparencyAttrib.MAlpha); root.setLightOff(); root.setDepthWrite(False)
    root.setTwoSided(True); root.setBin("transparent", 6)
    return root
