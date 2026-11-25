package app.staika

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.KeyboardArrowDown
import androidx.compose.material.icons.rounded.KeyboardArrowUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val models = listOf(
    "Claude Sonnet 5.5", "Claude Haiku 4.5", "GPT-5.5", "Gemini 3.5 Flash",
    "DeepSeek V4.1 Flash", "Kimi K3", "GLM-5.3",
)

/** Минимальный экран: внешность, имя, одно описание. Остальное спрятано в «Дополнительно». */
@Composable
fun CreateAgentScreen(onClose: () -> Unit) {
    var name by remember { mutableStateOf("") }
    var role by remember { mutableStateOf("") }
    var pal by remember { mutableStateOf(Pal.Blue) }
    var more by remember { mutableStateOf(false) }
    var model by remember { mutableStateOf(models[1]) }
    var team by remember { mutableStateOf(false) }
    var mail by remember { mutableStateOf(true) }
    var browser by remember { mutableStateOf(false) }
    var server by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().background(Color.White).imePadding()) {
        Row(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 16.dp, vertical = 10.dp)) {
            IconPill(Icons.Rounded.Close, onClose)
        }
        Column(
            Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.height(16.dp))
            Avatar(pal, 132.dp)
            Spacer(Modifier.height(18.dp))
            BasicTextField(
                name, { name = it }, Modifier.fillMaxWidth(), singleLine = true,
                textStyle = TextStyle(fontSize = 26.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center, color = C.Ink),
                cursorBrush = SolidColor(C.Ink),
                decorationBox = { inner ->
                    Box(contentAlignment = Alignment.Center) {
                        if (name.isEmpty()) Text("Имя агента", fontSize = 26.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFFC8C8D0))
                        inner()
                    }
                },
            )
            Spacer(Modifier.height(6.dp))
            BasicTextField(
                role, { role = it }, Modifier.fillMaxWidth(), maxLines = 3,
                textStyle = TextStyle(fontSize = 16.sp, textAlign = TextAlign.Center, color = C.Muted),
                cursorBrush = SolidColor(C.Ink),
                decorationBox = { inner ->
                    Box(contentAlignment = Alignment.Center) {
                        if (role.isEmpty()) Text("Чем он занимается?", fontSize = 16.sp, color = Color(0xFFC8C8D0))
                        inner()
                    }
                },
            )
            Spacer(Modifier.height(26.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(14.dp), contentPadding = PaddingValues(horizontal = 4.dp)) {
                items(Pal.entries) { p ->
                    Box(
                        Modifier.size(48.dp).scale(if (p == pal) 1.18f else 0.9f).clip(CircleShape).clickable { pal = p },
                        Alignment.Center,
                    ) { Avatar(p, 44.dp) }
                }
            }
            Spacer(Modifier.height(24.dp))
            Row(
                Modifier.clip(CircleShape).clickable { more = !more }.padding(horizontal = 14.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Дополнительно", color = C.Muted, fontSize = 15.sp)
                Icon(if (more) Icons.Rounded.KeyboardArrowUp else Icons.Rounded.KeyboardArrowDown, null, tint = C.Muted)
            }
            AnimatedVisibility(more) {
                Column(Modifier.fillMaxWidth()) {
                    Spacer(Modifier.height(8.dp))
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) { items(models) { m -> Chip(m, m == model) { model = m } } }
                    Spacer(Modifier.height(14.dp))
                    PermRow("Помощник главного", "Отчитывается главному агенту", team) { team = it }
                    PermRow("Своя почта", "Адрес на вашем домене", mail) { mail = it }
                    PermRow("Браузер", "Можно перехватить управление", browser) { browser = it }
                    PermRow("Сервер", "Файлы и команды в песочнице", server) { server = it }
                }
            }
            Spacer(Modifier.height(16.dp))
        }
        Box(Modifier.navigationBarsPadding().padding(horizontal = 24.dp, vertical = 16.dp)) {
            BlackButton("Создать", {
                Store.agents.add(
                    Agent("n${Store.agents.size}", name.ifBlank { pal.title }, role.ifBlank { "Новый помощник" }, pal, Status.Idle,
                        "Готов к работе. Поставьте первую задачу.", "сейчас",
                        parentId = if (team) "chief" else null, model = model),
                )
                onClose()
            })
        }
    }
}

@Composable
private fun PermRow(title: String, sub: String, on: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.Medium, fontSize = 16.sp)
            Text(sub, color = C.Muted, fontSize = 13.sp)
        }
        Toggle(on, onChange)
    }
}
