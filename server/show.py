"""Exhibition layer: attract mode (AI bot plays itself), timed rounds, results + high scores,
kill streak banners, 'what YOLO sees' picture-in-picture, and a PC-side tactical radar."""
import json
import math
import random
import time

from panda3d.core import CardMaker, LineSegs, TextNode, TransparencyAttrib

import config as C
import textures as T
from world import ray_world

SCORES = C.ROOT / "highscores.json"
WHITE, SOFT, ACCENT = (0.93, 0.95, 0.97, 1), (0.72, 0.78, 0.84, 1), (1.0, 0.62, 0.16, 1)
PIP_W, PIP_H = 0.64, 0.36
ARENA_R = 30.0


def _circle(ls, r, n=40):
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        (ls.moveTo if i == 0 else ls.drawTo)(r * math.cos(a), 0, r * math.sin(a))


class Show:
    def __init__(self, g):
        self.g = g
        self.mode = "attract" if C.ATTRACT else "free"
        self.round_t, self.results_t, self.final = float(C.ROUND_TIME), 0.0, None
        self.stats = self._blank()
        self.streak, self.last_kill = 0, -99.0
        self.banner_t = self.pop_t = 0.0
        self.scores = self._load()
        self.wp, self.wp_t, self.react, self.phase = None, 0.0, 0.0, random.random() * 6.28
        self.stuck_t, self.last_pos = 0.0, (0.0, 0.0)
        self.radar_t, self.radar, self.sec = 0.0, None, -1
        self._ui()
        self._apply_mode()

    # ------------------------------------------------------------------ UI
    def _ui(self):
        g = self.g
        a2d = g.aspect2d
        self.t_banner = g.txt("", (0, 0.45), a2d, 0.13, ACCENT, TextNode.ACenter)
        self.t_pop = g.txt("", (0, 0.32), a2d, 0.07, WHITE, TextNode.ACenter)
        self.t_timer = g.txt("", (0, -0.12), g.a2dTopCenter, 0.11, WHITE, TextNode.ACenter)

        self.att = a2d.attachNewNode("attract")
        g.card(self.att, -1.15, 0.0, 2.3, 0.88, (0, 0, 0, 0.58))
        g.txt("NEUROSTRIKE", (0, 0.72), self.att, 0.17, WHITE, TextNode.ACenter)
        g.txt("AI-VISION FPS   |   YOLO ENEMY DETECTION   |   PHONE CONTROLLER", (0, 0.63), self.att, 0.042, SOFT, TextNode.ACenter)
        self.t_join = g.txt("", (0, 0.52), self.att, 0.062, ACCENT, TextNode.ACenter)
        g.txt("HIGH SCORES", (0, 0.40), self.att, 0.05, SOFT, TextNode.ACenter)
        self.t_scores = g.txt("", (0, 0.33), self.att, 0.05, WHITE, TextNode.ACenter)

        self.res = a2d.attachNewNode("results")
        g.card(self.res, -0.9, -0.05, 1.8, 0.95, (0, 0, 0, 0.68))
        self.t_res_title = g.txt("", (0, 0.76), self.res, 0.13, ACCENT, TextNode.ACenter)
        self.t_res = g.txt("", (0, 0.58), self.res, 0.065, WHITE, TextNode.ACenter)
        self.t_res_rank = g.txt("", (0, 0.04), self.res, 0.05, SOFT, TextNode.ACenter)

        # picture-in-picture: the exact frames the detector receives, with its boxes
        self.pip = g.a2dBottomLeft.attachNewNode("pip"); self.pip.setPos(0.05, 0, 0.12)
        cm = CardMaker("ai"); cm.setFrame(0, PIP_W, 0, PIP_H)
        card = self.pip.attachNewNode(cm.generate()); card.setTexture(g.cap_tex); card.setLightOff()
        ls = LineSegs(); ls.setThickness(2); ls.setColor(0.2, 1, 0.5, 1)
        ls.moveTo(0, 0, 0); ls.drawTo(PIP_W, 0, 0); ls.drawTo(PIP_W, 0, PIP_H); ls.drawTo(0, 0, PIP_H); ls.drawTo(0, 0, 0)
        self.pip.attachNewNode(ls.create())
        t = g.txt("AI VISION  (what YOLO sees)", (0, PIP_H + 0.012), self.pip, 0.032, (0.2, 1, 0.5, 1))
        self.pip_b = None
        if not C.SHOW_AI_VIEW:
            self.pip.hide()

        # PC radar backdrop (lines are redrawn at ~12 Hz)
        self.rroot = g.a2dTopRight.attachNewNode("radar_bg"); self.rroot.setPos(-0.30, 0, -0.62)
        cm = CardMaker("rb"); cm.setFrame(-0.26, 0.26, -0.26, 0.26)
        bg = self.rroot.attachNewNode(cm.generate()); bg.setTexture(T.blob()); bg.setTransparency(TransparencyAttrib.MAlpha)
        bg.setColorScale(0, 0.1, 0.12, 1.6)

    def toggle_pip(self):
        (self.pip.hide if not self.pip.isHidden() else self.pip.show)()

    def pip_boxes(self, dets):
        if self.pip_b:
            self.pip_b.removeNode()
        self.pip_b = self.pip.attachNewNode("pb")
        ls = LineSegs(); ls.setThickness(2); ls.setColor(0.2, 1, 0.5, 1)
        for d in dets:
            x1, x2 = d["x1"] * PIP_W, d["x2"] * PIP_W
            z1, z2 = (1 - d["y2"]) * PIP_H, (1 - d["y1"]) * PIP_H
            ls.moveTo(x1, 0, z1); ls.drawTo(x2, 0, z1); ls.drawTo(x2, 0, z2); ls.drawTo(x1, 0, z2); ls.drawTo(x1, 0, z1)
        self.pip_b.attachNewNode(ls.create())

    def banner(self, text, secs=1.6):
        self.t_banner.setText(text); self.banner_t = secs

    def popup(self, text, secs=0.9):
        self.t_pop.setText(text); self.pop_t = secs

    def _fade(self, dt):
        for attr, node, base in (("banner_t", self.t_banner, ACCENT), ("pop_t", self.t_pop, WHITE)):
            v = getattr(self, attr)
            if v > 0:
                v -= dt; setattr(self, attr, v)
                node.setFg((base[0], base[1], base[2], max(0.0, min(1.0, v * 3))))
                if v <= 0:
                    node.setText("")

    # ---------------------------------------------------------------- modes
    def _apply_mode(self):
        g = self.g
        attract = self.mode == "attract"
        g.godmode = attract
        g.spawn_enabled = self.mode != "results"
        (self.att.show if attract else self.att.hide)()
        (self.res.show if self.mode == "results" else self.res.hide)()
        (self.t_timer.show if self.mode == "play" else self.t_timer.hide)()
        self.t_join.setText(f"PICK UP THE PHONE TO PLAY     |     CONNECT TO  {g.ip}")
        self.t_scores.setText(self._score_text())

    def start_round(self):
        g = self.g
        g.respawn()
        self.stats, self.streak, self.round_t = self._blank(), 0, float(C.ROUND_TIME)
        self.mode = "play"
        self._apply_mode()
        g.spawn_t = 0.4
        self.banner("GO!", 1.0)

    def end_round(self, reason):
        g, st = self.g, self.stats
        acc = round(100 * st["hits"] / max(1, st["shots"]))
        self.final = dict(score=g.score, kills=st["kills"], heads=st["heads"], acc=acc, date=time.strftime("%d %b %H:%M"))
        rank = self._add_score(self.final)
        for e in g.enemies:
            e.destroy()
        g.enemies.clear(); g.contacts.clear()
        self.mode, self.results_t = "results", float(C.RESULTS_TIME)
        self.t_res_title.setText(reason)
        self.t_res.setText(f"SCORE  {g.score}\nKILLS  {st['kills']}     HEADSHOTS  {st['heads']}\nACCURACY  {acc}%")
        self.t_res_rank.setText(f"#{rank} ON THE LEADERBOARD" if rank else "KEEP PRACTISING - NEXT PLAYER!")
        self._apply_mode()

    def to_attract(self):
        self.mode = "attract"
        self.g.respawn()
        self._apply_mode()

    # ----------------------------------------------------------------- tick
    def tick(self, dt, human):
        """Returns bot controls (jx, jy, dyaw, dpitch, fire, reload, tac) in attract mode, else None."""
        g = self.g
        self._fade(dt)
        self._radar(dt)
        if self.mode == "attract":
            if human:
                self.start_round()
                return None
            return self._bot(dt)
        if self.mode == "play":
            self.round_t -= dt
            if not g.alive:
                self.end_round("SYSTEM FAILURE")
            elif self.round_t <= 0:
                self.end_round("TIME UP")
            else:
                s = int(math.ceil(self.round_t))
                if s != self.sec:
                    self.sec = s
                    self.t_timer.setText(f"{s // 60}:{s % 60:02d}")
                    self.t_timer.setFg((1, 0.3, 0.25, 1) if s <= 10 else WHITE)
        elif self.mode == "results":
            self.results_t -= dt
            if self.results_t <= 0:
                self.to_attract()
        return None

    # ------------------------------------------------------------- scoring
    @staticmethod
    def _blank():
        return dict(shots=0, hits=0, kills=0, heads=0)

    def on_shot(self):
        self.stats["shots"] += 1

    def on_hit(self, head):
        self.stats["hits"] += 1

    def on_kill(self, head):
        now = self.g.clock.getFrameTime()
        self.streak = self.streak + 1 if now - self.last_kill < 4.0 else 1
        self.last_kill = now
        self.stats["kills"] += 1
        self.stats["heads"] += 1 if head else 0
        if head:
            self.popup("HEADSHOT  +150")
        names = {2: "DOUBLE KILL", 3: "TRIPLE KILL", 4: "QUAD KILL"}
        if self.streak >= 2:
            self.banner(names.get(self.streak, "RAMPAGE"), 1.4)

    def _load(self):
        try:
            return json.loads(SCORES.read_text())
        except Exception:
            return []

    def _add_score(self, entry):
        if entry["score"] <= 0:
            return None
        self.scores.append(entry)
        self.scores.sort(key=lambda e: e["score"], reverse=True)
        self.scores = self.scores[:10]
        try:
            SCORES.write_text(json.dumps(self.scores, indent=1))
        except OSError:
            pass
        return self.scores.index(entry) + 1 if entry in self.scores else None

    def _score_text(self):
        if not self.scores:
            return "no scores yet - be the first!"
        return "\n".join(f"{i + 1}.  {e['score']:5d}    {e['kills']} kills   {e['acc']}%" for i, e in enumerate(self.scores[:5]))

    # ------------------------------------------------------------------ bot
    def _bot(self, dt):
        """Plays the game by itself so the screen is never dead: patrols, strafes, aims, shoots, reloads."""
        g = self.g
        o = g.camera.getPos(g.render)
        best, tgt = 1e9, None
        for e in g.enemies:
            if g.los(e) and (d := math.hypot(e.x - g.px, e.y - g.py)) < best:
                best, tgt = d, e
        jx = jy = dyaw = dpitch = 0.0
        fire = False
        self.stuck_t += dt                                  # stuck against a wall? pick a new route
        if self.stuck_t > 1.2:
            if math.hypot(g.px - self.last_pos[0], g.py - self.last_pos[1]) < 0.8:
                self.wp = (random.uniform(-26, 26), random.uniform(-26, 26)); self.wp_t = 7.0
                self.unstick = 0.8
            self.stuck_t, self.last_pos = 0.0, (g.px, g.py)
        if getattr(self, "unstick", 0.0) > 0:               # back off and turn for a moment
            self.unstick -= dt
            return -0.6, -0.8, 120 * dt, 0.0, False, False, False
        if tgt is not None:
            hd = math.degrees(math.atan2(-(tgt.x - g.px), tgt.y - g.py))
            err = (hd - g.h + 180.0) % 360.0 - 180.0
            step = max(-260 * dt, min(260 * dt, err * min(1.0, 7 * dt)))
            dyaw = -step
            pd = math.degrees(math.atan2(1.30 - 1.70, best))
            dpitch = max(-120 * dt, min(120 * dt, (pd - g.p) * min(1.0, 7 * dt)))
            self.react = max(0.0, self.react - dt)
            fire = abs(err) < 2.5 and abs(pd - g.p) < 4 and self.react <= 0 and best < 45
            jx = 0.8 * math.sin(g.clock.getFrameTime() * 0.9 + self.phase)
            jy = 0.35 if best > 14 else -0.35
        else:
            self.react = 0.35
            self.wp_t -= dt
            if g.plates and g.armor < C.PLATE_MAX:         # grab armor plates when nothing to shoot
                pl = min(g.plates, key=lambda p: math.hypot(p.x - g.px, p.y - g.py))
                self.wp = (pl.x, pl.y)
            elif self.wp is None or self.wp_t <= 0 or math.hypot(self.wp[0] - g.px, self.wp[1] - g.py) < 3.0:
                self.wp = (random.uniform(-26, 26), random.uniform(-26, 26)); self.wp_t = 7.0
            hd = math.degrees(math.atan2(-(self.wp[0] - g.px), self.wp[1] - g.py))
            err = (hd - g.h + 180.0) % 360.0 - 180.0
            dyaw = -max(-180 * dt, min(180 * dt, err * min(1.0, 4 * dt)))
            dpitch = (0.0 - g.p) * min(1.0, 4 * dt)
            jy = 0.97 if abs(err) < 40 else 0.3
        return jx, jy, dyaw, dpitch, fire, (g.mag <= 4 and not g.reloading), False

    # --------------------------------------------------------------- radar
    def _radar(self, dt):
        self.radar_t -= dt
        if self.radar_t > 0:
            return
        self.radar_t = 0.08
        g = self.g
        if self.radar:
            self.radar.removeNode()
        self.radar = self.rroot.attachNewNode("radar_fg")
        R = 0.22
        ls = LineSegs(); ls.setThickness(1.5); ls.setColor(0.55, 0.85, 0.95, 0.9)
        _circle(ls, R); _circle(ls, R * 0.66); _circle(ls, R * 0.33)
        ls.moveTo(0, 0, 0); ls.drawTo(R * math.sin(math.radians(45)), 0, R * math.cos(math.radians(45)))
        ls.moveTo(0, 0, 0); ls.drawTo(-R * math.sin(math.radians(45)), 0, R * math.cos(math.radians(45)))
        ls2 = LineSegs(); ls2.setThickness(3); ls2.setColor(1, 0.25, 0.3, 1)
        hr = math.radians(g.h)
        ch, sh = math.cos(hr), math.sin(hr)
        now = time.time()
        for c in g.contacts.values():
            dx, dy = c["x"] - g.px, c["y"] - g.py
            x, z = (dx * ch + dy * sh) * R / ARENA_R, (-dx * sh + dy * ch) * R / ARENA_R
            d = math.hypot(x, z)
            if d > R * 0.95:
                x, z = x * R * 0.95 / d, z * R * 0.95 / d
            s = 0.012
            ls2.moveTo(x - s, 0, z); ls2.drawTo(x, 0, z + s); ls2.drawTo(x + s, 0, z); ls2.drawTo(x, 0, z - s); ls2.drawTo(x - s, 0, z)
        ls4 = LineSegs(); ls4.setThickness(3); ls4.setColor(0.3, 0.85, 1.0, 1)          # armor plates
        for p in g.plates:
            dx, dy = p.x - g.px, p.y - g.py
            x, z = (dx * ch + dy * sh) * R / ARENA_R, (-dx * sh + dy * ch) * R / ARENA_R
            d = math.hypot(x, z)
            if d > R * 0.95:
                x, z = x * R * 0.95 / d, z * R * 0.95 / d
            s = 0.010
            ls4.moveTo(x - s, 0, z - s); ls4.drawTo(x + s, 0, z - s); ls4.drawTo(x + s, 0, z + s); ls4.drawTo(x - s, 0, z + s); ls4.drawTo(x - s, 0, z - s)
        ls3 = LineSegs(); ls3.setThickness(2.5); ls3.setColor(1, 1, 1, 1)
        ls3.moveTo(0, 0, 0.018); ls3.drawTo(-0.011, 0, -0.01); ls3.drawTo(0.011, 0, -0.01); ls3.drawTo(0, 0, 0.018)
        for l in (ls, ls2, ls4, ls3):
            self.radar.attachNewNode(l.create())
