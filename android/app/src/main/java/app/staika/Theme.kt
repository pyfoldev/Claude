package app.staika

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Палитра: белая основная тема, нейтральные серые, яркий акцент только у персонажей. */
object C {
    val Bg = Color.White
    val Ink = Color(0xFF0B0B10)
    val Muted = Color(0xFF8C8C96)
    val Bubble = Color(0xFFF1F1F4)
    val Tile = Color(0xFFF1EBFC)
    val Line = Color(0xFFE9E9EF)
    val Accent = Color(0xFF7B5CF0)
    val Ok = Color(0xFF22B573)
    val Warn = Color(0xFFFF9F1C)
    val Bad = Color(0xFFE5484D)
    val Blue = Color(0xFF2F7BFF)
}

private val scheme = lightColorScheme(
    primary = C.Ink, onPrimary = Color.White,
    secondary = C.Accent, onSecondary = Color.White,
    background = C.Bg, onBackground = C.Ink,
    surface = Color.White, onSurface = C.Ink,
    surfaceVariant = C.Bubble, onSurfaceVariant = C.Muted,
    outline = C.Line,
)

private val type = Typography(
    headlineLarge = TextStyle(fontSize = 32.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.5).sp),
    headlineMedium = TextStyle(fontSize = 26.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.3).sp),
    titleLarge = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold),
    titleMedium = TextStyle(fontSize = 17.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontSize = 16.sp, lineHeight = 22.sp),
    bodyMedium = TextStyle(fontSize = 15.sp, lineHeight = 21.sp),
    bodySmall = TextStyle(fontSize = 13.sp, lineHeight = 18.sp),
    labelLarge = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.SemiBold),
    labelMedium = TextStyle(fontSize = 13.sp, fontWeight = FontWeight.Medium),
)

private val shapes = Shapes(
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(20.dp),
    large = RoundedCornerShape(28.dp),
)

@Composable
fun StaikaTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = scheme, typography = type, shapes = shapes, content = content)
}
