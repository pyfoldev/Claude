package openagent.app.com

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import kotlinx.coroutines.CompletableDeferred
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONObject

/**
 * Голосовой режим через Deepgram Voice Agent (сервер: /api/voice-agent): распознавание + Claude Haiku 4.5 + голос «Владимир» в одном потоке.
 * Микрофон (PCM 16 кГц) уходит на сервер, оттуда приходит готовый звук (PCM 24 кГц) — мы пишем его прямо в AudioTrack.
 * Перебивание: сервер присылает «flush» в момент, когда пользователь начал говорить, — очередь воспроизведения сбрасывается.
 */
class AgentVoiceSession(
    private val request: Request,
    private val client: OkHttpClient,
    private val onState: (VoiceState) -> Unit,
    private val onUser: (String) -> Unit,
    private val onAgent: (String) -> Unit,
    private val onLevel: (Float) -> Unit,
    private val onPhone: (id: String, args: JSONObject) -> Unit,
    private val onStatus: (String) -> Unit,
) {
    @Volatile var error: String? = null; private set
    @Volatile var ready = false; private set
    @Volatile var closed = false; private set
    @Volatile private var muted = false
    private val finished = CompletableDeferred<Unit>()
    private var ws: WebSocket? = null
    private var rec: AudioRecord? = null
    private var track: AudioTrack? = null
    @Volatile private var running = false
    private var thread: Thread? = null
    private val outLock = Any()

    @android.annotation.SuppressLint("MissingPermission")
    fun start(): Boolean {
        val rate = 16000
        val min = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (min <= 0) return false
        val r = runCatching { AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION, rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(min, 3200 * 4)) }.getOrNull() ?: return false
        if (r.state != AudioRecord.STATE_INITIALIZED) { r.release(); return false }
        // эхоподавление: иначе агент слышит сам себя из динамика и «перебивает» себя
        runCatching { if (android.media.audiofx.AcousticEchoCanceler.isAvailable()) android.media.audiofx.AcousticEchoCanceler.create(r.audioSessionId)?.enabled = true }
        runCatching { if (android.media.audiofx.NoiseSuppressor.isAvailable()) android.media.audiofx.NoiseSuppressor.create(r.audioSessionId)?.enabled = true }
        rec = r
        val outRate = 24000
        val tmin = AudioTrack.getMinBufferSize(outRate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        track = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setAudioFormat(AudioFormat.Builder().setSampleRate(outRate).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
            .setBufferSizeInBytes(maxOf(tmin, outRate / 4 * 2)).setTransferMode(AudioTrack.MODE_STREAM).build().also { it.play() }
        ws = client.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                val t = track ?: return
                val b = bytes.toByteArray()
                synchronized(outLock) { if (!closed) runCatching { t.write(b, 0, b.size) } }   // блокирующая запись — естественный контроль скорости
            }
            override fun onMessage(webSocket: WebSocket, text: String) {
                val o = runCatching { JSONObject(text) }.getOrNull() ?: return
                when (o.optString("t")) {
                    "ready" -> { ready = true; onState(VoiceState.Listening) }
                    "state" -> onState(when (o.optString("state")) { "thinking" -> VoiceState.Thinking; "speaking" -> VoiceState.Speaking; else -> VoiceState.Listening })
                    "user" -> onUser(o.optString("text"))
                    "agent" -> onAgent(o.optString("text"))
                    "flush" -> flush()
                    "tool" -> onStatus(o.optString("name"))
                    "status" -> onStatus(o.optString("text"))
                    "phone" -> onPhone(o.optString("id"), o.optJSONObject("args") ?: JSONObject())
                    "error" -> { error = o.optString("message").ifBlank { "Ошибка голосового агента" } }
                    "closed" -> finish()
                }
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) { if (!closed) error = error ?: "Нет связи с сервером"; finish() }
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { finish() }
        })
        running = true
        r.startRecording()
        thread = Thread {
            val buf = ShortArray(1600)                      // 100 мс
            val bytes = ByteArray(3200)
            var smooth = 0f
            while (running) {
                val n = r.read(buf, 0, buf.size)
                if (n <= 0) { if (n < 0) break else continue }
                var sum = 0.0
                for (i in 0 until n) { val v = buf[i].toInt(); sum += (v * v).toDouble(); bytes[2 * i] = (v and 0xff).toByte(); bytes[2 * i + 1] = ((v shr 8) and 0xff).toByte() }
                smooth += ((Math.sqrt(sum / n).toFloat() / 3500f).coerceIn(0f, 1f) - smooth) * 0.6f
                onLevel(if (muted) 0f else smooth)
                if (!muted) ws?.send(ByteString.of(*bytes.copyOf(n * 2)))
            }
        }.also { it.isDaemon = true; it.start() }
        return true
    }

    private fun flush() { track?.let { t -> synchronized(outLock) { runCatching { t.pause(); t.flush(); t.play() } } } }
    fun interrupt() { flush(); runCatching { ws?.send("{\"t\":\"interrupt\"}") } }
    fun sendText(s: String) { runCatching { ws?.send(JSONObject().put("t", "text").put("text", s).toString()) } }
    fun setMuted(m: Boolean) { muted = m; runCatching { ws?.send(JSONObject().put("t", "mute").put("on", m).toString()) } }
    fun phoneResult(id: String, text: String) { runCatching { ws?.send(JSONObject().put("t", "phone_result").put("id", id).put("text", text).toString()) } }

    private fun finish() { closed = true; running = false; finished.complete(Unit) }
    suspend fun await() = finished.await()

    fun cancel() {
        closed = true; running = false
        runCatching { ws?.send("{\"t\":\"end\"}") }
        runCatching { thread?.join(300) }
        runCatching { rec?.stop() }; runCatching { rec?.release() }; rec = null
        synchronized(outLock) { runCatching { track?.pause(); track?.flush(); track?.release() }; track = null }
        runCatching { ws?.close(1000, null) }; ws = null
        finished.complete(Unit)
    }
}
