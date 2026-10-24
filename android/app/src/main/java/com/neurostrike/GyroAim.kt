package com.neurostrike

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.view.Surface
import kotlin.math.abs

/**
 * Turns gyroscope angular velocity into relative aim deltas.
 * Axes are remapped from device space to screen space so it works in either landscape.
 * If an axis feels backwards on your phone, flip the sign in the two marked lines.
 */
class GyroAim(
    context: Context,
    private val input: InputController,
    private val rotation: () -> Int,
) : SensorEventListener {
    private val sm = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val gyro: Sensor? = sm.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
    private var last = 0L

    val available get() = gyro != null

    fun start() { last = 0L; gyro?.let { sm.registerListener(this, it, 5000) } }   // 5000 us = 200 Hz
    fun stop() = sm.unregisterListener(this)

    override fun onSensorChanged(e: SensorEvent) {
        if (last == 0L || !input.gyroOn) { last = e.timestamp; return }
        val dt = (e.timestamp - last) / 1e9f
        last = e.timestamp
        val gx = e.values[0]
        val gy = e.values[1]
        // angular velocity about the screen's right axis (wx) and up axis (wy), rad/s
        val (wx, wy) = when (rotation()) {
            Surface.ROTATION_90 -> gy to -gx
            Surface.ROTATION_270 -> -gy to gx
            Surface.ROTATION_180 -> -gx to -gy
            else -> gx to gy
        }
        if (abs(wx) < 0.01f && abs(wy) < 0.01f) return           // dead-zone against drift
        val deg = 57.29578f
        val dYaw = -wy * dt * deg                                // FLIP SIGN if yaw is inverted
        val dPitch = wx * dt * deg                               // FLIP SIGN if pitch is inverted
        input.addGyro(dYaw, dPitch)
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
}
