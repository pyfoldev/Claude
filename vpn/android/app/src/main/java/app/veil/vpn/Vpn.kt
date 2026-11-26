package app.veil.vpn

import android.content.Context
import android.util.Base64
import com.wireguard.android.backend.GoBackend
import com.wireguard.android.backend.Tunnel
import com.wireguard.config.Config
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import java.io.BufferedReader
import java.io.StringReader

/** Принимает vpn://<base64> ссылку или обычный WireGuard .conf текст. */
fun parseConfig(input: String): Config {
    val t = input.trim()
    val raw = if (t.startsWith("vpn://")) {
        String(Base64.decode(t.removePrefix("vpn://"), Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING))
    } else t
    return Config.parse(BufferedReader(StringReader(raw)))
}

object Vpn {
    private lateinit var backend: GoBackend
    lateinit var store: Store
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    val state = MutableStateFlow(Tunnel.State.DOWN)
    val busy = MutableStateFlow(false)
    val error = MutableStateFlow<String?>(null)
    val rx = MutableStateFlow(0L)
    val tx = MutableStateFlow(0L)
    val since = MutableStateFlow(0L)
    val endpoint = MutableStateFlow<String?>(null)

    private val tunnel = object : Tunnel {
        override fun getName() = "veil"
        override fun onStateChange(newState: Tunnel.State) {
            state.value = newState
            since.value = if (newState == Tunnel.State.UP) System.currentTimeMillis() else 0L
        }
    }

    fun init(ctx: Context) {
        if (::backend.isInitialized) return
        val app = ctx.applicationContext
        backend = GoBackend(app)
        store = Store(app)
        refreshEndpoint()
        scope.launch {
            while (true) {
                delay(1000)
                if (state.value == Tunnel.State.UP) runCatching {
                    val s = backend.getStatistics(tunnel)
                    rx.value = s.totalRx(); tx.value = s.totalTx()
                }
            }
        }
    }

    private fun refreshEndpoint() {
        endpoint.value = store.conf?.let {
            runCatching { parseConfig(it).peers.firstOrNull()?.endpoint?.orElse(null)?.toString() }.getOrNull()
        }
    }

    fun save(text: String) {
        val cfg = parseConfig(text)
        store.conf = cfg.toWgQuickString()
        error.value = null
        refreshEndpoint()
    }

    fun connect() {
        val conf = store.conf ?: run { error.value = "Сначала добавьте сервер"; return }
        scope.launch {
            busy.value = true; error.value = null
            try {
                backend.setState(tunnel, Tunnel.State.UP, parseConfig(conf))
                rx.value = 0; tx.value = 0
            } catch (e: Exception) {
                error.value = e.message ?: "Не удалось подключиться"
            } finally { busy.value = false }
        }
    }

    fun disconnect() {
        scope.launch {
            busy.value = true
            try { backend.setState(tunnel, Tunnel.State.DOWN, null) }
            catch (e: Exception) { error.value = e.message } finally { busy.value = false }
        }
    }
}
