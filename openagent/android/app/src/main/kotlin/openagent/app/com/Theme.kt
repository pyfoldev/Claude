package openagent.app.com

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.Density
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import android.os.Build

object C {
    var bg by mutableStateOf(Color(0xFF000000))            // чёрный
    var code by mutableStateOf(Color(0xFF060607))
    var surface by mutableStateOf(Color(0xFF0E0E10))
    var surface2 by mutableStateOf(Color(0xFF18181C))
    var surface3 by mutableStateOf(Color(0xFF222227))
    var outline by mutableStateOf(Color(0xFF35363D))
    var text by mutableStateOf(Color(0xFFEDEDF0))
    var dim by mutableStateOf(Color(0xFF9C9DA6))
    var accent by mutableStateOf(Color(0xFFC4C5CC))        // светло-серый
    var onAccent by mutableStateOf(Color(0xFF121214))
    var container by mutableStateOf(Color(0xFF2B2B30))
    var onContainer by mutableStateOf(Color(0xFFEDEDF0))
    var danger by mutableStateOf(Color(0xFFFFB4AB))
    var ok by mutableStateOf(Color(0xFF7FDB9C))
}

val Mono = TextStyle(fontFamily = FontFamily.Monospace)

private val fallback = darkColorScheme(
    primary = Color(0xFFC4C5CC), onPrimary = Color(0xFF121214), primaryContainer = Color(0xFF2B2B30), onPrimaryContainer = Color(0xFFEDEDF0),
    secondary = Color(0xFF9C9DA6), secondaryContainer = Color(0xFF232328), onSecondaryContainer = Color(0xFFE0E0E5),
    tertiary = Color(0xFFB0B1B8), background = Color.Black, surface = Color.Black, onSurface = Color(0xFFEDEDF0), onSurfaceVariant = Color(0xFF9C9DA6),
    surfaceContainerLowest = Color.Black, surfaceContainerLow = Color(0xFF0E0E10), surfaceContainer = Color(0xFF131316), surfaceContainerHigh = Color(0xFF18181C), surfaceContainerHighest = Color(0xFF222227),
    outline = Color(0xFF6E6F78), outlineVariant = Color(0xFF35363D), error = Color(0xFFFFB4AB),
)

val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(12.dp), small = RoundedCornerShape(16.dp), medium = RoundedCornerShape(22.dp),
    large = RoundedCornerShape(28.dp), extraLarge = RoundedCornerShape(36.dp),
)

private val AppTypography = Typography().let { t ->
    t.copy(
        bodyLarge = t.bodyLarge.copy(fontSize = 17.sp, lineHeight = 25.sp),
        bodyMedium = t.bodyMedium.copy(fontSize = 15.sp, lineHeight = 22.sp),
        titleLarge = t.titleLarge.copy(fontSize = 24.sp, fontWeight = FontWeight.SemiBold),
        titleMedium = t.titleMedium.copy(fontSize = 18.sp, fontWeight = FontWeight.Medium),
        labelLarge = t.labelLarge.copy(fontSize = 16.sp, fontWeight = FontWeight.Medium),
    )
}

@Composable
fun OpenAgentTheme(dynamic: Boolean, fontScale: Float, amoled: Boolean = false, content: @Composable () -> Unit) {
    val ctx = LocalContext.current
    val base = if (dynamic && Build.VERSION.SDK_INT >= 31) dynamicDarkColorScheme(ctx) else fallback
    // чёрный AMOLED-фон поверх любой палитры
    val isDyn = dynamic && Build.VERSION.SDK_INT >= 31
    val cs = if (!isDyn) (if (!amoled) base else base.copy(background = Color.Black, surface = Color.Black, surfaceContainerLowest = Color.Black, surfaceContainerLow = Color(0xFF0B0B0D), surfaceContainer = Color(0xFF111113), surfaceContainerHigh = Color(0xFF17171A), surfaceContainerHighest = Color(0xFF1F1F23))) else base.copy(
        background = Color.Black, surface = Color.Black, surfaceContainerLowest = Color.Black,
        surfaceContainerLow = base.surfaceContainerLow.lerpBlack(0.4f), surfaceContainer = base.surfaceContainer.lerpBlack(0.3f),
        surfaceContainerHigh = base.surfaceContainerHigh.lerpBlack(0.15f), surfaceContainerHighest = base.surfaceContainerHighest.lerpBlack(0.1f),
    )
    C.code = if (isDyn || amoled) Color.Black else Color(0xFF060607)
    C.bg = cs.background; C.surface = cs.surfaceContainerLow; C.surface2 = cs.surfaceContainerHigh; C.surface3 = cs.surfaceContainerHighest
    C.outline = cs.outlineVariant; C.text = cs.onSurface; C.dim = cs.onSurfaceVariant
    C.accent = cs.primary; C.onAccent = cs.onPrimary; C.container = cs.primaryContainer; C.onContainer = cs.onPrimaryContainer
    C.danger = Color(0xFFF2F2F5); C.ok = Color(0xFFD2D2D8)      // чёрно-белое оформление: без красного и зелёного
    val d = LocalDensity.current
    CompositionLocalProvider(LocalDensity provides Density(d.density, d.fontScale * fontScale)) {
        MaterialTheme(colorScheme = cs, typography = AppTypography, shapes = AppShapes, content = content)
    }
}

private fun Color.lerpBlack(f: Float) = androidx.compose.ui.graphics.lerp(this, Color.Black, f)

/** Haptic helper */
@Composable
fun rememberHaptic(enabled: Boolean): () -> Unit {
    val h = LocalHapticFeedback.current
    return remember(enabled) { { if (enabled) h.performHapticFeedback(HapticFeedbackType.TextHandleMove) } }
}

/** Три пульсирующие точки — индикатор «агент думает». */
@Composable
fun Thinking(modifier: Modifier = Modifier) {
    val t = rememberInfiniteTransition(label = "dots")
    Row(modifier.padding(vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
        repeat(3) { i ->
            val a by t.animateFloat(0.25f, 1f, infiniteRepeatable(tween(600, delayMillis = i * 150, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "d$i")
            Box(Modifier.size(7.dp).alpha(a).background(C.text, CircleShape))
        }
    }
}
