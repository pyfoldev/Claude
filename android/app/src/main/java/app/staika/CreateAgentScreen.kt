package app.staika

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val models = listOf(
    "Claude Sonnet 5.5", "Claude Haiku 4.5", "GPT-5.5", "Gemini 3.5 Flash",
    "DeepSeek V4.1 Flash", "Kimi K3", "GLM-5.3",
)

@Composable
fun CreateAgentScreen(onClose: () -> Unit) {
    var name by remember { mutableStateOf("") }
    var role by remember { mutableStateOf("") }
    var pal by remember { mutableStateOf(Pal.Cloud) }
    var model by remember { mutableStateOf(models[1]) }
    var team by remember { mutableStateOf(false) }
    var mail by remember { mutableStateOf(true) }
    var browser by remember { mutableStateOf(false) }
    var server by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().background(Color.White).imePadding()) {
        Row(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            IconPill(Icons.Rounded.Close, onClose)
            Spacer(Modifier.width(14.dp))
            Text("Новый агент", style = MaterialTheme.typography.titleLarge)
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Spacer(Modifier.height(8.dp))
            Avatar(pal, 148.dp, shape = RoundedCornerShape(44.dp))
            Spacer(Modifier.height(18.dp))
            PillField(name, { name = it }, "Имя, например «Закупщик»")
            Spacer(Modifier.height(10.dp))
            PillField(role, { role = it }, "Что он делает? Опишите задачу словами", shape = RoundedCornerShape(24.dp), singleLine = false)
            Spacer(Modifier.height(22.dp))
            Text("Внешность", color = C.Muted, modifier = Modifier.align(Alignment.Start).padding(bottom = 10.dp))
            // сетка 5 х 2
            Pal.entries.chunked(5).forEach { row ->
                Row(Modifier.fillMaxWidth().padding(bottom = 10.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    row.forEach { p ->
                        Box(
                            Modifier.size(58.dp).clip(RoundedCornerShape(20.dp))
                                .border(if (p == pal) 3.dp else 0.dp, C.Ink, RoundedCornerShape(20.dp))
                                .padding(if (p == pal) 3.dp else 0.dp).clickable { pal = p },
                        ) { Avatar(p, 58.dp, shape = RoundedCornerShape(18.dp)) }
                    }
                }
            }
            Spacer(Modifier.height(14.dp))
            Text("Модель", color = C.Muted, modifier = Modifier.align(Alignment.Start).padding(bottom = 10.dp))
            LazyRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(models) { m -> Chip(m, m == model) { model = m } }
            }
            Spacer(Modifier.height(22.dp))
            Text("Где работает", color = C.Muted, modifier = Modifier.align(Alignment.Start).padding(bottom = 10.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Chip("Самостоятельный", !team) { team = false }
                Chip("Помощник главного", team) { team = true }
            }
            Spacer(Modifier.height(22.dp))
            Text("Что можно", color = C.Muted, modifier = Modifier.align(Alignment.Start).padding(bottom = 4.dp))
            PermRow("Своя почта", "Адрес на вашем домене", mail) { mail = it }
            PermRow("Браузер", "Открывает сайты, вы можете перехватить", browser) { browser = it }
            PermRow("Сервер", "Файлы и команды в песочнице", server) { server = it }
            Spacer(Modifier.height(12.dp))
        }
        Box(Modifier.navigationBarsPadding().padding(20.dp)) {
            BlackButton("Создать", {
                val n = name.ifBlank { pal.title }
                Store.agents.add(
                    Agent("n${Store.agents.size}", n, role.ifBlank { "Новый помощник" }, pal, Status.Idle,
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
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.Medium, fontSize = 16.sp)
            Text(sub, color = C.Muted, fontSize = 13.sp)
        }
        Toggle(on, onChange)
    }
}
