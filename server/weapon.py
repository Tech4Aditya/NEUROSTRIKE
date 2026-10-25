"""First-person carbine with gloved hands.
Drawn in its own display region with its own depth buffer, so it never clips into walls
and has its own field of view. Animations: idle sway, look-lag, sprint carry, recoil,
bolt cycling, ejected brass, and a full two-handed magazine change."""
import math
import random

from panda3d.core import (AmbientLight, Camera, CardMaker, ColorBlendAttrib, DirectionalLight, NodePath,
                          PerspectiveLens, Point3, TransparencyAttrib, Vec3, Vec4)

import textures as T
from world import make_box

METAL, POLY, TAN = (0.19, 0.19, 0.21, 1), (0.27, 0.27, 0.29, 1), (0.58, 0.49, 0.34, 1)
GLOVE, SLEEVE, GLASS, BRASS = (0.20, 0.21, 0.19, 1), (0.34, 0.40, 0.26, 1), (0.10, 0.22, 0.32, 1), (0.82, 0.62, 0.20, 1)

# (pos, half-dims, colour) in gun space: x right, y forward (muzzle +y), z up
GUN = [
    ((0, 0.02, 0.015), (0.028, 0.17, 0.032), METAL),          # upper receiver
    ((0, -0.03, -0.03), (0.027, 0.13, 0.028), METAL),         # lower receiver
    ((0, 0.015, -0.062), (0.020, 0.034, 0.030), METAL),       # magwell
    ((0, 0.30, 0.003), (0.032, 0.14, 0.034), TAN),            # handguard
    ((0, 0.20, 0.043), (0.011, 0.33, 0.006), METAL),          # top rail
    ((0, 0.54, 0.006), (0.008, 0.15, 0.008), METAL),          # barrel
    ((0, 0.43, 0.020), (0.012, 0.020, 0.020), METAL),         # gas block
    ((0, 0.435, 0.047), (0.008, 0.008, 0.012), METAL),        # front sight base
    ((0, 0.435, 0.066), (0.002, 0.002, 0.014), METAL),        # front sight post
    ((0, 0.705, 0.006), (0.013, 0.035, 0.013), METAL),        # flash hider
    ((0, 0.07, 0.064), (0.022, 0.055, 0.028), METAL),         # optic housing
    ((0, 0.127, 0.066), (0.016, 0.002, 0.018), GLASS),        # optic front lens
    ((0, 0.013, 0.066), (0.016, 0.002, 0.018), GLASS),        # optic rear lens
    ((0, 0.07, 0.046), (0.014, 0.035, 0.010), METAL),         # optic mount
    ((0, -0.060, -0.066), (0.003, 0.038, 0.003), METAL),      # trigger guard (bottom)
    ((0, -0.025, -0.055), (0.003, 0.003, 0.012), METAL),      # trigger guard (front)
    ((0, -0.062, -0.052), (0.003, 0.004, 0.013), METAL),      # trigger
    ((0, -0.215, 0.016), (0.012, 0.09, 0.012), METAL),        # buffer tube
    ((0, -0.33, 0.002), (0.021, 0.075, 0.042), POLY),         # stock
    ((0, -0.405, 0.002), (0.022, 0.006, 0.044), METAL),       # butt pad
    ((0.0285, 0.025, 0.015), (0.002, 0.035, 0.014), (0, 0, 0, 1)),   # ejection port
]
MAG0 = (0, 0.015, -0.105)
HAND_HG = (0.0, 0.30, -0.032)           # left hand resting under the handguard


def sstep(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp3(a, b, t):
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t))


class Weapon:
    def __init__(self, game):
        self.g = game
        self.scene = NodePath("viewmodel_scene")
        lens = PerspectiveLens()
        lens.setAspectRatio(game.getAspectRatio()); lens.setFov(68); lens.setNearFar(0.02, 5.0)
        self.lens = lens
        cam = Camera("vmcam"); cam.setLens(lens)
        self.camNP = self.scene.attachNewNode(cam)
        dr = game.win.makeDisplayRegion()
        dr.setSort(5); dr.setClearDepthActive(True); dr.setCamera(self.camNP)
        amb = AmbientLight("a"); amb.setColor(Vec4(0.62, 0.64, 0.70, 1))
        sun = DirectionalLight("d"); sun.setColor(Vec4(1.0, 0.95, 0.85, 1))
        sun_np = self.scene.attachNewNode(sun); sun_np.setHpr(25, -50, 0)
        self.scene.setLight(self.scene.attachNewNode(amb)); self.scene.setLight(sun_np)
        self.rig = self.scene.attachNewNode("rig")
        self.rig.setScale(0.82)
        self.t, self.bolt_off, self.flash_t = 0.0, 0.0, 0.0
        self.lag = [0.0, 0.0]
        self.shells = []
        self._build()

    # ------------------------------------------------------------------ model
    @staticmethod
    def _part(parent, pos, dims, col, hpr=None):
        b = make_box(*dims); b.reparentTo(parent); b.setPos(*pos); b.setColor(*col)
        if hpr:
            b.setHpr(*hpr)
        return b

    def _build(self):
        P = self._part
        gun = self.rig.attachNewNode("gun")
        for pos, dims, col in GUN:
            P(gun, pos, dims, col)
        P(gun, (0, -0.112, -0.085), (0.018, 0.030, 0.055), POLY, (0, -18, 0))     # pistol grip
        for i in range(10):                                                         # rail notches
            P(gun, (0, 0.06 + 0.06 * i, 0.050), (0.012, 0.012, 0.004), METAL)
        gun.flattenStrong()

        self.mag = self.rig.attachNewNode("mag")
        P(self.mag, (0, 0, 0), (0.016, 0.030, 0.050), POLY)
        P(self.mag, (0, -0.012, -0.085), (0.016, 0.030, 0.045), POLY, (0, -9, 0))
        P(self.mag, (0, -0.02, -0.135), (0.017, 0.032, 0.006), TAN)
        self.mag.flattenStrong(); self.mag.setPos(*MAG0)

        self.bolt = self.rig.attachNewNode("bolt")
        P(self.bolt, (0, 0, 0), (0.0015, 0.020, 0.010), (0.55, 0.50, 0.40, 1))
        self.bolt.setPos(0.0295, 0.03, 0.015)
        self.charge = self.rig.attachNewNode("charge")
        P(self.charge, (0, 0, 0), (0.011, 0.018, 0.007), METAL)
        self.charge.setPos(0, -0.11, 0.052)

        rh = self.rig.attachNewNode("rhand")                                       # right hand on the grip
        for pos, dims in (((0.030, -0.112, -0.075), (0.012, 0.034, 0.050)), ((0.0, -0.082, -0.055), (0.022, 0.007, 0.009)),
                          ((0.0, -0.082, -0.075), (0.022, 0.007, 0.009)), ((0.0, -0.082, -0.095), (0.022, 0.007, 0.009)),
                          ((0.012, -0.060, -0.050), (0.006, 0.025, 0.007)), ((-0.026, -0.120, -0.045), (0.007, 0.022, 0.009)),
                          ((0.035, -0.115, -0.045), (0.008, 0.036, 0.030))):
            P(rh, pos, dims, GLOVE)
        fore = rh.attachNewNode("rfore"); fore.setPos(0.03, -0.14, -0.09); fore.lookAt(Point3(0.17, -0.58, -0.40))
        P(fore, (0, 0.22, 0), (0.032, 0.22, 0.032), SLEEVE); P(fore, (0, 0.015, 0), (0.036, 0.02, 0.036), GLOVE)
        rh.flattenStrong()

        self.lhand = self.rig.attachNewNode("lhand")                               # left hand (animated)
        for pos, dims in (((0, 0, 0), (0.028, 0.040, 0.012)), ((-0.034, 0, 0.012), (0.006, 0.040, 0.020)),
                          ((0.034, 0, 0.012), (0.006, 0.040, 0.020)), ((-0.030, -0.012, 0.034), (0.006, 0.025, 0.008))):
            P(self.lhand, pos, dims, GLOVE)
        self.lhand.flattenStrong()
        self.lfore = self.rig.attachNewNode("lfore")
        P(self.lfore, (0, 0.25, 0), (0.034, 0.25, 0.034), SLEEVE); P(self.lfore, (0, 0.02, 0), (0.038, 0.02, 0.038), GLOVE)
        self.lfore.flattenStrong()

        self.flash = self.rig.attachNewNode("flash"); self.flash.setPos(0, 0.76, 0.006)
        for roll in (0, 45):
            cm = CardMaker("f"); cm.setFrame(-0.10, 0.10, -0.10, 0.10)
            c = self.flash.attachNewNode(cm.generate()); c.setR(roll)
        self.flash.setTexture(T.muzzle()); self.flash.setLightOff(); self.flash.setTwoSided(True)
        self.flash.setTransparency(TransparencyAttrib.MAlpha); self.flash.setDepthWrite(False)
        self.flash.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha,
                                                   ColorBlendAttrib.OOne))
        self.flash.hide()

        # armor-plate animation: both gloved hands carry a plate up, hold it, then push it down into the vest
        STEEL = (0.30, 0.33, 0.37, 1)
        self.pnode = self.scene.attachNewNode("plate_anim")
        P(self.pnode, (0, 0, 0), (0.12, 0.012, 0.15), STEEL)
        P(self.pnode, (0, -0.012, 0), (0.09, 0.006, 0.12), (0.47, 0.51, 0.56, 1))
        P(self.pnode, (0, -0.016, 0.0), (0.02, 0.003, 0.12), (0.30, 0.34, 0.38, 1))
        for s_ in (-1, 1):
            P(self.pnode, (s_ * 0.135, 0, 0), (0.032, 0.022, 0.055), GLOVE)
            for k in (-0.03, 0.0, 0.03):
                P(self.pnode, (s_ * 0.10, -0.016, k), (0.03, 0.007, 0.009), GLOVE)
            fa = self.pnode.attachNewNode("fa"); fa.setPos(s_ * 0.14, 0, -0.04)
            fa.lookAt(Point3(s_ * 0.34, -0.55, -0.45))
            P(fa, (0, 0.25, 0), (0.034, 0.25, 0.034), SLEEVE)
        self.pnode.flattenStrong(); self.pnode.hide()
        self.pflash = self.scene.attachNewNode("plate_flash")
        cm = CardMaker("pf"); cm.setFrame(-0.30, 0.30, -0.30, 0.30)
        self.pflash.attachNewNode(cm.generate())
        self.pflash.setTexture(T.blob()); self.pflash.setLightOff(); self.pflash.setTwoSided(True)
        self.pflash.setTransparency(TransparencyAttrib.MAlpha); self.pflash.setDepthWrite(False)
        self.pflash.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha, ColorBlendAttrib.OOne))
        self.pflash.hide()

    # -------------------------------------------------------------- animation
    @staticmethod
    def _keys(empty):
        H1, LOW, H2 = (0, 0.01, -0.10), (0, 0.01, -0.32), (-0.15, 0.06, -0.36)
        k = [(0.00, HAND_HG, 0.0), (0.18, H1, 0.0), (0.34, LOW, -0.22), (0.46, H2, -0.22),
             (0.54, H2, -0.22), (0.66, LOW, -0.22), (0.76, H1, 0.0), (0.82, H1, 0.0)]
        if empty:
            k = [(t * 0.85, h, m) for t, h, m in k] + [(0.86, (0, -0.10, 0.045), 0.0), (0.94, (0, -0.10, 0.045), 0.0)]
        return k + [(1.00, HAND_HG, 0.0)]

    MODES = "gghxhggg"      # per key-segment: g = mag in gun, h = mag in hand, x = mag hidden (in the pouch)

    def _plate(self, p):
        if p < 0.30:                                       # hands bring the plate up
            u = sstep(p / 0.30); x, y, z, s = 0.0, 0.48, lerp(-0.45, -0.13, u), 0.72
        elif p < 0.62:                                     # inspect / seat it, slight rattle
            x, y, z, s = 0.004 * math.sin(p * 90), 0.48, -0.13 + 0.004 * math.sin(p * 70), 0.72
        elif p < 0.82:                                     # push it down into the vest
            u = sstep((p - 0.62) / 0.20); x, y, z, s = 0.0, lerp(0.48, 0.40, u), lerp(-0.13, -0.33, u), 0.72 - 0.16 * u
        else:
            self.pnode.hide()
            x = None
        if x is not None:
            self.pnode.show(); self.pnode.setPos(x, y, z); self.pnode.setScale(s)
            self.pnode.setHpr(0, -12 * sstep((p - 0.62) / 0.20) if p > 0.62 else 0, 0)
        if p > 0.78:                                       # cyan lock-in flash
            u = (p - 0.78) / 0.22
            self.pflash.show(); self.pflash.setPos(0, 0.34, -0.30); self.pflash.setScale(0.6 + 1.2 * u)
            self.pflash.setColorScale(0.3, 0.9, 1.0, max(0.0, 1 - u) * 1.4)
        else:
            self.pflash.hide()

    def fire(self):
        self.bolt_off = 1.0
        self.flash_t = 0.045
        self.flash.setScale(random.uniform(0.7, 1.3)); self.flash.setR(random.uniform(0, 360)); self.flash.show()
        sh = make_box(0.004, 0.012, 0.004); sh.reparentTo(self.scene); sh.setColor(*BRASS)
        sh.setPos(self.scene.getRelativePoint(self.rig, Point3(0.03, 0.03, 0.02)))
        vel = Vec3(random.uniform(1.0, 1.7), random.uniform(-0.6, 0.1), random.uniform(0.9, 1.5))
        self.shells.append([sh, vel, 0.7])

    def update(self, dt, c):
        self.t += dt
        k = math.exp(-dt * 8.0)
        self.lag[0] = max(-0.06, min(0.06, self.lag[0] * k - c["dyaw"] * 0.0016))
        self.lag[1] = max(-0.05, min(0.05, self.lag[1] * k - c["dpitch"] * 0.0016))
        sb = c["sprint"]
        p = c["rp"] if c["reloading"] else 0.0
        dip = math.sin(math.pi * min(1.0, p)) ** 0.7 if c["reloading"] else 0.0
        bx = 0.15 + self.lag[0] + 0.0012 * math.sin(self.t * 1.1)
        by = 0.55 - c["kick"] * 0.045
        bz = -0.155 + self.lag[1] + 0.0016 * math.sin(self.t * 1.7) + 0.4 * c["bob"] + c["kick"] * 0.008
        shake = 2.5 * math.sin(p * 90) * dip if c["reloading"] else 0.0
        pos = [lerp(bx, 0.04, sb) - 0.02 * dip, lerp(by, 0.50, sb) - 0.02 * dip, lerp(bz, -0.22, sb) - 0.03 * dip]
        hpr = [32.0 * sb, c["kick"] * 3.0 - 12.0 * sb - 6.0 * dip, -24.0 * sb + 14.0 * dip + shake]
        pp = c.get("plate", -1.0)
        if pp >= 0:                                         # plating: rifle drops away while both hands work
            pb = sstep(pp / 0.14) * (1 - sstep((pp - 0.88) / 0.12))
            pos = [lerp(pos[0], 0.16, pb), lerp(pos[1], 0.46, pb), lerp(pos[2], -0.38, pb)]
            hpr = [lerp(hpr[0], 18.0, pb), lerp(hpr[1], -24.0, pb), lerp(hpr[2], -36.0, pb)]
            self.lhand.hide(); self.lfore.hide()
            self._plate(pp)
        else:
            self.lhand.show(); self.lfore.show(); self.pnode.hide(); self.pflash.hide()
        self.rig.setPosHpr(*pos, *hpr)

        # left hand + magazine
        hand, moff, mode = HAND_HG, 0.0, "g"
        rack = 0.0
        if c["reloading"]:
            ks = self._keys(c["empty"])
            i = max(j for j, key in enumerate(ks[:-1]) if key[0] <= p)
            a, b = ks[i], ks[i + 1]
            u = sstep((p - a[0]) / max(1e-6, b[0] - a[0]))
            hand, moff = lerp3(a[1], b[1], u), lerp(a[2], b[2], u)
            mode = self.MODES[i] if i < len(self.MODES) else "g"
            if c["empty"] and 0.86 < p < 0.97:
                rack = sstep((p - 0.86) / 0.05) if p < 0.91 else 1 - sstep((p - 0.91) / 0.06)
        self.lhand.setPos(*hand)
        self.lfore.setPos(*hand); self.lfore.lookAt(Point3(-0.24, -0.42, -0.42))
        if mode == "x":
            self.mag.hide()
        else:
            self.mag.show()
            if mode == "h":
                self.mag.setPos(hand[0], hand[1] + 0.005, hand[2])
            else:
                self.mag.setPos(MAG0[0], MAG0[1], MAG0[2] + moff)

        self.bolt_off = max(0.0, self.bolt_off - dt * 35.0)
        self.bolt.setY(0.03 - 0.035 * max(self.bolt_off, rack))
        self.charge.setY(-0.11 - 0.035 * rack)

        if self.flash_t > 0:
            self.flash_t -= dt
            if self.flash_t <= 0:
                self.flash.hide()
        for sh in self.shells[:]:
            sh[1].z -= 9.8 * dt
            sh[0].setPos(sh[0].getPos() + sh[1] * dt); sh[0].setHpr(sh[0].getH() + 600 * dt, sh[0].getP() + 900 * dt, 0)
            sh[2] -= dt
            if sh[2] <= 0:
                sh[0].removeNode(); self.shells.remove(sh)
