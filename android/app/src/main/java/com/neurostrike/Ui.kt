package com.neurostrike

import android.content.Context
import android.os.VibrationEffect
import android.os.Vibrator
import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

private const val RADAR_RANGE = 30f      // metres — keep in sync with the server's view distance
private const val CONTACT_TTL = 2.0f     // seconds — matches server config.CONTACT_TTL

// ───────────────────────────── helpers ─────────────────────────────

private fun DrawScope.grid(step: Float = 48f, alpha: Float = 0.05f) {
    var x = 0f
    while (x < size.width) { drawLine(Neon.cyan.copy(alpha), Offset(x, 0f), Offset(x, size.height)); x += step }
    var y = 0f
    while (y < size.height) { drawLine(Neon.cyan.copy(alpha), Offset(0f, y), Offset(size.width, y)); y += step }
}

@Composable
private fun Mono(text: String, color: Color = Color.White, size: Int = 12, weight: FontWeight = FontWeight.Medium,
                 spacing: Int = 1, modifier: Modifier = Modifier) =
    Text(text, color = color, fontSize = size.sp, fontFamily = FontFamily.Monospace,
        fontWeight = weight, letterSpacing = spacing.sp, modifier = modifier)

private fun vibrate(ctx: Context, ms: Long) {
    val v = ctx.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator ?: return
    v.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE))
}

@Composable
private fun NeonChip(label: String, active: Boolean, enabled: Boolean = true, onClick: () -> Unit) {
    val shape = RoundedCornerShape(8.dp)
    val c = if (!enabled) Color.Gray else if (active) Neon.cyan else Neon.violet
    Box(
        Modifier.clip(shape)
            .background(if (active && enabled) Neon.cyan.copy(0.22f) else Neon.panel.copy(0.8f))
            .border(1.dp, c.copy(0.8f), shape)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 6.dp)
    ) { Mono(label, c, 11, FontWeight.Bold) }
}

// ───────────────────────────── app shell ─────────────────────────────

@Composable
fun NeuroStrikeApp(net: NetClient, input: InputController, gyroAvailable: Boolean) {
    val ctx = LocalContext.current
    val prefs = remember { ctx.getSharedPreferences("ns", Context.MODE_PRIVATE) }
    var started by remember { mutableStateOf(false) }
    MaterialTheme(colorScheme = darkColorScheme(primary = Neon.cyan, background = Neon.bg, surface = Neon.panel)) {
        if (!started) {
            ConnectScreen(prefs.getString("ip", "") ?: "") { ip ->
                prefs.edit().putString("ip", ip).apply()
                net.connect(ip)
                started = true
            }
        } else {
            BackHandler { net.disconnect(); started = false }
            HudScreen(net, input, gyroAvailable)
        }
    }
}

@Composable
fun ConnectScreen(initial: String, onConnect: (String) -> Unit) {
    var ip by remember { mutableStateOf(initial) }
    Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Neon.bg, Neon.bg2))),
        contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) { grid() }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("NEUROSTRIKE", style = TextStyle(color = Neon.cyan, fontSize = 44.sp, fontWeight = FontWeight.Black,
                fontFamily = FontFamily.Monospace, letterSpacing = 6.sp, shadow = Shadow(Neon.cyan, blurRadius = 28f)))
            Mono("PHONE CONTROLLER", Neon.violet, 13, spacing = 8)
            Spacer(Modifier.height(22.dp))
            OutlinedTextField(
                value = ip, onValueChange = { ip = it }, singleLine = true,
                label = { Text("PC IP ADDRESS") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                textStyle = TextStyle(color = Color.White, fontFamily = FontFamily.Monospace),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Neon.cyan, unfocusedBorderColor = Neon.cyan.copy(0.4f),
                    focusedLabelColor = Neon.cyan, unfocusedLabelColor = Neon.violet, cursorColor = Neon.cyan),
                modifier = Modifier.width(300.dp))
            Spacer(Modifier.height(14.dp))
            val shape = RoundedCornerShape(12.dp)
            Box(Modifier.width(300.dp).height(52.dp).clip(shape)
                .background(Brush.horizontalGradient(listOf(Neon.cyan.copy(0.25f), Neon.violet.copy(0.30f))))
                .border(1.5.dp, Neon.cyan, shape)
                .clickable { if (ip.isNotBlank()) onConnect(ip) },
                contentAlignment = Alignment.Center) { Mono("CONNECT", Neon.cyan, 18, FontWeight.Black, 4) }
            Spacer(Modifier.height(12.dp))
            Mono("Run server/main.py on the PC, enter the IP it prints. Same Wi-Fi.", Color(0xFF7F93A8), 11)
        }
    }
}

// ───────────────────────────── in-game HUD ─────────────────────────────

@Composable
fun HudScreen(net: NetClient, input: InputController, gyroAvailable: Boolean) {
    val st by net.state.collectAsState()
    val status by net.status.collectAsState()
    val rtt by net.rttMs.collectAsState()
    val ctx = LocalContext.current

    var gyroOn by remember { mutableStateOf(gyroAvailable) }
    var invert by remember { mutableStateOf(false) }
    var panel by remember { mutableStateOf(false) }
    var touchS by remember { mutableFloatStateOf(input.touchSens) }
    var gyroS by remember { mutableFloatStateOf(input.gyroSens) }
    LaunchedEffect(gyroOn) { input.gyroOn = gyroOn }
    LaunchedEffect(invert) { input.invertY = invert }
    LaunchedEffect(st.hurt) { if (st.hurt > 0) vibrate(ctx, 45) }

    val linked = status == NetClient.Status.LINKED
    val statusColor = when (status) {
        NetClient.Status.LINKED -> Neon.green
        NetClient.Status.CONNECTING -> Neon.amber
        else -> Neon.red
    }

    Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Neon.bg, Neon.bg2)))) {
        Canvas(Modifier.fillMaxSize()) { grid() }

        AimPad(input, Modifier.align(Alignment.CenterEnd).fillMaxHeight().fillMaxWidth(0.52f))
        Joystick(input, Modifier.align(Alignment.BottomStart).padding(start = 28.dp, bottom = 24.dp).size(150.dp))
        Radar(st, Modifier.align(Alignment.TopStart).padding(start = 190.dp, top = 12.dp).size(190.dp))
        FireButton(input, Modifier.align(Alignment.BottomEnd).padding(end = 28.dp, bottom = 24.dp).size(112.dp))
        SprintButton(st, { input.tacPulse = true },
            Modifier.align(Alignment.BottomEnd).padding(end = 48.dp, bottom = 150.dp).size(72.dp))
        ReloadButton(st, { input.reloadPulse = true },
            Modifier.align(Alignment.BottomEnd).padding(end = 156.dp, bottom = 40.dp).size(72.dp))
        Column(Modifier.align(Alignment.BottomEnd).padding(end = 150.dp, bottom = 118.dp), horizontalAlignment = Alignment.End) {
            Mono("${st.ammo}", if (st.ammo <= 5) Neon.red else Color.White, 30, FontWeight.Black)
            Mono(if (st.rel >= 0f) "RELOADING" else "/ ∞", Neon.amber, 11, FontWeight.Bold)
        }
        if (linked && st.spr > 0) {
            Box(Modifier.align(Alignment.TopCenter).padding(top = 10.dp)) {
                Mono(if (st.spr == 2) "TACTICAL SPRINT" else "SPRINT", Neon.amber, 13, FontWeight.Black, 3)
            }
        }

        // status / vitals
        Column(Modifier.align(Alignment.TopStart).padding(14.dp)) {
            Mono("● ${status.name}", statusColor, 12, FontWeight.Bold)
            Mono(if (linked) "RTT $rtt ms" else "…", Color(0xFF7F93A8), 11)
            Spacer(Modifier.height(8.dp))
            val frac = (st.hp / 100f).coerceIn(0f, 1f)
            Box(Modifier.width(150.dp).height(9.dp).clip(RoundedCornerShape(5.dp))
                .background(Neon.panel).border(1.dp, Neon.cyan.copy(0.4f), RoundedCornerShape(5.dp))) {
                Box(Modifier.fillMaxHeight().fillMaxWidth(frac)
                    .background(if (frac > 0.35f) Neon.green else Neon.red))
            }
            Spacer(Modifier.height(4.dp))
            Mono("HP ${st.hp}", Color.White, 12, FontWeight.Bold)
            Mono("SCORE ${st.score}", Neon.amber, 12, FontWeight.Bold)
            Spacer(Modifier.height(4.dp))
            Mono("${st.src} ${st.ms} ms", Neon.violet, 11)
        }

        // settings
        Column(Modifier.align(Alignment.TopEnd).padding(12.dp), horizontalAlignment = Alignment.End) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                NeonChip(if (gyroAvailable) "GYRO ${if (gyroOn) "ON" else "OFF"}" else "NO GYRO",
                    gyroOn, gyroAvailable) { gyroOn = !gyroOn }
                NeonChip("INV-Y", invert) { invert = !invert }
                NeonChip("⚙", panel) { panel = !panel }
            }
            if (panel) {
                Spacer(Modifier.height(8.dp))
                Column(Modifier.width(230.dp).clip(RoundedCornerShape(12.dp))
                    .background(Neon.panel.copy(0.92f)).border(1.dp, Neon.cyan.copy(0.5f), RoundedCornerShape(12.dp))
                    .padding(12.dp)) {
                    Mono("TOUCH SENS", Neon.cyan, 11, FontWeight.Bold)
                    Slider(touchS, { touchS = it; input.touchSens = it }, valueRange = 0.04f..0.4f,
                        colors = SliderDefaults.colors(thumbColor = Neon.cyan, activeTrackColor = Neon.cyan))
                    Mono("GYRO SENS", Neon.violet, 11, FontWeight.Bold)
                    Slider(gyroS, { gyroS = it; input.gyroSens = it }, valueRange = 0.3f..4f,
                        colors = SliderDefaults.colors(thumbColor = Neon.violet, activeTrackColor = Neon.violet))
                }
            }
        }

        if (!linked) {
            Box(Modifier.align(Alignment.TopCenter).padding(top = 10.dp).clip(RoundedCornerShape(8.dp))
                .background(Neon.panel.copy(0.9f)).border(1.dp, statusColor, RoundedCornerShape(8.dp))
                .padding(horizontal = 14.dp, vertical = 6.dp)) {
                Mono(if (status == NetClient.Status.CONNECTING) "CONNECTING…" else "SIGNAL LOST — RETRYING", statusColor, 12, FontWeight.Bold)
            }
        }
        if (linked && !st.alive) {
            Box(Modifier.fillMaxSize().background(Neon.red.copy(0.14f)), contentAlignment = Alignment.Center) {
                Text("SYSTEM FAILURE", style = TextStyle(color = Neon.red, fontSize = 34.sp, fontWeight = FontWeight.Black,
                    fontFamily = FontFamily.Monospace, letterSpacing = 4.sp, shadow = Shadow(Neon.red, blurRadius = 24f)))
            }
        }
    }
}

// ───────────────────────────── controls ─────────────────────────────

@Composable
fun Joystick(input: InputController, modifier: Modifier = Modifier) {
    var knob by remember { mutableStateOf(Offset.Zero) }   // -1..1
    var active by remember { mutableStateOf(false) }
    Canvas(modifier.pointerInput(Unit) {
        val r = size.width / 2f
        fun update(p: Offset) {
            var v = Offset((p.x - r) / r, (p.y - r) / r)
            val len = v.getDistance()
            if (len > 1f) v = Offset(v.x / len, v.y / len)
            knob = v
            input.setJoystick(v.x, -v.y)                  // screen-up = forward
        }
        fun release() { active = false; knob = Offset.Zero; input.setJoystick(0f, 0f) }
        detectDragGestures(
            onDragStart = { active = true; update(it) },
            onDragEnd = { release() },
            onDragCancel = { release() },
            onDrag = { change, _ -> change.consume(); update(change.position) },
        )
    }) {
        val r = size.minDimension / 2f
        drawCircle(Neon.panel.copy(0.75f), r, center)
        drawCircle(Neon.cyan.copy(if (active) 0.95f else 0.45f), r - 2f, center, style = Stroke(3f))
        drawCircle(Neon.cyan.copy(0.18f), r * 0.55f, center, style = Stroke(1.5f))
        drawLine(Neon.cyan.copy(0.18f), Offset(center.x - r, center.y), Offset(center.x + r, center.y))
        drawLine(Neon.cyan.copy(0.18f), Offset(center.x, center.y - r), Offset(center.x, center.y + r))
        val k = Offset(center.x + knob.x * r * 0.62f, center.y + knob.y * r * 0.62f)
        drawCircle(Brush.radialGradient(listOf(Neon.cyan, Neon.violet.copy(0.75f)), center = k, radius = r * 0.34f), r * 0.34f, k)
    }
}

@Composable
fun AimPad(input: InputController, modifier: Modifier = Modifier) {
    Box(modifier.pointerInput(Unit) {
        detectDragGestures(onDrag = { change, drag -> change.consume(); input.addTouch(drag.x, drag.y) })
    }, contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize().padding(10.dp)) {
            val len = 28f
            val w = size.width; val h = size.height
            val col = Neon.violet.copy(0.5f)
            val s = Stroke(3f)
            // corner brackets
            for ((cx, cy, sx, sy) in listOf(listOf(0f, 0f, 1f, 1f), listOf(w, 0f, -1f, 1f), listOf(0f, h, 1f, -1f), listOf(w, h, -1f, -1f))) {
                drawLine(col, Offset(cx, cy), Offset(cx + sx * len, cy), 3f)
                drawLine(col, Offset(cx, cy), Offset(cx, cy + sy * len), 3f)
            }
            drawCircle(Neon.violet.copy(0.10f), 36f, center, style = s)
        }
        Mono("TOUCH AIM", Neon.violet.copy(0.35f), 12, spacing = 6)
    }
}

@Composable
fun FireButton(input: InputController, modifier: Modifier = Modifier) {
    var down by remember { mutableStateOf(false) }
    Box(modifier.clip(CircleShape)
        .background(Neon.red.copy(if (down) 0.65f else 0.22f), CircleShape)
        .border(3.dp, Neon.red, CircleShape)
        .pointerInput(Unit) {
            detectTapGestures(onPress = {
                down = true; input.fire = true
                try { tryAwaitRelease() } finally { down = false; input.fire = false }
            })
        }, contentAlignment = Alignment.Center) {
        Mono("FIRE", Color.White, 18, FontWeight.Black, 3)
    }
}

// ───────────────────────────── tactical radar ─────────────────────────────

@Composable
fun Radar(st: GameState, modifier: Modifier = Modifier) {
    val t = rememberInfiniteTransition(label = "sweep")
    val sweep by t.animateFloat(0f, 360f, infiniteRepeatable(tween(2600, easing = LinearEasing), RepeatMode.Restart), label = "angle")
    Canvas(modifier) {
        val c = center
        val r = size.minDimension / 2f
        drawCircle(Color(0xCC050A18), r, c)
        for (i in 1..3) drawCircle(Neon.cyan.copy(0.22f), r * i / 3f, c, style = Stroke(1.2f))
        drawLine(Neon.cyan.copy(0.15f), Offset(c.x - r, c.y), Offset(c.x + r, c.y))
        drawLine(Neon.cyan.copy(0.15f), Offset(c.x, c.y - r), Offset(c.x, c.y + r))
        // field of view wedge (player always faces up)
        drawArc(Neon.cyan.copy(0.10f), -135f, 90f, true, Offset(c.x - r, c.y - r), Size(2 * r, 2 * r))
        // sweep with fading trail
        for (k in 0..10) {
            val a = Math.toRadians((sweep - k * 3f).toDouble())
            drawLine(Neon.cyan.copy((0.55f - k * 0.05f).coerceAtLeast(0f)), c,
                Offset(c.x + r * cos(a).toFloat(), c.y + r * sin(a).toFloat()), 3f)
        }
        // contacts: world position -> relative to player heading
        val hr = Math.toRadians(st.h.toDouble())
        val ch = cos(hr).toFloat(); val sh = sin(hr).toFloat()
        val scale = r / RADAR_RANGE
        for (ct in st.contacts) {
            val dx = ct.x - st.px; val dy = ct.y - st.py
            val right = dx * ch + dy * sh
            val fwd = -dx * sh + dy * ch
            var sx = right * scale; var sy = -fwd * scale
            val d = hypot(sx, sy)
            if (d > r - 6f) { sx *= (r - 6f) / d; sy *= (r - 6f) / d }
            val p = Offset(c.x + sx, c.y + sy)
            val fade = (1f - ct.age / CONTACT_TTL).coerceIn(0.15f, 1f)
            drawCircle(Neon.red.copy(0.25f * fade), 13f, p)
            drawCircle(Neon.red.copy(fade), 5f, p)
            drawCircle(Neon.red.copy(fade), 9f, p, style = Stroke(1.5f))
        }
        // player
        val tri = Path().apply { moveTo(c.x, c.y - 9f); lineTo(c.x - 6f, c.y + 7f); lineTo(c.x + 6f, c.y + 7f); close() }
        drawPath(tri, Neon.cyan)
        drawCircle(Neon.cyan.copy(0.65f), r - 1.5f, c, style = Stroke(2.5f))
    }
}

// ───────────────────────────── sprint / reload buttons ─────────────────────────────

@Composable
fun SprintButton(st: GameState, onTap: () -> Unit, modifier: Modifier = Modifier) {
    val active = st.spr == 2
    Box(modifier.pointerInput(Unit) { detectTapGestures(onPress = { onTap() }) }, contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val col = if (active) Neon.amber else Neon.cyan
            drawCircle(Neon.panel.copy(0.85f), size.minDimension / 2f, center)
            drawArc(col, -90f, 360f * st.stam.coerceIn(0f, 1f), false, Offset(4f, 4f),
                Size(size.width - 8f, size.height - 8f), style = Stroke(5f))          // stamina ring
        }
        Mono("TAC", if (active) Neon.amber else Color.White, 13, FontWeight.Black, 1)
    }
}

@Composable
fun ReloadButton(st: GameState, onTap: () -> Unit, modifier: Modifier = Modifier) {
    val reloading = st.rel >= 0f
    Box(modifier.pointerInput(Unit) { detectTapGestures(onPress = { onTap() }) }, contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            drawCircle(Neon.panel.copy(0.85f), size.minDimension / 2f, center)
            drawCircle(Neon.violet.copy(0.6f), size.minDimension / 2f - 3f, center, style = Stroke(2f))
            if (reloading) drawArc(Neon.amber, -90f, 360f * st.rel.coerceIn(0f, 1f), false, Offset(4f, 4f),
                Size(size.width - 8f, size.height - 8f), style = Stroke(5f))          // reload progress
        }
        Mono("R", if (reloading) Neon.amber else Color.White, 20, FontWeight.Black)
    }
}
