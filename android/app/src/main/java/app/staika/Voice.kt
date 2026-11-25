package app.staika

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.NoiseSuppressor
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONObject

/** Микрофон: PCM 16 бит, 16 кГц, моно, кадры по 80 мс. */
class PcmRecorder(private val onChunk: (ByteArray) -> Unit) {
    @Volatile private var running = false
    private var rec: AudioRecord? = null
    private var thread: Thread? = null
    @Volatile var muted = false

    @SuppressLint("MissingPermission")
    fun start(): Boolean {
        val chunk = 2560
        val min = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val r = try {
            AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION, 16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(min, chunk * 4))
        } catch (e: Exception) { return false }
        if (r.state != AudioRecord.STATE_INITIALIZED) { r.release(); return false }
        if (AcousticEchoCanceler.isAvailable()) try { AcousticEchoCanceler.create(r.audioSessionId)?.enabled = true } catch (_: Exception) {}
        if (NoiseSuppressor.isAvailable()) try { NoiseSuppressor.create(r.audioSessionId)?.enabled = true } catch (_: Exception) {}
        rec = r; running = true; r.startRecording()
        thread = Thread {
            val buf = ByteArray(chunk)
            while (running) {
                var off = 0
                while (running && off < chunk) { val n = r.read(buf, off, chunk - off); if (n <= 0) break; off += n }
                if (running && off == chunk) onChunk(if (muted) ByteArray(chunk) else buf.copyOf())
            }
        }.also { it.isDaemon = true; it.start() }
        return true
    }

    fun stop() {
        running = false
        try { rec?.stop() } catch (_: Exception) {}
        thread?.join(300)
        try { rec?.release() } catch (_: Exception) {}
        rec = null
    }
}

/** Воспроизведение ответа агента: PCM 16 бит, 24 кГц, моно. */
class PcmPlayer {
    private val track: AudioTrack = AudioTrack.Builder()
        .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
        .setAudioFormat(AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT).setSampleRate(24000).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
        .setBufferSizeInBytes(maxOf(AudioTrack.getMinBufferSize(24000, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT), 48000))
        .setTransferMode(AudioTrack.MODE_STREAM).build().also { it.play() }

    fun write(b: ByteArray) { try { track.write(b, 0, b.size) } catch (_: Exception) {} }
    /** Перебивание: пользователь заговорил, сбрасываем недопроигранное. */
    fun flush() { try { track.pause(); track.flush(); track.play() } catch (_: Exception) {} }
    fun release() { try { track.stop(); track.release() } catch (_: Exception) {} }
}

private fun voiceError(reason: String?): String = when (reason) {
    "voice_not_available" -> "Голос недоступен: добавьте ключ Deepgram в настройках или попросите владельца открыть доступ"
    "agent_not_found" -> "Агент не найден"
    "upstream_unavailable" -> "Сервис голоса сейчас недоступен"
    else -> "Соединение прервано"
}

/** Текст ошибки при обрыве соединения: если сервер ответил HTTP-кодом, показываем его, а не «нет связи». */
private fun failureText(r: Response?): String = when (r?.code) {
    null -> "Нет связи с сервером"
    401 -> "Сессия истекла, войдите заново"
    404 -> "Сервер не поддерживает голос: обновите сервер"
    else -> "Сервер отклонил соединение (${r.code})"
}

/** Диктовка: поток с микрофона через сервер в Deepgram Nova-3, текст приходит по мере речи. */
class Dictation(private val onText: (String) -> Unit, private val onEnd: (error: String?) -> Unit) {
    private var ws: WebSocket? = null
    private var rec: PcmRecorder? = null
    private var committed = ""
    private var interim = ""
    private var ended = false
    var active by mutableStateOf(false)

    fun start() {
        active = true
        Repo.scope.launch {
            val token = Api.freshToken()
            if (token == null) { finish("Нужно войти"); return@launch }
            val url = Api.wsUrl("/ws/dictate?token=$token&lang=${Prefs.voiceLang}")
            ws = Api.http.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    val r = PcmRecorder { webSocket.send(it.toByteString()) }
                    if (!r.start()) { webSocket.close(1000, null); Repo.scope.launch { finish("Не удалось включить микрофон") }; return }
                    rec = r
                }
                override fun onMessage(webSocket: WebSocket, text: String) {
                    val j = try { JSONObject(text) } catch (e: Exception) { return }
                    if (j.optString("type") != "Results") return
                    val t = j.optJSONObject("channel")?.optJSONArray("alternatives")?.optJSONObject(0)?.optString("transcript").orEmpty()
                    Repo.scope.launch {
                        if (j.optBoolean("is_final")) { if (t.isNotBlank()) committed = (committed + " " + t).trim(); interim = "" } else interim = t
                        onText((committed + " " + interim).trim())
                    }
                }
                // Сервер закрывает соединение с кодом и причиной (например, нет ключа Deepgram). Без onClosing эта причина терялась.
                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    webSocket.close(1000, null)
                    Repo.scope.launch { finish(if (code == 1000 || code == 1005) null else voiceError(reason)) }
                }
                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    Repo.scope.launch { finish(if (code == 1000 || code == 1005) null else voiceError(reason)) }
                }
                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    Repo.scope.launch { finish(failureText(response)) }
                }
            })
        }
    }

    /** Остановить запись; сервер дошлёт последние слова и закроет соединение. */
    fun stop() {
        rec?.stop(); rec = null
        ws?.send("""{"type":"CloseStream"}""")
        Repo.scope.launch { delay(2500); ws?.close(1000, null); finish(null) }
    }

    private fun finish(error: String?) {
        if (ended) return
        ended = true; active = false
        rec?.stop(); rec = null
        onEnd(error)
    }
}

/** Голосовой звонок: микрофон -> сервер -> Deepgram Voice Agent -> речь агента. */
class CallSession(private val ctx: Context, private val agentId: String) {
    enum class State { Connecting, Live, Ended }
    var state by mutableStateOf(State.Connecting)
    var error by mutableStateOf<String?>(null)
    var muted by mutableStateOf(false)
    var speaker by mutableStateOf(true)
    var seconds by mutableStateOf(0)
    var agentSpeaking by mutableStateOf(false)
    val lines = mutableStateListOf<Pair<String, String>>()   // (кто, текст)

    private var ws: WebSocket? = null
    private var rec: PcmRecorder? = null
    private var player: PcmPlayer? = null
    private val audio = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    fun start() {
        audio.mode = AudioManager.MODE_IN_COMMUNICATION
        audio.isSpeakerphoneOn = true
        Repo.scope.launch {
            val token = Api.freshToken() ?: run { fail("Нужно войти"); return@launch }
            val url = Api.wsUrl("/ws/call?token=$token&agentId=$agentId&lang=${Prefs.voiceLang}&model=" + java.net.URLEncoder.encode(Prefs.voiceModel, "UTF-8"))
            ws = Api.http.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    Repo.scope.launch {
                        player = PcmPlayer()
                        val r = PcmRecorder { webSocket.send(it.toByteString()) }
                        if (!r.start()) { fail("Не удалось включить микрофон"); return@launch }
                        rec = r; state = State.Live
                        while (state == State.Live) { delay(1000); seconds++ }
                    }
                }
                override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                    agentSpeaking = true
                    player?.write(bytes.toByteArray())
                }
                override fun onMessage(webSocket: WebSocket, text: String) {
                    val j = try { JSONObject(text) } catch (e: Exception) { return }
                    Repo.scope.launch {
                        when (j.optString("type")) {
                            "ConversationText" -> lines.add((if (j.optString("role") == "user") "Вы" else "Агент") to j.optString("content"))
                            "UserStartedSpeaking" -> { player?.flush(); agentSpeaking = false }
                            "AgentAudioDone" -> agentSpeaking = false
                            "Error" -> fail(j.optString("description", "Ошибка голоса"))
                        }
                    }
                }
                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    webSocket.close(1000, null)
                    Repo.scope.launch { if (state != State.Ended) { if (code != 1000 && code != 1005) fail(voiceError(reason)) else end() } }
                }
                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    Repo.scope.launch { if (state != State.Ended) { if (code != 1000 && code != 1005) fail(voiceError(reason)) else end() } }
                }
                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) { Repo.scope.launch { fail(failureText(response)) } }
            })
        }
    }

    fun mute(v: Boolean) { muted = v; rec?.muted = v }
    fun useSpeaker(v: Boolean) { speaker = v; audio.isSpeakerphoneOn = v }

    private fun fail(msg: String) { error = msg; end() }

    fun end() {
        if (state == State.Ended) return
        state = State.Ended
        rec?.stop(); rec = null
        player?.release(); player = null
        try { ws?.close(1000, null) } catch (_: Exception) {}
        audio.mode = AudioManager.MODE_NORMAL
        audio.isSpeakerphoneOn = false
        // расшифровка сохраняется сервером в чат, подтянем её
        Repo.scope.launch { delay(800); Repo.loadMessages(agentId, force = true) }
    }
}
