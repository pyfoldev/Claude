package app.staika

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Search
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
    val added = remember { mutableStateMapOf<String, Boolean>().also { m -> Store.plugins.forEach { m[it.name] = it.added } } }
    val shown = Store.plugins.filter { q.isBlank() || it.name.contains(q, true) || it.desc.contains(q, true) }

    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Плагины", onBack)
        PillField(q, { q = it }, "Поиск среди 130+ плагинов", Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
            trailing = { Icon(Icons.Rounded.Search, null, tint = C.Muted, modifier = Modifier.padding(end = 6.dp)) })
        LazyColumn(contentPadding = PaddingValues(bottom = 24.dp)) {
            shown.groupBy { it.group }.forEach { (group, items) ->
                item(key = group) {
                    Row(Modifier.padding(horizontal = 20.dp, vertical = 14.dp)) {
                        Text(group, color = C.Muted, fontSize = 14.sp, modifier = Modifier.weight(1f))
                        Text("Все", color = C.Muted, fontSize = 14.sp)
                    }
                }
                items(items.size, key = { items[it].name }) { i ->
                    val p = items[i]
                    val on = added[p.name] == true
                    Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                        GlyphBadge(p.glyph, p.color)
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f)) {
                            Text(p.name, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
                            Text(p.desc, color = C.Muted, fontSize = 14.sp, maxLines = 2)
                        }
                        Spacer(Modifier.width(10.dp))
                        Row(
                            Modifier.clip(CircleShape).background(if (on) C.Ok.copy(alpha = 0.12f) else C.Bubble)
                                .clickable { added[p.name] = !on }.padding(horizontal = 14.dp, vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            if (on) { Icon(Icons.Rounded.Check, null, tint = C.Ok, modifier = Modifier.size(16.dp)); Spacer(Modifier.width(4.dp)) }
                            Text(if (on) "Добавлено" else "Добавить", color = if (on) C.Ok else C.Ink, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                        }
                    }
                }
            }
        }
    }
}
