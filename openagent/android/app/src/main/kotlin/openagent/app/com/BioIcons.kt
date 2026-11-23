package openagent.app.com

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material3.Icon
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** Состояние иконки проверки: 0 — идёт, 1 — успех, 2 — не подошло. */
const val BIO_WORK = 0; const val BIO_OK = 1; const val BIO_FAIL = 2
private val OkGreen = Color(0xFF3DBE74); private val ErrRed = Color(0xFFE5484D)

/** Анимированная иконка в стиле Face ID: уголки рамки, лицо, бегущая линия сканирования; галочка при успехе, тряска при ошибке. */
@Composable
fun FaceIdIcon(state: Int, size: Dp = 132.dp, modifier: Modifier = Modifier) {
    val inf = rememberInfiniteTransition(label = "faceid")
    val scan by inf.animateFloat(0f, 1f, infiniteRepeatable(tween(1500, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "scan")
    val pulse by inf.animateFloat(0.55f, 1f, infiniteRepeatable(tween(1100), RepeatMode.Reverse), label = "pulse")
    val shake = remember { Animatable(0f) }
    val check = remember { Animatable(0f) }
    LaunchedEffect(state) {
        if (state == BIO_FAIL) { for (v in listOf(1f, -1f, 0.7f, -0.7f, 0.3f, 0f)) shake.animateTo(v, tween(60)) } else shake.snapTo(0f)
        if (state == BIO_OK) check.animateTo(1f, tween(380)) else check.snapTo(0f)
    }
    val base = C.onContainer
    val col = when (state) { BIO_OK -> OkGreen; BIO_FAIL -> ErrRed; else -> base }
    Canvas(modifier.size(size)) {
        val w = this.size.width; val sw = w * 0.035f
        val dx = shake.value * w * 0.04f
        val st = Stroke(sw, cap = StrokeCap.Round)
        // уголки
        val m = w * 0.06f; val L = w * 0.22f; val r = w * 0.1f
        val corners = listOf(Triple(m, m, 1 to 1), Triple(w - m, m, -1 to 1), Triple(m, w - m, 1 to -1), Triple(w - m, w - m, -1 to -1))
        for ((cx, cy, d) in corners) {
            val (sx, sy) = d
            val p = Path().apply {
                moveTo(cx + dx + sx * L, cy); lineTo(cx + dx + sx * r, cy)
                quadraticTo(cx + dx, cy, cx + dx, cy + sy * r); lineTo(cx + dx, cy + sy * L)
            }
            drawPath(p, col, style = st)
        }
        val fa = if (state == BIO_OK) 1f - check.value * 0.85f else 1f
        if (fa > 0.05f) {
            val c = col.copy(alpha = fa)
            // глаза, нос, улыбка
            val ey = w * 0.40f; val ex = w * 0.17f
            drawLine(c, Offset(w / 2 - ex + dx, ey - w * 0.04f), Offset(w / 2 - ex + dx, ey + w * 0.04f), sw * 1.3f, StrokeCap.Round)
            drawLine(c, Offset(w / 2 + ex + dx, ey - w * 0.04f), Offset(w / 2 + ex + dx, ey + w * 0.04f), sw * 1.3f, StrokeCap.Round)
            val nose = Path().apply { moveTo(w / 2 + dx, w * 0.42f); lineTo(w / 2 + dx, w * 0.56f); lineTo(w / 2 - w * 0.04f + dx, w * 0.56f) }
            drawPath(nose, c, style = st)
            drawArc(c, 20f, 140f, false, Offset(w / 2 - w * 0.17f + dx, w * 0.50f), Size(w * 0.34f, w * 0.2f), style = st)
        }
        if (state == BIO_WORK) {
            val y = w * (0.2f + 0.6f * scan)
            drawLine(base.copy(alpha = pulse), Offset(w * 0.22f, y), Offset(w * 0.78f, y), sw * 1.2f, StrokeCap.Round)
        }
        if (state == BIO_OK) {
            val t = check.value
            val p1 = Offset(w * 0.30f, w * 0.52f); val p2 = Offset(w * 0.45f, w * 0.66f); val p3 = Offset(w * 0.72f, w * 0.36f)
            val path = Path().apply {
                moveTo(p1.x, p1.y)
                if (t < 0.45f) { val k = t / 0.45f; lineTo(p1.x + (p2.x - p1.x) * k, p1.y + (p2.y - p1.y) * k) }
                else { lineTo(p2.x, p2.y); val k = (t - 0.45f) / 0.55f; lineTo(p2.x + (p3.x - p2.x) * k, p2.y + (p3.y - p2.y) * k) }
            }
            drawPath(path, OkGreen, style = Stroke(sw * 1.6f, cap = StrokeCap.Round, join = androidx.compose.ui.graphics.StrokeJoin.Round))
        }
    }
}

/** Иконка голоса: микрофон и кольца, которые «дышат» от громкости; зелёная/красная при результате. */
@Composable
fun VoiceIdIcon(level: Float, state: Int, listening: Boolean, size: Dp = 132.dp, modifier: Modifier = Modifier) {
    val inf = rememberInfiniteTransition(label = "voiceid")
    val ph by inf.animateFloat(0f, 1f, infiniteRepeatable(tween(1800, easing = LinearEasing)), label = "ph")
    val lv by animateFloatAsState(level.coerceIn(0f, 1f), tween(90), label = "lv")
    val col = when (state) { BIO_OK -> OkGreen; BIO_FAIL -> ErrRed; else -> C.onContainer }
    Box(modifier.size(size), contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(size)) {
            val w = this.size.width; val c = center
            for (i in 0..2) {
                val k = if (listening) ((ph + i / 3f) % 1f) else 0f
                val rad = w * (0.28f + 0.22f * k + 0.2f * lv * (1 - i * 0.25f))
                val a = if (listening) (1f - k) * (0.25f + 0.5f * lv) else 0.18f
                drawCircle(col.copy(alpha = a.coerceIn(0f, 1f)), rad, c, style = Stroke(w * 0.012f + w * 0.01f * lv))
            }
            drawCircle(col.copy(alpha = 0.14f), w * (0.26f + 0.05f * lv), c)
        }
        if (state == BIO_OK) Icon(androidx.compose.material.icons.Icons.Outlined.Check, null, tint = col, modifier = Modifier.size(size * 0.3f))
        else Icon(Icons.Outlined.Mic, null, tint = col, modifier = Modifier.size(size * 0.28f))
    }
}
