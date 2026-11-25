package app.staika

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.Send
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Tune
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun PluginsScreen(onBack: () -> Unit) {
    var q by remember { mutableStateOf("") }
    val shown = toolCatalog.filter { q.isBlank() || it.name.contains(q, true) || it.desc.contains(q, true) }
    val flat = buildList<Any> { shown.groupBy { it.group }.forEach { (g, l) -> add(g); addAll(l) } }

    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Плагины", onBack)
        PillField(q, { q = it }, "Поиск", Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            trailing = { Icon(Icons.Outlined.Search, null, tint = C.Muted, modifier = Modifier.padding(end = 8.dp)) })
        LazyColumn(contentPadding = PaddingValues(bottom = 28.dp)) {
            itemsIndexed(flat, key = { _, it -> if (it is ToolInfo) it.name else it.toString() }) { i, item ->
                if (item is String) {
                    Text(item, color = C.Muted, fontSize = 15.sp, modifier = Modifier.appear(i).padding(horizontal = 20.dp, vertical = 12.dp))
                } else if (item is ToolInfo) {
                    Row(Modifier.fillMaxWidth().appear(i).padding(horizontal = 16.dp, vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
                        BrandTile(item)
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f)) {
                            Text(item.name, fontWeight = FontWeight.SemiBold, fontSize = 18.sp)
                            Text(item.desc, color = C.Muted, fontSize = 15.sp, maxLines = 2, lineHeight = 20.sp)
                        }
                        Spacer(Modifier.width(10.dp))
                        Row(
                            Modifier.clip(CircleShape).background(if (item.ready) C.Ok.copy(alpha = 0.12f) else C.Bubble).padding(horizontal = 15.dp, vertical = 9.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            if (item.ready) { Icon(Icons.Outlined.Check, null, tint = C.Ok, modifier = Modifier.size(17.dp)); Spacer(Modifier.width(4.dp)) }
                            Text(if (item.ready) "Включено" else "Скоро", color = if (item.ready) C.Ok else C.Muted, fontSize = 15.sp, fontWeight = FontWeight.Medium)
                        }
                    }
                }
            }
        }
    }
}

/** Узнаваемые значки основных сервисов, остальные: цветная буква. */
@Composable
private fun BrandTile(p: ToolInfo) {
    val shape = androidx.compose.foundation.shape.RoundedCornerShape(15.dp)
    Box(Modifier.size(50.dp).clip(shape).background(Color.White).border(1.dp, C.Line, shape), Alignment.Center) {
        when (p.name) {
            "Gmail" -> androidx.compose.foundation.Canvas(Modifier.size(30.dp)) {
                val w = size.width; val sw = w * 0.15f
                fun l(c: Color, x1: Float, y1: Float, x2: Float, y2: Float) =
                    drawLine(c, androidx.compose.ui.geometry.Offset(x1 * w, y1 * w), androidx.compose.ui.geometry.Offset(x2 * w, y2 * w), sw, androidx.compose.ui.graphics.StrokeCap.Round)
                l(Color(0xFF4285F4), 0.16f, 0.78f, 0.16f, 0.30f)
                l(Color(0xFF34A853), 0.84f, 0.78f, 0.84f, 0.30f)
                l(Color(0xFFEA4335), 0.16f, 0.30f, 0.50f, 0.58f)
                l(Color(0xFFEA4335), 0.84f, 0.30f, 0.50f, 0.58f)
            }
            "Google Календарь" -> Box(Modifier.size(30.dp).clip(androidx.compose.foundation.shape.RoundedCornerShape(6.dp)).background(Color(0xFF4285F4)), Alignment.Center) {
                Box(Modifier.size(22.dp).clip(androidx.compose.foundation.shape.RoundedCornerShape(4.dp)).background(Color.White), Alignment.Center) {
                    Text("31", color = Color(0xFF4285F4), fontSize = 12.sp, fontWeight = FontWeight.Bold)
                }
            }
            "Google Диск" -> androidx.compose.foundation.Canvas(Modifier.size(30.dp)) {
                val w = size.width; val sw = w * 0.17f
                fun l(c: Color, x1: Float, y1: Float, x2: Float, y2: Float) =
                    drawLine(c, androidx.compose.ui.geometry.Offset(x1 * w, y1 * w), androidx.compose.ui.geometry.Offset(x2 * w, y2 * w), sw, androidx.compose.ui.graphics.StrokeCap.Round)
                l(Color(0xFF34A853), 0.40f, 0.18f, 0.14f, 0.66f)
                l(Color(0xFFFBBC04), 0.60f, 0.18f, 0.86f, 0.66f)
                l(Color(0xFF4285F4), 0.20f, 0.80f, 0.80f, 0.80f)
            }
            "Telegram" -> Box(Modifier.size(30.dp).clip(CircleShape).background(Color(0xFF229ED9)), Alignment.Center) {
                Icon(Icons.Outlined.Send, null, tint = Color.White, modifier = Modifier.size(16.dp))
            }
            else -> Text(p.glyph, color = Color(p.color), fontWeight = FontWeight.Bold, fontSize = 20.sp)
        }
    }
}
