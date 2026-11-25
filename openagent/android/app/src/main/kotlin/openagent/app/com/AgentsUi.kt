package openagent.app.com

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
private fun Panel(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, content: @Composable ColumnScope.() -> Unit) =
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(26.dp)).background(C.surface2).let { if (onClick != null) it.clickable { onClick() } else it }.padding(16.dp), content = content)

private fun everyLabel(m: Int?) = when { m == null || m == 0 -> "вручную"; m >= 1440 && m % 1440 == 0 -> "раз в ${m / 1440} дн."; m >= 60 && m % 60 == 0 -> "раз в ${m / 60} ч"; else -> "раз в $m мин" }
private val fmtTime = java.text.SimpleDateFormat("d MMM, HH:mm", java.util.Locale("ru"))

// ====================== Агенты ======================
@Composable
fun AgentsScreen(vm: AppVM) {
    LaunchedEffect(Unit) { vm.loadAgents() }
    var edit by remember { mutableStateOf<AgentItem?>(null) }; var creating by remember { mutableStateOf(false) }
    var del by remember { mutableStateOf<AgentItem?>(null) }
    val main = vm.agents.firstOrNull { it.isMain }; val team = vm.agents.filter { !it.isMain }
    PageScaffold("Агенты", { vm.screen = Screen.Chat }) {
        Box(Modifier.weight(1f)) {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 110.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item { Text("У каждого агента своя задача, свои коннекторы и память; они могут работать сами по расписанию. Главный агент — это обычный чат: он знает всю команду и поручает работу нужным агентам.", color = C.dim, fontSize = 14.sp, lineHeight = 20.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) }
                if (main != null) item {
                    Panel {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(main.emoji, fontSize = 26.sp); Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) { Text("Главный агент", color = C.text, fontSize = 17.sp, fontWeight = FontWeight.SemiBold); Text(if (team.isEmpty()) "команды пока нет" else "команда: ${team.size}", color = C.dim, fontSize = 13.sp) }
                        }
                        Text(main.instructions, color = C.text.copy(alpha = 0.8f), fontSize = 13.sp, lineHeight = 19.sp, maxLines = 4, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 8.dp))
                        Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            SoftChip(Icons.Outlined.ChatBubbleOutline, "Чат", false) { vm.screen = Screen.Chat; vm.newChat("chat") }
                            SoftChip(Icons.Outlined.Tune, "Настроить", false) { edit = main }
                        }
                    }
                }
                if (team.isEmpty()) item { EmptyHint(Icons.Outlined.Groups, "Агентов пока нет. Создайте первого — или скажите главному в чате: «заведи агента, который каждое утро собирает новости»") }
                items(team, key = { it.id }) { a ->
                    Panel(onClick = { edit = a }) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(a.emoji, fontSize = 24.sp); Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(a.name, color = C.text, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                                Text(everyLabel(a.everyMin) + (if (a.everyMin != null && a.everyMin > 0 && !a.enabled) " · пауза" else "") + (if (a.runs > 0) " · запусков: ${a.runs}" else ""), color = C.dim, fontSize = 12.sp)
                            }
                            val conns = a.connectors
                            Text(if (conns == null) "все коннекторы" else if (conns.isEmpty()) "без коннекторов" else "${conns.size} конн.", color = C.dim, fontSize = 12.sp, modifier = Modifier.clip(RoundedCornerShape(12.dp)).background(C.surface3).padding(horizontal = 10.dp, vertical = 4.dp))
                        }
                        Text(a.instructions, color = C.text.copy(alpha = 0.8f), fontSize = 13.sp, lineHeight = 19.sp, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 8.dp))
                        if (a.lastResult.isNotBlank()) Text("${a.lastRun?.let { fmtTime.format(java.util.Date(it)) } ?: "Результат"}: ${a.lastResult}", color = C.dim, fontSize = 12.sp, lineHeight = 17.sp, maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 6.dp))
                        Row(Modifier.padding(top = 10.dp).horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            SoftChip(Icons.Outlined.PlayArrow, "Запустить", false) { vm.runAgent(a) }
                            SoftChip(Icons.Outlined.ChatBubbleOutline, "Чат", false) { vm.chatWithAgent(a) }
                            if (a.everyMin != null && a.everyMin > 0) SoftChip(if (a.enabled) Icons.Outlined.Pause else Icons.Outlined.PlayCircleOutline, if (a.enabled) "Пауза" else "Включить", false) { vm.setAgentEnabled(a, !a.enabled) }
                            SoftChip(Icons.Outlined.DeleteOutline, "Удалить", false) { del = a }
                        }
                    }
                }
                item { Spacer(Modifier.height(4.dp)); Panel(onClick = { vm.screen = Screen.Integrations }) { Row(verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Outlined.Hub, null, tint = C.onContainer); Spacer(Modifier.width(12.dp)); Column(Modifier.weight(1f)) { Text("Коннекторы", color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold); Text("Подключено ${vm.agentConns.count { it.connected }} из ${vm.agentConns.size}: Telegram, Slack, GitHub, Notion, календарь…", color = C.dim, fontSize = 13.sp) }; Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) } } }
            }
            PillButton("Новый агент", { creating = true }, Modifier.align(Alignment.BottomEnd).padding(20.dp).navigationBarsPadding(), icon = Icons.Outlined.Add, height = 60.dp)
        }
    }
    if (creating) AgentEditor(vm, null) { creating = false }
    edit?.let { AgentEditor(vm, it) { edit = null } }
    del?.let { a -> AppDialog("Удалить агента?", { del = null }, "Удалить", true, { vm.deleteAgent(a); del = null }) { Text("«${a.name}» и его расписание будут удалены. Прошлые чаты останутся.", color = C.dim) } }
}

@Composable
private fun AgentEditor(vm: AppVM, a: AgentItem?, onClose: () -> Unit) {
    var emoji by remember { mutableStateOf(a?.emoji ?: "🤖") }; var name by remember { mutableStateOf(a?.name ?: "") }
    var instr by remember { mutableStateOf(a?.instructions ?: "") }
    var all by remember { mutableStateOf(a?.connectors == null) }; val sel = remember { mutableStateListOf<String>().also { l -> a?.connectors?.let { l.addAll(it) } } }
    var every by remember { mutableStateOf((a?.everyMin ?: 0).let { when { it == 0 -> "0"; it <= 15 -> "15"; it <= 60 -> "60"; it <= 360 -> "360"; else -> "1440" } }) }
    var writeOk by remember { mutableStateOf(a?.writeOk ?: false) }
    val main = a?.isMain == true
    AppDialog(if (a == null) "Новый агент" else if (main) "Главный агент" else "Агент", onClose, "Сохранить", name.isNotBlank() && (instr.isNotBlank() || main), {
        vm.saveAgent(a?.id, name.trim(), emoji.trim().ifBlank { "🤖" }, instr.trim(), if (all) listOf("*") else sel.toList(), every.toInt().takeIf { it > 0 }, writeOk); onClose()
    }) {
        if (a == null && vm.agentTemplates.isNotEmpty()) {
            Text("Шаблоны", color = C.dim, fontSize = 13.sp)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                vm.agentTemplates.forEach { t -> SoftChip(Icons.Outlined.AutoAwesome, "${t.emoji} ${t.name}", false) { emoji = t.emoji; name = t.name; instr = t.instructions; all = false; sel.clear(); sel.addAll(t.connectors); every = (t.everyMin ?: 0).let { m -> when { m == 0 -> "0"; m <= 15 -> "15"; m <= 60 -> "60"; m <= 360 -> "360"; else -> "1440" } } } }
            }
        }
        if (!main) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { Field(emoji, { emoji = it.take(4) }, "Эмодзи", Modifier.width(96.dp)); Field(name, { name = it }, "Имя", Modifier.weight(1f)) }
        Field(instr, { instr = it }, if (main) "Как вести себя главному агенту" else "Задача: что делать и как отчитываться", singleLine = false, minLines = 4)
        if (!main) {
            Text("Расписание", color = C.dim, fontSize = 13.sp)
            Segmented(listOf("0" to "Вручную", "15" to "15 мин", "60" to "Час", "360" to "6 ч", "1440" to "Сутки"), every, { every = it })
            Text("Коннекторы", color = C.dim, fontSize = 13.sp)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SoftChip(Icons.Outlined.SelectAll, "Все подключённые", all) { all = !all }
                if (!all) vm.agentConns.forEach { c -> SoftChip(if (c.connected) Icons.Outlined.CheckCircleOutline else Icons.Outlined.Link, "${c.icon} ${c.name}", c.id in sel) { if (c.id in sel) sel.remove(c.id) else sel.add(c.id) } }
            }
            if (!all && vm.agentConns.any { it.id in sel && !it.connected }) Text("Часть выбранных коннекторов ещё не подключена — откройте «Коннекторы».", color = C.dim, fontSize = 12.sp)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { Text("Разрешить действия", color = C.text, fontSize = 15.sp); Text("Сам отправлять сообщения и менять данные в сервисах во время автономных запусков. Выключено — только читает и предлагает.", color = C.dim, fontSize = 12.sp, lineHeight = 17.sp) }
                androidx.compose.material3.Switch(writeOk, { writeOk = it })
            }
        }
    }
}

// ====================== Коннекторы ======================
@Composable
fun ConnectorsScreen(vm: AppVM) {
    LaunchedEffect(Unit) { vm.loadConnectors() }
    var open by remember { mutableStateOf<Connector?>(null) }
    PageScaffold("Коннекторы", { vm.screen = Screen.Agents }) {
        LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 40.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { Text("Подключите сервисы по токену — агенты и главный чат смогут читать из них и (с вашего разрешения) писать. Данные хранятся на вашем сервере.", color = C.dim, fontSize = 14.sp, lineHeight = 20.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) }
            items(vm.connectors.toList(), key = { it.id }) { c ->
                Panel(onClick = { open = c }) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(c.icon, fontSize = 24.sp); Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) { Text(c.name, color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold); Text(c.desc, color = C.dim, fontSize = 13.sp, lineHeight = 18.sp) }
                        Spacer(Modifier.width(8.dp))
                        Text(if (c.connected) "подключён" else "подключить", color = if (c.connected) C.onContainer else C.dim, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.clip(RoundedCornerShape(12.dp)).background(if (c.connected) C.container else C.surface3).padding(horizontal = 10.dp, vertical = 4.dp))
                    }
                }
            }
            item { Panel(onClick = { vm.screen = Screen.Connections }) { Row(verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Outlined.Extension, null, tint = C.onContainer); Spacer(Modifier.width(12.dp)); Column(Modifier.weight(1f)) { Text("Ещё тысячи сервисов", color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold); Text("Через MCP: Zapier, Context7, Supabase, Hugging Face и свои серверы", color = C.dim, fontSize = 13.sp) }; Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) } } }
        }
    }
    open?.let { c ->
        val vals = remember(c.id) { mutableStateMapOf<String, String>().also { m -> c.fields.forEach { m[it.k] = it.value } } }
        AppDialog("${c.icon} ${c.name}", { open = null }, "Сохранить и проверить", c.fields.filter { !it.opt }.all { !vals[it.k].isNullOrBlank() }, { vm.saveConnector(c, vals.toMap(), true); open = null }) {
            Text(c.desc, color = C.dim, fontSize = 13.sp)
            c.fields.forEach { f -> Field(vals[f.k] ?: "", { vals[f.k] = it }, f.label + if (f.opt) " (необязательно)" else "", mono = f.secret); if (f.hint.isNotBlank()) Text(f.hint, color = C.dim, fontSize = 12.sp) }
            Text("Что умеет: " + c.actions.joinToString("; ") { it.desc + if (it.write) " ✎" else "" }, color = C.dim, fontSize = 12.sp, lineHeight = 17.sp)
            Text("✎ — действия, меняющие данные: в чате спрашивают подтверждение, у автономного агента — только при включённом «Разрешить действия».", color = C.dim, fontSize = 12.sp, lineHeight = 17.sp)
            if (c.connected) SoftChip(Icons.Outlined.LinkOff, "Отключить", false) { vm.removeConnector(c); open = null }
        }
    }
}
