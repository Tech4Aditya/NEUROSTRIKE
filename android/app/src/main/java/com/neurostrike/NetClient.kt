package com.neurostrike

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import okhttp3.*
import org.json.JSONObject
import java.net.InetAddress
import java.net.Socket
import java.util.concurrent.TimeUnit
import javax.net.SocketFactory

/** Disables Nagle's algorithm: tiny aim packets must be sent immediately, not batched (cuts latency spikes). */
private class NoDelayFactory : SocketFactory() {
    private val d = SocketFactory.getDefault()
    private fun cfg(s: Socket) = s.also { it.tcpNoDelay = true }
    override fun createSocket() = cfg(d.createSocket())
    override fun createSocket(h: String, p: Int) = cfg(d.createSocket(h, p))
    override fun createSocket(h: String, p: Int, la: InetAddress, lp: Int) = cfg(d.createSocket(h, p, la, lp))
    override fun createSocket(a: InetAddress, p: Int) = cfg(d.createSocket(a, p))
    override fun createSocket(a: InetAddress, p: Int, la: InetAddress, lp: Int) = cfg(d.createSocket(a, p, la, lp))
}

class NetClient(private val input: InputController) {
    enum class Status { IDLE, CONNECTING, LINKED, LOST }

    val status = MutableStateFlow(Status.IDLE)
    val state = MutableStateFlow(GameState())
    val rttMs = MutableStateFlow(0)

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val http = OkHttpClient.Builder().socketFactory(NoDelayFactory()).readTimeout(0, TimeUnit.MILLISECONDS).build()
    private var job: Job? = null

    fun connect(host: String) {
        job?.cancel()
        job = scope.launch {
            var backoff = 500L
            while (isActive) {
                status.value = Status.CONNECTING
                session(host.trim())
                if (!isActive) break
                status.value = Status.LOST
                delay(backoff)
                backoff = minOf(backoff * 2, 4000L)
            }
        }
    }

    fun disconnect() {
        job?.cancel()
        status.value = Status.IDLE
    }

    private suspend fun session(host: String) = coroutineScope {
        val done = CompletableDeferred<Unit>()
        val url = if (":" in host) "ws://$host" else "ws://$host:8765"
        val sock = http.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) { status.value = Status.LINKED }
            override fun onMessage(webSocket: WebSocket, text: String) {
                parseState(text)?.let { state.value = it; return }
                try {
                    val o = JSONObject(text)
                    if (o.optString("t") == "pong")
                        rttMs.value = ((System.nanoTime() - o.getLong("ts")) / 1_000_000).toInt()
                } catch (_: Exception) {}
            }
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { done.complete(Unit) }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) { done.complete(Unit) }
        })
        val sender = launch {
            var tick = 0
            while (isActive) {
                if (status.value == Status.LINKED) {
                    sock.send(input.snapshot())
                    if (++tick % 125 == 0)
                        sock.send(JSONObject().put("t", "ping").put("ts", System.nanoTime()).toString())
                }
                delay(8)                     // 125 Hz
            }
        }
        try { done.await() } finally { sender.cancel(); sock.cancel() }
    }
}
