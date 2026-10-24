package com.neurostrike

import org.json.JSONObject

/**
 * Collects joystick / touch-aim / gyro-aim / fire. Aim sources only ever ADD relative
 * deltas into one accumulator that is flushed on every network tick, so touch and gyro
 * never fight each other.
 */
class InputController {
    private val lock = Any()
    private var jx = 0f
    private var jy = 0f
    private var yaw = 0f
    private var pitch = 0f

    @Volatile var fire = false
    @Volatile var reloadPulse = false   // one-shot, cleared once sent
    @Volatile var tacPulse = false
    @Volatile var gyroOn = true
    @Volatile var invertY = false
    @Volatile var touchSens = 0.12f   // degrees per pixel
    @Volatile var gyroSens = 1.6f     // multiplier on real rotation

    fun setJoystick(x: Float, y: Float) = synchronized(lock) { jx = x; jy = y }

    /** dx/dy in pixels. Drag right -> turn right, drag up -> look up. */
    fun addTouch(dx: Float, dy: Float) = synchronized(lock) {
        yaw += dx * touchSens
        pitch += -dy * touchSens * if (invertY) -1f else 1f
    }

    /** Degrees already integrated from the gyro. */
    fun addGyro(dYaw: Float, dPitch: Float) = synchronized(lock) {
        yaw += dYaw * gyroSens
        pitch += dPitch * gyroSens * if (invertY) -1f else 1f
    }

    fun snapshot(): String = synchronized(lock) {
        val o = JSONObject()
            .put("t", "input").put("jx", jx.toDouble()).put("jy", jy.toDouble())
            .put("dyaw", yaw.toDouble()).put("dpitch", pitch.toDouble()).put("fire", fire)
            .put("reload", reloadPulse).put("tac", tacPulse)
        yaw = 0f; pitch = 0f; reloadPulse = false; tacPulse = false
        o.toString()
    }
}
