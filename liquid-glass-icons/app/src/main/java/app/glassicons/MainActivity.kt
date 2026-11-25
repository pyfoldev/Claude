package app.glassicons

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AccountBalanceWallet
import androidx.compose.material.icons.rounded.Bolt
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.CameraAlt
import androidx.compose.material.icons.rounded.ChatBubble
import androidx.compose.material.icons.rounded.Cloud
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.Folder
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Language
import androidx.compose.material.icons.rounded.Mail
import androidx.compose.material.icons.rounded.Map
import androidx.compose.material.icons.rounded.MenuBook
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.MusicNote
import androidx.compose.material.icons.rounded.Phone
import androidx.compose.material.icons.rounded.Photo
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Schedule
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.ShoppingBag
import androidx.compose.material.icons.rounded.SportsEsports
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.StickyNote2
import androidx.compose.material.icons.rounded.Videocam
import androidx.compose.material.icons.rounded.Wifi
import androidx.compose.material3.Icon
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.layer.drawLayer
import androidx.compose.ui.graphics.layer.toImageBitmap
import androidx.compose.ui.graphics.rememberGraphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.core.content.pm.ShortcutInfoCompat
import androidx.core.content.pm.ShortcutManagerCompat
import androidx.core.graphics.drawable.IconCompat
import kotlinx.coroutines.launch

// ---------------------------------------------------------------- data

data class GlassItem(val id: String, val label: String, val icon: ImageVector, val hue: Float)

val items = listOf(
    GlassItem("phone", "Телефон", Icons.Rounded.Phone, 145f),
    GlassItem("chat", "Сообщения", Icons.Rounded.ChatBubble, 120f),
    GlassItem("camera", "Камера", Icons.Rounded.CameraAlt, 215f),
    GlassItem("photo", "Фото", Icons.Rounded.Photo, 330f),
    GlassItem("music", "Музыка", Icons.Rounded.MusicNote, 350f),
    GlassItem("mail", "Почта", Icons.Rounded.Mail, 205f),
    GlassItem("map", "Карты", Icons.Rounded.Map, 160f),
    GlassItem("cloud", "Погода", Icons.Rounded.Cloud, 195f),
    GlassItem("settings", "Настройки", Icons.Rounded.Settings, 225f),
    GlassItem("calendar", "Календарь", Icons.Rounded.CalendarMonth, 10f),
    GlassItem("clock", "Часы", Icons.Rounded.Schedule, 260f),
    GlassItem("notes", "Заметки", Icons.Rounded.StickyNote2, 48f),
    GlassItem("shop", "Магазин", Icons.Rounded.ShoppingBag, 25f),
    GlassItem("wallet", "Кошелёк", Icons.Rounded.AccountBalanceWallet, 170f),
    GlassItem("health", "Здоровье", Icons.Rounded.Favorite, 340f),
    GlassItem("video", "Видео", Icons.Rounded.PlayArrow, 0f),
    GlassItem("files", "Файлы", Icons.Rounded.Folder, 38f),
    GlassItem("wifi", "Сеть", Icons.Rounded.Wifi, 200f),
    GlassItem("power", "Энергия", Icons.Rounded.Bolt, 55f),
    GlassItem("fav", "Избранное", Icons.Rounded.Star, 45f),
    GlassItem("home", "Дом", Icons.Rounded.Home, 280f),
    GlassItem("search", "Поиск", Icons.Rounded.Search, 235f),
    GlassItem("games", "Игры", Icons.Rounded.SportsEsports, 300f),
    GlassItem("books", "Книги", Icons.Rounded.MenuBook, 20f),
    GlassItem("web", "Браузер", Icons.Rounded.Language, 185f),
    GlassItem("rec", "Камера 2", Icons.Rounded.Videocam, 315f),
    GlassItem("voice", "Диктофон", Icons.Rounded.Mic, 5f),
)

/** Параметры стекла, общие для всех иконок. */
class GlassStyle(
    val opacity: Float,   // 0..1 — насколько плотное стекло
    val hueShift: Float,  // 0..360 — сдвиг оттенка
    val corner: Float,    // 0.2..0.5 — доля стороны, скругление
    val shine: Float,     // 0..1 — яркость бликов
)

fun tintOf(item: GlassItem, s: GlassStyle): Color =
    Color.hsv((item.hue + s.hueShift) % 360f, 0.62f, 1f)

// ---------------------------------------------------------------- activity

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { GlassApp() }
    }
}

// ---------------------------------------------------------------- screen

@Composable
fun GlassApp() {
    var opacity by remember { mutableFloatStateOf(0.45f) }
    var hueShift by remember { mutableFloatStateOf(0f) }
    var corner by remember { mutableFloatStateOf(0.32f) }
    var shine by remember { mutableFloatStateOf(0.8f) }
    var selected by remember { mutableStateOf<GlassItem?>(null) }
    val style = GlassStyle(opacity, hueShift, corner, shine)

    Box(Modifier.fillMaxSize().background(Color(0xFF0B1020))) {
        LiquidBackdrop()

        Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
            Column(Modifier.padding(horizontal = 20.dp, vertical = 16.dp)) {
                Text("Жидкое стекло", color = Color.White, fontSize = 28.sp, fontWeight = FontWeight.Bold)
                Text(
                    "Нажмите на иконку, чтобы добавить её на главный экран",
                    color = Color.White.copy(alpha = 0.65f),
                    fontSize = 13.sp,
                )
            }

            LazyVerticalGrid(
                columns = GridCells.Adaptive(82.dp),
                modifier = Modifier.weight(1f),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                items(items, key = { it.id }) { item ->
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier.clip(RoundedCornerShape(16.dp)).clickable { selected = item }.padding(4.dp),
                    ) {
                        GlassTile(item, style, 64.dp)
                        Text(
                            item.label,
                            color = Color.White.copy(alpha = 0.9f),
                            fontSize = 11.sp,
                            textAlign = TextAlign.Center,
                            maxLines = 1,
                            modifier = Modifier.padding(top = 6.dp),
                        )
                    }
                }
            }

            ControlPanel(
                style = style,
                onOpacity = { opacity = it },
                onHue = { hueShift = it },
                onCorner = { corner = it },
                onShine = { shine = it },
            )
        }

        selected?.let { PinDialog(it, style) { selected = null } }
    }
}

// ---------------------------------------------------------------- backdrop

/** Медленно плывущие цветные пятна: стеклу есть что преломлять. */
@Composable
fun LiquidBackdrop() {
    val t = rememberInfiniteTransition(label = "blobs")
    val p by t.animateFloat(
        0f, 1f,
        infiniteRepeatable(tween(18000, easing = LinearEasing), RepeatMode.Reverse),
        label = "p",
    )
    Canvas(Modifier.fillMaxSize().blur(70.dp)) {
        val w = size.width
        val h = size.height
        fun blob(color: Color, cx: Float, cy: Float, r: Float) =
            drawCircle(color, radius = r, center = Offset(cx, cy))
        blob(Color(0xFF3B82F6), w * (0.2f + 0.5f * p), h * (0.15f + 0.1f * p), w * 0.45f)
        blob(Color(0xFFEC4899), w * (0.9f - 0.5f * p), h * (0.45f + 0.1f * p), w * 0.42f)
        blob(Color(0xFF22D3AA), w * (0.1f + 0.4f * p), h * (0.75f - 0.15f * p), w * 0.40f)
        blob(Color(0xFFF59E0B), w * (0.8f - 0.3f * p), h * (0.95f - 0.1f * p), w * 0.30f)
    }
}

// ---------------------------------------------------------------- glass tile

@Composable
fun GlassTile(item: GlassItem, s: GlassStyle, size: Dp, shadow: Boolean = true) {
    val tint = tintOf(item, s)
    val shape = RoundedCornerShape(size * s.corner)
    val a = s.opacity

    Box(
        modifier = Modifier
            .size(size)
            .then(
                if (shadow) Modifier.shadow(
                    elevation = size / 6,
                    shape = shape,
                    ambientColor = tint,
                    spotColor = tint,
                ) else Modifier
            )
            .clip(shape)
            // тело стекла: цвет внизу, почти прозрачно вверху
            .background(
                Brush.linearGradient(
                    0f to Color.White.copy(alpha = 0.10f + 0.25f * a),
                    1f to tint.copy(alpha = 0.20f + 0.60f * a),
                )
            )
            // внутреннее свечение снизу справа, как свет, прошедший сквозь край
            .drawWithContent {
                drawContent()
                drawRect(
                    Brush.radialGradient(
                        colors = listOf(tint.copy(alpha = 0.55f * a + 0.1f), Color.Transparent),
                        center = Offset(this.size.width * 0.8f, this.size.height * 1.0f),
                        radius = this.size.width * 0.9f,
                    )
                )
                drawSpecular(s.shine)
            }
            // кромка: яркая сверху-слева, тусклая снизу-справа
            .border(
                width = (size.value / 40f).coerceAtLeast(1f).dp,
                brush = Brush.linearGradient(
                    0f to Color.White.copy(alpha = 0.95f * s.shine),
                    0.45f to Color.White.copy(alpha = 0.10f),
                    0.55f to Color.White.copy(alpha = 0.10f),
                    1f to Color.White.copy(alpha = 0.55f * s.shine),
                ),
                shape = shape,
            ),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = item.icon,
            contentDescription = item.label,
            tint = Color.White.copy(alpha = 0.96f),
            modifier = Modifier.size(size * 0.52f),
        )
    }
}

/** Блик сверху и узкая полоска света у нижней кромки. */
private fun DrawScope.drawSpecular(shine: Float) {
    val w = size.width
    val h = size.height
    drawOval(
        brush = Brush.verticalGradient(
            0f to Color.White.copy(alpha = 0.55f * shine),
            1f to Color.Transparent,
            startY = h * 0.04f,
            endY = h * 0.5f,
        ),
        topLeft = Offset(w * 0.08f, h * 0.04f),
        size = Size(w * 0.84f, h * 0.46f),
    )
    drawRect(
        brush = Brush.horizontalGradient(
            0f to Color.Transparent,
            0.5f to Color.White.copy(alpha = 0.35f * shine),
            1f to Color.Transparent,
        ),
        topLeft = Offset(w * 0.18f, h * 0.93f),
        size = Size(w * 0.64f, h * 0.025f),
    )
}

// ---------------------------------------------------------------- controls

@Composable
fun ControlPanel(
    style: GlassStyle,
    onOpacity: (Float) -> Unit,
    onHue: (Float) -> Unit,
    onCorner: (Float) -> Unit,
    onShine: (Float) -> Unit,
) {
    val shape = RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp)
    Column(
        Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(Color.White.copy(alpha = 0.10f))
            .border(1.dp, Color.White.copy(alpha = 0.25f), shape)
            .padding(horizontal = 20.dp, vertical = 12.dp),
    ) {
        LabeledSlider("Плотность", style.opacity, 0f..1f, onOpacity)
        LabeledSlider("Оттенок", style.hueShift, 0f..360f, onHue)
        LabeledSlider("Скругление", style.corner, 0.2f..0.5f, onCorner)
        LabeledSlider("Блики", style.shine, 0f..1f, onShine)
    }
}

@Composable
fun LabeledSlider(label: String, value: Float, range: ClosedFloatingPointRange<Float>, onChange: (Float) -> Unit) {
    Column {
        Text(label, color = Color.White.copy(alpha = 0.8f), fontSize = 12.sp)
        Slider(
            value = value,
            onValueChange = onChange,
            valueRange = range,
            colors = SliderDefaults.colors(
                thumbColor = Color.White,
                activeTrackColor = Color.White.copy(alpha = 0.85f),
                inactiveTrackColor = Color.White.copy(alpha = 0.22f),
            ),
        )
    }
}

// ---------------------------------------------------------------- pin to home screen

@Composable
fun PinDialog(item: GlassItem, style: GlassStyle, onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val layer = rememberGraphicsLayer()
    val cardShape = RoundedCornerShape(32.dp)

    Dialog(onDismissRequest = onDismiss) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier
                .clip(cardShape)
                .background(Color(0xCC1B2340))
                .border(1.dp, Color.White.copy(alpha = 0.3f), cardShape)
                .padding(24.dp),
        ) {
            // этот блок снимается в картинку для ярлыка
            Box(
                Modifier
                    .padding(8.dp)
                    .drawWithContent {
                        layer.record { this@drawWithContent.drawContent() }
                        drawLayer(layer)
                    }
            ) {
                GlassTile(item, style, 160.dp, shadow = false)
            }
            Text(
                item.label,
                color = Color.White,
                fontSize = 20.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(top = 16.dp),
            )
            Box(
                Modifier
                    .padding(top = 20.dp)
                    .clip(RoundedCornerShape(50))
                    .background(Color.White.copy(alpha = 0.18f))
                    .border(1.dp, Color.White.copy(alpha = 0.4f), RoundedCornerShape(50))
                    .clickable {
                        scope.launch {
                            val bmp = layer.toImageBitmap().asAndroidBitmap()
                            pinShortcut(ctx, item, bmp)
                            onDismiss()
                        }
                    }
                    .padding(horizontal = 28.dp, vertical = 12.dp),
            ) {
                Text("На главный экран", color = Color.White, fontWeight = FontWeight.Medium)
            }
        }
    }
}

fun pinShortcut(ctx: Context, item: GlassItem, bitmap: Bitmap) {
    if (!ShortcutManagerCompat.isRequestPinShortcutSupported(ctx)) {
        Toast.makeText(ctx, "Лаунчер не поддерживает закрепление ярлыков", Toast.LENGTH_LONG).show()
        return
    }
    val intent = Intent(ctx, MainActivity::class.java).setAction(Intent.ACTION_VIEW)
    val info = ShortcutInfoCompat.Builder(ctx, "glass_${item.id}_${System.currentTimeMillis()}")
        .setShortLabel(item.label)
        .setIcon(IconCompat.createWithBitmap(bitmap))
        .setIntent(intent)
        .build()
    ShortcutManagerCompat.requestPinShortcut(ctx, info, null)
}
