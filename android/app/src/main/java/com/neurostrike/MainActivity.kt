package com.neurostrike

import android.content.Context
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

class MainActivity : ComponentActivity() {
    private val input = InputController()
    private val net = NetClient(input)
    private lateinit var gyro: GyroAim
    private var wifiLock: WifiManager.WifiLock? = null

    @Suppress("DEPRECATION")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
        // Keep the Wi-Fi radio out of power-save while playing: the biggest source of random 50-200 ms lag spikes
        val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        val mode = if (Build.VERSION.SDK_INT >= 29) WifiManager.WIFI_MODE_FULL_LOW_LATENCY else WifiManager.WIFI_MODE_FULL_HIGH_PERF
        wifiLock = wm.createWifiLock(mode, "neurostrike").apply { setReferenceCounted(false) }
        gyro = GyroAim(this, input) { windowManager.defaultDisplay.rotation }
        setContent { NeuroStrikeApp(net, input, gyro.available) }
    }

    override fun onResume() { super.onResume(); gyro.start(); wifiLock?.acquire() }
    override fun onPause() { super.onPause(); gyro.stop(); wifiLock?.takeIf { it.isHeld }?.release() }
    override fun onDestroy() { super.onDestroy(); net.disconnect() }
}
