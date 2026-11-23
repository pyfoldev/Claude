package openagent.app.com

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import java.io.FileInputStream
import java.nio.channels.FileChannel
import kotlin.math.log10
import kotlin.math.sqrt

/**
 * Вызов ассистента двойным хлопком. Два этапа, чтобы не будить телефон аплодисментами и не тратить батарею:
 * 1) всегда дешёвый детектор резких коротких ударов по громкости (ClapDetector) — ищет ровно ДВА удара с паузой 0,17–0,65 с, тишиной до и после;
 * 2) только на такую пару — YAMNet (TFLite, 4 МБ): хлопок ли это (а не стук, щелчок, речь, аплодисменты).
 * Реализация зеркалит эталон clap-wake/detector.py (там же калибровка на ESC-50).
 */
object ClapState {
    @Volatile var paused = false        // идёт голосовой звонок — микрофон не трогаем
    @Volatile var last = ""             // диагностика: что слышал на последнем кандидате
}

object ClapIdx { const val SPEECH = 0; const val HANDS = 56; const val SNAP = 57; const val CLAPPING = 58; const val APPLAUSE = 62; const val SLAP = 461 }

class Yamnet(ctx: Context) {
    private val interp: org.tensorflow.lite.Interpreter
    private val out = Array(1) { FloatArray(521) }
    init {
        val fd = ctx.assets.openFd("yamnet.tflite")
        val map = FileInputStream(fd.fileDescriptor).channel.map(FileChannel.MapMode.READ_ONLY, fd.startOffset, fd.declaredLength)
        interp = org.tensorflow.lite.Interpreter(map, org.tensorflow.lite.Interpreter.Options().setNumThreads(2))
    }
    fun scores(w: FloatArray): FloatArray { interp.run(w, out); return out[0] }
    fun close() = runCatching { interp.close() }
}

class ClapDetector {
    class Candidate(val t1: Long, val t2: Long, val window: FloatArray)
    private val ring = ShortArray(16000 * 4)
    private var total = 0L
    private val frameBuf = ShortArray(160); private var fp = 0
    private val dbs = FloatArray(4)
    private var nFrames = 0L
    private var floorDb = -60f; private var initN = 0; private var initSum = 0f; private var inited = false
    private var open = -1L
    private var lastEndMs = -1_000_000L
    private val events = ArrayList<Long>()
    private var consumed = -1L

    fun feed(buf: ShortArray, n: Int): Candidate? {
        var cand: Candidate? = null
        for (k in 0 until n) {
            ring[(total % ring.size).toInt()] = buf[k]; total++
            frameBuf[fp++] = buf[k]
            if (fp == 160) { fp = 0; frame()?.let { cand = it } }
        }
        return cand
    }

    private fun frame(): Candidate? {
        var s = 0.0
        for (v in frameBuf) { val f = v / 32768.0; s += f * f }
        val db = (20 * log10(sqrt(s / 160) + 1e-5)).toFloat()
        val i = nFrames++; val ms = i * 10
        dbs[(i % 4).toInt()] = db
        if (!inited) { initSum += db; if (++initN >= 20) { floorDb = initSum / initN; inited = true }; return null }
        if (open >= 0) {
            val dur = (i - open) * 10
            if (db - floorDb <= 8f || dur > 400) {
                if (dur <= MAX_EVENT) events.add(open * 10)
                lastEndMs = open * 10 + dur; open = -1
            }
            return null
        }
        floorDb = if (db < floorDb + 6) minOf(floorDb + 0.002f, db) else floorDb + 0.002f      // медленно ползущий шумовой пол
        val prev = dbs[((i - 3) % 4 + 4).toInt() % 4]
        if (db - floorDb > ONSET && db - prev > RISE && ms - lastEndMs > REFRACT) open = i
        events.removeAll { it < ms - 4000 }
        for (k in 0 until events.size - 1) {
            val t1 = events[k]; val t2 = events[k + 1]; val gap = t2 - t1
            if (gap < GAP_MIN || gap > GAP_MAX || t2 == consumed) continue
            if (events.any { it >= t1 - QUIET_BEFORE && it < t1 }) continue          // перед первым ударом были другие — не «двойной»
            if (events.any { it > t2 && it <= t2 + QUIET_AFTER }) continue           // после второго есть ещё — серия/аплодисменты
            if (open >= 0 || ms < t2 + QUIET_AFTER) continue                         // ждём тишину после второго удара
            consumed = t2
            val start = maxOf(0L, (t1 - 120) * 16)
            val w = FloatArray(15600) { j -> val idx = start + j; if (idx < total && total - idx <= ring.size) ring[(idx % ring.size).toInt()] / 32768f else 0f }
            return Candidate(t1, t2, w)
        }
        return null
    }

    companion object {
        const val ONSET = 17f; const val RISE = 11f; const val MAX_EVENT = 170; const val REFRACT = 80
        const val GAP_MIN = 170L; const val GAP_MAX = 650L; const val QUIET_BEFORE = 900L; const val QUIET_AFTER = 750L
    }
}

object ClapWake {
    /** Порог «похоже на хлопок» (сумма Clapping + Hands + Slap + Snapping) по чувствительности. */
    fun threshold(sens: String) = when (sens) { "low" -> 0.40f; "high" -> 0.10f; else -> 0.20f }

    fun fire(ctx: Context) {
        runCatching { (ctx.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator).vibrate(VibrationEffect.createWaveform(longArrayOf(0, 60, 70, 60), -1)) }
        val intent = Intent(ctx, AssistActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        runCatching { ctx.startActivity(intent) }            // сработает, если приложение на экране или есть право «поверх других окон»
        // из фона Android 10+ часто запрещает прямой запуск — тогда окно откроет полноэкранное уведомление (или нажатие на него)
        val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= 26) nm.createNotificationChannel(NotificationChannel("clap_call", "Вызов ассистента хлопком", NotificationManager.IMPORTANCE_HIGH))
        val pi = PendingIntent.getActivity(ctx, 21, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = NotificationCompat.Builder(ctx, "clap_call").setSmallIcon(R.drawable.ic_stat).setContentTitle("Слушаю").setContentText("Ассистент вызван хлопком — нажмите, если окно не открылось")
            .setPriority(NotificationCompat.PRIORITY_HIGH).setCategory(NotificationCompat.CATEGORY_CALL).setAutoCancel(true).setTimeoutAfter(15000).setContentIntent(pi).setFullScreenIntent(pi, true).build()
        runCatching { nm.notify(21, n) }
    }
}

class ClapService : Service() {
    @Volatile private var running = false
    private var thread: Thread? = null

    override fun onBind(i: Intent?): android.os.IBinder? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "stop") { Store(this).clapWake = false; stopSelf(); return START_NOT_STICKY }
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= 26) nm.createNotificationChannel(NotificationChannel("clap", "Ожидание двойного хлопка", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 20, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE)
        val off = PendingIntent.getService(this, 22, Intent(this, ClapService::class.java).setAction("stop"), PendingIntent.FLAG_IMMUTABLE)
        val n: Notification = NotificationCompat.Builder(this, "clap").setSmallIcon(R.drawable.ic_stat).setContentTitle("Жду двойной хлопок").setContentText("Хлопните дважды — откроется голосовой звонок")
            .setOngoing(true).setContentIntent(open).addAction(0, "Выключить", off).setPriority(NotificationCompat.PRIORITY_LOW).build()
        val ok = runCatching { androidx.core.app.ServiceCompat.startForeground(this, 20, n, if (Build.VERSION.SDK_INT >= 30) ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE else 0) }.isSuccess
        if (!ok) { stopSelf(); return START_NOT_STICKY }
        if (!running) { running = true; thread = Thread { loop() }.also { it.isDaemon = true; it.start() } }
        return START_STICKY
    }

    @android.annotation.SuppressLint("MissingPermission")
    private fun loop() {
        val yam = runCatching { Yamnet(this) }.getOrNull() ?: run { ClapState.last = "YAMNet не загрузился"; stopSelf(); return }
        val st = Store(this)
        val buf = ShortArray(1600); var rec: AudioRecord? = null; var det = ClapDetector(); var cooldownUntil = 0L
        try {
            while (running) {
                if (ClapState.paused || !st.clapWake) {            // идёт звонок — освобождаем микрофон
                    rec?.let { runCatching { it.stop() }; runCatching { it.release() } }; rec = null; det = ClapDetector()
                    if (!st.clapWake) break
                    Thread.sleep(300); continue
                }
                if (rec == null) {
                    val min = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
                    val r = runCatching { AudioRecord(MediaRecorder.AudioSource.MIC, 16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(min * 2, 8000)) }.getOrNull()
                    if (r == null || r.state != AudioRecord.STATE_INITIALIZED) { r?.release(); Thread.sleep(2000); continue }
                    runCatching { r.startRecording() }; rec = r; det = ClapDetector()
                }
                val n = rec.read(buf, 0, buf.size)
                if (n <= 0) { if (n < 0) { runCatching { rec.release() }; rec = null }; continue }
                val c = det.feed(buf, n) ?: continue
                if (System.currentTimeMillis() < cooldownUntil) continue
                val s = yam.scores(c.window)
                val clap = s[ClapIdx.CLAPPING] + s[ClapIdx.HANDS] + s[ClapIdx.SLAP] + s[ClapIdx.SNAP]
                val thr = ClapWake.threshold(st.clapSens)
                val pass = clap >= thr && s[ClapIdx.APPLAUSE] < 0.35f && s[ClapIdx.SPEECH] < 0.5f
                ClapState.last = "хлопок %.2f (порог %.2f), аплодисменты %.2f, речь %.2f → %s".format(clap, thr, s[ClapIdx.APPLAUSE], s[ClapIdx.SPEECH], if (pass) "вызов" else "игнор")
                if (pass) { cooldownUntil = System.currentTimeMillis() + 6000; ClapWake.fire(this) }
            }
        } finally { rec?.let { runCatching { it.stop() }; runCatching { it.release() } }; yam.close(); running = false }
    }

    override fun onDestroy() { running = false; super.onDestroy() }

    companion object {
        fun start(ctx: Context) { runCatching { ContextCompat.startForegroundService(ctx, Intent(ctx, ClapService::class.java)) } }
        fun stop(ctx: Context) { runCatching { ctx.stopService(Intent(ctx, ClapService::class.java)) } }
    }
}
