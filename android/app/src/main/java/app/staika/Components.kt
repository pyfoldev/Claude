package app.staika

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.ChevronLeft
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

/** Нажатие с упругим «проседанием» без ряби. */
fun Modifier.bounceClick(enabled: Boolean = true, down: Float = 0.94f, onClick: () -> Unit): Modifier = composed {
    val src = remember { MutableInteractionSource() }
    val pressed by src.collectIsPressedAsState()
    val s by animateFloatAsState(if (pressed) down else 1f, spring(dampingRatio = 0.5f, stiffness = 600f), label = "press")
    this.graphicsLayer { scaleX = s; scaleY = s }
        .clickable(interactionSource = src, indication = null, enabled = enabled, onClick = onClick)
}

/** Плавное появление: прозрачность и подъём, с задержкой по номеру элемента. */
fun Modifier.appear(index: Int = 0, dy: Dp = 18.dp): Modifier = composed {
    val a = remember { Animatable(0f) }
    val px = with(androidx.compose.ui.platform.LocalDensity.current) { dy.toPx() }
    LaunchedEffect(Unit) {
        delay(index.coerceAtMost(14) * 38L)
        a.animateTo(1f, tween(430, easing = EaseOutCubic))
    }
    this.graphicsLayer { alpha = a.value; translationY = (1f - a.value) * px }
}

@Composable
fun Avatar(pal: Pal, size: Dp, modifier: Modifier = Modifier, chief: Boolean = false, status: Status? = null) {
    val breathe = rememberInfiniteTransition(label = "breathe")
    val k by breathe.animateFloat(
        1f, 1.05f, infiniteRepeatable(tween(1200, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "k",
    )
    val sc = if (status == Status.Working) k else 1f
    Box(modifier.size(size)) {
        Image(painterResource(pal.img), null, Modifier.fillMaxSize().scale(sc), contentScale = ContentScale.Fit)
        if (chief) {
            Box(
                Modifier.align(Alignment.BottomEnd).size(size * 0.34f).clip(CircleShape).background(C.Warn).border(2.dp, Color.White, CircleShape),
                Alignment.Center,
            ) { Icon(Icons.Filled.Star, null, tint = Color.White, modifier = Modifier.size(size * 0.2f)) }
        }
        if (status != null && status != Status.Idle) {
            val c = if (status == Status.Working) C.Ok else C.Warn
            Box(Modifier.align(Alignment.TopEnd).size(size * 0.22f).clip(CircleShape).background(c).border(2.dp, Color.White, CircleShape))
        }
    }
}

/** Круглая кнопка-иконка: белая, тонкая рамка и мягкая тень. */
@Composable
fun IconPill(icon: ImageVector, onClick: () -> Unit, modifier: Modifier = Modifier, size: Dp = 46.dp, tint: Color = C.Ink, fill: Color = Color.White) {
    Box(
        modifier.size(size).shadow(4.dp, CircleShape, ambientColor = C.Shadow, spotColor = C.Shadow).clip(CircleShape).background(fill)
            .border(1.dp, C.Line, CircleShape).bounceClick(onClick = onClick),
        Alignment.Center,
    ) { Icon(icon, null, tint = tint, modifier = Modifier.size(size * 0.52f)) }
}

@Composable
fun BackPill(onBack: () -> Unit) = IconPill(Icons.Outlined.ChevronLeft, onBack)

@Composable
fun BlackButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    Box(
        modifier.fillMaxWidth().height(56.dp).bounceClick(enabled = enabled, down = 0.97f, onClick = onClick)
            .clip(CircleShape).background(if (enabled) C.Ink else Color(0xFFCFCFD6)),
        Alignment.Center,
    ) { Text(text, color = Color.White, fontSize = 17.sp, fontWeight = FontWeight.SemiBold) }
}

@Composable
fun GrayButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, leading: (@Composable () -> Unit)? = null) {
    Row(
        modifier.fillMaxWidth().height(56.dp).bounceClick(down = 0.97f, onClick = onClick).clip(CircleShape).background(C.Bubble),
        Arrangement.Center, Alignment.CenterVertically,
    ) {
        leading?.let { it(); Spacer(Modifier.width(10.dp)) }
        Text(text, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun PillField(
    value: String, onChange: (String) -> Unit, placeholder: String, modifier: Modifier = Modifier,
    password: Boolean = false, keyboard: KeyboardType = KeyboardType.Text,
    shape: androidx.compose.ui.graphics.Shape = CircleShape, singleLine: Boolean = true,
    trailing: (@Composable () -> Unit)? = null,
) {
    TextField(
        value, onChange, modifier.fillMaxWidth().clip(shape),
        placeholder = { Text(placeholder, color = C.Muted, fontSize = 17.sp) },
        textStyle = MaterialTheme.typography.bodyLarge,
        singleLine = singleLine, minLines = if (singleLine) 1 else 3,
        visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = keyboard),
        trailingIcon = trailing,
        colors = TextFieldDefaults.colors(
            focusedContainerColor = C.Field, unfocusedContainerColor = C.Field,
            focusedIndicatorColor = Color.Transparent, unfocusedIndicatorColor = Color.Transparent, cursorColor = C.Ink,
        ),
    )
}

@Composable
fun ScreenTop(title: String, onBack: () -> Unit, trailing: @Composable RowScope.() -> Unit = {}) {
    Row(
        Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        BackPill(onBack)
        Spacer(Modifier.width(12.dp))
        Text(title, style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
        trailing()
    }
}

@Composable
fun StatusChip(status: Status) {
    val c = when (status) { Status.Idle -> C.Muted; Status.Working -> C.Ok; Status.Waiting -> C.Warn }
    Row(
        Modifier.clip(CircleShape).background(c.copy(alpha = 0.12f)).padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(7.dp).clip(CircleShape).background(c))
        Spacer(Modifier.width(6.dp))
        Text(status.label, color = c, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun Chip(text: String, selected: Boolean, onClick: () -> Unit) {
    val bg by animateColorAsState(if (selected) C.Ink else C.Bubble, tween(220), label = "chipBg")
    val fg by animateColorAsState(if (selected) Color.White else C.Ink, tween(220), label = "chipFg")
    Box(Modifier.bounceClick(onClick = onClick).clip(CircleShape).background(bg).padding(horizontal = 18.dp, vertical = 11.dp)) {
        Text(text, color = fg, fontSize = 15.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) =
    Text(text, color = C.Muted, fontSize = 15.sp, modifier = modifier.padding(horizontal = 20.dp, vertical = 8.dp))

@Composable
fun Card(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(Color.White)
            .border(1.dp, C.Line, RoundedCornerShape(24.dp)).padding(16.dp),
        content = content,
    )
}

@Composable
fun GlyphBadge(glyph: String, color: Long, size: Dp = 50.dp) {
    Box(
        Modifier.size(size).clip(RoundedCornerShape(size * 0.3f)).background(Color.White).border(1.dp, C.Line, RoundedCornerShape(size * 0.3f)),
        Alignment.Center,
    ) { Text(glyph, color = Color(color), fontWeight = FontWeight.Bold, fontSize = (size.value * 0.38f).sp) }
}

@Composable
fun Toggle(on: Boolean, onChange: (Boolean) -> Unit) {
    Switch(
        on, onChange,
        colors = SwitchDefaults.colors(
            checkedTrackColor = C.Ink, checkedThumbColor = Color.White, checkedBorderColor = Color.Transparent,
            uncheckedTrackColor = Color(0xFFDADAE0), uncheckedThumbColor = Color.White, uncheckedBorderColor = Color.Transparent,
        ),
    )
}

/** Полоса прогресса без стоп-индикатора Material; значение анимируется снаружи. */
@Composable
fun ProgressBar(progress: Float, modifier: Modifier = Modifier, color: Color = C.Ink, track: Color = C.Bubble, height: Dp = 6.dp) {
    Box(modifier.fillMaxWidth().height(height).clip(CircleShape).background(track)) {
        Box(Modifier.fillMaxHeight().fillMaxWidth(progress.coerceIn(0f, 1f)).clip(CircleShape).background(color))
    }
}
