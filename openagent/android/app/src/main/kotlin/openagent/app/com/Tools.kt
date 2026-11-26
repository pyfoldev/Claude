package openagent.app.com

import android.annotation.SuppressLint
import android.content.Intent
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material.icons.automirrored.filled.InsertDriveFile
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.layout.ContentScale
import coil.compose.AsyncImage
import coil.request.ImageRequest
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import kotlinx.serialization.json.*

/** Сегментированный выбор с анимированным индикатором. */
@Composable
fun Segmented(options: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit, modifier: Modifier = Modifier) {
    val idx = options.indexOfFirst { it.first == selected }.coerceAtLeast(0)
    val pos by animateFloatAsState(idx.toFloat(), spring(0.7f, 380f), label = "seg")
    BoxWithConstraints(modifier.fillMaxWidth().height(48.dp).clip(RoundedCornerShape(24.dp)).background(C.surface3).padding(4.dp)) {
        val w = maxWidth / options.size
        Box(Modifier.offset(x = w * pos).width(w).fillMaxHeight().clip(RoundedCornerShape(20.dp)).background(C.container))
        Row(Modifier.fillMaxSize()) {
            options.forEach { (k, label) ->
                val sel = k == selected
                Box(Modifier.weight(1f).fillMaxHeight().clip(RoundedCornerShape(20.dp)).clickable { if (!sel) { Haptics.click(); onSelect(k) } }, contentAlignment = Alignment.Center) {
                    Text(label, color = if (sel) C.onContainer else C.dim, fontSize = 14.sp, fontWeight = if (sel) FontWeight.SemiBold else FontWeight.Medium)
                }
            }
        }
    }
}

@Composable
fun AppDialog(title: String, onDismiss: () -> Unit, confirm: String, confirmEnabled: Boolean = true, onConfirm: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    AlertDialog(onDismissRequest = onDismiss, containerColor = C.surface2, shape = RoundedCornerShape(32.dp), titleContentColor = C.text, textContentColor = C.text,
        title = { Text(title, fontWeight = FontWeight.Bold, fontSize = 22.sp) },
        text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp), content = content) },
        confirmButton = { PillButton(confirm, { Haptics.click(); onConfirm() }, enabled = confirmEnabled, height = 48.dp) },
        dismissButton = { TextButton(onDismiss) { Text("Отмена", color = C.dim, fontSize = 16.sp) } })
}

@Composable
fun Field(value: String, onChange: (String) -> Unit, label: String, modifier: Modifier = Modifier, singleLine: Boolean = true, mono: Boolean = false, minLines: Int = 1) {
    OutlinedTextField(value, onChange, label = { Text(label) }, singleLine = singleLine, minLines = minLines, modifier = modifier.fillMaxWidth(), shape = RoundedCornerShape(22.dp), colors = fieldColors(),
        textStyle = androidx.compose.ui.text.TextStyle(fontSize = 16.sp, fontFamily = if (mono) FontFamily.Monospace else null, color = C.text))
}

// ====================== Выбор модели ======================
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ModelSheet(vm: AppVM, onDismiss: () -> Unit) {
    var addOpen by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { vm.loadProviders() }
    var viewProv by remember { mutableStateOf(vm.provider) }
    // «Perplexity Agent» показываем всегда: если сервер его не видит — рядом подсказка, что нужно сделать
    val allProviders = vm.providers + (if (vm.providers.none { it.id == "perplexity" }) listOf(ProviderInfo("perplexity", "Perplexity Agent", builtin = true, models = listOf("agent-fast", "agent-low", "agent-medium", "agent-high", "openai/gpt-6-luna", "anthropic/claude-haiku-5-5"))) else emptyList())
    val prov = allProviders.firstOrNull { it.id == viewProv }
    var query by remember { mutableStateOf("") }
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = C.surface, shape = RoundedCornerShape(topStart = 36.dp, topEnd = 36.dp), dragHandle = { BottomSheetDefaults.DragHandle(color = C.outline) }) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp).navigationBarsPadding()) {
            Text("Модель и режим", color = C.text, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(14.dp))
            Text("Усилие", color = C.dim, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 6.dp, bottom = 6.dp))
            Segmented(listOf("low" to "Быстро", "auto" to "Норма", "high" to "Глубоко"), vm.effort, vm::updEffort)
            Text(when (vm.effort) { "low" -> "Минимум шагов — самый быстрый ответ"; "high" -> "План и проверка результата, до 45 шагов"; else -> "Баланс скорости и качества, до 20 шагов" },
                color = C.dim, fontSize = 13.sp, modifier = Modifier.padding(start = 6.dp, top = 8.dp, bottom = 16.dp))
            Text("Провайдер", color = C.dim, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 6.dp, bottom = 6.dp))
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                allProviders.forEach { p -> SoftChip(if (p.builtin) Icons.Outlined.Bolt else Icons.Outlined.Hub, p.name, viewProv == p.id) { viewProv = p.id; query = "" } }
                SoftChip(Icons.Outlined.Add, "Свой", false) { addOpen = true }
            }
            Spacer(Modifier.height(14.dp))
            if (prov?.id == "perplexity") {
                val live = vm.providers.any { it.id == "perplexity" }
                val msg = when {
                    live -> "✓ Perplexity подключён — отвечает сам агент Perplexity: поиск, рассуждение, источники"
                    vm.pplxKeyState.isBlank() -> "Ключ не задан: Настройки → Поиск и Perplexity → «Ключ Perplexity»"
                    vm.serverNoPplx || vm.serverOld -> "Сервер не обновлён — запустите ./deploy/deploy.sh, затем откройте список снова"
                    else -> "Ключ есть, но телефон ещё не подключился к серверу. Подождите несколько секунд и откройте список снова (приложение должно быть открыто)"
                }
                Text(msg, color = if (live) C.ok else C.dim, fontSize = 13.sp, modifier = Modifier.padding(start = 6.dp, bottom = 8.dp))
                if (!live) Row(Modifier.padding(start = 6.dp, bottom = 10.dp)) { SoftChip(Icons.Outlined.Settings, "Открыть настройки", false) { onDismiss(); vm.screen = Screen.Settings } }
            }
            if (prov != null) {
                if (prov.models.size > 8) OutlinedTextField(query, { query = it }, singleLine = true, placeholder = { Text("Поиск модели", color = C.dim) }, leadingIcon = { Icon(Icons.Outlined.Search, null, tint = C.dim) },
                    modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp), shape = RoundedCornerShape(26.dp), colors = fieldColors())
                val rows = buildList {
                    prov.models.filter { query.isBlank() || it.contains(query, true) }.forEach { add(it to if (prov.id == "perplexity") when (it) { "agent-fast" -> "Быстрый — короткие факты со ссылками"; "agent-low" -> "Обычный — исследование с источниками"; "agent-medium" -> "Глубокий — много источников и шагов"; "agent-high" -> "Максимум — экспертный разбор"; "openai/gpt-6-luna" -> "GPT-6 Luna — быстрая модель OpenAI + поиск в интернете"; "anthropic/claude-haiku-5-5" -> "Claude Haiku 5.5 — быстрая модель Anthropic + поиск в интернете"; else -> it } else if (it.substringAfterLast('/') in listOf("gpt-6-luna", "claude-haiku-5-5")) vm.prettyModel(it) + "  ·  " + it else it) }
                }
                LazyColumn(Modifier.heightIn(max = 300.dp).clip(RoundedCornerShape(24.dp)).background(C.surface2)) {
                    if (rows.isEmpty()) item { Text(if (prov.models.isEmpty()) "Список моделей пуст — проверьте адрес и ключ провайдера" else "Ничего не найдено", color = C.dim, modifier = Modifier.padding(20.dp)) }
                    items(rows, key = { it.first }) { (id, label) ->
                        val sel = vm.provider == prov.id && vm.model == id
                        Row(Modifier.fillMaxWidth().clickable { Haptics.click(); vm.selectModel(prov.id, id); onDismiss() }.background(if (sel) C.container.copy(alpha = 0.55f) else Color.Transparent).padding(horizontal = 18.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(label, color = if (sel) C.onContainer else C.text, fontSize = 16.sp, fontWeight = if (sel) FontWeight.SemiBold else FontWeight.Normal, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                            if (sel) Icon(Icons.Outlined.CheckCircle, null, tint = C.accent)
                        }
                    }
                }
                if (!prov.builtin) {
                    var custom by remember(prov.id) { mutableStateOf("") }
                    Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(custom, { custom = it }, singleLine = true, placeholder = { Text("Свой id модели", color = C.dim) }, modifier = Modifier.weight(1f), shape = RoundedCornerShape(26.dp), colors = fieldColors())
                        PillButton("Выбрать", { vm.selectModel(prov.id, custom.trim()); onDismiss() }, enabled = custom.isNotBlank(), height = 56.dp)
                    }
                    Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("${prov.baseUrl}  ·  ключ ${prov.keyHint ?: ""}", color = C.dim, fontSize = 12.sp, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        TextButton({ vm.deleteProvider(prov.id); viewProv = "river" }) { Text("Удалить", color = C.danger) }
                    }
                }
            }
        }
    }
    if (addOpen) AddProviderDialog(vm) { addOpen = false; if (it) onDismiss() }
}

@Composable
fun AddProviderDialog(vm: AppVM, done: (Boolean) -> Unit) {
    var name by remember { mutableStateOf("") }; var url by remember { mutableStateOf("https://") }; var key by remember { mutableStateOf("") }; var effort by remember { mutableStateOf(false) }
    var models by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val ctx = LocalContext.current
    LaunchedEffect(Unit) { vm.loadPresets() }
    AppDialog("Свой провайдер", { done(false) }, if (busy) "Проверяю…" else "Подключить", url.length > 10 && !busy, onConfirm = { busy = true; vm.addProvider(name.ifBlank { "" }, url, key, effort, models) { ok -> busy = false; if (ok) done(true) } }) {
        Text("Любой OpenAI-совместимый API. Выберите шаблон или заполните вручную:", color = C.dim, fontSize = 14.sp)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            vm.presets.forEach { p -> SoftChip(Icons.Outlined.AutoAwesome, p.name, url == p.baseUrl) { name = p.name; url = p.baseUrl; models = p.models } }
        }
        vm.presets.firstOrNull { it.baseUrl == url }?.let { p ->
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(C.container.copy(alpha = 0.5f)).clickable { runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(p.keyUrl)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } }.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.Key, null, tint = C.onContainer, modifier = Modifier.size(20.dp)); Spacer(Modifier.width(10.dp))
                Text((p.note ?: "Получить API-ключ") + " — открыть", color = C.onContainer, fontSize = 13.sp)
            }
        }
        Field(name, { name = it }, "Название")
        Field(url, { url = it }, "Base URL (…/v1)")
        Field(key, { key = it }, "API-ключ")
        Field(models, { models = it }, "Модели через запятую (необязательно)", singleLine = false)
        Row(Modifier.fillMaxWidth().clickable { effort = !effort }.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text("Передавать reasoning_effort", color = C.text, fontSize = 15.sp); Text("Если провайдер поддерживает уровень размышлений", color = C.dim, fontSize = 12.sp) }
            Switch(effort, { Haptics.click(); effort = it }, colors = SwitchDefaults.colors(checkedThumbColor = C.onAccent, checkedTrackColor = C.accent, uncheckedThumbColor = C.dim, uncheckedTrackColor = C.surface3, uncheckedBorderColor = C.outline))
        }
    }
}

// ====================== Карточки в чате ======================
@Composable
fun TodoCard(argsJson: String) {
    val items = remember(argsJson) { runCatching { JSON.parseToJsonElement(argsJson).jsonObject["todos"]!!.jsonArray.map { it.jsonObject["text"]!!.jsonPrimitive.content to (it.jsonObject["status"]?.jsonPrimitive?.content ?: "pending") } }.getOrDefault(emptyList()) }
    if (items.isEmpty()) return
    val done = items.count { it.second == "done" }
    val prog by animateFloatAsState(done / items.size.toFloat(), spring(0.8f, 200f), label = "prog")
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(26.dp)).background(C.surface2).padding(16.dp).animateContentSize()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(38.dp).clip(CircleShape).background(C.container), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.Checklist, null, tint = C.onContainer, modifier = Modifier.size(20.dp)) }
            Spacer(Modifier.width(12.dp)); Text("План", color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Text("$done/${items.size}", color = C.accent, fontSize = 15.sp, fontWeight = FontWeight.Bold)
        }
        LinearProgressIndicator({ prog }, Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 8.dp).height(6.dp).clip(CircleShape), color = C.accent, trackColor = C.surface3, strokeCap = androidx.compose.ui.graphics.StrokeCap.Round)
        items.forEach { (t, st) ->
            Row(Modifier.padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
                when (st) {
                    "done" -> Icon(Icons.Outlined.CheckCircle, null, tint = C.ok, modifier = Modifier.size(22.dp))
                    "in_progress" -> CircularProgressIndicator(Modifier.size(22.dp), color = C.accent, strokeWidth = 2.5.dp)
                    else -> Icon(Icons.Outlined.RadioButtonUnchecked, null, tint = C.dim, modifier = Modifier.size(22.dp))
                }
                Spacer(Modifier.width(12.dp))
                Text(t, color = if (st == "done") C.dim else C.text, fontSize = 15.sp, textDecoration = if (st == "done") TextDecoration.LineThrough else null, lineHeight = 21.sp)
            }
        }
    }
}

@Composable
fun AskCard(argsJson: String, enabled: Boolean, onPick: (String) -> Unit) {
    val o = remember(argsJson) { runCatching { JSON.parseToJsonElement(argsJson).jsonObject }.getOrNull() }
    // модель иногда шлёт варианты объектами ({"label":…}) или вопрос не строкой — не падаем, берём текст как получится
    fun txt(e: kotlinx.serialization.json.JsonElement?): String = when (e) {
        null -> ""
        is kotlinx.serialization.json.JsonPrimitive -> e.content
        is kotlinx.serialization.json.JsonObject -> listOf("label", "title", "text", "name", "value", "option").firstNotNullOfOrNull { k -> (e[k] as? kotlinx.serialization.json.JsonPrimitive)?.content } ?: e.values.firstNotNullOfOrNull { (it as? kotlinx.serialization.json.JsonPrimitive)?.content } ?: ""
        is kotlinx.serialization.json.JsonArray -> e.joinToString(", ") { txt(it) }
    }
    val q = txt(o?.get("question"))
    val opts = (o?.get("options") as? kotlinx.serialization.json.JsonArray)?.map { txt(it) }?.filter { it.isNotBlank() }.orEmpty()
    val type = (o?.get("type") as? kotlinx.serialization.json.JsonPrimitive)?.contentOrNull ?: if (opts.isEmpty()) "text" else "single"
    val picked = remember { mutableStateListOf<String>() }
    var free by remember { mutableStateOf("") }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(26.dp)).background(C.surface2).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(38.dp).clip(CircleShape).background(C.container), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.HelpOutline, null, tint = C.onContainer, modifier = Modifier.size(20.dp)) }
            Spacer(Modifier.width(12.dp)); Text(q, color = C.text, fontSize = 16.sp, fontWeight = FontWeight.Medium, lineHeight = 22.sp)
        }
        if (type == "multi") {
            opts.forEach { opt ->
                val on = opt in picked
                val bg by animateColorAsState(if (on) C.container else C.surface3, label = "ms")
                Row(Modifier.fillMaxWidth().height(52.dp).bounceClick(enabled) { Haptics.tick(); if (on) picked.remove(opt) else picked.add(opt) }.clip(RoundedCornerShape(26.dp)).background(bg).padding(horizontal = 18.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(if (on) Icons.Outlined.CheckBox else Icons.Outlined.CheckBoxOutlineBlank, null, tint = if (on) C.accent else C.dim)
                    Spacer(Modifier.width(12.dp)); Text(opt, color = if (on) C.onContainer else C.text, fontSize = 16.sp, modifier = Modifier.weight(1f))
                }
            }
            PillButton("Отправить (${picked.size})", { onPick(picked.joinToString(", ")) }, Modifier.fillMaxWidth(), enabled = enabled && picked.isNotEmpty(), height = 52.dp)
        } else if (type == "single") {
            opts.forEach { opt ->
                Row(Modifier.fillMaxWidth().height(52.dp).bounceClick(enabled) { onPick(opt) }.clip(RoundedCornerShape(26.dp)).background(if (enabled) C.container else C.surface3).padding(horizontal = 20.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(opt, color = if (enabled) C.onContainer else C.dim, fontSize = 16.sp, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
                    Icon(Icons.Outlined.ChevronRight, null, tint = if (enabled) C.onContainer else C.dim)
                }
            }
        }
        if (type == "text" || type == "single") Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(free, { free = it }, enabled = enabled, singleLine = true, placeholder = { Text(if (type == "text") "Ваш ответ" else "Свой вариант…", color = C.dim) }, modifier = Modifier.weight(1f), shape = RoundedCornerShape(26.dp), colors = fieldColors())
            RoundButton(Icons.AutoMirrored.Outlined.Send, "Отправить", { onPick(free.trim()) }, container = C.accent, content = C.onAccent, size = 52.dp, enabled = enabled && free.isNotBlank())
        }
    }
}

// ====================== Автоматизации ======================
private fun fmtEvery(m: Int?) = when { m == null -> "разово"; m < 0 -> "каждый день"; m % 1440 == 0 -> "каждые ${m / 1440} дн"; m % 60 == 0 -> "каждые ${m / 60} ч"; else -> "каждые $m мин" }
private fun fmtTime(ms: Long?) = if (ms == null) "—" else java.text.SimpleDateFormat("d MMM, HH:mm", java.util.Locale("ru")).format(java.util.Date(ms))

private val AUTO_TEMPLATES = listOf(
    Triple("Утренний брифинг", "Составь мой утренний брифинг: погода на сегодня в моём городе (lookup weather; город возьми из памяти, если не знаешь — Алматы), мои невыполненные задачи (tasks list), главные новости по моим интересам за ночь, курс доллара и биткоина. Коротко, по пунктам, в тоне личного помощника.", -1 to "chat"),
    Triple("Вечерний итог", "Подведи итог дня: какие задачи из списка выполнены и какие остались (tasks list), что стоит сделать завтра, погода на завтра в моём городе. Коротко и дружелюбно.", -1 to "chat"),
    Triple("Утренняя сводка", "Найди главные новости за последние 12 часов по моим интересам (технологии, ИИ, мир), коротко перескажи 5–7 пунктов со ссылками на источники.", 1440 to "chat"),
    Triple("Проверка сервера", "Проверь состояние сервера: нагрузка, память, диск, упавшие службы. Если что-то выше 85% или упало — выдели это в начале отчёта. Ничего не перезапускай.", 60 to "code"),
    Triple("Дайджест GitHub", "Покажи, что нового в моих репозиториях за сутки: коммиты, открытые issues и PR. Только отчёт, без изменений.", 1440 to "code"),
    Triple("Курсы валют", "Узнай курс доллара, евро и биткоина и скажи, как они изменились за сутки.", 360 to "chat"),
)

@Composable
fun AutomationsScreen(vm: AppVM) {
    var add by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }; var prompt by remember { mutableStateOf("") }; var every by remember { mutableStateOf("60") }; var mode by remember { mutableStateOf("code") }
    var wUrl by remember { mutableStateOf("") }; var wText by remember { mutableStateOf("") }; var dTime by remember { mutableStateOf("08:00") }
    LaunchedEffect(Unit) { vm.loadSchedules() }
    PageScaffold("Автоматизации", { vm.screen = Screen.Chat }) {
        Box(Modifier.weight(1f)) {
            LazyColumn(contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 120.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item { Text("Агент сам запускает задачи по расписанию и пишет результат в новый чат. Когда задача готова, придёт уведомление.", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) }
                item {
                    Column {
                        Text("Шаблоны", color = C.dim, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp, bottom = 8.dp))
                        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            AUTO_TEMPLATES.forEach { (n, p, ev) ->
                                Column(Modifier.width(190.dp).height(120.dp).bounceClick { name = n; prompt = p; every = if (ev.first < 0) "daily" else ev.first.toString(); dTime = if (n.startsWith("Вечер")) "21:00" else "08:00"; mode = ev.second; add = true }.clip(RoundedCornerShape(24.dp)).background(C.surface2).padding(14.dp)) {
                                    Box(Modifier.size(34.dp).clip(CircleShape).background(C.container), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.AutoAwesome, null, tint = C.onContainer, modifier = Modifier.size(18.dp)) }
                                    Text(n, color = C.text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp), maxLines = 1)
                                    Text(fmtEvery(ev.first), color = C.dim, fontSize = 12.sp)
                                }
                            }
                        }
                    }
                }
                if (vm.schedules.isEmpty()) item { EmptyHint(Icons.Outlined.Schedule, "Пока нет автоматизаций") }
                items(vm.schedules, key = { it.id }) { s ->
                    Column(Modifier.fillMaxWidth().animateItem().clip(RoundedCornerShape(28.dp)).background(C.surface2).padding(18.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(44.dp).clip(CircleShape).background(C.container), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.Schedule, null, tint = C.onContainer) }
                            Spacer(Modifier.width(14.dp))
                            Column(Modifier.weight(1f)) {
                                Text(s.name, color = C.text, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text("${if (s.hookUrl != null) "вебхук" else if (s.watchUrl != null) "слежение" else fmtEvery(s.everyMin)} · ${if (s.mode == "code") "Code" else "Чат"} · запусков ${s.runs}", color = C.dim, fontSize = 13.sp)
                            }
                            Switch(s.enabled, { Haptics.click(); vm.toggleSchedule(s, it) }, colors = SwitchDefaults.colors(checkedThumbColor = C.onAccent, checkedTrackColor = C.accent, uncheckedThumbColor = C.dim, uncheckedTrackColor = C.surface3, uncheckedBorderColor = C.outline))
                        }
                        Text(s.prompt, color = C.text.copy(alpha = 0.85f), fontSize = 14.sp, maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 12.dp), lineHeight = 20.sp)
                        if (s.hookUrl != null) { val c2 = LocalContext.current; Text(s.hookUrl, color = C.accent, fontSize = 12.sp, style = Mono, maxLines = 2, modifier = Modifier.padding(top = 8.dp).clickable { copyToClipboard(c2, s.hookUrl); vm.toast = "Ссылка вебхука скопирована" }); Text("POST на эту ссылку запускает задачу (тело запроса попадёт агенту)", color = C.dim, fontSize = 12.sp) }
                        else Text("Следующий запуск: ${if (s.enabled) fmtTime(s.nextRun) else "выключено"}", color = C.accent, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
                        Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            SoftChip(Icons.Outlined.PlayArrow, "Запустить", false) { vm.runSchedule(s) }
                            SoftChip(Icons.Outlined.DeleteOutline, "Удалить", false) { vm.deleteSchedule(s) }
                        }
                    }
                }
            }
            PillButton("Новая", { name = ""; prompt = ""; every = "60"; mode = "code"; add = true }, Modifier.align(Alignment.BottomEnd).padding(20.dp).navigationBarsPadding(), icon = Icons.Outlined.Add, height = 60.dp)
        }
    }
    if (add) {
        AppDialog("Новая автоматизация", { add = false }, "Создать", name.isNotBlank() && prompt.isNotBlank() && (every != "watch" || wUrl.startsWith("http")) && (every != "daily" || Regex("\\d{1,2}:\\d{2}").matches(dTime)), { if (every == "watch") vm.addWatch(name, prompt, 30, wUrl.trim(), wText.trim()) else if (every == "daily") vm.addDaily(name, prompt, dTime, mode) else vm.addSchedule(name, prompt, if (every == "hook") 0 else (every.toIntOrNull() ?: 60), mode, every == "hook"); add = false }) {
            Field(name, { name = it }, "Название")
            Field(prompt, { prompt = it }, "Что делать агенту", singleLine = false, minLines = 3)
            Segmented(listOf("15" to "15м", "60" to "1ч", "360" to "6ч", "1440" to "Сутки", "daily" to "Каждый день", "hook" to "Вебхук", "watch" to "Страница"), every, { every = it })
            if (every == "daily") Field(dTime, { dTime = it.filter { c -> c.isDigit() || c == ':' }.take(5) }, "Время (ЧЧ:ММ, по часовому поясу телефона)")
            if (every == "watch") { Field(wUrl, { wUrl = it }, "Адрес страницы (https://…)", mono = true); Field(wText, { wText = it }, "Следить за текстом (необязательно)"); Text("Проверка раз в 30 минут. Агент запускается только если страница изменилась (или текст появился/пропал).", color = C.dim, fontSize = 12.sp) }
            else Segmented(listOf("code" to "Code", "chat" to "Чат"), mode, { mode = it })
        }
    }
}

@Composable
fun EmptyHint(icon: ImageVector, text: String) {
    Column(Modifier.fillMaxWidth().padding(vertical = 48.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Box(Modifier.size(72.dp).clip(CircleShape).background(C.surface2), contentAlignment = Alignment.Center) { Icon(icon, null, tint = C.dim, modifier = Modifier.size(34.dp)) }
        Spacer(Modifier.height(14.dp)); Text(text, color = C.dim, fontSize = 16.sp)
    }
}

// ====================== Навыки и плагины ======================
@Composable
fun SkillsScreen(vm: AppVM) {
    var edit by remember { mutableStateOf<Skill?>(null) }
    var adding by remember { mutableStateOf(false) }
    var tab by remember { mutableStateOf("mine") }
    var q by remember { mutableStateOf("") }
    var url by remember { mutableStateOf("") }
    LaunchedEffect(Unit) { vm.loadSkills() }
    LaunchedEffect(tab) { if (tab == "gh" && vm.repoHits.isEmpty()) vm.searchRepos("") }
    LaunchedEffect(q) { if (tab == "gh") { kotlinx.coroutines.delay(600); vm.searchRepos(q) } }
    PageScaffold("Навыки", { vm.screen = Screen.Chat }) {
        Box(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) { Segmented(listOf("mine" to "Мои (${vm.skills.size})", "gh" to "GitHub"), tab, { tab = it }) }
        Box(Modifier.weight(1f)) {
            if (tab == "mine") LazyColumn(contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 120.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item { Text("Навык — инструкция или плагин, который агент подгружает по необходимости. Ставьте готовые с GitHub в один клик или создавайте свои.", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) }
                if (vm.skills.isEmpty()) item { EmptyHint(Icons.Outlined.Extension, "Навыков пока нет") }
                items(vm.skills, key = { it.id }) { s ->
                    Row(Modifier.fillMaxWidth().animateItem().bounceClick { edit = s }.clip(RoundedCornerShape(26.dp)).background(C.surface2).padding(start = 16.dp, top = 12.dp, bottom = 12.dp, end = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(44.dp).clip(CircleShape).background(C.container), contentAlignment = Alignment.Center) { Icon(if (s.source != null) Icons.Outlined.Extension else Icons.Outlined.AutoFixHigh, null, tint = C.onContainer) }
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f)) {
                            Text(s.name, color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(s.description.ifBlank { s.content }, color = C.dim, fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                            if (s.source != null) Text("GitHub · ${s.source}", color = C.accent, fontSize = 11.sp, modifier = Modifier.padding(top = 2.dp), maxLines = 1)
                        }
                        RoundButton(Icons.Outlined.DeleteOutline, "Удалить", { vm.deleteSkill(s) }, container = Color.Transparent, content = C.dim, size = 44.dp)
                    }
                }
            } else LazyColumn(contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 40.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedTextField(q, { q = it }, singleLine = true, placeholder = { Text("Поиск навыков и плагинов на GitHub", color = C.dim) }, leadingIcon = { Icon(Icons.Outlined.Search, null, tint = C.dim) },
                            modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(28.dp), colors = fieldColors())
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedTextField(url, { url = it }, singleLine = true, placeholder = { Text("owner/repo или ссылка", color = C.dim) }, modifier = Modifier.weight(1f), shape = RoundedCornerShape(28.dp), colors = fieldColors())
                            PillButton(if (vm.installing == url.trim()) "…" else "Установить", { vm.installRepo(url.trim()); url = "" }, enabled = url.trim().length > 3 && vm.installing == null, height = 56.dp)
                        }
                        Text("Устанавливаются все SKILL.md, commands и agents из репозитория (формат Claude Code / Agent Skills).", color = C.dim, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 8.dp))
                    }
                }
                if (vm.repoSearching) item { Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = C.accent) } }
                items(vm.repoHits, key = { it.repo }) { h ->
                    val busy = vm.installing == h.repo
                    val has = vm.skills.any { it.source == h.repo }
                    Column(Modifier.fillMaxWidth().animateItem().clip(RoundedCornerShape(26.dp)).background(C.surface2).padding(16.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(h.repo, color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text("★ ${h.stars}" + if (h.topics.isNotEmpty()) "  ·  " + h.topics.take(3).joinToString(", ") else "", color = C.accent, fontSize = 12.sp, maxLines = 1)
                            }
                            Spacer(Modifier.width(10.dp))
                            if (busy) CircularProgressIndicator(Modifier.size(28.dp), color = C.accent, strokeWidth = 3.dp)
                            else Box(Modifier.height(44.dp).bounceClick(vm.installing == null) { vm.installRepo(h.repo) }.clip(RoundedCornerShape(22.dp)).background(if (has) C.surface3 else C.accent).padding(horizontal = 18.dp), contentAlignment = Alignment.Center) {
                                Text(if (has) "Обновить" else "Установить", color = if (has) C.text else C.onAccent, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                            }
                        }
                        if (h.description.isNotBlank()) Text(h.description, color = C.dim, fontSize = 13.sp, lineHeight = 18.sp, maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 8.dp))
                    }
                }
                if (!vm.repoSearching && vm.repoHits.isEmpty()) item { EmptyHint(Icons.Outlined.Search, "Ничего не найдено") }
            }
            if (tab == "mine") PillButton("Навык", { adding = true }, Modifier.align(Alignment.BottomEnd).padding(20.dp).navigationBarsPadding(), icon = Icons.Outlined.Add, height = 60.dp)
        }
    }
    if (adding || edit != null) {
        val e = edit
        var name by remember(e) { mutableStateOf(e?.name ?: "") }; var desc by remember(e) { mutableStateOf(e?.description ?: "") }; var body by remember(e) { mutableStateOf(e?.content ?: "") }
        AppDialog(if (e == null) "Новый навык" else "Навык", { adding = false; edit = null }, "Сохранить", name.isNotBlank() && body.isNotBlank(), { vm.saveSkill(name.trim(), desc.trim(), body); adding = false; edit = null }) {
            Field(name, { name = it }, "Название (латиницей)")
            Field(desc, { desc = it }, "Когда применять")
            Field(body, { body = it }, "Инструкция", singleLine = false, minLines = 6)
        }
    }
}

// ====================== Просмотр изображения ======================
@Composable
fun ImageViewer(vm: AppVM, a: Attach, onClose: () -> Unit) {
    val ctx = LocalContext.current
    var scale by remember { mutableStateOf(1f) }; var off by remember { mutableStateOf(androidx.compose.ui.geometry.Offset.Zero) }
    androidx.compose.ui.window.Dialog(onClose, androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.96f))) {
            AsyncImage(ImageRequest.Builder(ctx).data("${vm.api.base}/api/files/${a.id}").addHeader("Authorization", "Bearer ${vm.store.token}").build(), a.name, imageLoader = vm.imageLoader, contentScale = ContentScale.Fit,
                modifier = Modifier.fillMaxSize().padding(8.dp).androidx_graphicsLayer(scale, off)
                    .pointerInput(Unit) { detectTransformGestures { _, pan, zoom, _ -> scale = (scale * zoom).coerceIn(1f, 8f); off = if (scale > 1f) off + pan else androidx.compose.ui.geometry.Offset.Zero } }
                    .pointerInput(Unit) { detectTapGestures(onDoubleTap = { if (scale > 1f) { scale = 1f; off = androidx.compose.ui.geometry.Offset.Zero } else scale = 2.5f }) })
            Row(Modifier.align(Alignment.TopEnd).statusBarsPadding().padding(12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                RoundButton(Icons.Outlined.Share, "Поделиться", { vm.openFile(a) }, container = C.surface3)
                RoundButton(Icons.Outlined.Close, "Закрыть", onClose, container = C.surface3)
            }
        }
    }
}
private fun Modifier.androidx_graphicsLayer(scale: Float, off: androidx.compose.ui.geometry.Offset) = this.graphicsLayer(scaleX = scale, scaleY = scale, translationX = off.x, translationY = off.y)

// ====================== Файлы ======================
private fun fileIcon(n: String) = when {
    n.endsWith(".apk") -> Icons.Outlined.Android
    Regex(".*\\.(png|jpe?g|gif|webp|svg)$", RegexOption.IGNORE_CASE).matches(n) -> Icons.Outlined.Image
    Regex(".*\\.(zip|tar|gz|7z|rar)$", RegexOption.IGNORE_CASE).matches(n) -> Icons.Outlined.FolderZip
    Regex(".*\\.(kt|java|py|js|ts|sh|json|xml|md|yml|yaml|gradle|html|css|txt|log|toml)$", RegexOption.IGNORE_CASE).matches(n) -> Icons.Outlined.Code
    else -> Icons.AutoMirrored.Outlined.InsertDriveFile
}

@Composable
fun FilesScreen(vm: AppVM) {
    val scope = rememberCoroutineScope()
    var open by remember { mutableStateOf<Pair<String, String>?>(null) }
    var confirmDel by remember { mutableStateOf<FsItem?>(null) }
    LaunchedEffect(Unit) { if (vm.fsDir == null) vm.fsOpen(".") }
    val dir = vm.fsDir
    val atRoot = dir == null || dir.path == vm.fsRoot
    PageScaffold("Файлы", { if (!atRoot && dir != null) vm.fsOpen(dir.parent) else vm.screen = Screen.Chat }) {
        if (dir != null) Text(dir.path.removePrefix(vm.fsRoot).ifEmpty { "/" }, color = C.accent, style = Mono, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 24.dp, vertical = 4.dp), maxLines = 1, overflow = TextOverflow.Ellipsis)
        LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 24.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (!atRoot && dir != null) item { FileRow(Icons.Outlined.ArrowUpward, "..", "На уровень выше", true) { vm.fsOpen(dir.parent) } }
            if (dir != null && dir.items.isEmpty()) item { EmptyHint(Icons.Outlined.FolderOpen, "Папка пуста") }
            items(dir?.items.orEmpty(), key = { (dir?.path ?: "") + it.name }) { f ->
                Box(Modifier.animateItem()) {
                    FileRow(if (f.dir) Icons.Outlined.Folder else fileIcon(f.name), f.name, if (f.dir) "папка" else humanSize(f.size), f.dir, onLong = { confirmDel = f }) {
                        val full = dir!!.path.trimEnd('/') + "/" + f.name
                        if (f.dir) vm.fsOpen(full) else scope.launch {
                            if (f.size < 600 * 1024 && fileIcon(f.name) == Icons.Outlined.Code || f.name.endsWith(".txt")) vm.fsReadFile(full)?.let { open = full to it }
                            else vm.fsShare(full, f.name)
                        }
                    }
                }
            }
        }
    }
    open?.let { (path, text) ->
        var body by remember(path) { mutableStateOf(text) }
        AlertDialog({ open = null }, containerColor = C.surface2, shape = RoundedCornerShape(32.dp), modifier = Modifier.fillMaxWidth(0.96f), properties = androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false),
            title = { Text(path.substringAfterLast('/'), color = C.text, fontSize = 18.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis) },
            text = {
                BasicTextField(body, { body = it }, textStyle = androidx.compose.ui.text.TextStyle(color = C.text, fontSize = 12.sp, lineHeight = 17.sp, fontFamily = FontFamily.Monospace), cursorBrush = SolidColor(C.accent),
                    modifier = Modifier.fillMaxWidth().heightIn(min = 200.dp, max = 460.dp).clip(RoundedCornerShape(18.dp)).background(C.code).padding(14.dp).verticalScroll(rememberScrollState()))
            },
            confirmButton = { PillButton("Сохранить", { vm.fsSave(path, body); open = null }, height = 48.dp) },
            dismissButton = { Row { TextButton({ vm.fsShare(path, path.substringAfterLast('/')) }) { Text("Скачать", color = C.dim) }; TextButton({ open = null }) { Text("Закрыть", color = C.dim) } } })
    }
    confirmDel?.let { f ->
        AppDialog("Удалить «${f.name}»?", { confirmDel = null }, "Удалить", true, { vm.fsRemove(dir!!.path.trimEnd('/') + "/" + f.name); confirmDel = null }) {
            Text("Это действие нельзя отменить.", color = C.dim)
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun FileRow(icon: ImageVector, name: String, sub: String, dir: Boolean, onLong: (() -> Unit)? = null, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(C.surface2).combinedClickable(onClick = { Haptics.tick(); onClick() }, onLongClick = { Haptics.heavy(); onLong?.invoke() }).padding(horizontal = 14.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(42.dp).clip(RoundedCornerShape(14.dp)).background(if (dir) C.container else C.surface3), contentAlignment = Alignment.Center) { Icon(icon, null, tint = if (dir) C.onContainer else C.dim, modifier = Modifier.size(22.dp)) }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) { Text(name, color = C.text, fontSize = 16.sp, maxLines = 1, overflow = TextOverflow.Ellipsis); Text(sub, color = C.dim, fontSize = 12.sp) }
        if (dir) Icon(Icons.Outlined.ChevronRight, null, tint = C.dim)
    }
}

// ====================== Терминал ======================
@Composable
fun TerminalScreen(vm: AppVM) {
    var cmd by remember { mutableStateOf("") }
    val state = rememberLazyListState()
    val history = remember { mutableStateListOf<String>() }
    var hIdx by remember { mutableStateOf(-1) }
    LaunchedEffect(vm.term.size, vm.term.lastOrNull()?.text?.length) { if (vm.term.isNotEmpty()) state.scrollToItem(vm.term.size - 1) }
    fun run() { if (cmd.isBlank()) return; history.add(cmd); hIdx = -1; vm.termRun(cmd); cmd = "" }
    PageScaffold("Терминал", { vm.screen = Screen.Chat }) {
        Column(Modifier.weight(1f).padding(horizontal = 12.dp).clip(RoundedCornerShape(28.dp)).background(C.code).imePadding()) {
            LazyColumn(state = state, modifier = Modifier.weight(1f).padding(horizontal = 16.dp), contentPadding = PaddingValues(vertical = 14.dp)) {
                if (vm.term.isEmpty()) item { Text("root@server — полный доступ.\nКоманды выполняются в папке ${vm.termCwd}", color = C.dim, style = Mono, fontSize = 13.sp) }
                items(vm.term.size) { i ->
                    val l = vm.term[i]
                    when (l.kind) {
                        1 -> Text("$ ${l.text}", color = C.accent, style = Mono, fontSize = 13.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 10.dp))
                        2 -> Text(l.text, color = C.danger, style = Mono, fontSize = 13.sp)
                        else -> if (l.text.isNotEmpty()) Text(l.text, color = C.text.copy(alpha = 0.9f), style = Mono, fontSize = 12.sp, lineHeight = 17.sp)
                    }
                }
            }
            Row(Modifier.fillMaxWidth().background(C.surface2).padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("›", color = C.accent, style = Mono, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                BasicTextField(cmd, { cmd = it }, textStyle = androidx.compose.ui.text.TextStyle(color = C.text, fontSize = 15.sp, fontFamily = FontFamily.Monospace), cursorBrush = SolidColor(C.accent), singleLine = true,
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false, imeAction = ImeAction.Send), keyboardActions = KeyboardActions(onSend = { run() }),
                    modifier = Modifier.weight(1f).padding(horizontal = 10.dp, vertical = 10.dp), decorationBox = { inner -> if (cmd.isEmpty()) Text("команда…", color = C.dim, style = Mono, fontSize = 15.sp); inner() })
                RoundButton(Icons.Outlined.History, "История", { if (history.isNotEmpty()) { hIdx = if (hIdx < 0) history.size - 1 else (hIdx - 1).coerceAtLeast(0); cmd = history[hIdx] } }, size = 42.dp, container = Color.Transparent, content = C.dim, iconSize = 22.dp)
                if (vm.termBusy) RoundButton(Icons.Outlined.Stop, "Стоп", { vm.termStop() }, size = 44.dp, container = C.danger, content = Color.Black, iconSize = 22.dp)
                else RoundButton(Icons.AutoMirrored.Outlined.Send, "Выполнить", { run() }, size = 44.dp, container = C.accent, content = C.onAccent, iconSize = 22.dp, enabled = cmd.isNotBlank())
            }
        }
        Spacer(Modifier.height(12.dp))
    }
}

// ====================== Выбор голоса ======================
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VoiceSheet(vm: AppVM, onDismiss: () -> Unit) {
    var q by remember { mutableStateOf("") }
    var lang by remember { mutableStateOf("ru") }
    var playing by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(q, lang) { kotlinx.coroutines.delay(if (q.isEmpty()) 0 else 450); vm.searchVoices(q, lang) }
    DisposableEffect(Unit) { onDispose { vm.stopPreview() } }
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = C.surface, shape = RoundedCornerShape(topStart = 36.dp, topEnd = 36.dp), dragHandle = { BottomSheetDefaults.DragHandle(color = C.outline) }) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 16.dp).navigationBarsPadding()) {
            Text("Голос озвучки", color = C.text, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Text("Сейчас: ${vm.voiceName}. Голос всегда один и тот же — без «скачков» тембра.", color = C.dim, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp, bottom = 12.dp))
            OutlinedTextField(q, { q = it }, singleLine = true, placeholder = { Text("Поиск голоса (имя, стиль)", color = C.dim) }, leadingIcon = { Icon(Icons.Outlined.Search, null, tint = C.dim) },
                modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(26.dp), colors = fieldColors())
            Spacer(Modifier.height(10.dp))
            Segmented(listOf("ru" to "Русские", "en" to "English", "any" to "Все языки"), lang, { lang = it })
            Spacer(Modifier.height(12.dp))
            if (vm.voicesLoading && vm.voices.isEmpty()) Box(Modifier.fillMaxWidth().height(120.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = C.accent) }
            LazyColumn(Modifier.heightIn(max = 420.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (!vm.voicesLoading && vm.voices.isEmpty()) item { Text("Ничего не найдено", color = C.dim, modifier = Modifier.padding(16.dp)) }
                items(vm.voices, key = { it.id }) { v ->
                    val sel = v.id == vm.voiceId
                    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(if (sel) C.container else C.surface2).padding(start = 8.dp, end = 14.dp, top = 8.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        RoundButton(if (playing == v.id) Icons.Outlined.Stop else Icons.Outlined.PlayArrow, "Прослушать", { if (playing == v.id) { vm.stopPreview(); playing = null } else { playing = v.id; vm.previewVoice(v) } },
                            size = 46.dp, container = if (sel) C.accent else C.container, content = if (sel) C.onAccent else C.onContainer, enabled = v.sample != null)
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f).clickable { Haptics.click(); vm.chooseVoice(v) }) {
                            Text(v.title, color = if (sel) C.onContainer else C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            if (v.description.isNotBlank()) Text(v.description, color = if (sel) C.onContainer.copy(alpha = 0.8f) else C.dim, fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis, lineHeight = 16.sp)
                        }
                        if (sel) Icon(Icons.Outlined.CheckCircle, null, tint = C.accent, modifier = Modifier.padding(start = 8.dp)) else
                            Text("Выбрать", color = C.accent, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp).clip(RoundedCornerShape(14.dp)).clickable { Haptics.click(); vm.chooseVoice(v) }.padding(8.dp))
                    }
                }
            }
        }
    }
}

// ====================== Быстрые ответы под сообщением ======================
@Composable
fun QuickReplies(vm: AppVM) {
    val items = listOf(Triple(Icons.Outlined.Refresh, "Повторить", 0), Triple(Icons.Outlined.UnfoldMore, "Подробнее", 1), Triple(Icons.Outlined.UnfoldLess, "Короче", 2), Triple(Icons.Outlined.PlayArrow, "Продолжай", 3))
    Row(Modifier.horizontalScroll(rememberScrollState()).padding(top = 2.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items.forEach { (ic, label, k) ->
            Staggered(k) { SoftChip(ic, label, false) { when (k) { 0 -> vm.regenerate(); 1 -> vm.send("Подробнее, пожалуйста"); 2 -> vm.send("Короче, только суть"); else -> vm.send("Продолжай") } } }
        }
    }
}

// ====================== Сайты и мини-приложения ======================
private val urlRe = Regex("https?://[^\\s)]+")
fun urlFrom(text: String?): String? = text?.let { urlRe.find(it)?.value?.trimEnd('.', ',') }

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun LiveWeb(url: String, modifier: Modifier = Modifier, desktop: Boolean = false, reloadKey: Int = 0, onProgress: ((Int) -> Unit)? = null) {
    var view by remember { mutableStateOf<WebView?>(null) }
    AndroidView(factory = { c ->
        WebView(c).apply {
            setBackgroundColor(android.graphics.Color.WHITE)   // как в браузере: сайты без своего фона не должны становиться чёрными
            settings.javaScriptEnabled = true; settings.domStorageEnabled = true
            settings.allowFileAccess = false; settings.allowContentAccess = false
            settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
            settings.useWideViewPort = true; settings.loadWithOverviewMode = true
            settings.setSupportZoom(true); settings.builtInZoomControls = true; settings.displayZoomControls = false
            webViewClient = object : WebViewClient() {
                override fun onReceivedError(v: WebView, r: android.webkit.WebResourceRequest, e: android.webkit.WebResourceError) {
                    if (!r.isForMainFrame) return
                    val msg = "${e.description} (${e.errorCode})".replace("<", "&lt;")
                    val u = r.url.toString().replace("<", "&lt;")
                    v.loadDataWithBaseURL(null, "<body style='font-family:sans-serif;background:#18171b;color:#e8e6ec;padding:28px'><h2>Не удалось открыть сайт</h2><p style='color:#a9a6b3'>$msg</p><p style='word-break:break-all;color:#b9b0e0'>$u</p><p style='color:#a9a6b3'>Проверьте, что сайт опубликован и сервер доступен, затем нажмите «обновить».</p></body>", "text/html", "utf-8", null)
                }
                override fun onReceivedHttpError(v: WebView, r: android.webkit.WebResourceRequest, e: android.webkit.WebResourceResponse) {
                    if (r.isForMainFrame && e.statusCode >= 400) v.loadDataWithBaseURL(null, "<body style='font-family:sans-serif;background:#18171b;color:#e8e6ec;padding:28px'><h2>Ошибка ${e.statusCode}</h2><p style='color:#a9a6b3'>Сервер ответил ошибкой на ${r.url.toString().replace("<", "&lt;")}</p></body>", "text/html", "utf-8", null)
                }
                override fun shouldOverrideUrlLoading(v: WebView, r: android.webkit.WebResourceRequest): Boolean {
                    val same = r.url.host == android.net.Uri.parse(url).host
                    if (!same) { runCatching { c.startActivity(Intent(Intent.ACTION_VIEW, r.url).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }; return true }
                    return false
                }
            }
            webChromeClient = object : android.webkit.WebChromeClient() { override fun onProgressChanged(v: WebView, p: Int) { onProgress?.invoke(p) } }
            view = this
        }
    }, update = { w ->
        val ua = if (desktop) "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36" else null
        if (w.tag != "$url|$desktop|$reloadKey") {
            w.tag = "$url|$desktop|$reloadKey"
            w.settings.userAgentString = ua ?: android.webkit.WebSettings.getDefaultUserAgent(w.context)
            w.loadUrl(url)
        }
    }, modifier = modifier, onRelease = { it.destroy() })
}

/** Живое мини-приложение прямо в чате (html_app). */
@Composable
fun HtmlAppCard(vm: AppVM, title: String, url: String) {
    val ctx = LocalContext.current
    var progress by remember { mutableStateOf(0) }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(26.dp)).background(C.surface2)) {
        Row(Modifier.padding(start = 16.dp, end = 6.dp, top = 8.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(34.dp).clip(CircleShape).background(C.container), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.Widgets, null, tint = C.onContainer, modifier = Modifier.size(18.dp)) }
            Spacer(Modifier.width(10.dp)); Text(title.ifBlank { "Приложение" }, color = C.text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            RoundButton(Icons.Outlined.OpenInFull, "На весь экран", { vm.preview = url to title }, container = Color.Transparent, content = C.dim, size = 42.dp, iconSize = 20.dp)
            RoundButton(Icons.Outlined.Share, "Поделиться", { ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, url), title).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }, container = Color.Transparent, content = C.dim, size = 42.dp, iconSize = 20.dp)
        }
        Box(Modifier.padding(start = 8.dp, end = 8.dp, bottom = 8.dp).fillMaxWidth().height(400.dp).clip(RoundedCornerShape(20.dp)).background(C.code)) {
            LiveWeb(url, Modifier.fillMaxSize(), onProgress = { progress = it })
            if (progress in 1..99) LinearProgressIndicator({ progress / 100f }, Modifier.fillMaxWidth().align(Alignment.TopCenter), color = C.accent, trackColor = Color.Transparent)
        }
    }
}

/** Карточка опубликованного сайта. */
@Composable
fun SiteCard(vm: AppVM, url: String) {
    val ctx = LocalContext.current
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(26.dp)).background(C.container.copy(alpha = 0.55f)).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(44.dp).clip(CircleShape).background(C.accent), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.Public, null, tint = C.onAccent) }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) { Text("Сайт опубликован", color = C.onContainer, fontSize = 16.sp, fontWeight = FontWeight.SemiBold); Text(url.removePrefix("https://"), color = C.onContainer.copy(alpha = 0.8f), fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            PillButton("Превью", { vm.preview = url to url.removePrefix("https://").substringBefore('/') }, icon = Icons.Outlined.Visibility, height = 48.dp)
            SoftChip(Icons.Outlined.OpenInBrowser, "Открыть", false) { runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } }
            RoundButton(Icons.Outlined.ContentCopy, "Копировать", { copyToClipboard(ctx, url); vm.toast = "Ссылка скопирована" }, size = 48.dp, container = C.surface2, iconSize = 20.dp)
        }
    }
}

/** Полноэкранное превью сайта: перезагрузка, режим «телефон / компьютер», открыть, поделиться. */
@Composable
fun SitePreview(vm: AppVM, url: String, title: String, onClose: () -> Unit) {
    val ctx = LocalContext.current
    var desktop by remember { mutableStateOf(false) }
    var reload by remember { mutableStateOf(0) }
    var progress by remember { mutableStateOf(0) }
    androidx.compose.ui.window.Dialog(onClose, androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Column(Modifier.fillMaxSize().systemBarsPadding()) {
            Row(Modifier.fillMaxWidth().padding(10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                RoundButton(Icons.Outlined.Close, "Закрыть", onClose, size = 46.dp)
                Column(Modifier.weight(1f).padding(horizontal = 4.dp)) { Text(title.ifBlank { "Превью" }, color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis); Text(url.removePrefix("https://"), color = C.dim, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis) }
                RoundButton(if (desktop) Icons.Outlined.DesktopWindows else Icons.Outlined.PhoneAndroid, "Режим", { desktop = !desktop }, size = 46.dp, container = C.container, content = C.onContainer)
                RoundButton(Icons.Outlined.Refresh, "Обновить", { reload++ }, size = 46.dp)
                RoundButton(Icons.Outlined.OpenInBrowser, "Открыть", { runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } }, size = 46.dp)
            }
            Box(Modifier.weight(1f).fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp).clip(RoundedCornerShape(24.dp)).background(C.code)) {
                LiveWeb(url, Modifier.fillMaxSize(), desktop, reload, onProgress = { progress = it })
                if (progress in 1..99) LinearProgressIndicator({ progress / 100f }, Modifier.fillMaxWidth().align(Alignment.TopCenter), color = C.accent, trackColor = Color.Transparent)
            }
        }
    }
}

@Composable
fun SitesScreen(vm: AppVM) {
    val ctx = LocalContext.current
    LaunchedEffect(Unit) { vm.loadSites() }
    PageScaffold("Сайты", { vm.screen = Screen.Chat }) {
        LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item { Text("Сайты и мини-приложения, которые агент опубликовал на вашем домене. Попросите: «сделай лендинг и задеплой».", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) }
            if (vm.sites.isEmpty()) item { EmptyHint(Icons.Outlined.Public, "Пока нет сайтов") }
            items(vm.sites, key = { it.slug }) { s ->
                Column(Modifier.fillMaxWidth().animateItem().clip(RoundedCornerShape(26.dp)).background(C.surface2).padding(16.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(44.dp).clip(CircleShape).background(C.container), contentAlignment = Alignment.Center) { Icon(if (s.kind == "app") Icons.Outlined.Widgets else Icons.Outlined.Public, null, tint = C.onContainer) }
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f)) {
                            Text(s.title.ifBlank { s.slug }, color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text("/s/${s.slug}/ · ${humanSize(s.size)}", color = C.dim, fontSize = 12.sp, maxLines = 1)
                        }
                    }
                    Row(Modifier.padding(top = 12.dp).horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        SoftChip(Icons.Outlined.Visibility, "Превью", true) { vm.preview = s.url to s.title.ifBlank { s.slug } }
                        SoftChip(Icons.Outlined.ContentCopy, "Ссылка", false) { copyToClipboard(ctx, s.url); vm.toast = "Ссылка скопирована" }
                        SoftChip(Icons.Outlined.Share, "Поделиться", false) { ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, s.url), s.title).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
                        SoftChip(Icons.Outlined.DeleteOutline, "Удалить", false) { vm.deleteSite(s) }
                    }
                }
            }
        }
    }
}

// ====================== Блокировка приложения ======================
val LocalVM = androidx.compose.runtime.compositionLocalOf<AppVM?> { null }

@Composable
fun LockScreen(vm: AppVM) {
    if (vm.hasVoice || vm.hasFace) { BioGate(vm, true); return }   // записан голос или лицо — разблокировка по ним (пароль телефона — запасной вход)
    val ctx = LocalContext.current
    val km = remember { ctx.getSystemService(android.content.Context.KEYGUARD_SERVICE) as android.app.KeyguardManager }
    val launcher = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.StartActivityForResult()) { r -> if (r.resultCode == android.app.Activity.RESULT_OK) vm.locked = false }
    fun ask() {
        if (!km.isDeviceSecure) { vm.locked = false; return }
        @Suppress("DEPRECATION") val i = km.createConfirmDeviceCredentialIntent("OpenAgent", "Подтвердите, что это вы")
        if (i != null) runCatching { launcher.launch(i) } else vm.locked = false
    }
    LaunchedEffect(Unit) { ask() }
    Column(Modifier.fillMaxSize().background(C.bg).pointerInput(Unit) { detectTapGestures { } }, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        AppLogo(96.dp)
        Spacer(Modifier.height(20.dp)); Text("OpenAgent заблокирован", color = C.text, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Text("Доступ к серверу защищён", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp, bottom = 28.dp))
        PillButton("Разблокировать", { ask() }, icon = Icons.Outlined.LockOpen)
    }
}

// ====================== Закладки ======================
@Composable
fun BookmarksScreen(vm: AppVM) {
    val ctx = LocalContext.current
    PageScaffold("Закладки", { vm.screen = Screen.Chat }) {
        LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 24.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (vm.bookmarks.isEmpty()) item { EmptyHint(Icons.Outlined.BookmarkBorder, "Нажмите ☆ под ответом агента,\nчтобы сохранить его сюда") }
            items(vm.bookmarks.toList(), key = { "${it.convId}_${it.msgId}" }) { b ->
                Column(Modifier.fillMaxWidth().animateItem().clip(RoundedCornerShape(26.dp)).background(C.surface2).clickable { Haptics.tick(); vm.openChat(b.convId) }.padding(16.dp)) {
                    Text(b.title, color = C.accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
                    Text(b.text, color = C.text, fontSize = 15.sp, lineHeight = 22.sp, maxLines = 8, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 6.dp))
                    Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        SoftChip(Icons.Outlined.ContentCopy, "Копировать", false) { copyToClipboard(ctx, b.text); vm.toast = "Скопировано" }
                        SoftChip(Icons.Outlined.DeleteOutline, "Убрать", false) { vm.removeBookmark(b) }
                    }
                }
            }
        }
    }
}

// ====================== Проекты ======================
@Composable
fun ProjectsScreen(vm: AppVM) {
    var add by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var repo by remember { mutableStateOf("") }
    PageScaffold("Проекты", { vm.screen = Screen.Chat }) {
        Box(Modifier.weight(1f)) {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 100.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item { Text("Проект — общая папка на сервере для нескольких чатов: файлы и код сохраняются между разговорами.", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(bottom = 6.dp)) }
                if (vm.projects.isEmpty()) item { EmptyHint(Icons.Outlined.Folder, "Проектов пока нет") }
                items(vm.projects.toList(), key = { it.id }) { p ->
                    val active = vm.currentProject == p.id
                    Column(Modifier.fillMaxWidth().animateItem().clip(RoundedCornerShape(28.dp)).background(if (active) C.container else C.surface2).padding(18.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Outlined.Folder, null, tint = if (active) C.onContainer else C.accent); Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text(p.name, color = if (active) C.onContainer else C.text, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
                                Text("${p.chats} чатов" + (p.repo?.let { " · $it" } ?: ""), color = C.dim, fontSize = 13.sp, maxLines = 1)
                            }
                        }
                        Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            SoftChip(Icons.Outlined.Check, if (active) "Выбран" else if (vm.convId == null) "В новый чат" else "В этот чат", active) { vm.useProject(if (active) null else p); vm.screen = Screen.Chat }
                            SoftChip(Icons.Outlined.DeleteOutline, "Удалить", false) { vm.deleteProject(p) }
                        }
                    }
                }
            }
            PillButton("Новый", { name = ""; repo = ""; add = true }, Modifier.align(Alignment.BottomEnd).padding(20.dp).navigationBarsPadding(), icon = Icons.Outlined.Add, height = 60.dp)
        }
    }
    if (add) AppDialog("Новый проект", { add = false }, "Создать", name.isNotBlank(), { vm.createProject(name.trim(), repo.trim()); add = false }) {
        Field(name, { name = it }, "Название")
        Field(repo, { repo = it }, "Репозиторий GitHub (необязательно): user/repo")
    }
}

// ====================== Библиотека промптов ======================
@Composable
fun PromptsScreen(vm: AppVM) {
    var add by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var text by remember { mutableStateOf("") }
    PageScaffold("Промпты", { vm.screen = Screen.Chat }) {
        Box(Modifier.weight(1f)) {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 100.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item { Text("Сохраняйте частые запросы и вызывайте их в чате командой /название.", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(bottom = 6.dp)) }
                if (vm.prompts.isEmpty()) item { EmptyHint(Icons.Outlined.Bolt, "Промптов пока нет") }
                items(vm.prompts.toList(), key = { it.id }) { p ->
                    Column(Modifier.fillMaxWidth().animateItem().clip(RoundedCornerShape(26.dp)).background(C.surface2).padding(16.dp)) {
                        Text("/" + p.name, color = C.accent, style = Mono, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                        Text(p.text, color = C.text, fontSize = 14.sp, maxLines = 5, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 6.dp))
                        Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            SoftChip(Icons.Outlined.PlayArrow, "Отправить", false) { vm.screen = Screen.Chat; vm.send(p.text) }
                            SoftChip(Icons.Outlined.DeleteOutline, "Удалить", false) { vm.deletePrompt(p) }
                        }
                    }
                }
            }
            PillButton("Новый", { name = ""; text = ""; add = true }, Modifier.align(Alignment.BottomEnd).padding(20.dp).navigationBarsPadding(), icon = Icons.Outlined.Add, height = 60.dp)
        }
    }
    if (add) AppDialog("Новый промпт", { add = false }, "Сохранить", name.isNotBlank() && text.isNotBlank(), { vm.savePrompt(name.trim().lowercase().replace(' ', '-'), text.trim()); add = false }) {
        Field(name, { name = it }, "Команда (например: отчёт)")
        Field(text, { text = it }, "Текст запроса", singleLine = false, minLines = 4)
    }
}
