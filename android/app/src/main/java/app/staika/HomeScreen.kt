package app.staika

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun HomeScreen(onChat: (String) -> Unit, onProfile: () -> Unit, onCreate: () -> Unit, onPlugins: () -> Unit) {
    var search by remember { mutableStateOf(false) }
    var q by remember { mutableStateOf("") }
    var menu by remember { mutableStateOf(false) }
    val all = Store.agents
    val pinned = all.filter { it.pinned }
    val list = all.filter { !it.pinned && (q.isBlank() || it.name.contains(q, true) || it.role.contains(q, true)) }
    val waiting = all.count { it.status == Status.Waiting }

    Column(Modifier.fillMaxSize().background(Color.White)) {
        Row(
            Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 16.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(shape = CircleShape, color = Color.White, shadowElevation = 5.dp, modifier = Modifier.size(44.dp)) {
                Box(Modifier.fillMaxSize().clip(CircleShape).clickable(onClick = onProfile), Alignment.Center) {
                    Avatar(Pal.Cloud, 38.dp)
                }
            }
            Spacer(Modifier.weight(1f))
            IconPill(Icons.Rounded.Search, { search = !search; if (!search) q = "" })
            Spacer(Modifier.width(10.dp))
            Box {
                IconPill(Icons.Rounded.Add, { menu = true })
                DropdownMenu(menu, { menu = false }, shape = androidx.compose.foundation.shape.RoundedCornerShape(20.dp), containerColor = Color.White) {
                    DropdownMenuItem({ Text("Новый агент") }, { menu = false; onCreate() }, leadingIcon = { Icon(Icons.Rounded.SmartToy, null) })
                    DropdownMenuItem({ Text("Групповой чат") }, { menu = false }, leadingIcon = { Icon(Icons.Rounded.Groups, null) })
                    DropdownMenuItem({ Text("Плагины") }, { menu = false; onPlugins() }, leadingIcon = { Icon(Icons.Rounded.Extension, null) })
                }
            }
        }
        if (search) {
            PillField(q, { q = it }, "Поиск по агентам", Modifier.padding(horizontal = 16.dp, vertical = 4.dp))
        }
        if (waiting > 0 && !search) {
            Row(
                Modifier.padding(horizontal = 16.dp, vertical = 6.dp).fillMaxWidth().clip(androidx.compose.foundation.shape.RoundedCornerShape(18.dp))
                    .background(C.Warn.copy(alpha = 0.12f)).padding(horizontal = 14.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.size(8.dp).clip(CircleShape).background(C.Warn))
                Spacer(Modifier.width(10.dp))
                Text("Ждут вашего решения: $waiting", fontSize = 14.sp, fontWeight = FontWeight.Medium)
            }
        }
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
            if (!search && pinned.isNotEmpty()) {
                item {
                    LazyRow(
                        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
                        horizontalArrangement = Arrangement.spacedBy(20.dp),
                    ) {
                        items(pinned, key = { it.id }) { a ->
                            Column(
                                Modifier.width(92.dp).clip(androidx.compose.foundation.shape.RoundedCornerShape(20.dp)).clickable { onChat(a.id) },
                                horizontalAlignment = Alignment.CenterHorizontally,
                            ) {
                                Avatar(a.pal, 84.dp, chief = a.chief, status = a.status)
                                Spacer(Modifier.height(6.dp))
                                Text(a.name, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.Medium)
                            }
                        }
                    }
                }
            }
            items(list, key = { it.id }) { a ->
                Row(
                    Modifier.fillMaxWidth().clickable { onChat(a.id) }.padding(horizontal = 16.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Avatar(a.pal, 56.dp, status = a.status)
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Row {
                            Text(a.name, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                            Text(a.time, color = C.Muted, fontSize = 13.sp)
                        }
                        Spacer(Modifier.height(2.dp))
                        Text(a.last, color = if (a.status == Status.Waiting) C.Ink else C.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = 15.sp,
                            fontWeight = if (a.status == Status.Waiting) FontWeight.Medium else FontWeight.Normal)
                    }
                }
            }
        }
    }
}
