package app.staika

import androidx.compose.animation.core.EaseOutCubic
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.json.JSONObject

@Composable
private fun EmptyHint(text: String) {
    Box(Modifier.fillMaxWidth().padding(40.dp), Alignment.Center) { Text(text, color = C.Muted, fontSize = 16.sp, textAlign = TextAlign.Center) }
}

// ---------- Профиль ----------
@Composable
fun ProfileScreen(onBack: () -> Unit, go: (String) -> Unit) {
    val me = Repo.me
    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Профиль", onBack)
        Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
            Row(Modifier.fillMaxWidth().appear(0).clip(RoundedCornerShape(26.dp)).background(C.Tile).padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(64.dp).clip(CircleShape).background(Color.White), Alignment.Center) {
                    Text((me?.name?.firstOrNull() ?: 'С').uppercase(), fontSize = 28.sp, fontWeight = FontWeight.SemiBold)
                }
                Spacer(Modifier.width(14.dp))
                Column {
                    Text(me?.name.orEmpty(), style = MaterialTheme.typography.titleLarge)
                    Text(me?.email.orEmpty(), color = C.Muted, fontSize = 15.sp)
                    Text("${me?.roleLabel ?: ""} · агентов: ${Repo.agents.size}", color = C.Accent, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                }
            }
            Spacer(Modifier.height(10.dp))
            listOf(
                Triple(Icons.Outlined.Groups, "Команда" to "Кто кому подчиняется", "team"),
                Triple(Icons.Outlined.TaskAlt, "Задачи" to "Общая доска всех агентов", "tasks"),
                Triple(Icons.Outlined.Extension, "Плагины" to "Что умеют агенты", "plugins"),
                Triple(Icons.Outlined.BarChart, "Статистика" to "Расход токенов по агентам", "stats"),
                Triple(Icons.Outlined.History, "Журнал активности" to "Что делали агенты и ваши решения", "activity"),
                Triple(Icons.Outlined.Settings, "Настройки" to "Ключи, голос, сервер", "settings"),
            ).forEachIndexed { i, (icon, t, route) -> MenuRow(icon, t.first, t.second, i + 1) { go(route) } }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun MenuRow(icon: ImageVector, title: String, sub: String, index: Int, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().appear(index).bounceClick(down = 0.98f, onClick = onClick).padding(vertical = 10.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(48.dp).clip(RoundedCornerShape(15.dp)).background(C.Bubble), Alignment.Center) { Icon(icon, null, tint = C.Ink, modifier = Modifier.size(24.dp)) }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.SemiBold, fontSize = 18.sp)
            Text(sub, color = C.Muted, fontSize = 14.sp)
        }
        Icon(Icons.Outlined.ChevronRight, null, tint = C.Muted)
    }
}

// ---------- Команда ----------
@Composable
fun TeamScreen(onBack: () -> Unit, onChat: (String) -> Unit, onCreate: () -> Unit) {
    val all = Repo.agents
    val rows = ArrayList<Pair<Agent, Int>>()
    fun add(parent: String?, level: Int, seen: MutableSet<String>) {
        all.filter { it.parentId == parent && it.id !in seen }.forEach { seen.add(it.id); rows.add(it to level); add(it.id, level + 1, seen) }
    }
    val seen = mutableSetOf<String>()
    Repo.chief()?.let { c -> seen.add(c.id); rows.add(c to 0); add(c.id, 1, seen) }
    val solo = all.filter { it.id !in seen }

    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Команда", onBack)
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            itemsIndexed(rows, key = { _, r -> r.first.id }) { i, (a, level) -> TeamNode(a, level, i, onChat) }
            if (solo.isNotEmpty()) {
                item { Text(if (rows.isEmpty()) "Агенты" else "Самостоятельные агенты", color = C.Muted, fontSize = 15.sp, modifier = Modifier.padding(top = 12.dp, bottom = 2.dp)) }
                itemsIndexed(solo, key = { _, a -> "s" + a.id }) { i, a -> TeamNode(a, 0, i + rows.size, onChat) }
            }
            item { Spacer(Modifier.height(6.dp)); GrayButton("Добавить агента", onCreate) }
        }
    }
}

@Composable
private fun TeamNode(a: Agent, level: Int, index: Int, onChat: (String) -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(start = (level * 26).dp).appear(index).clip(RoundedCornerShape(24.dp))
            .background(if (a.chief) C.Tile else C.Bubble).bounceClick(down = 0.98f) { onChat(a.id) }.padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Avatar(a.pal, 56.dp, chief = a.chief, status = a.status)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(a.name, fontWeight = FontWeight.SemiBold, fontSize = 17.sp, maxLines = 1)
            if (a.role.isNotBlank()) Text(a.role, color = C.Muted, fontSize = 14.sp, maxLines = 1)
            Text(a.model, color = C.Accent, fontSize = 13.sp, fontWeight = FontWeight.Medium)
        }
        StatusChip(a.status)
    }
}

// ---------- Задачи ----------
@Composable
fun TasksScreen(onBack: () -> Unit, onChat: (String) -> Unit) {
    var f by remember { mutableStateOf("Все") }
    LaunchedEffect(Unit) { Repo.loadTasks() }
    val shown = Repo.tasks.filter { f == "Все" || it.status == f }
    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Задачи", onBack)
        LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(listOf("Все", "В работе", "Готово", "Не удалось")) { Chip(it, f == it) { f = it } }
        }
        if (shown.isEmpty()) EmptyHint("Задач пока нет. Они появляются, когда главный агент поручает работу помощникам.")
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            itemsIndexed(shown, key = { _, t -> t.id }) { i, t ->
                val a = Repo.agent(t.agentId)
                val p by animateFloatAsState(t.progress, tween(700, easing = EaseOutCubic), label = "tp")
                Card(Modifier.appear(i).bounceClick(down = 0.98f) { a?.let { onChat(it.id) } }) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        if (a != null) { Avatar(a.pal, 38.dp); Spacer(Modifier.width(10.dp)) }
                        Text(a?.name.orEmpty(), color = C.Muted, fontSize = 15.sp, modifier = Modifier.weight(1f))
                        Text(t.status, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = when (t.status) { "Готово" -> C.Ok; "Не удалось" -> C.Bad; else -> C.Ink })
                    }
                    Spacer(Modifier.height(10.dp))
                    Text(t.title, fontWeight = FontWeight.SemiBold, fontSize = 18.sp)
                    Spacer(Modifier.height(4.dp))
                    Text(timeLabel(t.at), color = C.Muted, fontSize = 14.sp)
                    Spacer(Modifier.height(10.dp))
                    ProgressBar(p)
                }
            }
        }
    }
}

// ---------- Статистика ----------
@Composable
fun StatsScreen(onBack: () -> Unit) {
    var rows by remember { mutableStateOf<List<UsageItem>?>(null) }
    LaunchedEffect(Unit) {
        try {
            val a = Api.obj("GET", "/api/stats").getJSONArray("byAgent")
            rows = (0 until a.length()).map { a.getJSONObject(it).let { u -> UsageItem(u.optString("agentId"), u.optLong("tokensIn"), u.optLong("tokensOut"), u.optDouble("costUsd")) } }
        } catch (e: ApiError) { Repo.say(e.message ?: "Ошибка"); rows = emptyList() }
    }
    val list = rows.orEmpty().sortedByDescending { it.tokensIn + it.tokensOut }
    val total = list.sumOf { it.tokensIn + it.tokensOut }
    val max = (list.maxOfOrNull { it.tokensIn + it.tokensOut } ?: 1L).coerceAtLeast(1L)
    fun fmt(n: Long) = when { n >= 1_000_000 -> "%.1f млн".format(n / 1e6); n >= 1000 -> "%.1f тыс".format(n / 1e3); else -> "$n" }
    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Статистика", onBack)
        if (rows == null) EmptyHint("Загружаю…")
        else if (list.isEmpty()) EmptyHint("Пока нет данных за последние 7 дней.")
        else Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Stat("Токенов за 7 дней", fmt(total), Modifier.weight(1f))
                val cost = list.sumOf { it.cost }
                Stat("Известная стоимость", if (cost > 0) "$%.2f".format(cost) else "–", Modifier.weight(1f))
            }
            Card {
                Text("По агентам", fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
                Spacer(Modifier.height(10.dp))
                list.forEach { u ->
                    val a = Repo.agent(u.agentId)
                    val v = u.tokensIn + u.tokensOut
                    Row(Modifier.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (a != null) Avatar(a.pal, 36.dp) else Spacer(Modifier.size(36.dp))
                        Spacer(Modifier.width(10.dp))
                        Column(Modifier.weight(1f)) {
                            Text(a?.name ?: "Удалённый агент", fontSize = 15.sp); Spacer(Modifier.height(5.dp))
                            ProgressBar(v.toFloat() / max)
                        }
                        Spacer(Modifier.width(10.dp)); Text(fmt(v), color = C.Muted, fontSize = 14.sp)
                    }
                }
                Text("Стоимость считается только для моделей с известной ценой (River).", color = C.Muted, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
            }
            Spacer(Modifier.height(20.dp))
        }
    }
}

@Composable
private fun Stat(label: String, value: String, modifier: Modifier) {
    Column(modifier.clip(RoundedCornerShape(24.dp)).background(C.Bubble).padding(16.dp)) {
        Text(label, color = C.Muted, fontSize = 14.sp); Spacer(Modifier.height(4.dp))
        Text(value, style = MaterialTheme.typography.headlineMedium)
    }
}

// ---------- Журнал ----------
private fun auditText(a: String): Pair<String, ImageVector> = when {
    a == "tool:fs_list" -> "Просмотрел файлы" to Icons.Outlined.Folder
    a == "tool:fs_read" -> "Прочитал файл" to Icons.Outlined.Description
    a == "tool:fs_write" -> "Записал файл" to Icons.Outlined.Edit
    a == "tool:fs_delete" -> "Удалил файл" to Icons.Outlined.Delete
    a == "tool:http_fetch" -> "Открыл страницу" to Icons.Outlined.Language
    a == "tool:remember" -> "Запомнил" to Icons.Outlined.Psychology
    a == "tool:recall" -> "Вспомнил" to Icons.Outlined.Psychology
    a == "tool:delegate_task" -> "Поручил задачу" to Icons.Outlined.Groups
    a == "tool:report_result" -> "Сообщил результат" to Icons.Outlined.TaskAlt
    a == "tool:create_agent" -> "Создал агента" to Icons.Outlined.SmartToy
    a == "tool:schedule_task" -> "Создал расписание" to Icons.Outlined.Schedule
    a == "tool:shell_exec" -> "Выполнил команду" to Icons.Outlined.Terminal
    a == "approval:allowed" -> "Вы разрешили" to Icons.Outlined.CheckCircle
    a == "approval:denied" -> "Вы отклонили" to Icons.Outlined.Cancel
    a == "agent_create" -> "Создан агент" to Icons.Outlined.SmartToy
    a == "agent_delete" -> "Удалён агент" to Icons.Outlined.Delete
    a == "voice_call" -> "Голосовой звонок" to Icons.Outlined.Call
    a == "key_set" -> "Добавлен ключ" to Icons.Outlined.Key
    a == "register" -> "Регистрация" to Icons.Outlined.Person
    a == "password_reset" -> "Сброс пароля" to Icons.Outlined.Lock
    else -> a to Icons.Outlined.History
}

@Composable
fun ActivityScreen(onBack: () -> Unit) {
    var items by remember { mutableStateOf<List<AuditItem>?>(null) }
    LaunchedEffect(Unit) {
        try {
            val a = Api.arr("GET", "/api/audit")
            items = (0 until a.length()).map { a.getJSONObject(it).let { r -> AuditItem(r.optString("agentId").ifEmpty { null }, r.optString("action"), r.optString("details"), r.optLong("createdAt")) } }
        } catch (e: ApiError) { Repo.say(e.message ?: "Ошибка"); items = emptyList() }
    }
    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Журнал", onBack)
        if (items == null) EmptyHint("Загружаю…") else if (items!!.isEmpty()) EmptyHint("Пока пусто.")
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            itemsIndexed(items.orEmpty()) { i, it ->
                val a = Repo.agent(it.agentId)
                val (text, icon) = auditText(it.action)
                Row(Modifier.fillMaxWidth().appear(i).clip(RoundedCornerShape(22.dp)).background(C.Bubble).padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    if (a != null) Avatar(a.pal, 46.dp) else Box(Modifier.size(46.dp).clip(CircleShape).background(Color.White), Alignment.Center) { Icon(icon, null, modifier = Modifier.size(22.dp)) }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(text, fontWeight = FontWeight.Medium, fontSize = 16.sp)
                        Text(listOfNotNull(a?.name, timeLabel(it.at)).joinToString(" · "), color = C.Muted, fontSize = 14.sp)
                        if (it.details.isNotBlank() && !it.action.startsWith("voice") && it.details.length < 120) Text(it.details, color = C.Muted, fontSize = 13.sp, maxLines = 1)
                    }
                }
            }
        }
    }
}

// ---------- Настройки ----------
private val providers = listOf("river" to "River AI", "anthropic" to "Anthropic", "openai" to "OpenAI", "google" to "Google Gemini", "deepgram" to "Deepgram (голос)")

@Composable
fun SettingsScreen(onBack: () -> Unit, onLogout: () -> Unit) {
    val scope = rememberCoroutineScope()
    var own by remember { mutableStateOf<Set<String>>(emptySet()) }
    var serverKeys by remember { mutableStateOf(false) }
    var keyDialog by remember { mutableStateOf<Pair<String, String>?>(null) }
    var modelDialog by remember { mutableStateOf(false) }
    var serverDialog by remember { mutableStateOf(false) }
    var users by remember { mutableStateOf<List<UserRow>?>(null) }
    var roleDialog by remember { mutableStateOf<UserRow?>(null) }
    var voiceModel by remember { mutableStateOf(Prefs.voiceModel) }
    var lang by remember { mutableStateOf(Prefs.voiceLang) }
    val isOwner = Repo.me?.role == "owner"

    suspend fun reload() {
        try {
            val k = Api.obj("GET", "/api/keys")
            own = (0 until k.getJSONArray("own").length()).map { k.getJSONArray("own").getString(it) }.toSet()
            serverKeys = k.optBoolean("serverKeysAllowed")
            if (isOwner) {
                val a = Api.arr("GET", "/api/admin/users")
                users = (0 until a.length()).map { a.getJSONObject(it).let { u -> UserRow(u.getString("id"), u.getString("email"), u.optString("name"), u.optString("role")) } }
            }
        } catch (e: ApiError) { Repo.say(e.message ?: "Ошибка") }
    }
    LaunchedEffect(Unit) { reload() }

    Column(Modifier.fillMaxSize().background(Color.White)) {
        ScreenTop("Настройки", onBack)
        Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
            Group("Ключи провайдеров") {
                providers.forEach { (id, label) ->
                    val has = id in own
                    ValueRow(label, if (has) "Свой ключ" else if (serverKeys) "Ключ сервера" else "Не подключён", if (has) C.Ok else C.Muted) {
                        keyDialog = id to label
                    }
                }
            }
            if (!serverKeys) Text("Ключи сервера доступны владельцу и роли «Семья». Остальным нужны свои ключи.", color = C.Muted, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp))
            Group("Голос") {
                ValueRow("Модель звонка", voiceModel) { modelDialog = true }
                ValueRow("Язык", if (lang == "ru") "Русский" else "English") { lang = if (lang == "ru") "en" else "ru"; Prefs.voiceLang = lang }
            }
            Group("Сервер") {
                ValueRow("Адрес", Prefs.server.removePrefix("https://").removePrefix("http://")) { serverDialog = true }
                ValueRow("Связь", if (Repo.connected) "Онлайн" else "Нет связи", if (Repo.connected) C.Ok else C.Bad)
            }
            if (isOwner && users != null) Group("Пользователи") {
                users!!.forEach { u -> ValueRow(u.email, when (u.role) { "owner" -> "Владелец"; "family" -> "Семья"; else -> "Участник" }) { roleDialog = u } }
            }
            Group("Безопасность") {
                ValueRow("Выйти на всех устройствах", "") { scope.launch { try { Api.obj("POST", "/api/auth/logout-all"); onLogout() } catch (e: ApiError) { Repo.say(e.message ?: "Ошибка") } } }
            }
            Spacer(Modifier.height(14.dp))
            GrayButton("Выйти", onLogout)
            Spacer(Modifier.height(30.dp))
        }
    }

    keyDialog?.let { (id, label) ->
        var text by remember(id) { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { keyDialog = null }, containerColor = Color.White, shape = RoundedCornerShape(28.dp),
            title = { Text(label, fontWeight = FontWeight.SemiBold) },
            text = {
                Column {
                    PillField(text, { text = it }, "Вставьте API-ключ", password = true)
                    Spacer(Modifier.height(8.dp))
                    Text("Ключ шифруется на сервере и нигде не показывается.", color = C.Muted, fontSize = 14.sp)
                }
            },
            confirmButton = {
                TextButton(enabled = text.isNotBlank(), onClick = {
                    keyDialog = null
                    scope.launch { try { Api.obj("PUT", "/api/keys/$id", JSONObject().put("key", text)); reload(); Repo.say("Ключ сохранён") } catch (e: ApiError) { Repo.say(e.message ?: "Ошибка") } }
                }) { Text("Сохранить", color = C.Ink, fontWeight = FontWeight.SemiBold) }
            },
            dismissButton = {
                Row {
                    if (id in own) TextButton({ keyDialog = null; scope.launch { try { Api.obj("DELETE", "/api/keys/$id"); reload() } catch (e: ApiError) { Repo.say(e.message ?: "Ошибка") } } }) { Text("Удалить", color = C.Bad) }
                    TextButton({ keyDialog = null }) { Text("Отмена", color = C.Muted) }
                }
            },
        )
    }
    if (modelDialog) {
        AlertDialog(
            onDismissRequest = { modelDialog = false }, containerColor = Color.White, shape = RoundedCornerShape(28.dp),
            title = { Text("Модель для звонков", fontWeight = FontWeight.SemiBold) },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    Text("Управляемые модели Deepgram работают без ключа. Модели River используют ваш ключ River.", color = C.Muted, fontSize = 14.sp, modifier = Modifier.padding(bottom = 10.dp))
                    Repo.models.forEach { m ->
                        Text(m.label, fontWeight = if (m.id == voiceModel) FontWeight.Bold else FontWeight.Normal, fontSize = 17.sp,
                            modifier = Modifier.fillMaxWidth().bounceClick { voiceModel = m.id; Prefs.voiceModel = m.id; modelDialog = false }.padding(vertical = 11.dp))
                    }
                }
            },
            confirmButton = {},
            dismissButton = { TextButton({ modelDialog = false }) { Text("Закрыть", color = C.Muted) } },
        )
    }
    if (serverDialog) ServerDialog(Prefs.server, { serverDialog = false }) { serverDialog = false; Repo.say("Адрес сохранён. Войдите заново, если сервер новый") }
    roleDialog?.let { u ->
        AlertDialog(
            onDismissRequest = { roleDialog = null }, containerColor = Color.White, shape = RoundedCornerShape(28.dp),
            title = { Text(u.email, fontWeight = FontWeight.SemiBold, fontSize = 18.sp) },
            text = {
                Column {
                    listOf("member" to "Участник: только свои ключи", "family" to "Семья: ключи сервера", "owner" to "Владелец: всё, включая команды на сервере").forEach { (r, d) ->
                        Text(d, fontWeight = if (u.role == r) FontWeight.Bold else FontWeight.Normal, fontSize = 16.sp,
                            modifier = Modifier.fillMaxWidth().bounceClick {
                                roleDialog = null
                                scope.launch { try { Api.obj("PUT", "/api/admin/users/${u.id}/role", JSONObject().put("role", r)); reload() } catch (e: ApiError) { Repo.say(e.message ?: "Ошибка") } }
                            }.padding(vertical = 11.dp))
                    }
                }
            },
            confirmButton = {}, dismissButton = { TextButton({ roleDialog = null }) { Text("Закрыть", color = C.Muted) } },
        )
    }
}

@Composable
private fun Group(title: String, content: @Composable ColumnScope.() -> Unit) {
    Text(title, color = C.Muted, fontSize = 15.sp, modifier = Modifier.padding(start = 6.dp, top = 18.dp, bottom = 8.dp))
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(C.Bubble).padding(horizontal = 16.dp, vertical = 4.dp), content = content)
}

@Composable
private fun ValueRow(title: String, value: String, valueColor: Color = C.Muted, onClick: (() -> Unit)? = null) {
    Row(
        Modifier.fillMaxWidth().then(if (onClick != null) Modifier.bounceClick(down = 0.985f, onClick = onClick) else Modifier).padding(vertical = 15.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(title, Modifier.weight(1f), fontSize = 17.sp, maxLines = 1)
        if (value.isNotEmpty()) Text(value, color = valueColor, fontSize = 16.sp, maxLines = 1)
    }
}
