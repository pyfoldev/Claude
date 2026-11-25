package app.staika

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

val Inter = FontFamily(
    Font(R.font.inter_regular, FontWeight.Normal),
    Font(R.font.inter_medium, FontWeight.Medium),
    Font(R.font.inter_semibold, FontWeight.SemiBold),
    Font(R.font.inter_bold, FontWeight.Bold),
)

/** Палитра: белая тема, нейтральные серые, цвет приносят только персонажи. */
object C {
    val Bg = Color.White
    val Ink = Color(0xFF0A0A0B)
    val Muted = Color(0xFF8E8E96)
    val Bubble = Color(0xFFF1F1F3)
    val Field = Color(0xFFF1F1F3)
    val Tile = Color(0xFFF1EBFC)
    val Line = Color(0xFFE9E9ED)
    val Accent = Color(0xFF7B5CF0)
    val Ok = Color(0xFF30B566)
    val Warn = Color(0xFFFF9500)
    val Bad = Color(0xFFE5484D)
    val Blue = Color(0xFF2F7BFF)
    val Shadow = Color(0x26000000)
}

private val scheme = lightColorScheme(
    primary = C.Ink, onPrimary = Color.White,
    secondary = C.Accent, onSecondary = Color.White,
    background = C.Bg, onBackground = C.Ink,
    surface = Color.White, onSurface = C.Ink,
    surfaceVariant = C.Bubble, onSurfaceVariant = C.Muted,
    outline = C.Line,
)

private fun t(size: Int, w: FontWeight, line: Int = 0, ls: Double = 0.0) =
    TextStyle(fontFamily = Inter, fontSize = size.sp, fontWeight = w, lineHeight = if (line > 0) line.sp else TextStyle.Default.lineHeight, letterSpacing = ls.sp)

private val type = Typography(
    headlineLarge = t(40, FontWeight.Bold, ls = -1.0),
    headlineMedium = t(30, FontWeight.Bold, ls = -0.6),
    titleLarge = t(22, FontWeight.SemiBold, ls = -0.3),
    titleMedium = t(18, FontWeight.SemiBold, ls = -0.2),
    bodyLarge = t(17, FontWeight.Normal, 23),
    bodyMedium = t(16, FontWeight.Normal, 22),
    bodySmall = t(14, FontWeight.Normal, 19),
    labelLarge = t(16, FontWeight.SemiBold),
    labelMedium = t(14, FontWeight.Medium),
)

private val shapes = Shapes(small = RoundedCornerShape(12.dp), medium = RoundedCornerShape(20.dp), large = RoundedCornerShape(28.dp))

@Composable
fun StaikaTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = scheme, typography = type, shapes = shapes, content = content)
}
