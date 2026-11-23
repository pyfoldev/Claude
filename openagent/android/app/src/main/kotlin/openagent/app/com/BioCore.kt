package openagent.app.com

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Matrix
import android.graphics.Paint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.facedetector.FaceDetector
import com.google.mediapipe.tasks.vision.gesturerecognizer.GestureRecognizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlin.math.sqrt

/**
 * Защита по голосу и лицу — всё на телефоне. Отпечатки (векторы 192/128 чисел, не записи и не фото) хранятся зашифрованными ключом Android Keystore.
 *  • голос: ReDimNet2-B2 (MIT, Palabra AI) — вектор говорящего по 2–10 с речи, сравнение косинусом;
 *  • лицо: MobileFaceNet (Apache-2.0, Qualcomm AI Hub) + детектор лица MediaPipe BlazeFace (выравнивание по глазам и рту);
 *  • жест ✌️: MediaPipe Gesture Recognizer (класс «Victory»).
 * Честно о надёжности: это удобная блокировка, а не защита уровня банка — запись голоса или фото владельца могут её обмануть (проверки «живости» нет).
 */
object BioVault {
    private const val ALIAS = "oa_bio"
    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val g = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        g.init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build())
        return g.generateKey()
    }
    private fun prefs(ctx: Context) = ctx.getSharedPreferences("bio_vault", Context.MODE_PRIVATE)
    fun save(ctx: Context, name: String, v: FloatArray) {
        val bb = ByteBuffer.allocate(v.size * 4).order(ByteOrder.LITTLE_ENDIAN); v.forEach { bb.putFloat(it) }
        val c = Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.ENCRYPT_MODE, key())
        prefs(ctx).edit().putString(name, Base64.encodeToString(c.iv + c.doFinal(bb.array()), Base64.NO_WRAP)).apply()
    }
    fun load(ctx: Context, name: String): FloatArray? = runCatching {
        val raw = Base64.decode(prefs(ctx).getString(name, null) ?: return null, Base64.NO_WRAP)
        val c = Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, raw, 0, 12))
        val bb = ByteBuffer.wrap(c.doFinal(raw, 12, raw.size - 12)).order(ByteOrder.LITTLE_ENDIAN)
        FloatArray(bb.remaining() / 4) { bb.getFloat() }
    }.getOrNull()
    fun clear(ctx: Context, name: String) { prefs(ctx).edit().remove(name).apply() }
    fun has(ctx: Context, name: String) = prefs(ctx).contains(name)
    fun anyEnrolled(ctx: Context) = has(ctx, "voice") || has(ctx, "face")
}

/** Что происходит с кадрами: показывается на экране проверки и в настройках, чтобы причину сбоя было видно, а не «лица не видно». */
object BioDiag {
    @Volatile var status = ""
    @Volatile var rot = 0                     // какой поворот кадра сработал в прошлый раз (самонастройка)
    /** Полная причина сбоя: цепочка исключений, верхний кадр стека и архитектура процессора телефона. */
    fun err(e: Throwable) {
        val chain = generateSequence(e) { it.cause }.take(4).joinToString(" ← ") { "${it.javaClass.simpleName}: ${it.message}" }
        val top = e.stackTrace.firstOrNull()?.let { " @${it.className.substringAfterLast('.')}.${it.methodName}" } ?: ""
        val abi = android.os.Build.SUPPORTED_ABIS.firstOrNull() ?: "?"
        status = "Сбой [${if (android.os.Process.is64Bit()) "64" else "32"} бит, $abi]: $chain$top".take(420)
    }
}
private fun rotated(b: Bitmap, deg: Int): Bitmap = if (deg == 0) b else Bitmap.createBitmap(b, 0, 0, b.width, b.height, Matrix().apply { postRotate(deg.toFloat()) }, true)
private val ROTS = listOf(0, 90, 270, 180)
private fun rotOrder() = (listOf(BioDiag.rot) + ROTS).distinct()

object Onnx {
    val env: OrtEnvironment by lazy { OrtEnvironment.getEnvironment() }
    fun session(ctx: Context, asset: String): OrtSession {
        val bytes = ctx.assets.open(asset).use { it.readBytes() }
        return env.createSession(bytes, OrtSession.SessionOptions().apply { setIntraOpNumThreads(2) })
    }
}

fun l2(v: FloatArray): FloatArray { var s = 0.0; for (x in v) s += x * x; val n = sqrt(s).toFloat().coerceAtLeast(1e-9f); return FloatArray(v.size) { v[it] / n } }
fun cosine(a: FloatArray, b: FloatArray): Float { var s = 0f; for (i in a.indices) s += a[i] * b[i]; return s }
fun centroid(list: List<FloatArray>): FloatArray { val c = FloatArray(list[0].size); for (v in list) for (i in c.indices) c[i] += v[i]; return l2(c) }

/** Строгость: порог «это вы» для голоса и лица. */
object BioThr {
    fun voice(strict: String) = when (strict) { "soft" -> 0.40f; "strict" -> 0.60f; else -> 0.50f }
    fun face(strict: String) = when (strict) { "soft" -> 0.40f; "strict" -> 0.60f; else -> 0.50f }
}

object VoicePrint {
    private var sess: OrtSession? = null
    @Synchronized private fun s(ctx: Context) = sess ?: Onnx.session(ctx, "redimnet2_b2.onnx").also { sess = it }
    /** Речь 16 кГц моно [-1,1] → вектор говорящего (192 числа, L2-нормирован). */
    fun embed(ctx: Context, pcm: FloatArray): FloatArray {
        val t = OnnxTensor.createTensor(Onnx.env, arrayOf(pcm))
        try { s(ctx).run(mapOf("wave" to t)).use { r -> @Suppress("UNCHECKED_CAST") return l2((r[0].value as Array<FloatArray>)[0]) } } finally { t.close() }
    }
    fun enrolled(ctx: Context) = BioVault.has(ctx, "voice")
    fun verify(ctx: Context, pcm: FloatArray): Float { val ref = BioVault.load(ctx, "voice") ?: return -1f; return cosine(embed(ctx, pcm), ref) }

    /** Запись речи (до maxMs): оставляем только фразы с речью — тишина и шум не портят отпечаток; null — речи меньше ~1,3 с. Останавливается сама после 2,3 с речи и паузы. */
    @android.annotation.SuppressLint("MissingPermission")
    suspend fun record(maxMs: Int, onLevel: (Float) -> Unit): FloatArray? = withContext(Dispatchers.IO) {
        ClapState.paused = true
        val min = AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val r = runCatching { AudioRecord(MediaRecorder.AudioSource.MIC, 16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(min * 2, 8000)) }.getOrNull()
        if (r == null || r.state != AudioRecord.STATE_INITIALIZED) { r?.release(); ClapState.paused = false; return@withContext null }
        val frames = ArrayList<FloatArray>(); val rmsList = ArrayList<Float>(); val buf = ShortArray(1600); var elapsed = 0; var speechN = 0; var quiet = 0
        try {
            r.startRecording()
            while (elapsed + 100 <= maxMs) {
                var got = 0; while (got < 1600) { val k = r.read(buf, got, 1600 - got); if (k <= 0) break; got += k }
                if (got < 1600) break
                var e = 0.0; val f = FloatArray(1600) { i -> (buf[i] / 32768.0).toFloat().also { e += it * it } }
                val rms = sqrt(e / 1600).toFloat(); frames.add(f); rmsList.add(rms); elapsed += 100
                onLevel((rms * 10).coerceIn(0f, 1f))
                if (rms > 0.012f) { speechN++; quiet = 0 } else quiet++
                if (speechN >= 23 && quiet >= 5) break
            }
        } finally { runCatching { r.stop() }; r.release(); ClapState.paused = false }
        if (frames.isEmpty()) return@withContext null
        val peakRms = rmsList.maxOrNull() ?: 0f
        val thr = maxOf(0.008f, peakRms * 0.12f)
        val keep = frames.indices.filter { rmsList[it] >= thr }
        if (keep.size < 13) return@withContext null
        val out = FloatArray(keep.size * 1600); keep.forEachIndexed { j, i -> frames[i].copyInto(out, j * 1600) }
        out
    }
}

object FacePrint {
    private var det: FaceDetector? = null
    private var sess: OrtSession? = null
    private val TPL = floatArrayOf(38.2946f, 51.6963f, 73.5318f, 51.5014f, 56.1396f, 92.2848f)   // ArcFace 112×112: левый глаз, правый глаз, центр рта
    @Synchronized private fun detector(ctx: Context) = det ?: FaceDetector.createFromOptions(ctx, FaceDetector.FaceDetectorOptions.builder()
        .setBaseOptions(BaseOptions.builder().setModelAssetPath("blaze_face_short_range.tflite").build()).setRunningMode(RunningMode.IMAGE).setMinDetectionConfidence(0.4f).build()).also { det = it }
    @Synchronized private fun s(ctx: Context) = sess ?: Onnx.session(ctx, "mobilefacenet.onnx").also { sess = it }

    /** Кадр → лицо 112×112, выровненное по глазам и рту; null — лица нет. Если лицо не нашлось, пробуем повернуть кадр (камеры по-разному отдают ориентацию) и запоминаем удачный поворот. */
    fun align(ctx: Context, src: Bitmap): Bitmap? {
        try {
            for (rot in rotOrder()) {
                val bmp = rotated(if (src.config == Bitmap.Config.ARGB_8888) src else src.copy(Bitmap.Config.ARGB_8888, false), rot)
                val d = detector(ctx).detect(BitmapImageBuilder(bmp).build()).detections().maxByOrNull { it.categories()[0].score() } ?: continue
                val kp = d.keypoints().orElse(null)
                if (kp == null || kp.size < 4) { BioDiag.status = "лицо найдено, но без ключевых точек"; continue }
                val w = bmp.width.toFloat(); val h = bmp.height.toFloat()
                val fw = d.boundingBox().width().let { if (it <= 1.5f) it * w else it }       // на случай нормированных координат
                if (fw < 40f) { BioDiag.status = "лицо слишком далеко (%.0f px) — приблизьтесь".format(fw); continue }
                BioDiag.rot = rot; BioDiag.status = "лицо видно (кадр ${src.width}×${src.height}, поворот $rot°, ширина %.0f px)".format(fw)
                val s = floatArrayOf(kp[0].x() * w, kp[0].y() * h, kp[1].x() * w, kp[1].y() * h, kp[3].x() * w, kp[3].y() * h)
                // преобразование подобия (поворот+масштаб+сдвиг) по трём точкам, метод наименьших квадратов
                val sx = (s[0] + s[2] + s[4]) / 3; val sy = (s[1] + s[3] + s[5]) / 3; val dx = (TPL[0] + TPL[2] + TPL[4]) / 3; val dy = (TPL[1] + TPL[3] + TPL[5]) / 3
                var num1 = 0f; var num2 = 0f; var den = 0f
                for (i in 0 until 3) { val a = s[2 * i] - sx; val b = s[2 * i + 1] - sy; val c = TPL[2 * i] - dx; val e = TPL[2 * i + 1] - dy; num1 += a * c + b * e; num2 += a * e - b * c; den += a * a + b * b }
                if (den < 1f) continue
                val ca = num1 / den; val cb = num2 / den
                val m = Matrix().apply { setValues(floatArrayOf(ca, -cb, dx - (ca * sx - cb * sy), cb, ca, dy - (cb * sx + ca * sy), 0f, 0f, 1f)) }
                val out = Bitmap.createBitmap(112, 112, Bitmap.Config.ARGB_8888)
                Canvas(out).drawBitmap(bmp, m, Paint(Paint.FILTER_BITMAP_FLAG))
                return out
            }
            if (!BioDiag.status.startsWith("лицо слишком") && !BioDiag.status.startsWith("лицо найдено")) BioDiag.status = "лица в кадре нет (кадр ${src.width}×${src.height}, пробовал повороты)"
            return null
        } catch (e: Throwable) { BioDiag.err(e); return null }
    }

    /** Выровненное лицо → вектор (128 чисел, L2). Модель принимает пару лиц — подаём одно и то же, берём первую строку. */
    fun embed(ctx: Context, face: Bitmap): FloatArray {
        val px = IntArray(112 * 112); face.getPixels(px, 0, 112, 0, 0, 112, 112)
        val a = FloatArray(3 * 112 * 112)
        for (i in px.indices) { val p = px[i]; a[i] = ((p shr 16) and 255) / 255f; a[112 * 112 + i] = ((p shr 8) and 255) / 255f; a[2 * 112 * 112 + i] = (p and 255) / 255f }
        val shape = longArrayOf(1, 3, 112, 112)
        val t1 = OnnxTensor.createTensor(Onnx.env, FloatBuffer.wrap(a), shape); val t2 = OnnxTensor.createTensor(Onnx.env, FloatBuffer.wrap(a), shape)
        try { s(ctx).run(mapOf("img1" to t1, "img2" to t2)).use { r -> @Suppress("UNCHECKED_CAST") return l2((r[0].value as Array<FloatArray>)[0]) } } finally { t1.close(); t2.close() }
    }
    fun enrolled(ctx: Context) = BioVault.has(ctx, "face")
    /** Кадр → сходство с вашим лицом; null — лица в кадре нет. */
    fun verify(ctx: Context, frame: Bitmap): Float? { val ref = BioVault.load(ctx, "face") ?: return null; val f = align(ctx, frame) ?: return null; return cosine(embed(ctx, f), ref) }
}

object GestureRec {
    private var rec: GestureRecognizer? = null
    @Synchronized private fun r(ctx: Context) = rec ?: GestureRecognizer.createFromOptions(ctx, GestureRecognizer.GestureRecognizerOptions.builder()
        .setBaseOptions(BaseOptions.builder().setModelAssetPath("gesture_recognizer.task").build()).setRunningMode(RunningMode.IMAGE).setNumHands(1).setMinHandDetectionConfidence(0.4f).setMinHandPresenceConfidence(0.4f).build()).also { rec = it }
    /** true, если в кадре жест «Victory» ✌️ с уверенностью ≥ 0,5. Рук нет → пробуем другие повороты кадра и запоминаем удачный. */
    fun isVictory(ctx: Context, frame: Bitmap): Boolean {
        try {
            val base = if (frame.config == Bitmap.Config.ARGB_8888) frame else frame.copy(Bitmap.Config.ARGB_8888, false)
            for (rot in rotOrder()) {
                val res = r(ctx).recognize(BitmapImageBuilder(rotated(base, rot)).build())
                if (res.landmarks().isEmpty()) continue
                BioDiag.rot = rot
                val g = res.gestures(); val top = g.firstOrNull()?.firstOrNull()
                BioDiag.status = "рука видна: ${top?.categoryName() ?: "?"} %.2f (поворот $rot°)".format(top?.score() ?: 0f)
                return top != null && top.categoryName() == "Victory" && top.score() >= 0.5f
            }
            BioDiag.status = "руки в кадре нет (кадр ${frame.width}×${frame.height})"
            return false
        } catch (e: Throwable) { BioDiag.err(e); return false }
    }
}
