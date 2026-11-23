package openagent.app.com

import android.content.Context
import android.media.AudioAttributes
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Тактильный отклик через Vibrator (работает на всех устройствах, в отличие от HapticFeedback Compose). */
object Haptics {
    @Volatile var enabled = true
    private var vib: Vibrator? = null
    fun init(ctx: Context) {
        vib = if (Build.VERSION.SDK_INT >= 31) (ctx.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager).defaultVibrator
        else @Suppress("DEPRECATION") ctx.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
    }
    private fun play(effectId: Int, fallbackMs: Long, amp: Int) {
        if (!enabled) return
        val v = vib ?: return
        if (!v.hasVibrator()) return
        runCatching {
            val e = if (Build.VERSION.SDK_INT >= 29) VibrationEffect.createPredefined(effectId) else VibrationEffect.createOneShot(fallbackMs, amp)
            if (Build.VERSION.SDK_INT >= 33) v.vibrate(e, android.os.VibrationAttributes.createForUsage(android.os.VibrationAttributes.USAGE_TOUCH))
            else @Suppress("DEPRECATION") v.vibrate(e, AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION).build())
        }
    }
    fun tick() = play(VibrationEffect.EFFECT_TICK, 12, 90)
    fun click() = play(VibrationEffect.EFFECT_CLICK, 22, 160)
    fun heavy() = play(VibrationEffect.EFFECT_HEAVY_CLICK, 40, 255)
    fun success() = play(VibrationEffect.EFFECT_DOUBLE_CLICK, 50, 200)
}

/** Нажатие с пружинистым «вдавливанием» и вибро-откликом. */
fun Modifier.bounceClick(enabled: Boolean = true, strong: Boolean = false, onClick: () -> Unit): Modifier = composed {
    val src = remember { MutableInteractionSource() }
    val pressed by src.collectIsPressedAsState()
    val s by animateFloatAsState(if (pressed && enabled) 0.88f else 1f, spring(dampingRatio = 0.45f, stiffness = 700f), label = "press")
    this.scale(s).clickable(src, LocalIndicationCompat.current, enabled = enabled) { if (strong) Haptics.heavy() else Haptics.click(); onClick() }
}
private object LocalIndicationCompat { val current @Composable get() = androidx.compose.foundation.LocalIndication.current }

/** Круглая кнопка с иконкой: единый стиль для всего приложения. */
@Composable
fun RoundButton(icon: ImageVector, desc: String?, onClick: () -> Unit, modifier: Modifier = Modifier, size: Dp = 48.dp,
                container: Color = C.surface2, content: Color = C.text, enabled: Boolean = true, iconSize: Dp = 24.dp, strong: Boolean = false) {
    Box(modifier.size(size).bounceClick(enabled, strong, onClick).clip(CircleShape).background(if (enabled) container else C.surface3), contentAlignment = Alignment.Center) {
        Icon(icon, desc, tint = if (enabled) content else C.dim, modifier = Modifier.size(iconSize))
    }
}

/** Кнопка-таблетка с текстом (заполненная). */
@Composable
fun PillButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, icon: ImageVector? = null, container: Color = C.accent, content: Color = C.onAccent,
               enabled: Boolean = true, height: Dp = 56.dp) {
    Row(modifier.height(height).bounceClick(enabled, onClick = onClick).clip(RoundedCornerShape(height / 2)).background(if (enabled) container else C.container.copy(alpha = 0.45f)).padding(horizontal = 24.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
        if (icon != null) { Icon(icon, null, tint = if (enabled) content else C.onContainer.copy(alpha = 0.6f), modifier = Modifier.size(22.dp)); Spacer(Modifier.width(10.dp)) }
        Text(text, color = if (enabled) content else C.onContainer.copy(alpha = 0.6f), fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
    }
}

/** Переключатель Chat / Code со скользящим индикатором. */
@Composable
fun ModeSwitch(mode: String, onSelect: (String) -> Unit, modifier: Modifier = Modifier) {
    val idx by animateFloatAsState(if (mode == "code") 1f else 0f, spring(dampingRatio = 0.7f, stiffness = 380f), label = "mode")
    BoxWithConstraints(modifier.height(48.dp).clip(RoundedCornerShape(24.dp)).background(C.surface2).padding(4.dp)) {
        val w = maxWidth / 2
        Box(Modifier.offset(x = w * idx).width(w).fillMaxHeight().clip(RoundedCornerShape(20.dp)).background(C.container))
        Row(Modifier.fillMaxSize()) {
            listOf("chat" to "Чат", "code" to "Code").forEach { (m, label) ->
                val sel = mode == m
                Box(Modifier.weight(1f).fillMaxHeight().clip(RoundedCornerShape(20.dp)).clickable { if (!sel) { Haptics.click(); onSelect(m) } }, contentAlignment = Alignment.Center) {
                    Text(label, color = if (sel) C.onContainer else C.dim, fontSize = 15.sp, fontWeight = if (sel) FontWeight.SemiBold else FontWeight.Medium)
                }
            }
        }
    }
}

/** Контейнер с бегущей по краю дугой, пока агент работает. Анимация создаётся только в активном состоянии — в покое кадры не тратятся. */
@Composable
fun RunningBorder(active: Boolean, radius: Dp, modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {
    val a by animateFloatAsState(if (active) 1f else 0f, tween(350), label = "rba")
    if (a < 0.01f) { Box(modifier.clip(RoundedCornerShape(radius))) { content() }; return }
    val t = rememberInfiniteTransition(label = "rb")
    val angle by t.animateFloat(0f, 360f, infiniteRepeatable(tween(2400, easing = LinearEasing)), label = "ang")
    val c1 = C.accent; val c2 = C.container
    val brush = remember(c1, c2, a) { { center: Offset -> Brush.sweepGradient(listOf(Color.Transparent, c2.copy(alpha = a), c1.copy(alpha = a), Color.Transparent, Color.Transparent), center) } }
    Box(modifier.clip(RoundedCornerShape(radius)).drawBehind { rotate(angle) { drawCircle(brush(center), radius = this.size.maxDimension, center = center) } }.padding(2.5.dp * a)) { content() }
}

enum class OrbState { Idle, Listening, Thinking, Speaking }

/** Живой шар: кольца-волны при прослушивании, вращающиеся дуги при размышлении, пульс при речи. */
@Composable
fun LiveOrb(size: Dp, level: Float = 0f, state: OrbState = OrbState.Idle) {
    val t = rememberInfiniteTransition(label = "orb")
    val breathe by t.animateFloat(0.96f, 1.04f, infiniteRepeatable(tween(2400, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "b")
    val spin by t.animateFloat(0f, 360f, infiniteRepeatable(tween(if (state == OrbState.Thinking) 1100 else 9000, easing = LinearEasing)), label = "spin")
    val wave by t.animateFloat(0f, 1f, infiniteRepeatable(tween(2000, easing = LinearEasing)), label = "wave")
    val lv by animateFloatAsState(level, spring(dampingRatio = 0.6f, stiffness = 500f), label = "lv")
    val c1 = C.accent; val c2 = C.container
    val coreScale = breathe + lv * 0.28f
    Box(Modifier.size(size), contentAlignment = Alignment.Center) {
        // кольца
        if (state == OrbState.Listening || state == OrbState.Speaking) {
            repeat(3) { i ->
                val p = (wave + i / 3f) % 1f
                Box(Modifier.fillMaxSize(0.55f + p * 0.45f).alpha((1f - p) * (0.35f + lv)).border(2.dp, c1, CircleShape))
            }
        }
        // свечение
        Box(Modifier.fillMaxSize().scale(coreScale).background(Brush.radialGradient(listOf(c1.copy(alpha = 0.28f + lv * 0.4f), Color.Transparent)), CircleShape))
        // ядро с вращающимся градиентом
        Box(Modifier.fillMaxSize(0.56f).scale(coreScale).drawBehind {
            rotate(spin) { drawCircle(Brush.sweepGradient(listOf(c1, c2, c1.copy(alpha = 0.35f), c2, c1), center)) }
        })
        Box(Modifier.fillMaxSize(0.5f).scale(coreScale).background(Color.Black, CircleShape))
        // дуги «думаю»
        if (state == OrbState.Thinking) Box(Modifier.fillMaxSize(0.7f).drawBehind {
            rotate(-spin * 1.4f) { drawArc(c1, 0f, 100f, false, style = Stroke(5.dp.toPx(), cap = androidx.compose.ui.graphics.StrokeCap.Round)) }
            rotate(spin) { drawArc(c2, 180f, 70f, false, style = Stroke(5.dp.toPx(), cap = androidx.compose.ui.graphics.StrokeCap.Round)) }
        })
        Box(Modifier.fillMaxSize((0.2f + lv * 0.14f).coerceAtMost(0.4f)).background(c1, CircleShape))
    }
}

/** Плавное появление элемента с задержкой (для каскадов). */
@Composable
fun Staggered(index: Int, content: @Composable () -> Unit) {
    val a = remember { Animatable(0f) }
    LaunchedEffect(Unit) { kotlinx.coroutines.delay(index * 70L); a.animateTo(1f, spring(dampingRatio = 0.72f, stiffness = 260f)) }
    Box(Modifier.graphicsLayerCompat(a.value)) { content() }
}
private fun Modifier.graphicsLayerCompat(v: Float) = this.then(Modifier.alpha(v.coerceIn(0f, 1f)).offset(y = ((1f - v) * 28).dp).scale(0.94f + 0.06f * v))

/** Логотип приложения: совпадает с иконкой (тёмный фон + орбита, ядро и искра). */
@Composable
fun AppLogo(size: Dp, modifier: Modifier = Modifier) {
    androidx.compose.foundation.Canvas(modifier.size(size).clip(RoundedCornerShape(size * 0.28f))) {
        val s = this.size.minDimension
        drawRect(Brush.radialGradient(listOf(Color(0xFF2C2C36), Color(0xFF08080C)), Offset(s * 0.30f, s * 0.22f), s * 0.95f))
        drawMark(Offset(s / 2, s / 2), s / 108f, 1f)
    }
}

/** Знак приложения (без фона): орбита, ядро и искра. */
@Composable
fun SaturnMark(size: Dp, modifier: Modifier = Modifier, alpha: Float = 1f) {
    androidx.compose.foundation.Canvas(modifier.size(size)) { drawMark(center, this.size.minDimension / 62f, alpha) }
}

/** u — пикселей на единицу сетки 108×108 (как в иконке): кольцо R=22, ядро 9.2, искра на разрыве кольца. */
private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawMark(c: Offset, u: Float, alpha: Float = 1f) {
    val r = 22f * u; val w = 6.6f * u
    val ringBrush = Brush.linearGradient(listOf(Color.White.copy(alpha = alpha), Color(0xFF8C8D99).copy(alpha = alpha)), Offset(c.x - 24 * u, c.y - 24 * u), Offset(c.x + 26 * u, c.y + 26 * u))
    drawArc(ringBrush, -15f, 300f, false, Offset(c.x - r, c.y - r), androidx.compose.ui.geometry.Size(2 * r, 2 * r), style = Stroke(w, cap = androidx.compose.ui.graphics.StrokeCap.Round))
    drawCircle(Brush.linearGradient(listOf(Color.White.copy(alpha = alpha), Color(0xFFAAABB6).copy(alpha = alpha)), Offset(c.x - 10 * u, c.y - 12 * u), Offset(c.x + 10 * u, c.y + 12 * u)), 9.2f * u, c)
    val sx = c.x + 15.56f * u; val sy = c.y - 15.56f * u; val R = 9.5f * u
    drawCircle(Brush.radialGradient(listOf(Color.White.copy(alpha = 0.35f * alpha), Color.Transparent), Offset(sx, sy), R * 1.5f), R * 1.5f, Offset(sx, sy))
    val star = androidx.compose.ui.graphics.Path().apply {
        moveTo(sx, sy - R); quadraticBezierTo(sx, sy, sx + R, sy); quadraticBezierTo(sx, sy, sx, sy + R); quadraticBezierTo(sx, sy, sx - R, sy); quadraticBezierTo(sx, sy, sx, sy - R); close()
    }
    drawPath(star, Color.White.copy(alpha = alpha))
}

/** Официальный логотип Google «G» (4 цвета). */
@Composable
fun GoogleG(size: Dp) {
    val parts = remember {
        listOf(
            "M45.12 24.5c0-1.56-.14-3.06-.4-4.5H24v8.51h11.84c-.51 2.75-2.06 5.08-4.39 6.64v5.52h7.11c4.16-3.83 6.56-9.47 6.56-16.17z" to Color.White,
            "M24 46c5.94 0 10.92-1.97 14.56-5.33l-7.11-5.52c-1.97 1.32-4.49 2.1-7.45 2.1-5.73 0-10.58-3.87-12.31-9.07H4.34v5.7C7.96 41.07 15.4 46 24 46z" to Color.White,
            "M11.69 28.18C11.25 26.86 11 25.45 11 24s.25-2.86.69-4.18v-5.7H4.34C2.85 17.09 2 20.45 2 24c0 3.55.85 6.91 2.34 9.88l7.35-5.7z" to Color.White,
            "M24 10.75c3.23 0 6.13 1.11 8.41 3.29l6.31-6.31C34.91 4.18 29.93 2 24 2 15.4 2 7.96 6.93 4.34 14.12l7.35 5.7c1.73-5.2 6.58-9.07 12.31-9.07z" to Color.White,
        ).map { (d, col) -> androidx.compose.ui.graphics.vector.PathParser().parsePathString(d).toPath() to col }
    }
    androidx.compose.foundation.Canvas(Modifier.size(size)) {
        val k = this.size.minDimension / 48f
        parts.forEach { (p, col) -> val q = androidx.compose.ui.graphics.Path().apply { addPath(p) }; q.transform(androidx.compose.ui.graphics.Matrix().apply { scale(k, k) }); drawPath(q, col) }
    }
}


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


/** Анимация «эхо» для звонка: расходящиеся кольца, сила зависит от громкости (ваш голос или голос агента). Без иконки. */
@Composable
fun EchoRipples(level: Float, state: OrbState, modifier: Modifier = Modifier) {
    val t = rememberInfiniteTransition(label = "echo")
    val phase by t.animateFloat(0f, 1f, infiniteRepeatable(tween(2800, easing = LinearEasing)), label = "ph")
    val breathe by t.animateFloat(0.4f, 1f, infiniteRepeatable(tween(1600, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "br")
    val lv by animateFloatAsState(level.coerceIn(0f, 1f), tween(110), label = "lv")
    androidx.compose.foundation.Canvas(modifier) {
        val c = center; val maxR = size.minDimension / 2f
        val live = state == OrbState.Listening || state == OrbState.Speaking
        if (!live) return@Canvas                                   // «Думаю»/ожидание: без колец — только Сатурн
        val strength = when (state) { OrbState.Listening, OrbState.Speaking -> 0.25f + lv * 0.75f; OrbState.Thinking -> 0.3f * breathe; else -> 0.12f }
        // мягкое белое свечение в центре
        drawCircle(Brush.radialGradient(listOf(Color.White.copy(alpha = 0.06f + 0.16f * strength), Color.Transparent), c, maxR * (0.5f + 0.35f * strength)), radius = maxR)
        val rings = 5
        for (k in 0 until rings) {
            val p = if (state == OrbState.Thinking || state == OrbState.Idle) ((phase * 0.5f + k / rings.toFloat()) % 1f) else ((phase + k / rings.toFloat()) % 1f)
            val r = maxR * (0.14f + (0.86f * p) * (0.6f + 0.4f * strength))
            val a = ((1f - p) * (1f - p)) * (0.10f + 0.62f * strength) * (if (live) 1f else 0.7f)
            drawCircle(Color.White.copy(alpha = a.coerceIn(0f, 0.9f)), radius = r, center = c, style = androidx.compose.ui.graphics.drawscope.Stroke(width = (1.2f + 2.4f * strength * (1f - p)).dp.toPx()))
        }
    }
}
