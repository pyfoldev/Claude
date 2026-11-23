package openagent.app.com

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat

private val Switches @Composable get() = SwitchDefaults.colors(checkedThumbColor = C.onAccent, checkedTrackColor = C.accent, uncheckedThumbColor = C.dim, uncheckedTrackColor = C.surface3, uncheckedBorderColor = C.outline)

@Composable
private fun Card(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) =
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(26.dp)).background(C.surface2).padding(16.dp), content = content)

private fun presetIcon(id: String) = when (id) {
    "github" -> Icons.Outlined.AccountTree; "context7", "deepwiki" -> Icons.Outlined.MenuBook; "huggingface" -> Icons.Outlined.Psychology
    "linear" -> Icons.Outlined.TaskAlt; "stripe" -> Icons.Outlined.CreditCard; "supabase" -> Icons.Outlined.Storage; "cloudflare-docs" -> Icons.Outlined.Cloud
    "exa", "tavily" -> Icons.Outlined.Search; "firecrawl" -> Icons.Outlined.Language; "zapier" -> Icons.Outlined.Bolt; else -> Icons.Outlined.Extension
}

// ====================== Подключения (MCP + встроенные коннекторы) ======================
@Composable
fun ConnectionsScreen(vm: AppVM) {
    LaunchedEffect(Unit) { vm.loadMcp() }
    var form by remember { mutableStateOf<McpPreset?>(null) }
    PageScaffold("Подключения", { vm.screen = Screen.Chat }) {
        LazyColumn(contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 40.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { Text("Подключайте внешние сервисы по протоколу MCP — агент получит их инструменты и будет вызывать сам, когда нужно.", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) }
            item {
                Card {
                    Text("Встроено, без ключей", color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    Text("Погода · Википедия · курсы валют и крипто · arXiv · Hacker News · геокодер · RSS. Агент подключает их сам по вопросу («погода в Алматы», «курс евро»).", color = C.dim, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp), lineHeight = 19.sp)
                }
            }
            item {
                var mailForm by remember { mutableStateOf(false) }
                LaunchedEffect(Unit) { vm.loadMail() }
                Card {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.MailOutline, null, tint = C.text, modifier = Modifier.size(24.dp)); Spacer(Modifier.width(10.dp))
                        Text("Почта", color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                        SoftChip(Icons.Outlined.Add, "Подключить", false) { vm.mailHint = ""; mailForm = true }
                    }
                    Text("Агент читает, разбирает и отвечает на письма сам — в том числе по расписанию (например, утренний разбор входящих).", color = C.dim, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp), lineHeight = 19.sp)
                    vm.mailAccounts.toList().forEach { a ->
                        Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(a.email, color = C.text, fontSize = 14.sp, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                            IconButton({ vm.deleteMail(a) }) { Icon(Icons.Outlined.DeleteOutline, null, tint = C.dim) }
                        }
                    }
                }
                if (mailForm) {
                    var em by remember { mutableStateOf("") }; var pw by remember { mutableStateOf("") }; var imap by remember { mutableStateOf("") }; var smtp by remember { mutableStateOf("") }
                    LaunchedEffect(em) { if (em.contains("@") && em.length > 5) { kotlinx.coroutines.delay(500); vm.loadMailHint(em) } }
                    AppDialog("Подключить почту", { mailForm = false }, if (vm.mailBusy) "Проверяю…" else "Подключить", em.contains("@") && pw.isNotBlank() && !vm.mailBusy, { vm.addMail(em, pw, imap, smtp) { ok -> if (ok) mailForm = false } }) {
                        Field(em, { em = it }, "Email", mono = true)
                        Field(pw, { pw = it }, "Пароль приложения", mono = true)
                        if (vm.mailHint.isNotBlank()) Text(vm.mailHint, color = C.dim, fontSize = 12.sp, lineHeight = 17.sp)
                        if (vm.mailHint.startsWith("Укажите")) { Field(imap, { imap = it }, "IMAP-сервер (imap.example.com)", mono = true); Field(smtp, { smtp = it }, "SMTP-сервер (smtp.example.com)", mono = true) }
                        Text("Обычный пароль от почты не подойдёт — нужен отдельный пароль приложения. Он хранится на вашем сервере в зашифрованном виде.", color = C.dim, fontSize = 12.sp, lineHeight = 17.sp)
                    }
                }
            }
            if (vm.mcpServers.isNotEmpty()) item { Text("Мои подключения", color = C.dim, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp, top = 8.dp)) }
            items(vm.mcpServers.toList(), key = { "s" + it.id }) { s ->
                Card {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(42.dp).clip(CircleShape).background(C.container), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.Extension, null, tint = C.onContainer, modifier = Modifier.size(22.dp)) }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(s.name, color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(s.url.removePrefix("https://"), color = C.dim, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        Switch(s.enabled, { Haptics.click(); vm.toggleMcp(s, it) }, colors = Switches)
                    }
                    Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        SoftChip(Icons.Outlined.NetworkCheck, "Проверить", false) { vm.testMcp(s) }
                        SoftChip(Icons.Outlined.DeleteOutline, "Удалить", false) { vm.deleteMcp(s) }
                    }
                }
            }
            if (vm.mcpBusy) item { Box(Modifier.fillMaxWidth().padding(8.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(Modifier.size(22.dp), color = C.accent, strokeWidth = 2.dp) } }
            item { Text("Каталог", color = C.dim, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp, top = 8.dp)) }
            items(vm.mcpPresets.toList(), key = { "p" + it.id }) { p ->
                Row(Modifier.fillMaxWidth().bounceClick { form = p }.clip(RoundedCornerShape(26.dp)).background(C.surface2).padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(42.dp).clip(CircleShape).background(C.surface3), contentAlignment = Alignment.Center) { Icon(presetIcon(p.id), null, tint = C.text, modifier = Modifier.size(22.dp)) }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(p.name, color = C.text, fontSize = 16.sp, fontWeight = FontWeight.Medium)
                        Text(p.desc, color = C.dim, fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    }
                    Text(if (p.auth == "none") "без ключа" else "нужен ключ", color = C.dim, fontSize = 11.sp)
                    Spacer(Modifier.width(6.dp)); Icon(Icons.Outlined.Add, null, tint = C.accent)
                }
            }
        }
    }
    form?.let { p ->
        var name by remember(p) { mutableStateOf(if (p.id == "custom") "" else p.name) }
        var url by remember(p) { mutableStateOf(p.url) }
        var token by remember(p) { mutableStateOf("") }
        AppDialog(if (p.id == "custom") "Свой MCP-сервер" else p.name, { form = null }, "Подключить", url.startsWith("http") && name.isNotBlank(), { vm.addMcp(name.trim(), url.trim(), token.trim(), ""); form = null }) {
            if (p.hint.isNotBlank()) Text(p.hint, color = C.dim, fontSize = 13.sp)
            Field(name, { name = it }, "Название")
            Field(url, { url = it }, "Адрес (https://…/mcp)", mono = true)
            if (p.auth != "none") Field(token, { token = it }, "Токен / API-ключ (необязательно для некоторых)", mono = true)
            Text("Токен хранится на вашем сервере и не показывается модели.", color = C.dim, fontSize = 12.sp)
        }
    }
}

// ====================== Заметки (в т.ч. голосовые) ======================
@Composable
fun NotesScreen(vm: AppVM) {
    val ctx = LocalContext.current
    LaunchedEffect(Unit) { vm.loadNotes() }
    var add by remember { mutableStateOf(false) }; var text by remember { mutableStateOf("") }
    var open by remember { mutableStateOf<NoteItem?>(null) }
    val rec = remember { Recorder(ctx) }
    var recording by remember { mutableStateOf(false) }
    DisposableEffect(Unit) { onDispose { if (recording) rec.cancel() } }
    fun toggle() {
        if (recording) { recording = false; rec.stop()?.let { vm.noteFromAudio(it) } }
        else if (rec.start()) { recording = true; Haptics.click() } else vm.toast = "Не удалось начать запись"
    }
    val perm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { if (it) toggle() else vm.toast = "Нужен доступ к микрофону" }
    PageScaffold("Заметки", { vm.screen = Screen.Chat }) {
        Box(Modifier.weight(1f)) {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 160.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item { Text("Нажмите микрофон, наговорите мысль — она расшифруется, получит заголовок и краткое резюме.", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) }
                if (vm.noteBusy) item { Card { Row(verticalAlignment = Alignment.CenterVertically) { CircularProgressIndicator(Modifier.size(20.dp), color = C.accent, strokeWidth = 2.dp); Spacer(Modifier.width(12.dp)); Text("Расшифровываю…", color = C.dim) } } }
                if (vm.notes.isEmpty() && !vm.noteBusy) item { EmptyHint(Icons.Outlined.StickyNote2, "Заметок пока нет") }
                items(vm.notes.toList(), key = { it.id }) { n ->
                    Card(Modifier.clickable { open = n }) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(if (n.source == "voice") Icons.Outlined.Mic else Icons.Outlined.StickyNote2, null, tint = C.dim, modifier = Modifier.size(18.dp)); Spacer(Modifier.width(8.dp))
                            Text(n.title.monoEmoji(), color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                            Text(android.text.format.DateUtils.getRelativeTimeSpanString(n.updatedAt, System.currentTimeMillis(), android.text.format.DateUtils.MINUTE_IN_MILLIS).toString(), color = C.dim, fontSize = 11.sp)
                        }
                        Text(n.summary ?: n.text, color = C.text.copy(alpha = 0.8f), fontSize = 14.sp, maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 6.dp), lineHeight = 20.sp)
                    }
                }
            }
            Row(Modifier.align(Alignment.BottomEnd).padding(20.dp).navigationBarsPadding(), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                RoundButton(Icons.Outlined.Edit, "Текст", { text = ""; add = true }, size = 56.dp, container = C.surface3, content = C.text)
                PillButton(if (recording) "Стоп" else "Записать", {
                    if (recording || ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) toggle() else perm.launch(Manifest.permission.RECORD_AUDIO)
                }, icon = if (recording) Icons.Outlined.Stop else Icons.Outlined.Mic, height = 60.dp)
            }
        }
    }
    if (add) AppDialog("Новая заметка", { add = false }, "Сохранить", text.isNotBlank(), { vm.addNote(text.trim()); add = false }) { Field(text, { text = it }, "Текст", singleLine = false, minLines = 5) }
    open?.let { n ->
        AlertDialog(onDismissRequest = { open = null }, containerColor = C.surface2, shape = RoundedCornerShape(32.dp),
            title = { Text(n.title, color = C.text, fontWeight = FontWeight.Bold, fontSize = 20.sp) },
            text = { Column(Modifier.verticalScroll(rememberScrollState())) {
                n.summary?.let { Text(it, color = C.accent, fontSize = 14.sp, modifier = Modifier.padding(bottom = 10.dp)) }
                Text(n.text, color = C.text, fontSize = 15.sp, lineHeight = 22.sp)
            } },
            confirmButton = { Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                TextButton({ copyToClipboard(ctx, n.text); vm.toast = "Скопировано" }) { Text("Копировать", color = C.accent) }
                TextButton({ vm.screen = Screen.Chat; vm.newChat("chat"); vm.send("Вот моя заметка, помоги довести до дела (план/структура/следующие шаги):\n\n${n.text}"); open = null }) { Text("В чат", color = C.accent) }
            } },
            dismissButton = { TextButton({ vm.deleteNote(n); open = null }) { Text("Удалить", color = C.danger) } })
    }
}

// ====================== Задачи ======================
@Composable
fun TasksScreen(vm: AppVM) {
    LaunchedEffect(Unit) { vm.loadTodos() }
    var text by remember { mutableStateOf("") }
    val open = vm.todos.filter { !it.done }; val done = vm.todos.filter { it.done }
    PageScaffold("Задачи", { vm.screen = Screen.Chat }) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(text, { text = it }, singleLine = true, placeholder = { Text("Новая задача…", color = C.dim) }, modifier = Modifier.weight(1f), shape = RoundedCornerShape(26.dp), colors = fieldColors())
            Spacer(Modifier.width(10.dp))
            RoundButton(Icons.Outlined.Add, "Добавить", { if (text.isNotBlank()) { vm.addTodo(text.trim()); text = "" } }, size = 54.dp)
        }
        LazyColumn(contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 40.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item { Text("Агент тоже видит этот список: «добавь в дела…», «что у меня в задачах?».", color = C.dim, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 8.dp)) }
            if (vm.todos.isEmpty()) item { EmptyHint(Icons.Outlined.TaskAlt, "Список пуст") }
            items(open, key = { it.id }) { t -> TodoRow(vm, t) }
            if (done.isNotEmpty()) item { Text("Выполнено", color = C.dim, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp, top = 10.dp)) }
            items(done, key = { it.id }) { t -> TodoRow(vm, t) }
        }
    }
}

@Composable
private fun TodoRow(vm: AppVM, t: TodoItem) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(C.surface2).padding(start = 6.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Checkbox(t.done, { Haptics.tick(); vm.setTodo(t, it) }, colors = CheckboxDefaults.colors(checkedColor = C.accent, uncheckedColor = C.dim, checkmarkColor = C.onAccent))
        Text(t.text.monoEmoji(), color = if (t.done) C.dim else C.text, fontSize = 16.sp, textDecoration = if (t.done) TextDecoration.LineThrough else null, modifier = Modifier.weight(1f).padding(vertical = 12.dp))
        IconButton({ vm.deleteTodo(t) }) { Icon(Icons.Outlined.Close, null, tint = C.dim, modifier = Modifier.size(20.dp)) }
    }
}

// ====================== Миссии ======================
@Composable
fun MissionsScreen(vm: AppVM) {
    LaunchedEffect(Unit) { vm.loadMissions() }
    var add by remember { mutableStateOf(false) }; var goal by remember { mutableStateOf("") }; var every by remember { mutableStateOf("60") }
    PageScaffold("Миссии", { vm.screen = Screen.Chat }) {
        Box(Modifier.weight(1f)) {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 110.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item { Text("Поставьте долгую цель — агент сам будет двигаться к ней шаг за шагом в фоне (искать, сравнивать, следить, собирать) и сообщит, когда всё готово или нужен ваш ответ.", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp), lineHeight = 20.sp) }
                if (vm.missions.isEmpty()) item { EmptyHint(Icons.Outlined.Flag, "Миссий пока нет") }
                items(vm.missions.toList(), key = { it.id }) { m ->
                    Card {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(m.goal.monoEmoji(), color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                            Spacer(Modifier.width(8.dp))
                            Text(when (m.status) { "active" -> "идёт"; "done" -> "готово"; "blocked" -> "нужен ответ"; else -> "пауза" }, color = if (m.status == "blocked") C.text else C.dim, fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.clip(RoundedCornerShape(12.dp)).background(if (m.status == "active") C.container else C.surface3).padding(horizontal = 10.dp, vertical = 4.dp))
                        }
                        val last = m.notes.lines().lastOrNull { it.isNotBlank() }
                        if (last != null) Text(last, color = C.text.copy(alpha = 0.8f), fontSize = 13.sp, maxLines = 4, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 8.dp), lineHeight = 19.sp)
                        Text("шагов: ${m.steps} · проверка раз в ${if (m.everyMin >= 60) "${m.everyMin / 60} ч" else "${m.everyMin} мин"}", color = C.dim, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp))
                        Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            if (m.status == "active") SoftChip(Icons.Outlined.Pause, "Пауза", false) { vm.setMission(m, "paused") }
                            else if (m.status != "done") SoftChip(Icons.Outlined.PlayArrow, "Продолжить", false) { vm.setMission(m, "active") }
                            SoftChip(Icons.Outlined.DeleteOutline, "Удалить", false) { vm.deleteMission(m) }
                        }
                    }
                }
            }
            PillButton("Новая миссия", { goal = ""; add = true }, Modifier.align(Alignment.BottomEnd).padding(20.dp).navigationBarsPadding(), icon = Icons.Outlined.Add, height = 60.dp)
        }
    }
    if (add) AppDialog("Новая миссия", { add = false }, "Запустить", goal.isNotBlank(), { vm.screen = Screen.Chat; vm.newChat("chat"); vm.send("Запусти миссию (mission_create, проверка раз в $every мин): $goal"); add = false }) {
        Field(goal, { goal = it }, "Цель (например: найти квартиру до 400 000 ₸ в Бостандыкском районе и присылать новые варианты)", singleLine = false, minLines = 3)
        Segmented(listOf("30" to "30м", "60" to "1ч", "240" to "4ч", "1440" to "Сутки"), every, { every = it })
    }
}

// ====================== Журнал действий агента ======================
@Composable
fun ActivityScreen(vm: AppVM) {
    LaunchedEffect(Unit) { vm.loadActivity() }
    val fmt = remember { java.text.SimpleDateFormat("d MMM, HH:mm", java.util.Locale("ru")) }
    PageScaffold("Журнал агента", { vm.screen = Screen.Chat }) {
        LazyColumn(contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 40.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item { Text("Что агент делал на телефоне и сервере за последние 2 недели: звонки, сообщения, команды, запросы, публикации. Жирным помечены действия «вовне».", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp), lineHeight = 20.sp) }
            if (vm.activity.isEmpty()) item { EmptyHint(Icons.Outlined.History, "Пока пусто") }
            items(vm.activity.toList(), key = { "${it.ts}-${it.tool}-${it.summary.hashCode()}-${it.convId}" }) { a ->
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(C.surface2).clickable { vm.openChat(a.convId) }.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(38.dp).clip(CircleShape).background(if (a.outward) C.container else C.surface3), contentAlignment = Alignment.Center) {
                        Icon(when (a.tool) { "phone" -> Icons.Outlined.PhoneAndroid; "bash", "process" -> Icons.Outlined.Terminal; "http_request", "github_api" -> Icons.Outlined.Public; "deploy_site", "delete_site" -> Icons.Outlined.Language; else -> Icons.Outlined.Schedule }, null, tint = if (a.outward) C.onContainer else C.dim, modifier = Modifier.size(20.dp))
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(a.summary.ifBlank { a.tool }, color = C.text, fontSize = 14.sp, fontWeight = if (a.outward) FontWeight.SemiBold else FontWeight.Normal, maxLines = 2, overflow = TextOverflow.Ellipsis, style = if (a.tool == "bash") Mono else androidx.compose.ui.text.TextStyle.Default)
                        Text("${fmt.format(java.util.Date(a.ts))} · ${a.title.monoEmoji()}", color = C.dim, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
        }
    }
}

// ====================== Секреты ======================
@Composable
fun SecretsScreen(vm: AppVM) {
    LaunchedEffect(Unit) { vm.loadSecrets() }
    var add by remember { mutableStateOf(false) }; var name by remember { mutableStateOf("") }; var value by remember { mutableStateOf("") }
    PageScaffold("Секреты", { vm.screen = Screen.Chat }) {
        Box(Modifier.weight(1f)) {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 100.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item { Text("Ключи и пароли хранятся зашифрованными на вашем сервере. Модель их не видит: в командах пишет {{secret:ИМЯ}}, а подставляется значение уже при выполнении. В ответах значения скрываются.", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp), lineHeight = 20.sp) }
                if (vm.secretNames.isEmpty()) item { EmptyHint(Icons.Outlined.Key, "Секретов пока нет") }
                items(vm.secretNames.toList(), key = { it }) { n ->
                    Card { Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.Key, null, tint = C.dim); Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) { Text(n, color = C.text, style = Mono, fontSize = 15.sp); Text("{{secret:$n}}", color = C.dim, fontSize = 12.sp, style = Mono) }
                        IconButton({ vm.deleteSecret(n) }) { Icon(Icons.Outlined.DeleteOutline, null, tint = C.dim) }
                    } }
                }
            }
            PillButton("Добавить", { name = ""; value = ""; add = true }, Modifier.align(Alignment.BottomEnd).padding(20.dp).navigationBarsPadding(), icon = Icons.Outlined.Add, height = 60.dp)
        }
    }
    if (add) AppDialog("Новый секрет", { add = false }, "Сохранить", name.isNotBlank() && value.isNotBlank(), { vm.saveSecret(name.trim(), value); add = false }) {
        Field(name, { name = it.filter { c -> c.isLetterOrDigit() || c in "_.-" }.take(40) }, "Имя (например: GITHUB_TOKEN)", mono = true)
        Field(value, { value = it }, "Значение", mono = true)
    }
}

// ====================== Сравнение моделей ======================
@Composable
fun CompareDialog(vm: AppVM) {
    val ctx = LocalContext.current
    var q by remember { mutableStateOf("") }
    val options = remember(vm.providers.size) {
        buildList {
            vm.providers.forEach { p -> p.models.take(6).forEach { m -> add(Triple(p.id, m, "${p.name} · ${m.substringAfterLast('/')}")) } }
            if (vm.providers.none { it.id == "perplexity" }) add(Triple("perplexity", "agent-low", "Perplexity Agent · low"))
        }
    }
    var picked by remember { mutableStateOf(setOf<Int>()) }
    LaunchedEffect(Unit) { vm.loadProviders() }
    AlertDialog(onDismissRequest = { vm.showCompare = false }, containerColor = C.surface2, shape = RoundedCornerShape(32.dp),
        title = { Text("Сравнить модели", color = C.text, fontWeight = FontWeight.Bold, fontSize = 22.sp) },
        text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Field(q, { q = it }, "Вопрос", singleLine = false, minLines = 2)
            Text("Выберите 2–3 модели:", color = C.dim, fontSize = 13.sp)
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                options.forEachIndexed { i, o ->
                    val on = i in picked
                    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(if (on) C.container else C.surface3).clickable { picked = if (on) picked - i else if (picked.size < 3) picked + i else picked }.padding(horizontal = 14.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(o.third, color = if (on) C.onContainer else C.text, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                        if (on) Icon(Icons.Outlined.Check, null, tint = C.onContainer, modifier = Modifier.size(18.dp))
                    }
                }
            }
            if (vm.compareBusy) Row(verticalAlignment = Alignment.CenterVertically) { CircularProgressIndicator(Modifier.size(20.dp), color = C.accent, strokeWidth = 2.dp); Spacer(Modifier.width(10.dp)); Text("Модели отвечают…", color = C.dim) }
            vm.compareOut.forEach { r ->
                Card {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(r.label, color = C.accent, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text("${r.ms / 100 / 10.0} с", color = C.dim, fontSize = 12.sp)
                    }
                    Text((r.text ?: "Ошибка: ${r.error}").monoEmoji(), color = if (r.text == null) C.dim else C.text, fontSize = 14.sp, lineHeight = 20.sp, modifier = Modifier.padding(top = 6.dp).clickable { r.text?.let { copyToClipboard(ctx, it); vm.toast = "Скопировано" } })
                }
            }
        } },
        confirmButton = { PillButton("Сравнить", { vm.compare(q.trim(), picked.sorted().map { options[it].first to options[it].second }) }, enabled = q.isNotBlank() && picked.size >= 2 && !vm.compareBusy, height = 48.dp) },
        dismissButton = { TextButton({ vm.showCompare = false }) { Text("Закрыть", color = C.dim, fontSize = 16.sp) } })
}

@Composable
fun ResearchDialog(vm: AppVM) {
    var topic by remember { mutableStateOf("") }
    AppDialog("Глубокое исследование", { vm.showResearch = false }, "Начать", topic.isNotBlank(), { vm.deepResearch(topic.trim()); vm.showResearch = false; vm.screen = Screen.Chat }) {
        Text("Агент изучит несколько источников, сверит факты и подготовит отчёт со ссылками. Займёт несколько минут.", color = C.dim, fontSize = 13.sp)
        Field(topic, { topic = it }, "Тема или вопрос", singleLine = false, minLines = 3)
    }
}
