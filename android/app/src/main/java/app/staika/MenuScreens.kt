package app.staika

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// ---------- Профиль / главное меню ----------
@Composable
fun ProfileScreen(onBack: () -> Unit, go: (String) -> Unit) {
    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Профиль", onBack)
        Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(C.Tile).padding(16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Avatar(Pal.Cloud, 64.dp)
                Spacer(Modifier.width(14.dp))
                Column {
                    Text("Вы", style = MaterialTheme.typography.titleLarge)
                    Text("you@example.com", color = C.Muted, fontSize = 14.sp)
                    Text("Владелец · 10 агентов", color = C.Accent, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                }
            }
            Spacer(Modifier.height(14.dp))
            MenuRow(Icons.Outlined.Groups, "Команда", "Кто кому подчиняется") { go("team") }
            MenuRow(Icons.Outlined.TaskAlt, "Задачи", "Общая доска всех агентов") { go("tasks") }
            MenuRow(Icons.Outlined.Extension, "Плагины", "Gmail, Календарь, Диск и другие") { go("plugins") }
            MenuRow(Icons.Outlined.Computer, "Компьютер агентов", "Браузер, файлы, терминал") { go("computer") }
            MenuRow(Icons.Outlined.BarChart, "Статистика", "Расходы и работа агентов") { go("stats") }
            MenuRow(Icons.Outlined.History, "Журнал активности", "Что делали агенты и ваши решения") { go("activity") }
            MenuRow(Icons.Outlined.Settings, "Настройки", "Провайдеры, голос, сервер") { go("settings") }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun MenuRow(icon: ImageVector, title: String, sub: String, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).clickable(onClick = onClick).padding(vertical = 12.dp, horizontal = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(C.Bubble), Alignment.Center) { Icon(icon, null, tint = C.Ink) }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
            Text(sub, color = C.Muted, fontSize = 13.sp)
        }
        Icon(Icons.Outlined.ChevronRight, null, tint = C.Muted)
    }
}

// ---------- Команда ----------
@Composable
fun TeamScreen(onBack: () -> Unit, onChat: (String) -> Unit, onCreate: () -> Unit) {
    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Команда", onBack)
        val chief = Store.agents.first { it.chief }
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { TeamNode(chief, 0, onChat) }
            val tree = ArrayList<Pair<Agent, Int>>()
            fun addChildren(parent: String, level: Int) {
                Store.agents.filter { it.parentId == parent }.forEach {
                    tree.add(it to level); addChildren(it.id, level + 1)
                }
            }
            addChildren(chief.id, 1)
            items(tree.size) { TeamNode(tree[it].first, tree[it].second, onChat) }
            item {
                Text("Самостоятельные агенты", color = C.Muted, modifier = Modifier.padding(top = 14.dp, bottom = 2.dp))
            }
            items(Store.agents.filter { it.parentId == null && !it.chief }) { TeamNode(it, 0, onChat) }
            item { Spacer(Modifier.height(6.dp)); GrayButton("Добавить агента", onCreate) }
        }
    }
}

@Composable
private fun TeamNode(a: Agent, level: Int, onChat: (String) -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(start = (level * 28).dp).clip(RoundedCornerShape(22.dp))
            .background(if (a.chief) C.Tile else C.Bubble).clickable { onChat(a.id) }.padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Avatar(a.pal, 52.dp, chief = a.chief, status = a.status)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(a.name, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
            Text(a.role, color = C.Muted, fontSize = 13.sp, maxLines = 1)
            Text(a.model, color = C.Accent, fontSize = 12.sp, fontWeight = FontWeight.Medium)
        }
        StatusChip(a.status)
    }
}

// ---------- Задачи ----------
@Composable
fun TasksScreen(onBack: () -> Unit, onChat: (String) -> Unit) {
    var f by remember { mutableStateOf("Все") }
    val shown = Store.tasks.filter { f == "Все" || it.status == f }
    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Задачи", onBack)
        LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(listOf("Все", "В работе", "Ждёт вас", "Готово")) { Chip(it, f == it) { f = it } }
        }
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            items(shown) { t ->
                val a = Store.agent(t.agentId)
                Card(Modifier.clickable { onChat(a.id) }) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Avatar(a.pal, 36.dp)
                        Spacer(Modifier.width(10.dp))
                        Text(a.name, color = C.Muted, fontSize = 14.sp, modifier = Modifier.weight(1f))
                        Text(t.status, fontWeight = FontWeight.SemiBold, fontSize = 13.sp,
                            color = when (t.status) { "Готово" -> C.Ok; "Ждёт вас" -> C.Warn; else -> C.Ink })
                    }
                    Spacer(Modifier.height(10.dp))
                    Text(t.title, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
                    Spacer(Modifier.height(4.dp))
                    Text(t.due, color = C.Muted, fontSize = 13.sp)
                    Spacer(Modifier.height(10.dp))
                    ProgressBar(t.progress)
                }
            }
        }
    }
}

// ---------- Компьютер агента ----------
@Composable
fun ComputerScreen(onBack: () -> Unit) {
    var tab by remember { mutableIntStateOf(0) }
    var mine by remember { mutableStateOf(false) }
    val a = Store.agent("dev")
    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Компьютер", onBack) { Avatar(a.pal, 38.dp, status = a.status) }
        Row(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("Браузер", "Файлы", "Терминал").forEachIndexed { i, t -> Chip(t, tab == i) { tab = i } }
        }
        Spacer(Modifier.height(12.dp))
        Box(Modifier.weight(1f).padding(horizontal = 16.dp).clip(RoundedCornerShape(24.dp)).border(1.dp, C.Line, RoundedCornerShape(24.dp))) {
            when (tab) {
                0 -> Column(Modifier.fillMaxSize()) {
                    Row(Modifier.fillMaxWidth().background(C.Bubble).padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.Lock, null, tint = C.Muted, modifier = Modifier.size(16.dp)); Spacer(Modifier.width(8.dp))
                        Text("console.hosting.example/projects", fontSize = 13.sp, color = C.Ink)
                    }
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("Проекты", fontWeight = FontWeight.Bold, fontSize = 20.sp)
                        listOf("staika-api · работает", "staika-web · деплой 0.4.2…", "staika-db · работает").forEach {
                            Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(C.Bubble).padding(14.dp)) { Text(it, fontSize = 15.sp) }
                        }
                        Box(Modifier.clip(CircleShape).background(C.Ink).padding(horizontal = 18.dp, vertical = 10.dp)) { Text("Выкатить", color = Color.White, fontSize = 14.sp) }
                    }
                }
                1 -> Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    listOf("📁 /workspaces/dev", "📁   releases", "📄   notes.md", "📄   deploy.sh", "📁 /shared", "📄   report-q3.pdf").forEach {
                        Text(it, fontFamily = FontFamily.Monospace, fontSize = 15.sp)
                    }
                }
                else -> Column(Modifier.fillMaxSize().background(Color(0xFF14141A)).padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf("$ git pull", "Already up to date.", "$ ./gradlew test", "BUILD SUCCESSFUL in 41s", "$ docker compose up -d api", "[+] Running 2/2", "✔ Container staika-api  Started").forEach {
                        Text(it, color = if (it.startsWith("$")) Color(0xFF8BE9A8) else Color(0xFFE8E8EE), fontFamily = FontFamily.Monospace, fontSize = 13.sp)
                    }
                }
            }
            Row(
                Modifier.align(Alignment.TopEnd).padding(10.dp).clip(CircleShape).background(Color.White).padding(horizontal = 10.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.size(8.dp).clip(CircleShape).background(if (mine) C.Warn else C.Ok)); Spacer(Modifier.width(6.dp))
                Text(if (mine) "Вы управляете" else "Агент работает", fontSize = 12.sp, fontWeight = FontWeight.Medium)
            }
        }
        Box(Modifier.navigationBarsPadding().padding(16.dp)) {
            if (mine) BlackButton("Вернуть управление агенту", { mine = false })
            else GrayButton("Взять управление", { mine = true })
        }
    }
}

// ---------- Статистика ----------
@Composable
fun StatsScreen(onBack: () -> Unit) {
    val days = listOf("Пн" to 1.2f, "Вт" to 2.1f, "Ср" to 1.6f, "Чт" to 3.4f, "Пт" to 2.8f, "Сб" to 0.9f, "Вс" to 1.4f)
    val max = days.maxOf { it.second }
    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Статистика", onBack)
        Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Stat("Сегодня", "$1.42", Modifier.weight(1f)); Stat("За неделю", "$13.40", Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Stat("Задач выполнено", "47", Modifier.weight(1f)); Stat("Минут звонков", "38", Modifier.weight(1f))
            }
            Card {
                Text("Расходы по дням, $", fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(14.dp))
                Row(Modifier.fillMaxWidth().height(140.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Bottom) {
                    days.forEachIndexed { i, (d, v) ->
                        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Bottom) {
                            Box(Modifier.width(30.dp).height((100 * v / max).dp).clip(RoundedCornerShape(10.dp)).background(if (i == 3) C.Ink else C.Tile))
                            Spacer(Modifier.height(6.dp)); Text(d, color = C.Muted, fontSize = 12.sp)
                        }
                    }
                }
            }
            Card {
                Text("По агентам", fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(10.dp))
                listOf("dev" to 0.82f, "chief" to 0.55f, "mail" to 0.4f, "res" to 0.22f, "ea" to 0.1f).forEach { (id, p) ->
                    val a = Store.agent(id)
                    Row(Modifier.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Avatar(a.pal, 32.dp); Spacer(Modifier.width(10.dp))
                        Column(Modifier.weight(1f)) {
                            Text(a.name, fontSize = 14.sp); Spacer(Modifier.height(4.dp))
                            ProgressBar(p)
                        }
                        Spacer(Modifier.width(10.dp)); Text("$%.2f".format(p * 5), color = C.Muted, fontSize = 13.sp)
                    }
                }
            }
            Spacer(Modifier.height(20.dp))
        }
    }
}

@Composable
private fun Stat(label: String, value: String, modifier: Modifier) {
    Column(modifier.clip(RoundedCornerShape(22.dp)).background(C.Bubble).padding(16.dp)) {
        Text(label, color = C.Muted, fontSize = 13.sp); Spacer(Modifier.height(4.dp))
        Text(value, style = MaterialTheme.typography.headlineMedium)
    }
}

// ---------- Журнал ----------
private data class Act(val icon: ImageVector, val who: String, val text: String, val time: String, val tag: String)

@Composable
fun ActivityScreen(onBack: () -> Unit) {
    val items = listOf(
        Act(Icons.Outlined.Mail, "mail", "Прочитал 41 письмо", "8:20", "Авто"),
        Act(Icons.Outlined.Check, "ea", "Создал событие «Совет директоров»", "8:41", "Вы разрешили"),
        Act(Icons.Outlined.Terminal, "dev", "Запустил тесты в песочнице", "8:50", "Авто"),
        Act(Icons.Outlined.RocketLaunch, "dev", "Деплой staika-api 0.4.2", "9:02", "Ждёт вас"),
        Act(Icons.Outlined.Send, "mail", "Отправка письма anna@example.com", "9:05", "Вы отклонили"),
        Act(Icons.Outlined.Backup, "ops", "Резервная копия 2.1 ГБ", "03:00", "Авто"),
    )
    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Журнал", onBack)
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(items) { it ->
                val a = Store.agent(it.who)
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).background(C.Bubble).padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Avatar(a.pal, 44.dp); Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(it.text, fontWeight = FontWeight.Medium, fontSize = 15.sp)
                        Text("${a.name} · ${it.time}", color = C.Muted, fontSize = 13.sp)
                    }
                    Text(it.tag, fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
                        color = when (it.tag) { "Вы отклонили" -> C.Bad; "Ждёт вас" -> C.Warn; "Вы разрешили" -> C.Ok; else -> C.Muted })
                }
            }
        }
    }
}

// ---------- Настройки ----------
@Composable
fun SettingsScreen(onBack: () -> Unit, onLogout: () -> Unit) {
    var push by remember { mutableStateOf(true) }
    var proactive by remember { mutableStateOf(true) }
    var always by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Настройки", onBack)
        Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
            Group("Провайдеры моделей") {
                KeyRow("River AI", "Ключ добавлен", true); KeyRow("Anthropic", "Ключ добавлен", true)
                KeyRow("OpenAI", "Не подключён", false); KeyRow("Google Gemini", "Не подключён", false)
            }
            Group("Голос") {
                ValueRow("Диктовка", "Deepgram Nova-3"); ValueRow("Модель звонка", "Claude Haiku 4.5"); ValueRow("Голос агента", "Владимир")
            }
            Group("Сервер") {
                ValueRow("Адрес", "agents.example.com"); ValueRow("Состояние", "Онлайн · 12 агентов")
            }
            Group("Безопасность") {
                SwitchRow("Спрашивать перед внешними действиями", "Письма, платежи, деплой", !always) { always = !it }
                SwitchRow("Проактивная проверка почты", "Только чтение, пока вы заняты", proactive) { proactive = it }
                ValueRow("Входы и устройства", "2 устройства")
            }
            Group("Уведомления") { SwitchRow("Пуши о решениях и итогах", "Тексты в пуши не попадают", push) { push = it } }
            Spacer(Modifier.height(12.dp))
            GrayButton("Выйти", onLogout)
            Spacer(Modifier.height(30.dp))
        }
    }
}

@Composable
private fun Group(title: String, content: @Composable ColumnScope.() -> Unit) {
    Text(title, color = C.Muted, fontSize = 14.sp, modifier = Modifier.padding(start = 6.dp, top = 18.dp, bottom = 8.dp))
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(C.Bubble).padding(horizontal = 16.dp, vertical = 4.dp), content = content)
}

@Composable
private fun ValueRow(title: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(title, Modifier.weight(1f), fontSize = 16.sp); Text(value, color = C.Muted, fontSize = 15.sp)
    }
}

@Composable
private fun KeyRow(title: String, value: String, ok: Boolean) {
    Row(Modifier.fillMaxWidth().padding(vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(title, Modifier.weight(1f), fontSize = 16.sp)
        Text(value, color = if (ok) C.Ok else C.Muted, fontSize = 15.sp)
    }
}

@Composable
private fun SwitchRow(title: String, sub: String, on: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) { Text(title, fontSize = 16.sp); Text(sub, color = C.Muted, fontSize = 13.sp) }
        Toggle(on, onChange)
    }
}
