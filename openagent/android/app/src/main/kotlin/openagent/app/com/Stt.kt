package openagent.app.com

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognitionService
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Выбор службы распознавания: Google (быстрая, потоковая). Свою (OpenAgent) исключаем, чтобы не зациклиться. */
object RecognizerPicker {
    fun pick(ctx: Context): ComponentName? {
        val list = ctx.packageManager.queryIntentServices(Intent(RecognitionService.SERVICE_INTERFACE), 0).filter { it.serviceInfo.packageName != ctx.packageName }
        val s = (list.firstOrNull { it.serviceInfo.packageName == "com.google.android.googlequicksearchbox" } ?: list.firstOrNull())?.serviceInfo ?: return null
        return ComponentName(s.packageName, s.name)
    }
}

/** Быстрое распознавание речи на устройстве: результат приходит сразу после паузы, без загрузки файла на сервер. Вызывать из главного потока. */
class FastStt(private val ctx: Context) {
    class Unavailable(msg: String) : Exception(msg)

    fun available() = RecognizerPicker.pick(ctx) != null

    private fun tag(lang: String) = when (lang) { "ru" -> "ru-RU"; "en" -> "en-US"; "uk" -> "uk-UA"; "de" -> "de-DE"; else -> "ru-RU" }

    /** Возвращает текст, "" если речи не было, бросает Unavailable при сбое службы (тогда нужен запасной путь). */
    suspend fun listen(lang: String, onLevel: (Float) -> Unit, onPartial: (String) -> Unit, offline: Boolean = false): String = suspendCancellableCoroutine { c ->
        val comp = RecognizerPicker.pick(ctx)
        if (comp == null) { c.resumeWithException(Unavailable("Нет службы распознавания речи")); return@suspendCancellableCoroutine }
        val sr = runCatching { SpeechRecognizer.createSpeechRecognizer(ctx, comp) }.getOrNull()
        if (sr == null) { c.resumeWithException(Unavailable("Не удалось создать распознаватель")); return@suspendCancellableCoroutine }
        var done = false; var ready = false
        fun finish(r: Result<String>) { if (done) return; done = true; runCatching { sr.destroy() }; if (c.isActive) { r.fold({ c.resume(it) }, { c.resumeWithException(it) }) } }
        sr.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(p: Bundle?) { ready = true }
            override fun onBeginningOfSpeech() { ready = true }
            override fun onRmsChanged(rms: Float) { ready = true; onLevel(((rms + 2f) / 12f).coerceIn(0f, 1f)) }
            override fun onBufferReceived(b: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(t: Int, p: Bundle?) {}
            override fun onPartialResults(b: Bundle?) { b?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.let(onPartial) }
            override fun onResults(b: Bundle?) { finish(Result.success(b?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty())) }
            override fun onError(e: Int) {
                when (e) {
                    SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> finish(Result.success(""))
                    SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> finish(Result.success(""))
                    else -> finish(Result.failure(Unavailable("Распознавание: ошибка $e")))
                }
            }
        })
        val i = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE, tag(lang))
            .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            .putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            .putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, offline)
            .putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, ctx.packageName)
            .putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 650L)
            .putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 450L)
        c.invokeOnCancellation { Handler(Looper.getMainLooper()).post { runCatching { sr.cancel() }; runCatching { sr.destroy() } } }
        runCatching { sr.startListening(i) }.onFailure { finish(Result.failure(Unavailable(it.message ?: "старт не удался"))) }
        // служба не ответила за 4 с (нет Google-сервисов/разрешения) — отдаём управление запасному пути
        Handler(Looper.getMainLooper()).postDelayed({ if (!ready && !done) finish(Result.failure(Unavailable("служба распознавания не отвечает"))) }, 4000)
    }
}

/**
 * Системная служба распознавания OpenAgent (нужна описанию ассистента). Чтобы не ломать диктовку в других приложениях,
 * она просто передаёт запросы настоящему распознавателю (Google).
 */
class OaRecognitionService : RecognitionService() {
    private var sr: SpeechRecognizer? = null
    override fun onStartListening(intent: Intent?, cb: Callback?) {
        val comp = RecognizerPicker.pick(this)
        val r = comp?.let { runCatching { SpeechRecognizer.createSpeechRecognizer(this, it) }.getOrNull() }
        if (r == null || cb == null) { runCatching { cb?.error(SpeechRecognizer.ERROR_CLIENT) }; return }
        sr?.destroy(); sr = r
        r.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(p: Bundle?) { runCatching { cb.readyForSpeech(p ?: Bundle()) } }
            override fun onBeginningOfSpeech() { runCatching { cb.beginningOfSpeech() } }
            override fun onRmsChanged(v: Float) { runCatching { cb.rmsChanged(v) } }
            override fun onBufferReceived(b: ByteArray?) { runCatching { cb.bufferReceived(b ?: ByteArray(0)) } }
            override fun onEndOfSpeech() { runCatching { cb.endOfSpeech() } }
            override fun onError(e: Int) { runCatching { cb.error(e) } }
            override fun onResults(b: Bundle?) { runCatching { cb.results(b ?: Bundle()) } }
            override fun onPartialResults(b: Bundle?) { runCatching { cb.partialResults(b ?: Bundle()) } }
            override fun onEvent(t: Int, p: Bundle?) {}
        })
        r.startListening(intent ?: Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH))
    }
    override fun onCancel(cb: Callback?) { runCatching { sr?.cancel() } }
    override fun onStopListening(cb: Callback?) { runCatching { sr?.stopListening() } }
    override fun onDestroy() { runCatching { sr?.destroy() }; sr = null; super.onDestroy() }
}

/**
 * Потоковое распознавание речи Deepgram через наш сервер (WebSocket /api/stt-stream).
 * Микрофон (PCM 16 кГц) уходит на сервер по мере речи, текст приходит сразу, итог — через долю секунды после конца фразы.
 */
class RtSession(
    private val ctx: Context, private val request: okhttp3.Request, private val client: okhttp3.OkHttpClient,
    private val onLevel: (Float) -> Unit, private val onPartial: (String) -> Unit,
) {
    @Volatile var level = 0f; private set
    @Volatile var error: String? = null; private set
    @Volatile var turnEnded = false; private set
    @Volatile var eager = false; private set
    @Volatile var model = ""; private set
    private val text = StringBuilder()
    @Volatile private var interim = ""
    private val pcm = java.io.ByteArrayOutputStream()
    private val done = kotlinx.coroutines.CompletableDeferred<String>()
    private var ws: okhttp3.WebSocket? = null
    private var rec: android.media.AudioRecord? = null
    @Volatile private var running = false
    @Volatile private var closed = false
    private var thread: Thread? = null

    @android.annotation.SuppressLint("MissingPermission")
    fun start(): Boolean {
        val rate = 16000
        val min = android.media.AudioRecord.getMinBufferSize(rate, android.media.AudioFormat.CHANNEL_IN_MONO, android.media.AudioFormat.ENCODING_PCM_16BIT)
        if (min <= 0) return false
        val r = runCatching { android.media.AudioRecord(android.media.MediaRecorder.AudioSource.VOICE_COMMUNICATION, rate, android.media.AudioFormat.CHANNEL_IN_MONO, android.media.AudioFormat.ENCODING_PCM_16BIT, maxOf(min, 3200 * 6)) }.getOrNull() ?: return false
        if (r.state != android.media.AudioRecord.STATE_INITIALIZED) { r.release(); return false }
        rec = r
        ws = client.newWebSocket(request, object : okhttp3.WebSocketListener() {
            override fun onMessage(webSocket: okhttp3.WebSocket, t: String) {
                val o = runCatching { org.json.JSONObject(t) }.getOrNull() ?: return
                when (o.optString("t")) {
                    "delta" -> { text.append(o.optString("text")); interim = ""; onPartial(text.toString().trim()) }
                    "interim" -> { interim = o.optString("text"); onPartial((text.toString() + interim).trim()) }
                    "model" -> model = o.optString("model")
                    "eager" -> eager = true
                    "turn_end" -> turnEnded = true
                    "done" -> { val d = o.optString("text"); done.complete(if (d.isNotBlank()) d else text.toString().trim()) }
                    "error" -> { error = o.optString("message").ifBlank { "ошибка распознавания" }; done.complete(text.toString().trim()) }
                }
            }
            override fun onFailure(webSocket: okhttp3.WebSocket, t: Throwable, response: okhttp3.Response?) { if (!closed) { error = "Нет связи с сервером распознавания"; done.complete(text.toString().trim()) } }
            override fun onClosed(webSocket: okhttp3.WebSocket, code: Int, reason: String) { done.complete(text.toString().trim()) }
        })
        running = true
        r.startRecording()
        thread = Thread {
            val buf = ShortArray(1600)                          // 100 мс
            val bytes = ByteArray(3200)
            var smooth = 0f
            while (running) {
                val n = r.read(buf, 0, buf.size)
                if (n <= 0) { if (n < 0) break else continue }
                var sum = 0.0
                for (i in 0 until n) { val v = buf[i].toInt(); sum += (v * v).toDouble(); bytes[2 * i] = (v and 0xff).toByte(); bytes[2 * i + 1] = ((v shr 8) and 0xff).toByte() }
                val rms = Math.sqrt(sum / n).toFloat()
                smooth += ((rms / 3500f).coerceIn(0f, 1f) - smooth) * 0.6f
                level = smooth; onLevel(smooth)
                if (pcm.size() < 16000 * 2 * 150) synchronized(pcm) { pcm.write(bytes, 0, n * 2) }
                ws?.send(okio.ByteString.of(*bytes.copyOf(n * 2)))
            }
        }.also { it.isDaemon = true; it.start() }
        return true
    }

    private fun stopMic() { running = false; runCatching { thread?.join(300) }; runCatching { rec?.stop() }; runCatching { rec?.release() }; rec = null }

    /** Останавливает микрофон, сообщает серверу конец речи и ждёт итоговый текст. */
    suspend fun finish(): String {
        stopMic()
        runCatching { ws?.send("{\"t\":\"end\"}") }
        if (turnEnded && text.isNotBlank()) return text.toString().trim()   // сервер уже подтвердил конец фразы — итог готов, не ждём «done»
        val t = kotlinx.coroutines.withTimeoutOrNull(2500) { done.await() } ?: text.toString().trim()
        return t
    }

    /** Всё, что услышал микрофон, как WAV 16 кГц — для повторного (более точного) распознавания целой фразы. */
    fun wav(): ByteArray? {
        val data = synchronized(pcm) { pcm.toByteArray() }
        if (data.size < 16000 * 2 / 4) return null
        val h = java.nio.ByteBuffer.allocate(44).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        h.put("RIFF".toByteArray()).putInt(36 + data.size).put("WAVEfmt ".toByteArray()).putInt(16).putShort(1).putShort(1).putInt(16000).putInt(32000).putShort(2).putShort(16).put("data".toByteArray()).putInt(data.size)
        return h.array() + data
    }

    fun cancel() { closed = true; stopMic(); runCatching { ws?.close(1000, null) }; ws = null; done.complete(text.toString().trim()) }
}
