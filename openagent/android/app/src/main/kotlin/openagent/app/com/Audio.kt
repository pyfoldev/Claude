package openagent.app.com

import android.content.Context
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import kotlinx.coroutines.*
import java.io.File
import kotlin.coroutines.resume

/** Запись с микрофона (AAC/m4a) с уровнем звука для анимации и детектором тишины. */
class Recorder(private val ctx: Context) {
    private var rec: MediaRecorder? = null
    private var file: File? = null
    val active get() = rec != null

    fun start(): Boolean {
        stopQuiet()
        val f = File(ctx.cacheDir, "rec_${System.currentTimeMillis()}.m4a")
        return try {
            val r = if (Build.VERSION.SDK_INT >= 31) MediaRecorder(ctx) else @Suppress("DEPRECATION") MediaRecorder()
            r.setAudioSource(MediaRecorder.AudioSource.VOICE_COMMUNICATION)
            r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            r.setAudioSamplingRate(16000); r.setAudioEncodingBitRate(48000)
            r.setOutputFile(f.absolutePath)
            r.prepare(); r.start()
            rec = r; file = f; true
        } catch (e: Exception) { stopQuiet(); false }
    }

    /** 0f..1f */
    fun level(): Float = try { (rec?.maxAmplitude ?: 0) / 12000f } catch (e: Exception) { 0f }.coerceIn(0f, 1f)

    fun stop(): File? {
        val r = rec ?: return null
        rec = null
        return try { r.stop(); r.release(); file } catch (e: Exception) { runCatching { r.release() }; null }
    }

    fun cancel() { stop()?.delete() }
    private fun stopQuiet() { runCatching { rec?.stop() }; runCatching { rec?.release() }; rec = null }
}

/** Одновременно играет один звук. */
class Player {
    val pcm = PcmPlayer()
    private var mp: MediaPlayer? = null
    private var cont: CancellableContinuation<Unit>? = null

    suspend fun play(file: File) = suspendCancellableCoroutine { c ->
        stop()
        cont = c
        val p = MediaPlayer()
        mp = p
        try {
            p.setDataSource(file.absolutePath)
            p.setOnCompletionListener { finish(p) }
            p.setOnErrorListener { _, _, _ -> finish(p); true }
            p.prepare(); p.start()
        } catch (e: Exception) { finish(p) }
        c.invokeOnCancellation { runCatching { p.stop() }; runCatching { p.release() }; if (mp === p) mp = null }
    }

    /** Подготовка плеера заранее (в фоне), чтобы следующий кусок стартовал без паузы. */
    fun prepare(file: File): MediaPlayer? = try { MediaPlayer().apply { setDataSource(file.absolutePath); prepare() } } catch (e: Exception) { null }

    suspend fun playPrepared(p: MediaPlayer) = suspendCancellableCoroutine { c ->
        stop()
        cont = c; mp = p
        p.setOnCompletionListener { finish(p) }
        p.setOnErrorListener { _, _, _ -> finish(p); true }
        try { p.start() } catch (e: Exception) { finish(p) }
        // страховка: если система не прислала «завершено» (бывает в окне ассистента) — сами замечаем, что звук давно не играет
        val h = android.os.Handler(android.os.Looper.getMainLooper()); var silent = 0
        val watch = object : Runnable { override fun run() {
            if (mp !== p || !c.isActive) return
            val playing = runCatching { p.isPlaying }.getOrDefault(false)
            silent = if (playing) 0 else silent + 1
            if (silent >= 4) finish(p) else h.postDelayed(this, 350)
        } }
        h.postDelayed(watch, 1200)
        c.invokeOnCancellation { h.removeCallbacks(watch); runCatching { p.stop() }; runCatching { p.release() }; if (mp === p) mp = null }
    }

    /** Потоковая озвучка: плеер начинает играть, как только пришли первые байты (не ждёт готовый файл). null — не получилось. */
    suspend fun prepareRemote(ctx: android.content.Context, url: String, headers: Map<String, String>): MediaPlayer? = suspendCancellableCoroutine { c ->
        val p = MediaPlayer()
        var done = false
        fun end(ok: Boolean) { if (done) return; done = true; if (c.isActive) { if (ok) c.resume(p) else { runCatching { p.release() }; c.resume(null) } } else runCatching { p.release() } }
        try {
            p.setDataSource(ctx, android.net.Uri.parse(url), headers)
            p.setOnPreparedListener { end(true) }
            p.setOnErrorListener { _, _, _ -> end(false); true }
            p.prepareAsync()
        } catch (e: Exception) { end(false) }
        c.invokeOnCancellation { if (!done) { done = true; runCatching { p.release() } } }
    }

    private fun finish(p: MediaPlayer) {
        runCatching { p.release() }
        if (mp === p) mp = null
        cont?.let { if (it.isActive) it.resume(Unit) }; cont = null
    }

    /** Играет ли сейчас звук (для контроля зависших состояний). */
    fun active(): Boolean = pcm.playing || (mp?.let { runCatching { it.isPlaying }.getOrDefault(false) } ?: false)

    fun stop() {
        pcm.stopNow()
        val p = mp ?: return
        mp = null
        runCatching { p.stop() }; runCatching { p.release() }
        cont?.let { if (it.isActive) it.resume(Unit) }; cont = null
    }
}
