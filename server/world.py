"""Urban arena: textured geometry, sky dome, collision and ray helpers."""
import itertools
import math
import random

from panda3d.core import (CardMaker, Geom, GeomNode, GeomTriangles, GeomVertexData,
                          GeomVertexFormat, GeomVertexWriter, LineSegs, NodePath, TextureStage,
                          TransparencyAttrib)

import config as C
import textures as T
from shadows import build_contact_shadows

HAZE = (0.72, 0.79, 0.86)
ZENITH = (0.22, 0.42, 0.76)
SUN_DIR = (0.45, -0.55, 0.70)          # direction *towards* the sun

# (cx, cy, half_x, half_y, half_z, kind)
OBSTACLES = [
    # buildings
    (-27, 24, 6, 5, 7, "building"), (25, 26, 7, 4, 5.5, "building"), (-30, -4, 4, 8, 6.5, "building"),
    (30, -2, 4, 7, 8, "building"), (2, 32, 9, 3, 6, "building"), (-24, -29, 6, 4, 5, "building"),
    (20, -31, 7, 4, 6, "building"),
    # shipping containers
    (-10, -12, 3, 1.2, 1.3, "container"), (9, -10, 1.2, 3, 1.3, "container"),
    (-8, 13, 3, 1.2, 1.3, "container"), (13, 12, 1.2, 3, 1.3, "container"),
    (0, -22, 3, 1.2, 1.3, "container"), (-19, 3, 1.2, 3, 1.3, "container"),
    (21, -17, 3, 1.2, 1.3, "container"), (-16, -22, 1.2, 3, 1.3, "container"),
    # jersey barriers (low: hitscan at head height passes over them)
    (-4, -6, 1.2, 0.3, 0.55, "barrier"), (5, 6, 0.3, 1.2, 0.55, "barrier"),
    (-3, 8, 1.2, 0.3, 0.55, "barrier"), (6, -3, 0.3, 1.2, 0.55, "barrier"),
    (14, 0, 1.2, 0.3, 0.55, "barrier"), (-13, 10, 0.3, 1.2, 0.55, "barrier"),
    (-22, 14, 1.2, 0.3, 0.55, "barrier"), (18, 18, 0.3, 1.2, 0.55, "barrier"),
    # crates
    (3, -6, 0.6, 0.6, 0.6, "crate"), (-6, 3, 0.6, 0.6, 0.6, "crate"), (11, 5, 0.6, 0.6, 0.6, "crate"),
    (-12, -1, 0.6, 0.6, 0.6, "crate"), (16, -6, 0.6, 0.6, 0.6, "crate"), (-2, 15, 0.6, 0.6, 0.6, "crate"),
    (7, -15, 0.6, 0.6, 0.6, "crate"), (-20, -12, 0.6, 0.6, 0.6, "crate"), (26, 12, 0.6, 0.6, 0.6, "crate"),
    # wrecked cars (length along the longer half-extent)
    (-14.5, -17, 2.2, 0.95, 0.7, "car"), (16, -12, 0.95, 2.2, 0.7, "car"),
    (-6, 24, 2.2, 0.95, 0.7, "car"), (20, -3, 0.95, 2.2, 0.7, "car"),
    # sandbag walls
    (-18, 16, 1.6, 0.4, 0.45, "sandbag"), (8, 22, 1.6, 0.4, 0.45, "sandbag"), (24, 8, 0.4, 1.6, 0.45, "sandbag"),
    # oil drums
    (-5.5, -9.5, 0.32, 0.32, 0.45, "drum"), (-4.8, -10.2, 0.32, 0.32, 0.45, "drum"),
    (-6.3, -10.3, 0.32, 0.32, 0.45, "drum"), (12, 18, 0.32, 0.32, 0.45, "drum"), (12.7, 18.5, 0.32, 0.32, 0.45, "drum"),
    # street lamps
    (-14, 5.8, 0.1, 0.1, 3.0, "pole"), (14, -5.8, 0.1, 0.1, 3.0, "pole"),
    (-24, 6, 0.1, 0.1, 3.0, "pole"), (24, -6, 0.1, 0.1, 3.0, "pole"), (-8, 5.8, 0.1, 0.1, 3.0, "pole"),
]
CAR_COLORS = [(0.28, 0.30, 0.33, 1), (0.28, 0.32, 0.22, 1), (0.12, 0.16, 0.26, 1), (0.55, 0.50, 0.40, 1)]
DRUM_COLORS = [(0.35, 0.50, 0.75, 1), (0.40, 0.55, 0.38, 1), (0.55, 0.55, 0.58, 1)]


def _box_faces(hx, hy, hz):
    return [
        ((1, 0, 0), [(hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz), (hx, -hy, hz)]),
        ((-1, 0, 0), [(-hx, hy, -hz), (-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz)]),
        ((0, 1, 0), [(hx, hy, -hz), (-hx, hy, -hz), (-hx, hy, hz), (hx, hy, hz)]),
        ((0, -1, 0), [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)]),
        ((0, 0, 1), [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]),
        ((0, 0, -1), [(hx, -hy, -hz), (-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz)]),
    ]


def _build_boxes(specs, tile, two_sided):
    """specs = [((px,py,pz), (hx,hy,hz)), ...] -> ONE geom containing all boxes."""
    vd = GeomVertexData("box", GeomVertexFormat.getV3n3t2(), Geom.UHStatic)
    vw, nw, tw = (GeomVertexWriter(vd, n) for n in ("vertex", "normal", "texcoord"))
    tris = GeomTriangles(Geom.UHStatic)
    for (px, py, pz), (hx, hy, hz) in specs:
        for n, verts in _box_faces(hx, hy, hz):
            base = vw.getWriteRow()
            for v in verts:
                vw.addData3(v[0] + px, v[1] + py, v[2] + pz)
                nw.addData3(*n)
                if n[0]:
                    u, w_ = v[1], v[2]
                elif n[1]:
                    u, w_ = v[0], v[2]
                else:
                    u, w_ = v[0], v[1]
                tw.addData2(u / tile[0], w_ / tile[1])
            tris.addVertices(base, base + 1, base + 2)
            tris.addVertices(base, base + 2, base + 3)
    geom = Geom(vd)
    geom.addPrimitive(tris)
    node = GeomNode("box")
    node.addGeom(geom)
    np_ = NodePath(node)
    if two_sided:
        np_.setTwoSided(True)
    return np_


def make_box(hx, hy, hz, tile=(1.0, 1.0)):
    """Box centred on the origin with world-scaled UVs (one texture tile = `tile` metres)."""
    return _build_boxes([((0, 0, 0), (hx, hy, hz))], tile, True)


def make_boxes(specs):
    """Many boxes merged into ONE single-sided mesh (used for the enemy outline hull, which needs
    back-face rendering; merging with flattenStrong() would break face culling)."""
    return _build_boxes(specs, (1.0, 1.0), False)


def outline(hx, hy, hz, color, thickness=2.0):
    """Wireframe edges for a box (debug helper)."""
    ls = LineSegs()
    ls.setThickness(thickness)
    ls.setColor(*color)
    corners = list(itertools.product((-1, 1), repeat=3))
    for i, a in enumerate(corners):
        for b in corners[i + 1:]:
            if sum(x != y for x, y in zip(a, b)) == 1:
                ls.moveTo(a[0] * hx, a[1] * hy, a[2] * hz)
                ls.drawTo(b[0] * hx, b[1] * hy, b[2] * hz)
    np_ = NodePath(ls.create())
    np_.setLightOff()
    return np_


def _flat_quad(parent, cx, cy, w, h, color, z=0.015):
    cm = CardMaker("q")
    cm.setFrame(-w / 2, w / 2, -h / 2, h / 2)
    q = parent.attachNewNode(cm.generate())
    q.setP(-90); q.setPos(cx, cy, z); q.setColor(*color, 1); q.setTwoSided(True)
    return q


def make_cylinder(r, h, seg=10, tile=(1.0, 1.0)):
    """Upright cylinder centred on the origin."""
    vd = GeomVertexData("cyl", GeomVertexFormat.getV3n3t2(), Geom.UHStatic)
    vw, nw, tw = (GeomVertexWriter(vd, n) for n in ("vertex", "normal", "texcoord"))
    tris = GeomTriangles(Geom.UHStatic)
    circ = 2 * math.pi * r
    for i in range(seg):
        a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
        base = vw.getWriteRow()
        for a, z, u in ((a0, -h / 2, i / seg), (a1, -h / 2, (i + 1) / seg), (a1, h / 2, (i + 1) / seg), (a0, h / 2, i / seg)):
            vw.addData3(r * math.cos(a), r * math.sin(a), z); nw.addData3(math.cos(a), math.sin(a), 0)
            tw.addData2(u * circ / tile[0], (z + h / 2) / tile[1])
        tris.addVertices(base, base + 1, base + 2); tris.addVertices(base, base + 2, base + 3)
    c = vw.getWriteRow()
    vw.addData3(0, 0, h / 2); nw.addData3(0, 0, 1); tw.addData2(0.5, 0.5)
    for i in range(seg):
        a = 2 * math.pi * i / seg
        vw.addData3(r * math.cos(a), r * math.sin(a), h / 2); nw.addData3(0, 0, 1)
        tw.addData2(0.5 + 0.5 * math.cos(a), 0.5 + 0.5 * math.sin(a))
    for i in range(seg):
        tris.addVertices(c, c + 1 + i, c + 1 + (i + 1) % seg)
    geom = Geom(vd); geom.addPrimitive(tris)
    node = GeomNode("cyl"); node.addGeom(geom)
    np_ = NodePath(node); np_.setTwoSided(True)
    return np_


def _car(parent, cx, cy, hx, hy, color):
    car = parent.attachNewNode("car")
    L, W = max(hx, hy), min(hx, hy)
    dark, glass = (0.05, 0.05, 0.05, 1), (0.06, 0.10, 0.14, 1)
    for pos, dims, col in (((0, 0, 0.62), (L, W, 0.38), color), ((-L * 0.08, 0, 1.10), (L * 0.48, W * 0.88, 0.30), color),
                           ((-L * 0.08, 0, 1.12), (L * 0.485, W * 0.895, 0.17), glass),
                           ((L, W * 0.6, 0.72), (0.02, 0.12, 0.06), (0.9, 0.88, 0.7, 1)),
                           ((L, -W * 0.6, 0.72), (0.02, 0.12, 0.06), (0.9, 0.88, 0.7, 1))):
        b = make_box(*dims); b.reparentTo(car); b.setPos(*pos); b.setColor(*col)
    for sx in (-1, 1):
        for sy in (-1, 1):
            w = make_cylinder(0.33, 0.24, 10); w.reparentTo(car)
            w.setPos(sx * L * 0.62, sy * (W - 0.12), 0.33); w.setP(90); w.setColor(*dark)
    car.setPos(cx, cy, 0)
    if hy > hx:
        car.setH(90)
    car.flattenStrong()


def _pole(parent, cx, cy, hz):
    p = parent.attachNewNode("pole")
    for pos, dims, col, lit in (((0, 0, hz), (0.07, 0.07, hz), (0.46, 0.48, 0.52, 1), False),
                                ((0, 0.45, 2 * hz - 0.05), (0.04, 0.5, 0.04), (0.46, 0.48, 0.52, 1), False),
                                ((0, 0.85, 2 * hz - 0.1), (0.12, 0.25, 0.04), (1.0, 0.96, 0.82, 1), True)):
        b = make_box(*dims); b.reparentTo(p); b.setPos(*pos); b.setColor(*col)
        if lit:
            b.setLightOff()
    p.setPos(cx, cy, 0)
    p.setH(0 if cy > 0 else 180)           # lamp arm always reaches towards the road
    p.flattenStrong()


def build_arena(render):
    """Asphalt + grime, road markings, walls, buildings, containers, barriers, crates, cars,
    sandbags, drums, lamps, a hazy city skyline, and baked fake shadows."""
    root = render.attachNewNode("arena")
    H = C.ARENA_HALF
    size = 2 * H + 8

    cm = CardMaker("ground")
    cm.setFrame(-size / 2, size / 2, -size / 2, size / 2)
    ground = root.attachNewNode(cm.generate())
    ground.setP(-90); ground.setTwoSided(True)
    ground.setTexture(T.asphalt()); ground.setTexScale(TextureStage.getDefault(), size / 3.0, size / 3.0)
    dirt = root.attachNewNode(cm.generate())
    dirt.setP(-90); dirt.setTwoSided(True); dirt.setZ(0.006)
    dirt.setTexture(T.grime()); dirt.setTexScale(TextureStage.getDefault(), size / 18.0, size / 18.0)
    dirt.setTransparency(TransparencyAttrib.MAlpha); dirt.setDepthWrite(False); dirt.setLightOff()

    for x in range(-int(H) + 3, int(H), 6):
        _flat_quad(root, x, 0, 3.0, 0.18, (0.85, 0.70, 0.12))
    for y in (-4.6, 4.6):
        _flat_quad(root, 0, y, 2 * H, 0.14, (0.80, 0.80, 0.78))

    conc = T.concrete()
    wall_h = 6.0
    for cx, cy, hx, hy in ((0, H + 0.5, H + 1, 0.5), (0, -H - 0.5, H + 1, 0.5),
                           (H + 0.5, 0, 0.5, H + 1), (-H - 0.5, 0, 0.5, H + 1)):
        b = make_box(hx, hy, wall_h / 2, (5, 5))
        b.reparentTo(root); b.setPos(cx, cy, wall_h / 2); b.setTexture(conc)

    ci = ki = di = 0
    for cx, cy, hx, hy, hz, kind in OBSTACLES:
        if kind == "car":
            _car(root, cx, cy, hx, hy, CAR_COLORS[ki % len(CAR_COLORS)]); ki += 1
            continue
        if kind == "pole":
            _pole(root, cx, cy, hz)
            continue
        if kind == "drum":
            b = make_cylinder(0.32, 0.9, 10, (1.0, 0.9)); b.setTexture(T.drum()); b.setColor(*DRUM_COLORS[di % 3]); di += 1
            b.reparentTo(root); b.setPos(cx, cy, 0.45)
            continue
        if kind == "building":
            b = make_box(hx, hy, hz, (8, 6)); b.setTexture(T.facade())
            roof = make_box(hx + 0.2, hy + 0.2, 0.15, (3, 3)); roof.setTexture(conc)
            roof.reparentTo(root); roof.setPos(cx, cy, 2 * hz + 0.15)
        elif kind == "container":
            b = make_box(hx, hy, hz, (6, 2.6)); b.setTexture(T.container(ci)); ci += 1
        elif kind == "crate":
            b = make_box(hx, hy, hz, (1.2, 1.2)); b.setTexture(T.crate())
        elif kind == "sandbag":
            b = make_box(hx, hy, hz, (1.3, 0.9)); b.setTexture(T.sandbag())
        else:  # barrier
            b = make_box(hx, hy, hz, (3, 3)); b.setTexture(conc)
        b.reparentTo(root); b.setPos(cx, cy, hz)

    rng = random.Random(4)                              # distant city for depth
    sky_line = root.attachNewNode("skyline")
    for i in range(40):
        ang = 2 * math.pi * i / 40 + rng.uniform(-0.05, 0.05)
        r = rng.uniform(85, 130)
        w, d, h = rng.uniform(14, 26), rng.uniform(12, 22), rng.uniform(22, 70)
        b = make_box(w / 2, d / 2, h / 2, (16, 12)); b.setTexture(T.facade()); b.setColor(0.85, 0.9, 1.0, 1)
        b.reparentTo(sky_line); b.setPos(r * math.cos(ang), r * math.sin(ang), h / 2); b.setH(math.degrees(ang))
    sky_line.flattenStrong()

    build_contact_shadows(root, OBSTACLES, SUN_DIR, projected=C.FAKE_SHADOWS)
    return root


def build_sky(render, seg=48, rings=20, radius=250.0):
    """Textured sky dome (gradient, sun, clouds baked into one texture); follows the camera."""
    vd = GeomVertexData("sky", GeomVertexFormat.getV3t2(), Geom.UHStatic)
    vw, tw = GeomVertexWriter(vd, "vertex"), GeomVertexWriter(vd, "texcoord")
    for i in range(rings + 1):
        el = math.radians(-12 + i * (102.0 / rings))
        for j in range(seg + 1):
            az = 2 * math.pi * j / seg
            vw.addData3(radius * math.cos(el) * math.cos(az), radius * math.cos(el) * math.sin(az), radius * math.sin(el))
            tw.addData2(j / seg, i / rings)
    tris = GeomTriangles(Geom.UHStatic)
    for i in range(rings):
        for j in range(seg):
            a = i * (seg + 1) + j
            b, c, d = a + 1, a + seg + 1, a + seg + 2
            tris.addVertices(a, b, d); tris.addVertices(a, d, c)
    geom = Geom(vd); geom.addPrimitive(tris)
    node = GeomNode("sky"); node.addGeom(geom)
    sky = render.attachNewNode(node)
    sky.setTexture(T.sky(HAZE, ZENITH, SUN_DIR))
    sky.setTwoSided(True); sky.setLightOff(); sky.setFogOff(); sky.setShaderOff(1)
    sky.setBin("background", 0); sky.setDepthWrite(False); sky.setDepthTest(False)
    return sky


# --- collision -------------------------------------------------------------
def push_out(x, y, r):
    """Clamp a circle to the arena and push it out of every obstacle."""
    lim = C.ARENA_HALF - r
    x = max(-lim, min(lim, x))
    y = max(-lim, min(lim, y))
    for cx, cy, hx, hy, _hz, _kind in OBSTACLES:
        nx = max(cx - hx, min(x, cx + hx))
        ny = max(cy - hy, min(y, cy + hy))
        dx, dy = x - nx, y - ny
        d2 = dx * dx + dy * dy
        if d2 < r * r:
            if d2 > 1e-9:
                d = math.sqrt(d2)
                x, y = nx + dx / d * r, ny + dy / d * r
            else:
                ox = hx + r - abs(x - cx)
                oy = hy + r - abs(y - cy)
                if ox < oy:
                    x = cx + math.copysign(hx + r, x - cx)
                else:
                    y = cy + math.copysign(hy + r, y - cy)
    return x, y


def ray_sphere(o, d, c, r):
    oc = o - c
    b = oc.dot(d)
    disc = b * b - (oc.dot(oc) - r * r)
    if disc < 0:
        return None
    t = -b - math.sqrt(disc)
    return t if t > 0 else None


def ray_aabb(o, d, mn, mx):
    tmin, tmax = 0.0, 1e9
    for i in range(3):
        if abs(d[i]) < 1e-9:
            if o[i] < mn[i] or o[i] > mx[i]:
                return None
        else:
            t1, t2 = (mn[i] - o[i]) / d[i], (mx[i] - o[i]) / d[i]
            if t1 > t2:
                t1, t2 = t2, t1
            tmin, tmax = max(tmin, t1), min(tmax, t2)
            if tmin > tmax:
                return None
    return tmin


def ray_world(o, d):
    """Distance to the first obstacle/floor along a ray (or 80 m)."""
    best = 80.0
    for cx, cy, hx, hy, hz, _ in OBSTACLES:
        t = ray_aabb(o, d, (cx - hx, cy - hy, 0), (cx + hx, cy + hy, 2 * hz))
        if t is not None and t < best:
            best = t
    if d[2] < -1e-6:
        best = min(best, -o[2] / d[2])
    return best
