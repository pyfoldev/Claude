package app.staika

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.KeyboardArrowDown
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

private val fallbackModels = listOf(ModelOpt("Claude Haiku 4.5", "Claude Haiku 4.5", "anthropic"), ModelOpt("Claude Sonnet 5.5", "Claude Sonnet 5.5", "anthropic"))

/** Создание и редактирование агента: аватар, имя, роль, внешность. Остальное спрятано в «Дополнительно». */
@Composable
fun CreateAgentScreen(editId: String?, onClose: () -> Unit) {
    val editing = editId?.let { Repo.agent(it) }
    var name by remember { mutableStateOf(editing?.name ?: "") }
    var role by remember { mutableStateOf(editing?.role ?: "") }
    var pal by remember { mutableStateOf(editing?.pal ?: Pal.Blue) }
    var more by remember { mutableStateOf(false) }
    var model by remember { mutableStateOf(editing?.model ?: "Claude Haiku 4.5") }
    val hasChief = Repo.chief() != null
    var asChief by remember { mutableStateOf(!hasChief && Repo.agents.isEmpty()) }
    var underChief by remember { mutableStateOf(false) }
    var server by remember { mutableStateOf(editing?.perms?.server ?: false) }
    var busy by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val arrow by animateFloatAsState(if (more) 180f else 0f, tween(260), label = "arrow")
    val models = Repo.models.ifEmpty { fallbackModels }
    val isOwner = Repo.me?.role == "owner"

    Column(Modifier.fillMaxSize().background(Color.White).imePadding()) {
        Row(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconPill(Icons.Outlined.Close, onClose)
            Spacer(Modifier.width(12.dp))
            Text(if (editing != null) "Агент" else "Новый агент", style = MaterialTheme.typography.titleLarge)
        }
        CenteredScroll(Modifier.weight(1f).padding(horizontal = 20.dp)) {
            AnimatedContent(
                pal, Modifier.size(150.dp),
                transitionSpec = { (scaleIn(spring(0.55f, 420f), initialScale = 0.6f) + fadeIn(tween(160))) togetherWith (scaleOut(tween(140), targetScale = 0.8f) + fadeOut(tween(120))) },
                label = "bigAvatar",
            ) { p -> Avatar(p, 150.dp) }
            Spacer(Modifier.height(14.dp))
            BasicTextField(
                name, { name = it.take(60) }, Modifier.fillMaxWidth(), singleLine = true,
                textStyle = TextStyle(fontFamily = Inter, fontSize = 22.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center, color = C.Ink),
                cursorBrush = SolidColor(C.Ink),
                decorationBox = { inner ->
                    Box(Modifier.fillMaxWidth().clip(CircleShape).background(C.Field).padding(vertical = 15.dp), Alignment.Center) {
                        if (name.isEmpty()) Text("Имя агента", fontSize = 22.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFFC3C3CB))
                        inner()
                    }
                },
            )
            Spacer(Modifier.height(8.dp))
            BasicTextField(
                role, { role = it.take(500) }, Modifier.fillMaxWidth(), singleLine = true,
                textStyle = TextStyle(fontFamily = Inter, fontSize = 17.sp, textAlign = TextAlign.Center, color = C.Ink),
                cursorBrush = SolidColor(C.Ink),
                decorationBox = { inner ->
                    Box(Modifier.fillMaxWidth().clip(CircleShape).background(C.Field).padding(vertical = 13.dp, horizontal = 16.dp), Alignment.Center) {
                        if (role.isEmpty()) Text("Чем он занимается?", fontSize = 17.sp, color = Color(0xFFC3C3CB))
                        inner()
                    }
                },
            )
            Spacer(Modifier.height(22.dp))
            Pal.entries.chunked(5).forEach { row ->
                Row(Modifier.fillMaxWidth().padding(bottom = 6.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
                    row.forEach { p ->
                        val sel = p == pal
                        val sc by animateFloatAsState(if (sel) 1.12f else 0.92f, spring(0.5f, 500f), label = "sel")
                        val ring by animateColorAsState(if (sel) C.Field else Color.Transparent, tween(200), label = "ring")
                        Box(Modifier.size(72.dp).scale(sc).clip(CircleShape).background(ring).bounceClick(down = 0.85f) { pal = p }, Alignment.Center) {
                            Avatar(p, 60.dp)
                        }
                    }
                }
            }
            Spacer(Modifier.height(6.dp))
            Row(
                Modifier.clip(CircleShape).bounceClick { more = !more }.padding(horizontal = 14.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Дополнительно", color = C.Muted, fontSize = 16.sp)
                Icon(Icons.Outlined.KeyboardArrowDown, null, tint = C.Muted, modifier = Modifier.rotate(arrow))
            }
            AnimatedVisibility(more, enter = expandVertically(tween(300, easing = EaseOutCubic)) + fadeIn(tween(240)), exit = shrinkVertically(tween(220)) + fadeOut(tween(160))) {
                Column(Modifier.fillMaxWidth()) {
                    Spacer(Modifier.height(6.dp))
                    Text("Модель", color = C.Muted, fontSize = 14.sp, modifier = Modifier.padding(bottom = 8.dp))
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { items(models) { m -> Chip(m.label, m.id == model) { model = m.id } } }
                    Spacer(Modifier.height(12.dp))
                    if (editing == null) {
                        if (!hasChief) PermRow("Главный агент", "Руководит командой и распределяет задачи", asChief) { asChief = it }
                        else PermRow("Помощник главного", "Отчитывается главному агенту", underChief) { underChief = it }
                    }
                    if (isOwner) PermRow("Сервер", "Команды в песочнице, каждая с вашего разрешения", server) { server = it }
                }
            }
            if (editing != null) {
                Spacer(Modifier.height(10.dp))
                Text("Удалить агента", color = C.Bad, fontSize = 16.sp, modifier = Modifier.clip(CircleShape).bounceClick { confirmDelete = true }.padding(horizontal = 16.dp, vertical = 10.dp))
            }
        }
        Box(Modifier.navigationBarsPadding().padding(horizontal = 20.dp, vertical = 14.dp)) {
            BlackButton(if (busy) "Подождите…" else if (editing != null) "Сохранить" else "Создать", {
                busy = true
                scope.launch {
                    val n = name.ifBlank { pal.title }
                    if (editing != null) { Repo.updateAgent(editing, n, role, pal, model, Perms(server = server)); onClose() }
                    else if (Repo.createAgent(n, role, pal, model, asChief, underChief, Perms(server = server)) != null) onClose()
                    busy = false
                }
            }, enabled = !busy)
        }
    }
    if (confirmDelete && editing != null) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false }, containerColor = Color.White, shape = androidx.compose.foundation.shape.RoundedCornerShape(28.dp),
            title = { Text("Удалить «${editing.name}»?", fontWeight = FontWeight.SemiBold) },
            text = { Text("Переписка и память агента будут удалены без возможности восстановления.", color = C.Muted) },
            confirmButton = { TextButton({ confirmDelete = false; scope.launch { Repo.deleteAgent(editing.id); onClose(); onClose() } }) { Text("Удалить", color = C.Bad, fontWeight = FontWeight.SemiBold) } },
            dismissButton = { TextButton({ confirmDelete = false }) { Text("Отмена", color = C.Muted) } },
        )
    }
}

@Composable
private fun PermRow(title: String, sub: String, on: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.Medium, fontSize = 17.sp)
            Text(sub, color = C.Muted, fontSize = 14.sp)
        }
        Toggle(on, onChange)
    }
}
