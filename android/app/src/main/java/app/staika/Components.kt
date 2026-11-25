package app.staika

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
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

@Composable
fun Avatar(
    pal: Pal, size: Dp, modifier: Modifier = Modifier,
    chief: Boolean = false, status: Status? = null,
) {
    val breathe = rememberInfiniteTransition(label = "breathe")
    val k by breathe.animateFloat(
        1f, 1.045f,
        infiniteRepeatable(tween(1100, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "k",
    )
    val sc = if (status == Status.Working) k else 1f
    Box(modifier.size(size)) {
        Image(
            painterResource(pal.img), null,
            Modifier.fillMaxSize().scale(sc),
            contentScale = ContentScale.Fit,
        )
        if (chief) {
            Box(
                Modifier.align(Alignment.BottomEnd).size(size * 0.34f).clip(CircleShape)
                    .background(C.Warn).border(2.dp, Color.White, CircleShape),
                Alignment.Center,
            ) { Icon(Icons.Rounded.Star, null, tint = Color.White, modifier = Modifier.size(size * 0.2f)) }
        }
        if (status != null && status != Status.Idle) {
            val c = if (status == Status.Working) C.Ok else C.Warn
            Box(
                Modifier.align(Alignment.TopEnd).size(size * 0.22f).clip(CircleShape)
                    .background(c).border(2.dp, Color.White, CircleShape),
            )
        }
    }
}

@Composable
fun IconPill(icon: ImageVector, onClick: () -> Unit, modifier: Modifier = Modifier, size: Dp = 44.dp, tint: Color = C.Ink) {
    Surface(shape = CircleShape, color = Color.White, shadowElevation = 5.dp, modifier = modifier.size(size)) {
        Box(Modifier.fillMaxSize().clip(CircleShape).clickable(onClick = onClick), Alignment.Center) {
            Icon(icon, null, tint = tint, modifier = Modifier.size(size * 0.5f))
        }
    }
}

@Composable
fun BackPill(onBack: () -> Unit) = IconPill(Icons.AutoMirrored.Rounded.ArrowBack, onBack)

@Composable
fun BlackButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    Button(
        onClick, modifier.fillMaxWidth().height(54.dp), enabled = enabled, shape = CircleShape,
        colors = ButtonDefaults.buttonColors(
            containerColor = C.Ink, contentColor = Color.White,
            disabledContainerColor = Color(0xFFCFCFD6), disabledContentColor = Color.White,
        ),
    ) { Text(text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold) }
}

@Composable
fun GrayButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, leading: (@Composable () -> Unit)? = null) {
    Button(
        onClick, modifier.fillMaxWidth().height(54.dp), shape = CircleShape,
        colors = ButtonDefaults.buttonColors(containerColor = C.Bubble, contentColor = C.Ink),
    ) {
        leading?.let { it(); Spacer(Modifier.width(10.dp)) }
        Text(text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
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
        placeholder = { Text(placeholder, color = C.Muted) },
        singleLine = singleLine, minLines = if (singleLine) 1 else 3,
        visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = keyboard),
        trailingIcon = trailing,
        colors = TextFieldDefaults.colors(
            focusedContainerColor = C.Bubble, unfocusedContainerColor = C.Bubble,
            focusedIndicatorColor = Color.Transparent, unfocusedIndicatorColor = Color.Transparent,
            cursorColor = C.Ink,
        ),
    )
}

@Composable
fun ScreenTop(title: String, onBack: () -> Unit, trailing: @Composable RowScope.() -> Unit = {}) {
    Row(
        Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        BackPill(onBack)
        Spacer(Modifier.width(14.dp))
        Text(title, style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
        trailing()
    }
}

@Composable
fun StatusChip(status: Status) {
    val c = when (status) { Status.Idle -> C.Muted; Status.Working -> C.Ok; Status.Waiting -> C.Warn }
    Row(
        Modifier.clip(CircleShape).background(c.copy(alpha = 0.12f)).padding(horizontal = 10.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(7.dp).clip(CircleShape).background(c))
        Spacer(Modifier.width(6.dp))
        Text(status.label, color = c, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun Chip(text: String, selected: Boolean, onClick: () -> Unit) {
    Box(
        Modifier.clip(CircleShape).background(if (selected) C.Ink else C.Bubble).clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 9.dp),
    ) { Text(text, color = if (selected) Color.White else C.Ink, fontSize = 14.sp, fontWeight = FontWeight.Medium) }
}

@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) =
    Text(text, color = C.Muted, fontSize = 14.sp, modifier = modifier.padding(horizontal = 20.dp, vertical = 8.dp))

@Composable
fun Card(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier.fillMaxWidth().shadow(0.dp).clip(RoundedCornerShape(22.dp)).background(Color.White)
            .border(1.dp, C.Line, RoundedCornerShape(22.dp)).padding(16.dp),
        content = content,
    )
}

@Composable
fun GlyphBadge(glyph: String, color: Long, size: Dp = 46.dp) {
    Box(
        Modifier.size(size).clip(RoundedCornerShape(size * 0.28f)).background(Color(color).copy(alpha = 0.12f)),
        Alignment.Center,
    ) { Text(glyph, color = Color(color), fontWeight = FontWeight.Bold, fontSize = (size.value * 0.36f).sp) }
}

@Composable
fun Toggle(on: Boolean, onChange: (Boolean) -> Unit) {
    Switch(
        on, onChange,
        colors = SwitchDefaults.colors(
            checkedTrackColor = C.Ink, checkedThumbColor = Color.White,
            uncheckedTrackColor = Color(0xFFDADAE0), uncheckedThumbColor = Color.White, uncheckedBorderColor = Color.Transparent,
        ),
    )
}
