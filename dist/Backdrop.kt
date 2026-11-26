package your.app.package   // <- замените на пакет нового приложения

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.unit.dp

// Анимированный фон OpenAgent: чёрный экран, сетка белых точек, мягкое свечение по краям.
// Использование:  Box(Modifier.fillMaxSize()) { Backdrop(); /* ваш интерфейс поверх */ }
// Backdrop(opaque = false) — без чёрной заливки (поверх своего цвета).
// FxLevel.level = 0f..1f — громкость голоса: точки ярчают, по сетке расходятся волны, свечение пульсирует (можно не трогать — тогда фон просто мерцает).
// Зависимости: только Jetpack Compose (foundation, runtime, ui). Больше ничего не нужно.

/** Громкость голоса (ваш или агента) для анимации фона: 0..1. Пишется экраном звонка. */
object FxLevel { var level by mutableFloatStateOf(0f) }

/**
 * Фон: полностью чёрный, белые точки по всему экрану и мягкое белое свечение по всем краям.
 * Всё живое: точки мерцают волной, а во время речи (вашей и агента) по сетке расходятся волны, точки ярчают, свечение по краям пульсирует.
 */
@Composable
fun Backdrop(opaque: Boolean = true) {
    var t by remember { mutableLongStateOf(0L) }
    LaunchedEffect(Unit) {
        var last = 0L
        while (true) {
            androidx.compose.animation.core.withInfiniteAnimationFrameMillis { ms -> val gap = if (FxLevel.level > 0.03f) 33 else 66; if (ms - last >= gap) { last = ms; t = ms } }
        }
    }
    val state = remember { object { val lv = floatArrayOf(0f); val arrs = Array(6) { FloatArray(9000) }; val cnt = IntArray(6) } }
    androidx.compose.foundation.Canvas(Modifier.fillMaxSize()) {
        val time = t.toFloat()
        val w = size.width; val h = size.height
        val W = Color.White
        // сглаженная громкость
        state.lv[0] += (FxLevel.level - state.lv[0]) * 0.35f
        val lv = state.lv[0]
        if (opaque) drawRect(Color.Black)
        // ---- точки ----
        val step = 13.dp.toPx(); val rowH = step * 0.866f
        val ox = w / 2f; val oy = h * 0.42f; val maxD = kotlin.math.hypot(w, h) * 0.62f
        val amp = 0.10f + 1.5f * lv
        val speed = 0.00022f + 0.0006f * lv
        val pos = FloatArray(3) { k -> ((time * speed + k / 3f) % 1f) }
        java.util.Arrays.fill(state.cnt, 0)
        var row = 0; var y = rowH / 2
        while (y < h) {
            val ty = y / h
            val edgeV = kotlin.math.max(1f - ty * 5f, 0f) * 0.5f
            val base = 0.13f + 0.2f * ty * ty * ty + edgeV * 0.12f
            var x = if (row % 2 == 0) step / 2 else step
            while (x < w) {
                val shimmer = 0.72f + 0.28f * kotlin.math.sin(time * 0.0014f + x * 0.013f + y * 0.009f)
                val d = kotlin.math.hypot(x - ox, y - oy) / maxD
                var wv = 0f
                for (k in 0 until 3) { val e = d - pos[k]; wv += kotlin.math.exp(-(e * e) / 0.006f) }
                val a = (base * shimmer + amp * wv * 0.42f).coerceIn(0f, 0.9f)
                val bi = (a / 0.9f * 5.99f).toInt().coerceIn(0, 5)
                val c = state.cnt[bi]; if (c < 8998) { state.arrs[bi][c] = x; state.arrs[bi][c + 1] = y; state.cnt[bi] = c + 2 }
                x += step
            }
            y += rowH; row++
        }
        drawIntoCanvas { canvas ->
            val p = androidx.compose.ui.graphics.Paint().apply { style = androidx.compose.ui.graphics.PaintingStyle.Stroke; strokeCap = androidx.compose.ui.graphics.StrokeCap.Round; isAntiAlias = true }
            for (bi in 0 until 6) {
                if (state.cnt[bi] == 0) continue
                p.color = W.copy(alpha = (0.1f + 0.9f * (bi + 0.5f) / 6f * 0.9f).coerceAtMost(0.92f))
                p.strokeWidth = (1.3f + 0.45f * bi).dp.toPx()
                canvas.drawRawPoints(androidx.compose.ui.graphics.PointMode.Points, state.arrs[bi].copyOf(state.cnt[bi]), p)
            }
        }
        // ---- свечение по краям (пульсирует голосом) ----
        fun glow(a0: Float, rev: Boolean = false): Array<Pair<Float, Color>> {
            val f = floatArrayOf(0f, 0.18f, 0.42f, 0.72f, 1f); val k = floatArrayOf(1f, 0.55f, 0.2f, 0.05f, 0f)
            return Array(5) { i -> if (!rev) f[i] to W.copy(alpha = (a0 * k[i]).coerceAtMost(0.8f)) else (1f - f[4 - i]) to W.copy(alpha = (a0 * k[4 - i]).coerceAtMost(0.8f)) }
        }
        val gm = 1f + 2.4f * lv + 0.12f * kotlin.math.sin(time * 0.002f)
        val gw = (74.dp.toPx()) * (1f + 0.7f * lv); val gh = 90.dp.toPx() * (1f + 0.6f * lv)
        drawRect(androidx.compose.ui.graphics.Brush.horizontalGradient(*glow(0.13f * gm), startX = 0f, endX = gw), size = androidx.compose.ui.geometry.Size(gw, h))
        drawRect(androidx.compose.ui.graphics.Brush.horizontalGradient(*glow(0.13f * gm, true), startX = w - gw, endX = w), topLeft = Offset(w - gw, 0f), size = androidx.compose.ui.geometry.Size(gw, h))
        drawRect(androidx.compose.ui.graphics.Brush.verticalGradient(*glow(0.11f * gm), startY = 0f, endY = gh), size = androidx.compose.ui.geometry.Size(w, gh))
        drawRect(androidx.compose.ui.graphics.Brush.verticalGradient(*glow(0.16f * gm, true), startY = h - gh, endY = h), topLeft = Offset(0f, h - gh), size = androidx.compose.ui.geometry.Size(w, gh))
    }
}
