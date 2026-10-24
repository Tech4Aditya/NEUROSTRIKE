"""NeuroStrike — Panda3D game: first-person camera, auto-movement, enemies, hitscan
shooting, offscreen frame capture for YOLO, and the phone link."""
import math
import random
import sys
import time

import cv2
import numpy as np
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (AmbientLight, AntialiasAttrib, BitMask32, CardMaker, ClockObject,
                          CullFaceAttrib, DirectionalLight, Fog, LineSegs, PerspectiveLens, Point2,
                          Point3, TextNode, TransparencyAttrib, Vec3, Vec4, WindowProperties,
                          loadPrcFileData)

import config as C
from audio import Sfx
from shadows import make_blob
from show import Show
from weapon import Weapon
from net import PhoneLink, lan_ip
from vision import VisionWorker, build_detector
from world import (HAZE, SUN_DIR, build_arena, build_sky, make_box, push_out, ray_sphere, ray_world)

loadPrcFileData("", f"window-title NeuroStrike\nwin-size {C.WIN_W} {C.WIN_H}\nsync-video {1 if C.VSYNC else 0}\nfullscreen {1 if C.FULLSCREEN else 0}\nframebuffer-multisample {1 if C.MSAA else 0}\nmultisamples {C.MSAA}\n")

HUD = (0.93, 0.95, 0.97, 1.0)
SOFT = (0.72, 0.78, 0.84, 1.0)
ACCENT = (1.0, 0.62, 0.16, 1.0)
GREEN = (0.2, 1.0, 0.5, 1.0)
HOSTILE = (1.0, 0.08, 0.12, 1.0)      # enemy outline: pure red, ignores fog
CAP_MASK = BitMask32.bit(2)           # offscreen capture camera (never sees weapon / flash)
MAIN_MASK = BitMask32.bit(1)


class Enemy:
    """Soldier built from boxes, merged into a handful of draw calls (important on integrated GPUs):
    one body mesh, two swinging legs, three red outline hulls, one blob shadow."""

    UPPER = [((0, 0, 1.18), (0.27, 0.16, 0.30), (0.22, 0.26, 0.17, 1)),          # torso
             ((0, 0.10, 1.22), (0.22, 0.05, 0.22), (0.13, 0.14, 0.12, 1)),       # plate carrier
             ((-0.37, 0.04, 1.20), (0.07, 0.07, 0.26), (0.22, 0.26, 0.17, 1)),   # arms
             ((0.37, 0.04, 1.20), (0.07, 0.07, 0.26), (0.22, 0.26, 0.17, 1)),
             ((0, 0, 1.62), (0.10, 0.11, 0.12), (0.55, 0.40, 0.32, 1)),          # head
             ((0, 0, 1.73), (0.13, 0.14, 0.07), (0.20, 0.23, 0.16, 1)),          # helmet
             ((0, 0.11, 1.64), (0.10, 0.02, 0.035), (0.07, 0.07, 0.07, 1)),      # goggles
             ((0.18, 0.30, 1.20), (0.03, 0.36, 0.045), (0.07, 0.07, 0.07, 1))]   # rifle
    LEG = [((0, 0, -0.37), (0.10, 0.11, 0.34), (0.22, 0.26, 0.17, 1)),
           ((0, 0.05, -0.80), (0.09, 0.15, 0.08), (0.07, 0.07, 0.07, 1))]

    def __init__(self, game, x, y):
        self.x, self.y = x, y
        self.hp = C.ENEMY_HP
        self.flash = 0.0
        self.game, self.snd = game, None
        self.phase = random.random() * 6.28
        self.root = game.render.attachNewNode("enemy")
        self.hulls = []

        def build(parent, parts, origin=(0, 0, 0), color=None):
            for pos, dims, col in parts:
                b = make_box(*dims); b.reparentTo(parent)
                b.setPos(pos[0] - origin[0], pos[1] - origin[1], pos[2] - origin[2])
                if color is None:
                    b.setColor(*col)
            parent.flattenStrong()
            if color is not None:
                parent.setColor(*color)

        def hull(parent, center, half, parts):
            h = parent.attachNewNode("hull"); h.setPos(*center)
            build(h, parts, center, HOSTILE)
            # priority 1 beats the per-box two-sided state, so only the BACK faces draw -> outline ring
            h.setAttrib(CullFaceAttrib.make(CullFaceAttrib.MCullCounterClockwise), 1)
            h.setLightOff(); h.setFogOff()
            self.hulls.append((h, half))

        self.upper = self.root.attachNewNode("upper")
        build(self.upper, self.UPPER)
        self.legs = []
        for s_ in (-1, 1):
            piv = self.root.attachNewNode("hip"); piv.setPos(s_ * 0.14, 0, 0.88)
            build(piv, self.LEG)
            self.legs.append((piv, s_))
        if C.ENEMY_HIGHLIGHT:
            hull(self.root, (0, 0.05, 1.34), (0.45, 0.20, 0.47), self.UPPER)
            for piv, _ in self.legs:
                hull(piv, (0, 0.02, -0.45), (0.10, 0.12, 0.43), self.LEG)
        self.shadow = make_blob(game.render) if C.FAKE_SHADOWS else None
        sx, sy = -SUN_DIR[0], -SUN_DIR[1]
        n = math.hypot(sx, sy)
        self.sdir = (sx / n, sy / n)

    def update(self, dt, px, py, t):
        dx, dy = px - self.x, py - self.y
        d = math.hypot(dx, dy)
        moving = d > 1.2
        if moving:
            self.x += dx / d * C.ENEMY_SPEED * dt
            self.y += dy / d * C.ENEMY_SPEED * dt
            self.x, self.y = push_out(self.x, self.y, 0.5)
        self.root.setPos(self.x, self.y, 0)
        self.root.setH(math.degrees(math.atan2(-dx, dy)))
        swing = 28 * math.sin(t * 7 + self.phase) if moving else 0.0
        for piv, s_ in self.legs:
            piv.setP(swing * s_)
        pad = 0.045 + 0.010 * d            # outline grows with distance so it stays visible
        for h, half in self.hulls:
            h.setScale(1 + pad / half[0], 1 + pad / half[1], 1 + pad / half[2])
        if self.shadow is not None:
            self.shadow.setPos(self.x + self.sdir[0] * 0.9, self.y + self.sdir[1] * 0.9, 0)
            self.shadow.setH(math.degrees(math.atan2(-self.sdir[0], self.sdir[1])))
            self.shadow.setScale(0.9, 2.0, 1)
        if self.flash > 0:
            self.flash -= dt
            k = 2.8 if self.flash > 0 else 1.0
            self.upper.setColorScale(k, k, k, 1)
            for piv, _ in self.legs:
                piv.setColorScale(k, k, k, 1)
        return d

    def destroy(self):
        if self.snd is not None:
            self.game.sfx.release_steps(self.snd); self.snd = None
        if self.shadow is not None:
            self.shadow.removeNode()
        self.root.removeNode()


class NeuroStrike(ShowBase):
    def __init__(self, detector_mode="auto"):
        super().__init__()
        self.disableMouse()
        self.fullscreen = C.FULLSCREEN
        self.accept("aspectRatioChanged", self.on_aspect)
        self.setBackgroundColor(HAZE[0], HAZE[1], HAZE[2], 1)
        self.camLens.setFov(C.HFOV)
        self.camLens.setNearFar(0.1, 300)
        self.clock = ClockObject.getGlobalClock()

        self.px = self.py = 0.0
        self.h = self.p = 0.0
        self.hp, self.score, self.hurt_count = 100.0, 0, 0
        self.alive, self.dead_t = True, 0.0
        self.move_ang, self.auto_move = 0.0, C.AUTO_MOVE
        self.enemies, self.fx, self.contacts = [], [], {}
        self.spawn_t, self.fire_cd, self.hurt_cd, self.dmg_flash = 1.0, 0.0, 0.0, 0.0
        self.keys = {k: False for k in "wasd"}
        self.mouse_fire = self.mouse_look = False
        self.show_boxes, self.recording = True, False
        self.rec_t = self.vis_t = self.pub_t = 0.0
        self.last_seq, self.box_root, self.n_targets, self.rec_count = -1, None, 0, 0
        self.walk_t, self.moving = 0.0, False
        self.mag, self.reloading, self.reload_t, self.reload_len, self.reload_empty = C.MAG_SIZE, False, 0.0, 1.0, False
        self.sprint, self.sprint_blend, self.tac_t, self.tac_cd = 0, 0.0, 0.0, 0.0
        self.sprint_key, self.last_shift, self.kb_reload, self.kb_tac, self.step_t = False, -9.0, False, False, 0.0
        self.cap_pending, self.cap_meta, self.q_stage, self.q_t, self.hud_acc = False, None, 0, 0.0, 1.0
        self.godmode, self.spawn_enabled = False, True
        self.since_shot, self.recoil_acc, self.kick = 9.0, 0.0, 0.0

        self.setup_scene()
        self.setup_capture()
        self.setup_hud()
        self.setup_input()
        self.sfx = Sfx(self.loader, C.ROOT / "sounds")
        self.sfx.loop("ambience", 0.35)

        self.link = PhoneLink(C.WS_HOST, C.WS_PORT, C.STATE_HZ)
        self.link.start()
        self.vision = VisionWorker(build_detector(detector_mode))
        self.vision.start()
        self.ip = lan_ip()
        self.show = Show(self)
        print("\n  ⚡ NEUROSTRIKE online")
        print(f"  Phone → enter  {self.ip}   (ws://{self.ip}:{C.WS_PORT})\n")
        self.taskMgr.add(self.update, "update")

    # ------------------------------------------------------------------ setup
    def setup_scene(self):
        build_arena(self.render).flattenStrong()    # merge ~60 static nodes into a few draw calls
        self.sky = build_sky(self.render)
        amb = AmbientLight("amb"); amb.setColor(Vec4(0.40, 0.45, 0.55, 1))     # sky fill light
        sun = DirectionalLight("sun"); sun.setColor(Vec4(1.0, 0.92, 0.78, 1))   # warm sun
        self.sun = sun
        if C.SHADERS:
            sun.setShadowCaster(True, C.SHADOW_SIZE, C.SHADOW_SIZE)
            span = 2 * C.ARENA_HALF + 40
            sun.getLens().setFilmSize(span, span)
            sun.getLens().setNearFar(10, 260)
        sun_np = self.render.attachNewNode(sun)
        k = 110.0 / math.sqrt(sum(c * c for c in SUN_DIR))
        sun_np.setPos(SUN_DIR[0] * k, SUN_DIR[1] * k, SUN_DIR[2] * k)
        sun_np.lookAt(0, 0, 0)
        self.render.setLight(self.render.attachNewNode(amb))
        self.render.setLight(sun_np)
        fog = Fog("haze"); fog.setColor(*HAZE); fog.setExpDensity(0.009)
        self.render.setFog(fog)
        self.render.setAntialias(AntialiasAttrib.MAuto)
        if C.SHADERS:
            self.render.setShaderAuto()
        self.filters = None
        if C.SHADERS and C.BLOOM:
            try:
                from direct.filter.CommonFilters import CommonFilters
                self.filters = CommonFilters(self.win, self.cam)
                self.filters.setBloom(blend=(0.3, 0.4, 0.3, 0.0), mintrigger=0.82, maxtrigger=1.0,
                                      desat=0.6, intensity=0.9, size="medium")
            except Exception as e:
                print(f"[gfx] bloom unavailable ({e}); set BLOOM = False in config.py to silence")

    def setup_capture(self):
        """Offscreen second camera -> RAM texture. Contains the 3D scene only (no HUD),
        so the detector never sees our own overlay boxes."""
        self.cap_buf = self.win.makeTextureBuffer("capture", C.CAP_W, C.CAP_H, None, True)
        self.cap_tex = self.cap_buf.getTexture()
        self.cap_buf.setActive(False)               # one-shot: rendered only when a frame is requested
        lens = PerspectiveLens()
        lens.setAspectRatio(C.CAP_W / C.CAP_H)
        lens.setFov(C.HFOV)
        lens.setNearFar(0.1, 300)
        cam = self.makeCamera(self.cap_buf, lens=lens, scene=self.render, camName="capcam",
                              clearColor=Vec4(HAZE[0], HAZE[1], HAZE[2], 1))
        cam.reparentTo(self.camera)
        cam.node().setCameraMask(CAP_MASK)
        self.cam.node().setCameraMask(MAIN_MASK)

    def txt(self, text, pos, parent, scale=0.05, fg=HUD, align=TextNode.ALeft):
        return OnscreenText(text=text, pos=pos, scale=scale, fg=fg, align=align, parent=parent,
                            mayChange=True, shadow=(0, 0, 0, 0.9), font=None)

    def card(self, parent, x, z, w, h, color):
        cm = CardMaker("c"); cm.setFrame(0, 1, 0, 1)
        n = parent.attachNewNode(cm.generate())
        n.setPos(x, 0, z); n.setScale(w, 1, h); n.setColor(*color); n.setTransparency(TransparencyAttrib.MAlpha)
        return n

    def setup_hud(self):
        tl, tr, bl = self.a2dTopLeft, self.a2dTopRight, self.a2dBottomLeft
        self.txt("NEUROSTRIKE", (0.05, -0.10), tl, 0.08, HUD)
        self.t_stats = self.txt("", (0.05, -0.19), tl, 0.05, (1, 1, 1, 1))
        self.hp_bg = self.card(tl, 0.05, -0.27, 0.55, 0.028, (0.1, 0.12, 0.2, 0.9))
        self.hp_fg = self.card(tl, 0.05, -0.27, 0.55, 0.028, (0.2, 1.0, 0.5, 1))
        self.t_link = self.txt("", (0.05, -0.33), tl, 0.04, ACCENT)
        br = self.a2dBottomRight
        self.t_ammo = self.txt("", (-0.08, 0.14), br, 0.12, HUD, TextNode.ARight)
        self.t_ammo2 = self.txt("", (-0.08, 0.07), br, 0.04, ACCENT, TextNode.ARight)
        self.st_bg = self.card(br, -0.60, 0.22, 0.52, 0.016, (0.1, 0.12, 0.2, 0.9))
        self.st_fg = self.card(br, -0.60, 0.22, 0.52, 0.016, (1.0, 0.62, 0.16, 1))
        self.t_vis = self.txt("", (-0.05, -0.08), tr, 0.045, GREEN, TextNode.ARight)
        self.t_vis2 = self.txt("", (-0.05, -0.14), tr, 0.04, SOFT, TextNode.ARight)
        self.txt("WASD move | SHIFT sprint (double-tap = tactical) | R reload | MOUSE1 fire | M mouse-look | B boxes | F9 record",
                 (0.05, 0.05), bl, 0.035, (0.5, 0.7, 0.8, 1))
        self.t_center = self.txt("", (0, 0.35), self.aspect2d, 0.12, (1, 0.2, 0.3, 1), TextNode.ACenter)
        ls = LineSegs(); ls.setThickness(2); ls.setColor(*HUD)
        for a_, b_ in ((0.016, 0.042), (-0.042, -0.016)):
            ls.moveTo(a_, 0, 0); ls.drawTo(b_, 0, 0)
            ls.moveTo(0, 0, a_); ls.drawTo(0, 0, b_)
        self.aspect2d.attachNewNode(ls.create())
        hm = LineSegs(); hm.setThickness(3); hm.setColor(1, 1, 1, 1)
        for sx, sz in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            hm.moveTo(sx * 0.022, 0, sz * 0.022); hm.drawTo(sx * 0.05, 0, sz * 0.05)
        self.hitmarker = self.aspect2d.attachNewNode(hm.create()); self.hitmarker.hide(); self.hit_t = 0.0
        self.weapon = Weapon(self)
        self.dmg_card = self.card(self.render2d, -1, -1, 2, 2, (1, 0, 0, 0))

    def setup_input(self):
        for k in "wasd":
            self.accept(k, self.keys.__setitem__, [k, True])
            self.accept(k + "-up", self.keys.__setitem__, [k, False])
        self.accept("mouse1", self.set_fire, [True]); self.accept("mouse1-up", self.set_fire, [False])
        self.accept("b", self.toggle_boxes); self.accept("x", self.toggle_auto)
        self.accept("m", self.toggle_mouse); self.accept("f9", self.toggle_record)
        self.accept("r", self.key_reload); self.accept("shift", self.shift_down); self.accept("shift-up", self.shift_up)
        self.accept("v", self.toggle_pip); self.accept("f11", self.toggle_fullscreen); self.accept("escape", sys.exit)

    def set_fire(self, v): self.mouse_fire = v
    def key_reload(self): self.kb_reload = True
    def toggle_pip(self): self.show.toggle_pip()

    def on_aspect(self):
        if hasattr(self, "weapon"):
            self.weapon.lens.setAspectRatio(self.getAspectRatio())

    def toggle_fullscreen(self):
        """F11: borderless window covering the screen <-> normal window."""
        if not hasattr(self.win, "requestProperties"):
            return
        self.fullscreen = not self.fullscreen
        wp = WindowProperties()
        if self.fullscreen:
            wp.setUndecorated(True); wp.setOrigin(0, 0)
            wp.setSize(self.pipe.getDisplayWidth(), self.pipe.getDisplayHeight())
        else:
            wp.setUndecorated(False); wp.setSize(C.WIN_W, C.WIN_H); wp.setOrigin(100, 60)
        self.win.requestProperties(wp)
    def shift_up(self): self.sprint_key = False
    def shift_down(self):
        now = self.clock.getFrameTime()
        self.sprint_key = True
        if now - self.last_shift < 0.35:       # double-tap -> tactical sprint
            self.kb_tac = True
        self.last_shift = now
    def toggle_boxes(self):
        self.show_boxes = not self.show_boxes
        if self.box_root: (self.box_root.show if self.show_boxes else self.box_root.hide)()
    def toggle_auto(self): self.auto_move = not self.auto_move
    def toggle_record(self):
        self.recording = not self.recording
        print(f"[dataset] recording {'ON' if self.recording else 'OFF'} -> {C.DATASET_DIR}")

    def toggle_mouse(self):
        self.mouse_look = not self.mouse_look
        wp = WindowProperties(); wp.setCursorHidden(self.mouse_look); self.win.requestProperties(wp)
        if self.mouse_look:
            self.win.movePointer(0, self.win.getXSize() // 2, self.win.getYSize() // 2)

    # ------------------------------------------------------------------- loop
    def update(self, task):
        dt = min(self.clock.getDt(), 0.05)
        now = self.clock.getFrameTime()
        jx, jy, fire, dyaw, dpitch, rel_req, tac_req, phone_on = self.link.input.consume()
        self.phone_on = phone_on

        kx = int(self.keys["d"]) - int(self.keys["a"])
        ky = int(self.keys["w"]) - int(self.keys["s"])
        if kx or ky:
            n = math.hypot(kx, ky)
            k = 1.0 if self.sprint_key else 0.9          # edge of the stick = sprint
            jx, jy = kx / n * k, ky / n * k
        if self.mouse_look:
            cx, cy = self.win.getXSize() // 2, self.win.getYSize() // 2
            ptr = self.win.getPointer(0)
            dyaw += (ptr.getX() - cx) * C.MOUSE_SENS
            dpitch -= (ptr.getY() - cy) * C.MOUSE_SENS
            self.win.movePointer(0, cx, cy)
        fire = fire or self.mouse_fire
        rel_req = rel_req or self.kb_reload
        tac_req = tac_req or self.kb_tac
        self.kb_reload = self.kb_tac = False
        human = bool(kx or ky or self.mouse_fire or (phone_on and (
            abs(jx) > 0.25 or abs(jy) > 0.25 or fire or abs(dyaw) + abs(dpitch) > 1.5 or rel_req or tac_req)))
        ctrl = self.show.tick(dt, human)                  # attract mode: the AI bot drives
        if ctrl is not None:
            jx, jy, dyaw, dpitch, fire, rel_req, tac_req = ctrl
        mag = math.hypot(jx, jy)

        if self.alive:
            self.h -= dyaw
            self.p = max(-80.0, min(80.0, self.p + dpitch))
            self.update_sprint(dt, jx, jy, mag, fire, tac_req)
            self.update_reload(dt, rel_req)
            self.move_player(dt, jx, jy, mag)
        else:
            self.dead_t -= dt
            if self.dead_t <= 0:
                self.respawn()

        self.moving = self.alive and (mag > 0.15 or self.auto_move)
        lvl = self.sprint
        if self.moving:
            self.walk_t += dt * (8.5, 11.0, 13.0)[lvl]
            self.step_t += dt
            if self.step_t >= (0.42, 0.31, 0.26)[lvl]:
                self.step_t = 0.0
                self.sfx.play("step", (0.35, 0.5, 0.6)[lvl], random.uniform(0.9, 1.1))
        bob = (0.030, 0.055, 0.070)[lvl] * math.sin(self.walk_t) if self.moving else 0.0
        roll = (0.0, 0.6, 1.2)[lvl] * math.sin(self.walk_t * 0.5) if self.moving else 0.0
        self.kick = max(0.0, self.kick - dt * 9.0)
        self.camera.setPos(self.px, self.py, 1.7 + bob)
        self.camera.setHpr(self.h, self.p + self.kick * 1.2, roll)
        self.sky.setPos(self.px, self.py, 0)

        self.weapon.update(dt, dict(
            dyaw=dyaw, dpitch=dpitch, bob=bob, kick=self.kick, sprint=self.sprint_blend, moving=self.moving,
            reloading=self.reloading, rp=self.reload_t / self.reload_len if self.reloading else 0.0,
            empty=self.reload_empty))
        if self.hit_t > 0:
            self.hit_t -= dt
            if self.hit_t <= 0:
                self.hitmarker.hide()
        self.since_shot += dt                              # aim recoil recovery
        if self.since_shot > 0.12 and self.recoil_acc > 0:
            rec = min(self.recoil_acc, 7.0 * dt)
            self.p -= rec; self.recoil_acc -= rec

        self.fire_cd -= dt
        if self.alive and fire and self.fire_cd <= 0 and not self.reloading and self.sprint == 0:
            if self.mag > 0:
                self.fire_cd = C.FIRE_COOLDOWN
                self.mag -= 1
                self.shoot()
            else:
                self.fire_cd = 0.35
                self.sfx.play("click")
                self.start_reload()                      # auto-reload on empty

        self.update_enemies(dt, now)
        self.update_fx(dt)
        self.vision_tick(dt)
        self.publish(dt)
        self.update_hud(dt)
        self.auto_quality(dt)
        return task.cont

    def update_sprint(self, dt, jx, jy, mag, fire, tac_req):
        """Stick at the edge = sprint. TAC button / double-tap Shift = tactical sprint (timed, recharges)."""
        self.tac_cd = max(0.0, self.tac_cd - dt)
        forward = jy > 0.35 and mag > 0.5
        want = forward and (mag > 0.92 or self.sprint_key)
        if self.sprint == 2:
            self.tac_t -= dt
            if self.tac_t <= 0 or not forward:
                self.sprint = 1 if want else 0
                self.tac_cd = C.TAC_COOLDOWN
        elif tac_req and forward and self.tac_cd <= 0:
            self.sprint, self.tac_t = 2, C.TAC_TIME
            self.sfx.play("whoosh", 0.7)
        else:
            self.sprint = 1 if want else 0
        if fire and self.sprint:                          # can't shoot from the hip while sprinting
            if self.sprint == 2:
                self.tac_cd = C.TAC_COOLDOWN
            self.sprint = 0
            self.fire_cd = max(self.fire_cd, 0.18)
        self.sprint_blend += ((1.0 if self.sprint else 0.0) - self.sprint_blend) * min(1.0, dt * 12)

    def stamina(self):
        if self.sprint == 2:
            return max(0.0, self.tac_t / C.TAC_TIME)
        return 1.0 - self.tac_cd / C.TAC_COOLDOWN

    def update_reload(self, dt, req):
        if self.reloading:
            self.reload_t += dt
            if self.reload_t >= self.reload_len:
                self.reloading = False
                self.mag = C.MAG_SIZE + (0 if self.reload_empty else 1)   # +1 in the chamber
        elif req and self.mag < C.MAG_SIZE:
            self.start_reload()

    def start_reload(self):
        if self.reloading or self.mag >= C.MAG_SIZE:
            return
        self.reloading, self.reload_t = True, 0.0
        self.reload_empty = self.mag == 0
        self.reload_len = C.RELOAD_EMPTY if self.reload_empty else C.RELOAD_TACTICAL
        self.sfx.play("reload" if self.reload_empty else "reload_tac", 0.9)

    def move_player(self, dt, jx, jy, mag):
        if self.sprint == 2:
            speed = C.TAC_SPEED
        elif self.sprint == 1:
            speed = C.SPRINT_SPEED
        elif mag > 0.15:
            speed = C.WALK_SPEED * min(1.0, mag / 0.9)
        elif self.auto_move:
            speed = C.WALK_SPEED * C.AUTO_IDLE_SPEED
        else:
            return
        if mag > 0.15:
            self.move_ang = math.atan2(jx, jy)       # 0 = straight ahead, + = right
        hr = math.radians(self.h)
        f, r = (-math.sin(hr), math.cos(hr)), (math.cos(hr), math.sin(hr))
        a = self.move_ang
        dx = f[0] * math.cos(a) + r[0] * math.sin(a)
        dy = f[1] * math.cos(a) + r[1] * math.sin(a)
        self.px, self.py = push_out(self.px + dx * speed * dt, self.py + dy * speed * dt, C.PLAYER_RADIUS)

    def auto_quality(self, dt):
        """Under ~52 fps after warm-up: lite shrinks the window (960x540, then 800x450);
        high drops shadows to 1024, then turns bloom off."""
        self.q_t += dt
        if self.q_stage >= 3 or self.q_t < (10.0 if self.q_stage == 0 else 7.0):
            return
        self.q_t = 0.0
        fps = self.clock.getAverageFrameRate()
        if fps >= 52:
            self.q_stage = 3
            return
        self.q_stage += 1
        if C.QUALITY == "high":
            if self.q_stage == 1:
                self.sun.setShadowCaster(True, 1024, 1024); print(f"[gfx] {fps:.0f} fps -> shadow map 1024")
            elif self.q_stage == 2 and self.filters is not None:
                self.filters.cleanup(); self.filters = None; print(f"[gfx] {fps:.0f} fps -> bloom off")
        elif hasattr(self.win, "requestProperties") and not self.fullscreen:
            w, h = (960, 540) if self.q_stage == 1 else (800, 450)
            wp = WindowProperties(); wp.setSize(w, h); self.win.requestProperties(wp)
            print(f"[gfx] {fps:.0f} fps -> window {w}x{h}  (also try: python main.py --renderer dx9)")

    def los(self, e):
        """True if nothing solid blocks the line from the camera to the enemy's chest."""
        o = self.camera.getPos(self.render)
        c = Vec3(e.x, e.y, 1.2)
        dist = (c - o).length()
        return dist < 1e-3 or ray_world(o, (c - o) / dist) >= dist - 0.4

    def add_enemy(self, x, y):
        e = Enemy(self, x, y)
        e.snd = self.sfx.acquire_steps()
        self.enemies.append(e)

    def enemy_audio(self, e, d):
        if e.snd is None:
            return
        hr = math.radians(self.h)
        bal = ((e.x - self.px) * math.cos(hr) + (e.y - self.py) * math.sin(hr)) / max(d, 0.1)
        e.snd.setVolume(max(0.0, 1.0 - d / 30.0) ** 2 * 0.9 * C.MASTER_VOLUME)
        e.snd.setBalance(max(-1.0, min(1.0, bal)))

    def respawn(self):
        for e in self.enemies: e.destroy()
        self.enemies.clear(); self.contacts.clear()
        self.px = self.py = 0.0; self.hp = 100.0; self.score = 0; self.alive = True
        self.mag, self.reloading, self.sprint, self.tac_cd = C.MAG_SIZE, False, 0, 0.0
        self.t_center.setText("")

    # ---------------------------------------------------------------- combat
    def shoot(self):
        self.sfx.play("shot", 0.9, random.uniform(0.97, 1.04))
        self.weapon.fire()
        self.show.on_shot()
        o = self.camera.getPos(self.render)
        q = self.camera.getQuat(self.render)
        spread = math.radians(0.25 + (0.9 if self.moving else 0.0) + 0.35 * self.kick)
        r_, a_ = spread * math.sqrt(random.random()), random.uniform(0, 6.2832)
        d = q.getForward() + q.getRight() * math.tan(r_ * math.cos(a_)) + q.getUp() * math.tan(r_ * math.sin(a_))
        d.normalize()
        best, hit, head = ray_world(o, d), None, False
        for e in self.enemies:
            th = ray_sphere(o, d, Vec3(e.x, e.y, 1.68), 0.19)
            tb = ray_sphere(o, d, Vec3(e.x, e.y, 0.95), 0.85)
            t, is_head = (th, True) if th is not None else (tb, False)
            if t is not None and t < best:
                best, hit, head = t, e, is_head
        end = o + d * best
        muzzle = o + q.getRight() * 0.21 + q.getUp() * -0.19 + d * 0.9
        ls = LineSegs(); ls.setThickness(2.5); ls.setColor(1.0, 0.85, 0.5, 1)
        ls.moveTo(muzzle); ls.drawTo(end)
        tracer = self.render.attachNewNode(ls.create()); tracer.setLightOff(); tracer.setFogOff()
        self.taskMgr.doMethodLater(0.05, lambda t, n=tracer: n.removeNode(), "tracer")
        self.burst(end, 3, (0.75, 0.70, 0.60, 1))
        self.kick = 1.0
        kp = random.uniform(0.45, 0.65)                  # real recoil: climbs the aim, partly recovers
        self.p += kp
        self.h += random.uniform(-0.2, 0.22)
        self.recoil_acc = min(9.0, self.recoil_acc + kp)
        self.since_shot = 0.0
        if hit:
            hit.hp -= 3 if head else 1
            hit.flash = 0.08
            self.hit_t = 0.12
            self.hitmarker.setColorScale(1, 1, 1, 1); self.hitmarker.show()
            self.sfx.play("hit", 0.8)
            self.show.on_hit(head)
            if hit.hp <= 0:
                self.hitmarker.setColorScale(1, 0.2, 0.2, 1)
                self.sfx.play("kill", 0.9)
                self.burst(Point3(hit.x, hit.y, 1.0), 12, (0.80, 0.76, 0.66, 1))
                hit.destroy(); self.enemies.remove(hit)
                self.score += 150 if head else 100
                self.show.on_kill(head)

    def burst(self, pos, n, color):
        for _ in range(n):
            b = make_box(0.05, 0.05, 0.05); b.reparentTo(self.render); b.setLightOff(); b.setColor(*color)
            b.setPos(pos)
            vel = Vec3(random.uniform(-3, 3), random.uniform(-3, 3), random.uniform(1, 5))
            self.fx.append([b, vel, random.uniform(0.3, 0.6)])

    def update_fx(self, dt):
        for fx in self.fx[:]:
            fx[1].z -= 9 * dt
            fx[0].setPos(fx[0].getPos() + fx[1] * dt)
            fx[2] -= dt
            if fx[2] <= 0:
                fx[0].removeNode(); self.fx.remove(fx)

    def update_enemies(self, dt, now):
        if self.alive and self.spawn_enabled:
            self.spawn_t -= dt
            if self.spawn_t <= 0 and len(self.enemies) < C.MAX_ENEMIES:
                self.spawn_t = C.SPAWN_INTERVAL
                for _ in range(20):
                    x = random.uniform(-C.ARENA_HALF + 2, C.ARENA_HALF - 2)
                    y = random.uniform(-C.ARENA_HALF + 2, C.ARENA_HALF - 2)
                    if math.hypot(x - self.px, y - self.py) < 18:
                        continue
                    if (x, y) != push_out(x, y, 0.8):
                        continue
                    self.add_enemy(x, y); break
        self.hurt_cd -= dt
        for e in self.enemies:
            d = e.update(dt, self.px, self.py, now)
            self.enemy_audio(e, d)
            if self.alive and not self.godmode and d < 1.5 and self.hurt_cd <= 0:
                self.hurt_cd = 0.8; self.hp -= 12; self.hurt_count += 1; self.dmg_flash = 0.5
                self.sfx.play("hurt", 1.0)
                if self.hp <= 0:
                    self.hp, self.alive, self.dead_t = 0, False, 3.0
        for i, a in enumerate(self.enemies):  # keep enemies from stacking
            for b in self.enemies[i + 1:]:
                dx, dy = b.x - a.x, b.y - a.y; d = math.hypot(dx, dy)
                if 1e-6 < d < 1.0:
                    s = (1.0 - d) / 2 / d
                    a.x -= dx * s; a.y -= dy * s; b.x += dx * s; b.y += dy * s

    # ---------------------------------------------------------------- vision
    def grab_frame(self):
        tex = self.cap_tex
        if not tex.hasRamImage():
            return None
        data = tex.getRamImageAs("BGR")
        if data is None or len(data) == 0:
            return None
        a = np.frombuffer(data.getData(), np.uint8).reshape(tex.getYSize(), tex.getXSize(), 3)
        return np.ascontiguousarray(a[::-1])  # OpenGL is bottom-up

    def vision_tick(self, dt):
        """Capture is one-shot: request a render on one frame, read it back on the next.
        The offscreen buffer sits idle in between, so there is no per-frame GPU readback."""
        self.vis_t += dt
        if self.cap_pending:
            self.cap_pending = False
            frame = self.grab_frame()
            self.cap_buf.setActive(False)
            if frame is not None:
                self.vision.submit(frame, self.cap_meta)
                if self.cap_meta.get("labels") is not None:
                    self.record_sample(frame, self.cap_meta["labels"])
        elif self.vis_t >= 1.0 / C.VISION_HZ:
            self.vis_t = 0.0
            labels = None
            if self.recording:
                self.rec_t -= 1.0 / C.VISION_HZ
                if self.rec_t <= 0:
                    self.rec_t = 0.3
                    labels = [b for b in (self.project_enemy(e) for e in self.enemies) if b]
            self.cap_meta = dict(px=self.px, py=self.py, h=self.h, t=time.time(), labels=labels)
            self.cap_buf.setActive(True)
            self.cap_pending = True
        res = self.vision.latest()
        if res and res["seq"] != self.last_seq:
            self.last_seq = res["seq"]
            self.n_targets = len(res["dets"])
            self.draw_boxes(res)
            self.ingest(res)

    def draw_boxes(self, res):
        if self.box_root:
            self.box_root.removeNode()
        self.box_root = self.aspect2d.attachNewNode("boxes")
        if not self.show_boxes:
            self.box_root.hide()
        ar = self.getAspectRatio()
        kz = ar * C.CAP_H / C.CAP_W          # capture is 16:9; screen may not be (16:10, 3:2...)
        ls = LineSegs(); ls.setThickness(2.5); ls.setColor(*GREEN)
        for d in res["dets"]:
            x1, x2 = (d["x1"] * 2 - 1) * ar, (d["x2"] * 2 - 1) * ar
            y1, y2 = (1 - d["y1"] * 2) * kz, (1 - d["y2"] * 2) * kz   # y1 = top edge
            cl = min(x2 - x1, y1 - y2) * 0.28
            for cx, cy, sx, sy in ((x1, y1, 1, -1), (x2, y1, -1, -1), (x1, y2, 1, 1), (x2, y2, -1, 1)):
                ls.moveTo(cx + sx * cl, 0, cy); ls.drawTo(cx, 0, cy); ls.drawTo(cx, 0, cy + sy * cl)
            tn = TextNode("lbl"); tn.setText(f"ENEMY #{d['id']}  {d['conf'] * 100:.0f}%")
            tn.setTextColor(*GREEN)
            t = self.box_root.attachNewNode(tn); t.setScale(0.045); t.setPos(x1, 0, y1 + 0.012)
        self.box_root.attachNewNode(ls.create())
        self.show.pip_boxes(res["dets"])

    def ingest(self, res):
        """Detections -> world-space radar contacts, using the pose at capture time."""
        m = res["meta"]
        hr = math.radians(m["h"])
        f, r = (-math.sin(hr), math.cos(hr)), (math.cos(hr), math.sin(hr))
        tan_h = math.tan(math.radians(C.HFOV) / 2)
        tan_v = tan_h * C.CAP_H / C.CAP_W
        for d in res["dets"]:
            cx = (d["x1"] + d["x2"]) / 2
            hn = max(d["y2"] - d["y1"], 1e-3)
            if C.ENEMY_HIGHLIGHT:                             # solve hn = (H + 2*pad(z)) / (2*z*tan_v) for z
                zc = (C.ENEMY_HEIGHT + 0.09) / max(0.02, 2 * hn * tan_v - 0.02)
            else:
                zc = C.ENEMY_HEIGHT / (hn * 2 * tan_v)         # depth along the view axis
            lat = zc * (cx - 0.5) * 2 * tan_h
            self.contacts[d["id"]] = dict(x=m["px"] + f[0] * zc + r[0] * lat,
                                          y=m["py"] + f[1] * zc + r[1] * lat,
                                          c=d["conf"], t=time.time())

    # --------------------------------------------------- auto-labelled dataset
    def project_enemy(self, e):
        o = self.camera.getPos(self.render)
        c = Vec3(e.x, e.y, 1.0)
        dist = (c - o).length()
        if dist < 0.5 or ray_world(o, (c - o) / dist) < dist - 0.5:
            return None  # too close or occluded
        xs, ys = [], []
        tan_h = math.tan(math.radians(C.HFOV) / 2)
        tan_v = tan_h * C.CAP_H / C.CAP_W
        pad = (0.045 + 0.010 * dist) if C.ENEMY_HIGHLIGHT else 0.0      # include the red outline
        for sx in (-1, 1):
            for sy in (-1, 1):
                for z in (-pad, C.ENEMY_HEIGHT + pad):
                    rel = self.camera.getRelativePoint(self.render, Point3(
                        e.x + sx * (C.ENEMY_HALF_W + pad), e.y + sy * (C.ENEMY_HALF_W + pad), z))
                    if rel.y <= 0.1:
                        return None                      # partly behind the camera
                    xs.append(rel.x / (rel.y * tan_h))   # pinhole projection -> NDC
                    ys.append(rel.z / (rel.y * tan_v))
        x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
        full = (x2 - x1) * (y2 - y1)
        x1, x2, y1, y2 = max(x1, -1), min(x2, 1), max(y1, -1), min(y2, 1)
        if x2 - x1 < 0.02 or y2 - y1 < 0.04 or (x2 - x1) * (y2 - y1) < 0.6 * full:
            return None
        return ((x1 + x2) / 4 + 0.5, 0.5 - (y1 + y2) / 4, (x2 - x1) / 2, (y2 - y1) / 2)

    def record_sample(self, frame, labels):
        if not labels and random.random() > 0.1:   # keep ~10% negatives
            return
        img_dir, lbl_dir = C.DATASET_DIR / "images", C.DATASET_DIR / "labels"
        img_dir.mkdir(parents=True, exist_ok=True); lbl_dir.mkdir(parents=True, exist_ok=True)
        name = f"{int(time.time() * 1000)}"
        cv2.imwrite(str(img_dir / f"{name}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        (lbl_dir / f"{name}.txt").write_text(
            "\n".join(f"0 {a:.6f} {b:.6f} {w:.6f} {h:.6f}" for a, b, w, h in labels))
        self.rec_count += 1

    # ------------------------------------------------------------ phone state
    def publish(self, dt):
        self.pub_t += dt
        if self.pub_t < 1.0 / C.STATE_HZ:
            return
        self.pub_t = 0.0
        now = time.time()
        for k in [k for k, c in self.contacts.items() if now - c["t"] > C.CONTACT_TTL]:
            del self.contacts[k]
        res = self.vision.latest()
        self.link.publish({
            "t": "state", "px": round(self.px, 2), "py": round(self.py, 2), "h": round(self.h, 1),
            "hp": int(self.hp), "score": self.score, "hurt": self.hurt_count, "alive": self.alive,
            "ammo": self.mag, "mag": C.MAG_SIZE, "spr": self.sprint, "stam": round(self.stamina(), 2),
            "rel": round(self.reload_t / self.reload_len, 2) if self.reloading else -1,
            "src": self.vision.name, "ms": int(res["ms"]) if res else 0,
            "contacts": [{"id": k, "x": round(c["x"], 2), "y": round(c["y"], 2),
                          "c": round(c["c"], 2), "a": round(now - c["t"], 2)}
                         for k, c in self.contacts.items()],
        })

    def update_hud(self, dt):
        self.dmg_flash = max(0.0, self.dmg_flash - dt)
        self.dmg_card.setColor(1, 0, 0, self.dmg_flash * 0.5)
        frac = max(0.0, self.hp / 100.0)
        self.hp_fg.setScale(0.55 * frac, 1, 0.028)
        self.hp_fg.setColor(1 - frac, 0.3 + 0.7 * frac, 0.4 * frac, 1)
        self.st_fg.setScale(0.52 * self.stamina(), 1, 0.016)
        self.hud_acc += dt
        if self.hud_acc < 0.1:
            return
        self.hud_acc = 0.0
        self.t_stats.setText(f"HP {int(self.hp):3d}     SCORE {self.score}")
        n = len(self.link.clients)
        self.t_link.setText(f"PHONE {'LINKED' if self.phone_on else ('IDLE' if n else 'WAITING')}"
                            f"  |  {self.ip}:{C.WS_PORT}" + ("  |  AUTO-RUN" if self.auto_move else ""))
        res = self.vision.latest()
        self.t_vis.setText(f"{self.vision.name}  {res['ms']:.0f} ms" if res else f"{self.vision.name}  --")
        rec = f"   REC {self.rec_count}" if self.recording else ""
        self.t_vis2.setText(f"{self.n_targets} targets   {self.clock.getAverageFrameRate():.0f} fps{rec}")
        self.t_ammo.setText(str(self.mag))
        if self.reloading:
            self.t_ammo2.setText(f"RELOADING {int(100 * self.reload_t / self.reload_len)}%")
        else:
            self.t_ammo2.setText("/ INF   " + ("TACTICAL SPRINT" if self.sprint == 2 else "SPRINT" if self.sprint == 1 else ""))
