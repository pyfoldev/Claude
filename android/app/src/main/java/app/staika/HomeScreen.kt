package app.staika

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

@Composable
fun HomeScreen(onChat: (String) -> Unit, onProfile: () -> Unit, onCreate: () -> Unit, onPlugins: () -> Unit) {
    var search by remember { mutableStateOf(false) }
    var q by remember { mutableStateOf("") }
    var menu by remember { mutableStateOf(false) }
    val all = Repo.agents
    val pinned = Repo.pinned()
    val list = all.filter { it !in pinned && (q.isBlank() || it.name.contains(q, true) || it.role.contains(q, true)) }
        .sortedByDescending { it.lastAt }

    Column(Modifier.fillMaxSize().background(Color.White)) {
        Row(
            Modifier.fillMaxWidth().statusBarsPadding().padding(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                Modifier.size(48.dp).shadow(4.dp, CircleShape, ambientColor = C.Shadow, spotColor = C.Shadow).clip(CircleShape)
                    .background(Color.White).border(1.dp, C.Line, CircleShape).bounceClick(onClick = onProfile),
                Alignment.Center,
            ) { Text((Repo.me?.name?.firstOrNull() ?: 'С').uppercase(), fontSize = 20.sp, fontWeight = FontWeight.SemiBold) }
            Spacer(Modifier.weight(1f))
            IconPill(Icons.Outlined.Search, { search = !search; if (!search) q = "" }, size = 48.dp)
            Spacer(Modifier.width(10.dp))
            Box {
                IconPill(Icons.Outlined.Add, { menu = true }, size = 48.dp)
                DropdownMenu(menu, { menu = false }, shape = RoundedCornerShape(22.dp), containerColor = Color.White) {
                    DropdownMenuItem({ Text("Новый агент") }, { menu = false; onCreate() }, leadingIcon = { Icon(Icons.Outlined.SmartToy, null) })
                    DropdownMenuItem({ Text("Групповой чат") }, { menu = false }, leadingIcon = { Icon(Icons.Outlined.Groups, null) })
                    DropdownMenuItem({ Text("Плагины") }, { menu = false; onPlugins() }, leadingIcon = { Icon(Icons.Outlined.Extension, null) })
                }
            }
        }
        AnimatedVisibility(search, enter = expandVertically(tween(260)) + fadeIn(), exit = shrinkVertically(tween(200)) + fadeOut()) {
            PillField(q, { q = it }, "Поиск", Modifier.padding(horizontal = 16.dp, vertical = 4.dp))
        }
        AnimatedVisibility(!Repo.connected && Repo.loggedIn) {
            Text(
                "Нет связи с сервером, переподключаюсь…", color = C.Muted, fontSize = 14.sp, textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp).clip(CircleShape).background(C.Bubble).padding(vertical = 8.dp),
            )
        }
        if (Repo.loaded && all.isEmpty()) {
            Column(Modifier.fillMaxSize().padding(horizontal = 32.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                Avatar(Pal.Blue, 150.dp, Modifier.appear(0))
                Spacer(Modifier.height(18.dp))
                Text("Создайте первого агента", style = MaterialTheme.typography.titleLarge, modifier = Modifier.appear(1))
                Spacer(Modifier.height(6.dp))
                Text("Он станет вашим главным помощником. Потом добавите остальных.", color = C.Muted, fontSize = 16.sp, textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.appear(2))
                Spacer(Modifier.height(24.dp))
                Box(Modifier.appear(3)) { BlackButton("Создать агента", onCreate) }
                Spacer(Modifier.height(60.dp))
            }
            return@Column
        }
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 28.dp)) {
            if (!search && pinned.isNotEmpty()) {
                item {
                    LazyRow(
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 10.dp),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        itemsIndexed(pinned, key = { _, a -> a.id }) { i, a ->
                            var shown by remember { mutableStateOf(false) }
                            LaunchedEffect(Unit) { delay(80L + i * 90L); shown = true }
                            val sc by animateFloatAsState(if (shown) 1f else 0.5f, spring(0.55f, 380f), label = "pop")
                            Column(
                                Modifier.width(108.dp).scale(sc).bounceClick { onChat(a.id) },
                                horizontalAlignment = Alignment.CenterHorizontally,
                            ) {
                                Avatar(a.pal, 92.dp, chief = a.chief, status = a.status)
                                Spacer(Modifier.height(4.dp))
                                Text(a.name, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.Medium)
                            }
                        }
                    }
                }
            }
            itemsIndexed(list, key = { _, a -> a.id }) { i, a ->
                Row(
                    Modifier.fillMaxWidth().appear(i + 2).bounceClick(down = 0.98f) { onChat(a.id) }
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Avatar(a.pal, 62.dp, status = a.status)
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(a.name, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f), maxLines = 1)
                            Text(a.time, color = C.Muted, fontSize = 14.sp)
                        }
                        Spacer(Modifier.height(1.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                a.last, color = if (a.status == Status.Waiting) C.Ink else C.Muted, maxLines = 1,
                                overflow = TextOverflow.Ellipsis, fontSize = 16.sp, modifier = Modifier.weight(1f),
                                fontWeight = if (a.status == Status.Waiting) FontWeight.Medium else FontWeight.Normal,
                            )
                            if (a.status == Status.Waiting) {
                                Spacer(Modifier.width(8.dp))
                                Box(Modifier.size(10.dp).clip(CircleShape).background(C.Warn))
                            }
                        }
                    }
                }
            }
        }
    }
}
