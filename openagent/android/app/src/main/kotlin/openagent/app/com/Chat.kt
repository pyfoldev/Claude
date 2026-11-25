package openagent.app.com

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material.icons.automirrored.filled.InsertDriveFile
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.graphicsLayer
import android.content.Intent
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import coil.compose.AsyncImage
import coil.request.ImageRequest
import kotlinx.coroutines.launch
import kotlinx.serialization.json.*

@Composable
fun ChatRoot(vm: AppVM) {
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    ModalNavigationDrawer(
        drawerState = drawer,
        drawerContent = {
            ModalDrawerSheet(drawerContainerColor = C.bg, drawerContentColor = C.text, drawerShape = RoundedCornerShape(topEnd = 32.dp, bottomEnd = 32.dp), modifier = Modifier.fillMaxWidth(0.88f).widthIn(max = 420.dp)) {
                DrawerContent(vm) { scope.launch { drawer.close() } }
            }
        },
        scrimColor = Color.Black.copy(alpha = 0.65f),
    ) { ChatScreen(vm, openDrawer = { Haptics.click(); scope.launch { drawer.open() } }) }
}

private fun dayBucket(ts: Long): Int {
    val c = java.util.Calendar.getInstance().apply { set(java.util.Calendar.HOUR_OF_DAY, 0); set(java.util.Calendar.MINUTE, 0); set(java.util.Calendar.SECOND, 0); set(java.util.Calendar.MILLISECOND, 0) }
    val today = c.timeInMillis; val day = 86_400_000L
    return when { ts >= today -> 0; ts >= today - day -> 1; ts >= today - 6 * day -> 2; ts >= today - 29 * day -> 3; else -> 4 }
}
private val BUCKETS = listOf("Сегодня", "Вчера", "На этой неделе", "В этом месяце", "Ранее")

@Composable
fun DrawerContent(vm: AppVM, close: () -> Unit) {
    var query by remember { mutableStateOf("") }
    var renaming by remember { mutableStateOf<Conv?>(null) }
    var tools by remember { mutableStateOf(false) }
    val code = vm.mode == "code"
    LaunchedEffect(Unit) { if (vm.projects.isEmpty()) vm.loadProjects() }
    @Composable
    fun ModePill(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
        val bg by animateColorAsState(if (selected) C.container else C.surface2, label = "mp")
        Row(modifier.height(46.dp).clip(RoundedCornerShape(23.dp)).background(bg).clickable { Haptics.tick(); onClick() }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
            Icon(icon, null, tint = if (selected) C.onContainer else C.dim, modifier = Modifier.size(20.dp)); Spacer(Modifier.width(8.dp))
            Text(label, color = if (selected) C.onContainer else C.text, fontSize = 15.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal)
        }
    }
    Column(Modifier.fillMaxHeight().systemBarsPadding().padding(horizontal = 14.dp)) {
        Row(Modifier.fillMaxWidth().padding(start = 6.dp, top = 12.dp, bottom = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            SaturnMark(30.dp); Spacer(Modifier.width(11.dp))
            Text("OpenAgent", color = C.text, fontSize = 25.sp, fontWeight = FontWeight.Medium, fontFamily = androidx.compose.ui.text.font.FontFamily.Serif, modifier = Modifier.weight(1f))
            RoundButton(Icons.Outlined.Apps, "Инструменты", { tools = true }, size = 42.dp, container = Color.Transparent, content = C.dim, iconSize = 22.dp)
            RoundButton(Icons.Outlined.Settings, "Настройки", { vm.screen = Screen.Settings; close() }, size = 42.dp, container = Color.Transparent, content = C.dim, iconSize = 22.dp)
        }
        // поиск: всегда на виду
        Row(Modifier.fillMaxWidth().height(48.dp).clip(RoundedCornerShape(24.dp)).background(C.surface2).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.Search, null, tint = C.dim, modifier = Modifier.size(20.dp)); Spacer(Modifier.width(10.dp))
            Box(Modifier.weight(1f)) {
                if (query.isEmpty()) Text("Поиск по чатам", color = C.dim, fontSize = 15.sp)
                androidx.compose.foundation.text.BasicTextField(query, { query = it; vm.searchChats(it) }, singleLine = true, textStyle = androidx.compose.ui.text.TextStyle(color = C.text, fontSize = 15.sp), cursorBrush = androidx.compose.ui.graphics.SolidColor(C.accent), modifier = Modifier.fillMaxWidth())
            }
            if (query.isNotEmpty()) Icon(Icons.Outlined.Close, null, tint = C.dim, modifier = Modifier.size(32.dp).clip(CircleShape).clickable { query = ""; vm.searchChats("") }.padding(6.dp))
        }
        Spacer(Modifier.height(10.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ModePill(Icons.Outlined.ChatBubbleOutline, "Чат", !code, Modifier.weight(1f)) { vm.newChat("chat"); close() }
            ModePill(Icons.Outlined.Code, "Code", code, Modifier.weight(1f)) { vm.newChat("code"); close() }
        }
        HorizontalDivider(color = C.outline, modifier = Modifier.padding(vertical = 6.dp, horizontal = 4.dp))
        val searching = query.trim().length >= 2
        @Composable fun Header(t: String, top: Int = 10) = Text(t.uppercase(), color = C.dim, fontSize = 11.sp, letterSpacing = 0.8.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 14.dp, top = top.dp, bottom = 4.dp))
        LazyColumn(Modifier.weight(1f)) {
            if (searching) {
                if (vm.chatSearching) item { Box(Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(Modifier.size(22.dp), color = C.accent, strokeWidth = 2.dp) } }
                if (!vm.chatSearching && vm.chatHits.isEmpty()) item { Text("Ничего не найдено", color = C.dim, modifier = Modifier.padding(16.dp)) }
                items(vm.chatHits, key = { "h" + it.id }) { h ->
                    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).clickable { Haptics.tick(); vm.openChat(h.id); query = ""; vm.searchChats(""); close() }.padding(horizontal = 14.dp, vertical = 9.dp)) {
                        Text(h.title, color = C.text, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(h.snippet, color = C.dim, fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    }
                }
            } else {
                val pinned = vm.convs.filter { it.pinned }
                val groups = vm.convs.filter { !it.pinned }.sortedByDescending { it.updatedAt }.groupBy { dayBucket(it.updatedAt) }.toSortedMap()
                if (pinned.isNotEmpty()) { item(key = "ph") { Header("Закреплённые", 4) }; items(pinned, key = { it.id }) { c -> ConvRow(vm, c, close, { renaming = c }) } }
                groups.forEach { (b, list) ->
                    item(key = "g$b") { Header(BUCKETS[b]) }
                    items(list, key = { it.id }) { c -> ConvRow(vm, c, close, { renaming = c }) }
                }
                if (vm.convs.isEmpty()) item { Text("Чатов пока нет", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(16.dp)) }
            }
        }
        HorizontalDivider(color = C.outline, modifier = Modifier.padding(vertical = 6.dp, horizontal = 4.dp))
        Row(Modifier.fillMaxWidth().padding(bottom = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            val nm = vm.user?.name?.takeIf { it.isNotBlank() }
            val letter = (nm ?: vm.user?.email ?: "?").trim().take(1).uppercase()
            Row(Modifier.weight(1f).clip(RoundedCornerShape(26.dp)).clickable { Haptics.tick(); vm.screen = Screen.Settings; close() }.padding(end = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(46.dp).clip(CircleShape).background(C.accent), contentAlignment = Alignment.Center) { Text(letter, color = C.onAccent, fontSize = 19.sp, fontWeight = FontWeight.Bold) }
                Spacer(Modifier.width(10.dp))
                Column { Text(nm ?: "Профиль", color = C.text, fontSize = 15.sp, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis); Text(vm.user?.email ?: "", color = C.dim, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis) }
            }
            Row(Modifier.height(48.dp).clip(RoundedCornerShape(24.dp)).background(Color(0xFFF2F2F5)).clickable { Haptics.click(); vm.newChat(vm.mode); close() }.padding(horizontal = 18.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.Add, null, tint = Color(0xFF111114), modifier = Modifier.size(22.dp)); Spacer(Modifier.width(6.dp))
                Text("Новый", color = Color(0xFF111114), fontSize = 16.sp, fontWeight = FontWeight.Medium)
            }
        }
    }
    renaming?.let { c ->
        var t by remember(c) { mutableStateOf(c.title) }
        AppDialog("Название чата", { renaming = null }, "Сохранить", t.isNotBlank(), { vm.rename(c.id, t.trim()); renaming = null }) { Field(t, { t = it }, "Название") }
    }
    if (tools) ToolsSheet(vm, { tools = false }, close)
    if (vm.showCp) CheckpointsDialog(vm)
    if (vm.showCompare) CompareDialog(vm)
    if (vm.showResearch) ResearchDialog(vm)
}

@Composable
fun ConvRow(vm: AppVM, c: Conv, close: () -> Unit, onRename: () -> Unit) {
    var menu by remember { mutableStateOf(false) }
    val sel = c.id == vm.convId
    val bg by animateColorAsState(if (sel) C.surface3 else Color.Transparent, label = "sel")
    val proj = c.projectId?.let { id -> vm.projects.firstOrNull { it.id == id }?.name }
    Row(Modifier.fillMaxWidth().padding(vertical = 1.dp).heightIn(min = 46.dp).clip(RoundedCornerShape(23.dp)).background(bg)
        .clickable { Haptics.tick(); vm.openChat(c.id); close() }.padding(start = 14.dp, end = 2.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(if (c.mode == "code") Icons.Outlined.Code else Icons.Outlined.ChatBubbleOutline, null, tint = if (sel) C.text else C.dim, modifier = Modifier.size(18.dp)); Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f).padding(vertical = 6.dp)) {
            Text(remember(c.title) { c.title.monoEmoji() }, color = C.text, maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = 15.5.sp, fontWeight = if (sel) FontWeight.Medium else FontWeight.Normal)
            if (proj != null) Text(proj, color = C.dim, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        if (c.running) Box(Modifier.padding(horizontal = 6.dp).size(8.dp).clip(CircleShape).background(C.text))
        Box {
            Icon(Icons.Outlined.MoreVert, null, tint = C.dim, modifier = Modifier.size(36.dp).clip(CircleShape).clickable { menu = true }.padding(8.dp))
            DropdownMenu(menu, { menu = false }, containerColor = C.surface3, shape = RoundedCornerShape(20.dp)) {
                DropdownMenuItem(text = { Text(if (c.pinned) "Открепить" else "Закрепить") }, leadingIcon = { Icon(Icons.Outlined.PushPin, null) }, onClick = { menu = false; vm.pin(c) })
                DropdownMenuItem(text = { Text("Переименовать") }, leadingIcon = { Icon(Icons.Outlined.Edit, null) }, onClick = { menu = false; onRename() })
                DropdownMenuItem(text = { Text("Поделиться ссылкой") }, leadingIcon = { Icon(Icons.Outlined.Link, null) }, onClick = { menu = false; vm.shareChat(c.id) })
                DropdownMenuItem(text = { Text("Экспорт в Markdown") }, leadingIcon = { Icon(Icons.Outlined.IosShare, null) }, onClick = { menu = false; vm.exportChat(c.id) })
                DropdownMenuItem(text = { Text("Удалить", color = C.danger) }, leadingIcon = { Icon(Icons.Outlined.DeleteOutline, null, tint = C.danger) }, onClick = { menu = false; vm.deleteChat(c.id) })
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ToolsSheet(vm: AppVM, onDismiss: () -> Unit, close: () -> Unit) {
    val ctx = LocalContext.current
    val owner = vm.user?.role == "owner"
    val tiles = buildList {
        if (owner) add(Triple(Icons.Outlined.Terminal, "Терминал") { vm.screen = Screen.Terminal })
        add(Triple(Icons.Outlined.Folder, "Файлы") { vm.screen = Screen.Files })
        add(Triple(Icons.Outlined.Public, "Сайты") { vm.screen = Screen.Sites })
        add(Triple(Icons.Outlined.Schedule, "Автоматизации") { vm.screen = Screen.Automations })
        add(Triple(Icons.Outlined.AutoFixHigh, "Навыки") { vm.screen = Screen.Skills })
        add(Triple(Icons.Outlined.Psychology, "Память") { vm.screen = Screen.Memory; vm.loadMemories() })
        if (owner) add(Triple(Icons.Outlined.Dns, "Сервер") { vm.screen = Screen.Server })
        if (owner) add(Triple(Icons.Outlined.AccountTree, "Git") { vm.screen = Screen.Git })
        if (vm.convId != null) add(Triple(Icons.Outlined.History, "Откаты") { vm.showCp = true; vm.loadCheckpoints() })
        add(Triple(Icons.Outlined.Folder, "Проекты") { vm.screen = Screen.Projects; vm.loadProjects() })
        add(Triple(Icons.Outlined.Bolt, "Промпты") { vm.screen = Screen.Prompts; vm.loadPrompts() })
        if (vm.convId != null) add(Triple(Icons.Outlined.IosShare, "Экспорт чата") { shareText(ctx, vm.exportChatText()) })
        add(Triple(Icons.Outlined.BookmarkBorder, "Закладки") { vm.screen = Screen.Bookmarks })
        add(Triple(Icons.Outlined.Extension, "Подключения") { vm.screen = Screen.Connections })
        add(Triple(Icons.Outlined.StickyNote2, "Заметки") { vm.screen = Screen.Notes })
        add(Triple(Icons.Outlined.TaskAlt, "Задачи") { vm.screen = Screen.Tasks })
        add(Triple(Icons.Outlined.Flag, "Миссии") { vm.screen = Screen.Missions })
        add(Triple(Icons.Outlined.Groups, "Агенты") { vm.screen = Screen.Agents })
        add(Triple(Icons.Outlined.Hub, "Коннекторы") { vm.screen = Screen.Integrations })
        add(Triple(Icons.Outlined.History, "Журнал агента") { vm.screen = Screen.Activity })
        add(Triple(Icons.Outlined.Key, "Секреты") { vm.screen = Screen.Secrets })
        add(Triple(Icons.Outlined.Compare, "Сравнить модели") { vm.compareOut.clear(); vm.showCompare = true })
        add(Triple(Icons.Outlined.Biotech, "Исследование") { vm.showResearch = true })
    }
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = C.surface, shape = RoundedCornerShape(topStart = 36.dp, topEnd = 36.dp), dragHandle = { BottomSheetDefaults.DragHandle(color = C.outline) }) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp).navigationBarsPadding()) {
            Text("Инструменты", color = C.text, fontSize = 22.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 14.dp))
            tiles.chunked(3).forEach { row ->
                Row(Modifier.fillMaxWidth().padding(vertical = 5.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    row.forEach { (ic, label, go) ->
                        Column(Modifier.weight(1f).height(92.dp).bounceClick { go(); onDismiss(); close() }.clip(RoundedCornerShape(26.dp)).background(C.surface2), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                            Icon(ic, null, tint = C.accent, modifier = Modifier.size(28.dp)); Spacer(Modifier.height(8.dp)); Text(label, color = C.text, fontSize = 13.sp, maxLines = 1)
                        }
                    }
                    repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                }
            }
        }
    }
}

@Composable
fun DrawerItem(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().height(56.dp).clip(RoundedCornerShape(28.dp)).clickable { Haptics.tick(); onClick() }.padding(horizontal = 18.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, null, tint = C.text); Spacer(Modifier.width(16.dp)); Text(label, color = C.text, fontSize = 16.sp)
    }
}

sealed interface UiItem { val key: String }
data class UserItem(val m: Msg) : UiItem { override val key get() = "u${if (m.cid != 0L) m.cid else m.id}" }
data class TextItem(val m: Msg) : UiItem { override val key get() = "t${m.id}" }
data class WorkItem(val id: Long, val calls: List<Pair<ToolCall, Msg?>>) : UiItem { override val key get() = "w$id" }
data class SpecialItem(val m: Msg, val call: ToolCall, val result: Msg?) : UiItem { override val key get() = "s${call.id}" }
data class AttachItem(val m: Msg, val a: Attach) : UiItem { override val key get() = "f${m.id}_${a.id}" }

/** Превращает сырые сообщения в элементы списка: подряд идущие вызовы инструментов сворачиваются в одну группу «ход работы». */
fun buildItems(messages: List<Msg>): List<UiItem> {
    val results = HashMap<String?, Msg>()
    var lastTodo: String? = null
    for (m in messages) {
        if (m.role == "tool") results[m.toolCallId] = m
        m.toolCalls?.forEach { if (it.name == "todo_write") lastTodo = it.id }
    }
    val out = ArrayList<UiItem>()
    var group: MutableList<Pair<ToolCall, Msg?>>? = null
    var gid = 0L
    fun flush() { group?.takeIf { it.isNotEmpty() }?.let { out.add(WorkItem(gid, it.toList())) }; group = null }
    for (m in messages) when (m.role) {
        "user" -> { flush(); out.add(UserItem(m)) }
        "assistant" -> {
            if (m.content.isNotBlank()) { flush(); out.add(TextItem(m)) }
            m.toolCalls?.forEach { c ->
                val res = results[c.id]
                when {
                    c.name == "todo_write" -> if (c.id == lastTodo) { flush(); out.add(SpecialItem(m, c, res)) }
                    c.name == "ask_user" -> { flush(); out.add(SpecialItem(m, c, res)) }
                    c.name == "html_app" && urlFrom(res?.content) != null -> { flush(); out.add(SpecialItem(m, c, res)) }
                    else -> {
                        if (group == null) { group = mutableListOf(); gid = m.id }
                        group!!.add(c to res)
                        if (c.name == "deploy_site" && res?.content?.startsWith("Опубликовано") == true) { flush(); out.add(SpecialItem(m, c, res)) }
                    }
                }
            }
            m.attachments?.forEach { flush(); out.add(AttachItem(m, it)) }
        }
    }
    flush()
    return out
}

@Composable
fun ChatScreen(vm: AppVM, openDrawer: () -> Unit) {
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val items by remember { derivedStateOf { buildItems(vm.messages) } }
    val code = vm.mode == "code"
    val lastUserId = vm.messages.lastOrNull { it.role == "user" }?.id ?: Long.MIN_VALUE
    val lastItem = items.lastOrNull()

    // «прилипание» к низу: следуем за новыми сообщениями, только пока пользователь не уехал вверх сам
    var pinned by remember { mutableStateOf(true) }
    LaunchedEffect(listState) { snapshotFlow { listState.isScrollInProgress }.collect { moving -> if (!moving) pinned = !listState.canScrollBackward } }
    LaunchedEffect(items.size) { if (pinned && items.isNotEmpty()) listState.animateScrollToItem(0) }
    LaunchedEffect(lastUserId) { if (items.isNotEmpty()) { pinned = true; listState.animateScrollToItem(0) } }
    val showFab by remember { derivedStateOf { listState.canScrollBackward && (listState.firstVisibleItemIndex > 0 || listState.firstVisibleItemScrollOffset > 400) } }

    Column(Modifier.fillMaxSize().systemBarsPadding().imePadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            RoundButton(Icons.Outlined.Menu, "Меню", openDrawer)
            ModeSwitch(vm.mode, { vm.newChat(it) }, Modifier.weight(1f).padding(horizontal = 12.dp))
            RoundButton(Icons.Outlined.GraphicEq, "Голосовой режим", { vm.startVoice() }, container = C.container, content = C.onContainer)
        }
        val title = vm.convs.firstOrNull { it.id == vm.convId }?.title
        AnimatedVisibility(title != null, enter = fadeIn() + expandVertically(), exit = fadeOut() + shrinkVertically()) {
            Row(Modifier.fillMaxWidth().padding(start = 24.dp, end = 24.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                if (code) Text("›_ ", color = C.accent, style = Mono, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                AnimatedContent(title.orEmpty(), transitionSpec = { (fadeIn(tween(300)) + slideInVertically { it / 2 }) togetherWith (fadeOut(tween(120)) + slideOutVertically { -it / 2 }) }, label = "title") {
                    Text(it, color = C.dim, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
        }
        Box(Modifier.weight(1f)) {
            androidx.compose.animation.AnimatedVisibility(items.isEmpty() && !vm.running && !vm.loadingChat, enter = fadeIn(tween(250)), exit = fadeOut(tween(120))) { EmptyState(vm) }
            if (vm.loadingChat && items.isEmpty()) ChatSkeleton()
            LazyColumn(state = listState, reverseLayout = true, modifier = Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 12.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                if (vm.running) item(key = "live") { LiveBlock(vm) }
                items(items.asReversed(), key = { it.key }) { it -> Box(Modifier.animateItem(fadeInSpec = tween(260), fadeOutSpec = tween(160), placementSpec = spring(dampingRatio = 0.85f, stiffness = 380f))) { ItemView(vm, it, live = vm.running && it === lastItem) } }
                if (vm.hasMoreOld && items.isNotEmpty() && vm.convId != null) item(key = "older") { LaunchedEffect(vm.messages.size) { vm.loadOlder() }; Box(Modifier.fillMaxWidth().padding(12.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(Modifier.size(22.dp), color = C.accent, strokeWidth = 2.dp) } }
            }
            androidx.compose.animation.AnimatedVisibility(showFab, modifier = Modifier.align(Alignment.BottomEnd).padding(end = 16.dp, bottom = 12.dp), enter = scaleIn(spring(0.6f, 500f)) + fadeIn(), exit = scaleOut() + fadeOut()) {
                RoundButton(Icons.Outlined.KeyboardArrowDown, "Вниз", { pinned = true; scope.launch { listState.animateScrollToItem(0) } }, size = 46.dp, container = C.surface3, content = C.text)
            }
        }
        InputBar(vm)
    }
    vm.toast?.let { t -> LaunchedEffect(t) { kotlinx.coroutines.delay(3500); if (vm.toast == t) vm.toast = null } }
}

@Composable
private fun ItemView(vm: AppVM, item: UiItem, live: Boolean) {
    when (item) {
        is UserItem -> Appear(remember(item.key) { vm.consumeFresh(item.m.id) }, fromRight = true) { UserBubble(vm, item.m) }
        is TextItem -> Appear(remember(item.key) { vm.consumeFresh(item.m.id) }) { AssistantText(vm, item.m) }
        is WorkItem -> Appear(remember(item.key) { vm.consumeFresh(item.id) }) { WorkGroupCard(vm, item, live) }
        is SpecialItem -> Appear(remember(item.key) { vm.consumeFresh(item.m.id) }) {
            val c = item.call
            when (c.name) {
                "todo_write" -> TodoCard(c.args)
                "ask_user" -> AskCard(c.args, enabled = vm.messages.none { it.id > item.m.id && it.role == "user" } && !vm.running) { vm.send(it) }
                "html_app" -> HtmlAppCard(vm, runCatching { JSON.parseToJsonElement(c.args).jsonObject["title"]?.jsonPrimitive?.content }.getOrNull().orEmpty(), urlFrom(item.result?.content)!!)
                "deploy_site" -> urlFrom(item.result?.content)?.let { SiteCard(vm, it) }
            }
        }
        is AttachItem -> AttachmentView(vm, item.a, mine = false)
    }
}

/** Появление нового элемента: один раз, лёгко (на GPU-слое, без перекомпоновки). История и повторный показ при прокрутке — без анимации. */
@Composable
fun Appear(animate: Boolean, fromRight: Boolean = false, content: @Composable () -> Unit) {
    if (!animate) { content(); return }
    val a = remember { androidx.compose.animation.core.Animatable(0f) }
    LaunchedEffect(Unit) { a.animateTo(1f, spring(dampingRatio = 0.82f, stiffness = 420f)) }
    Box(Modifier.graphicsLayer {
        val p = a.value
        alpha = p.coerceIn(0f, 1f)
        translationY = (1f - p) * 28.dp.toPx()
        translationX = if (fromRight) (1f - p) * 36.dp.toPx() else 0f
        scaleX = 0.96f + 0.04f * p; scaleY = scaleX
    }) { content() }
}

@Composable
private fun LiveBlock(vm: AppVM) {
    Column(Modifier.fillMaxWidth()) {
        if (vm.shown.isNotEmpty() || vm.partial.isNotEmpty()) { Markdown(vm.shown.ifEmpty { vm.partial.take(2) }); StreamCursor() }
        else {
            Thinking()
            AnimatedVisibility(vm.statusText.isNotBlank()) { Text(vm.statusText, color = C.dim, fontSize = 13.sp, modifier = Modifier.padding(top = 2.dp)) }
        }
    }
}

@Composable
private fun StreamCursor() {
    val a by rememberInfiniteTransition(label = "cur").animateFloat(0.25f, 1f, infiniteRepeatable(tween(500), RepeatMode.Reverse), label = "ca")
    Box(Modifier.padding(top = 6.dp).size(9.dp).graphicsLayer { alpha = a }.background(C.accent, CircleShape))
}

@Composable
private fun ChatSkeleton() {
    val a by rememberInfiniteTransition(label = "sk").animateFloat(0.35f, 0.8f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "ska")
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(18.dp, Alignment.Bottom)) {
        listOf(0.55f to true, 0.85f to false, 0.7f to false, 0.45f to true).forEach { (w, right) ->
            Box(Modifier.fillMaxWidth(), contentAlignment = if (right) Alignment.CenterEnd else Alignment.CenterStart) {
                Box(Modifier.fillMaxWidth(w).height(if (right) 44.dp else 72.dp).graphicsLayer { alpha = a }.clip(RoundedCornerShape(24.dp)).background(C.surface2))
            }
        }
    }
}

// ---------------- группа шагов агента ----------------
private fun plural(n: Int, one: String, few: String, many: String) = when { n % 100 in 11..14 -> many; n % 10 == 1 -> one; n % 10 in 2..4 -> few; else -> many }
private fun toolIcon(name: String) = when (name) {
    "bash" -> Icons.Outlined.Terminal; "web_fetch" -> Icons.Outlined.Language; "web_search" -> Icons.Outlined.Search; "send_file" -> Icons.Outlined.Upload
    "memory_save", "memory_search", "memory_forget" -> Icons.Outlined.Psychology; "delegate" -> Icons.Outlined.AccountTree; "grep", "glob" -> Icons.Outlined.ManageSearch; "http_request" -> Icons.Outlined.Http
    "chart" -> Icons.Outlined.BarChart; "plot_function" -> Icons.Outlined.ShowChart; "geometry" -> Icons.Outlined.Straighten; "diagram" -> Icons.Outlined.AccountTree; "draw_svg" -> Icons.Outlined.Brush
    "calculate" -> Icons.Outlined.Calculate; "python" -> Icons.Outlined.Code; "skill_search", "skill_install" -> Icons.Outlined.Extension; "deploy_site", "list_sites", "delete_site" -> Icons.Outlined.Public
    "html_app" -> Icons.Outlined.Widgets; "github_api" -> Icons.Outlined.Hub; "process" -> Icons.Outlined.Memory; "skill_load", "skill_save" -> Icons.Outlined.AutoFixHigh
    "schedule_create", "schedule_list", "schedule_delete" -> Icons.Outlined.Schedule; else -> Icons.Outlined.Description
}
private fun isFailed(res: Msg?) = res?.content?.startsWith("Ошибка") == true || Regex("\\[exit [1-9]").containsMatchIn(res?.content ?: "")
private val urlInText = Regex("https?://[^\\s)\\]]+")

@Composable
fun WorkGroupCard(vm: AppVM, item: WorkItem, live: Boolean) {
    var open by remember(item.key) { mutableStateOf(false) }
    val running = live && item.calls.any { it.second == null }
    val current = item.calls.lastOrNull { it.second == null } ?: item.calls.last()
    val failed = item.calls.count { isFailed(it.second) }
    val done = item.calls.size
    val sources = remember(item.calls.map { it.second?.id }) {
        item.calls.filter { it.first.name == "web_search" || it.first.name == "web_fetch" }.flatMap { urlInText.findAll(it.second?.content.orEmpty()).map { m -> m.value.trimEnd('.', ',') }.toList() }.distinct().take(6)
    }
    val ctx = LocalContext.current
    val rot by animateFloatAsState(if (open) 180f else 0f, spring(0.7f, 500f), label = "wr")
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(C.surface2).animateContentSize(spring(0.85f, 450f))) {
        Row(Modifier.clickable { Haptics.tick(); open = !open }.padding(horizontal = 14.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            // стопка иконок инструментов
            val names = item.calls.map { it.first.name }.distinct().take(3)
            Box(Modifier.width((34 + 20 * (names.size - 1)).dp).height(34.dp)) {
                names.indices.reversed().forEach { i ->
                    val n = names[i]
                    Box(Modifier.padding(start = (20 * i).dp).size(34.dp).clip(CircleShape).background(if (i == 0) C.container else C.surface3).border(2.dp, C.surface2, CircleShape), contentAlignment = Alignment.Center) {
                        Icon(toolIcon(n), null, tint = if (i == 0) C.onContainer else C.dim, modifier = Modifier.size(17.dp))
                    }
                }
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(if (running) toolTitle(current.first.name) else "Выполнено: $done ${plural(done, "действие", "действия", "действий")}" + if (failed > 0) " · ошибок: $failed" else "", color = C.text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
                val sub = if (running) toolSummary(current.first.name, current.first.args) else item.calls.map { toolTitle(it.first.name) }.groupingBy { it }.eachCount().entries.joinToString(" · ") { if (it.value > 1) "${it.key} ×${it.value}" else it.key }
                Text(sub, color = C.dim, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            if (running) CircularProgressIndicator(Modifier.size(20.dp), color = C.accent, strokeWidth = 2.5.dp)
            else Icon(if (failed > 0) Icons.Outlined.ErrorOutline else Icons.Outlined.CheckCircle, null, tint = if (failed > 0) C.danger else C.ok, modifier = Modifier.size(22.dp))
            Icon(Icons.Outlined.ExpandMore, null, tint = C.dim, modifier = Modifier.padding(start = 6.dp).size(22.dp).graphicsLayer { rotationZ = rot })
        }
        // живой вывод терминала, пока команда выполняется
        if (running && current.first.name == "bash") {
            val out = vm.toolOutput[current.first.id].orEmpty().trimEnd().lines().takeLast(5).joinToString("\n")
            if (out.isNotBlank()) Text(out, color = C.text.copy(alpha = 0.85f), style = Mono, fontSize = 11.sp, lineHeight = 15.sp, maxLines = 5, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(start = 10.dp, end = 10.dp, bottom = 10.dp).fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(C.code).padding(10.dp))
        }
        if (open) Column(Modifier.padding(start = 8.dp, end = 8.dp, bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            item.calls.forEach { (c, r) -> ToolRow(vm, c, r, live && r == null) }
        }
        if (!open && sources.isNotEmpty()) Row(Modifier.horizontalScroll(rememberScrollState()).padding(start = 12.dp, end = 12.dp, bottom = 12.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            sources.forEach { u ->
                val host = remember(u) { runCatching { android.net.Uri.parse(u).host.orEmpty().removePrefix("www.") }.getOrDefault(u) }
                Row(Modifier.height(30.dp).bounceClick { runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(u)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } }.clip(RoundedCornerShape(15.dp)).background(C.surface3).padding(horizontal = 11.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Link, null, tint = C.accent, modifier = Modifier.size(14.dp)); Spacer(Modifier.width(5.dp)); Text(host, color = C.dim, fontSize = 12.sp, maxLines = 1)
                }
            }
        }
    }
}

@Composable
private fun ToolRow(vm: AppVM, call: ToolCall, result: Msg?, live: Boolean) {
    var open by remember(call.id) { mutableStateOf(false) }
    val out = result?.content ?: vm.toolOutput[call.id].orEmpty()
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(C.surface3.copy(alpha = 0.55f)).animateContentSize(spring(0.9f, 500f))) {
        Row(Modifier.clickable { Haptics.tick(); open = !open }.padding(horizontal = 10.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(toolIcon(call.name), null, tint = C.dim, modifier = Modifier.size(18.dp)); Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(toolTitle(call.name), color = C.text, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                Text((if (call.name == "bash") "$ " else "") + toolSummary(call.name, call.args), color = C.dim, fontSize = 11.sp, style = if (call.name == "bash") Mono else androidx.compose.ui.text.TextStyle.Default, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            if (live) CircularProgressIndicator(Modifier.size(16.dp), color = C.accent, strokeWidth = 2.dp) else if (isFailed(result)) Icon(Icons.Outlined.Close, null, tint = C.danger, modifier = Modifier.size(18.dp)) else Icon(Icons.Outlined.Check, null, tint = C.ok, modifier = Modifier.size(18.dp))
        }
        if (open) Text(out.takeLast(3000).ifEmpty { "…" }, color = C.text.copy(alpha = 0.88f), style = Mono, fontSize = 11.sp, lineHeight = 15.sp,
            modifier = Modifier.padding(start = 8.dp, end = 8.dp, bottom = 8.dp).fillMaxWidth().heightIn(max = 240.dp).clip(RoundedCornerShape(12.dp)).verticalScroll(rememberScrollState()).background(C.code).padding(10.dp))
    }
}

@Composable
fun EmptyState(vm: AppVM) {
    val code = vm.mode == "code"
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        SaturnMark(110.dp)
        Spacer(Modifier.height(24.dp))
        AnimatedContent(if (code) "Что построим?" else "Чем помочь?", transitionSpec = { (fadeIn() + slideInVertically { it / 2 }) togetherWith (fadeOut() + slideOutVertically { -it / 2 }) }, label = "h") {
            Text(it, color = C.text, fontSize = 32.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun UserBubble(vm: AppVM, m: Msg) {
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        m.attachments?.forEach { AttachmentView(vm, it, mine = true) }
        if (m.content.isNotBlank()) {
            val ctx = LocalContext.current
            var menu by remember { mutableStateOf(false) }
            var editing by remember { mutableStateOf(false) }
            Box {
                Text(remember(m.content) { m.content.monoEmoji() }, color = C.onContainer, fontSize = 17.sp, lineHeight = 25.sp,
                    modifier = Modifier.widthIn(max = 340.dp).clip(RoundedCornerShape(26.dp, 26.dp, 8.dp, 26.dp)).background(C.container)
                        .combinedClickable(onClick = {}, onLongClick = { Haptics.heavy(); menu = true }).padding(horizontal = 18.dp, vertical = 13.dp))
                DropdownMenu(menu, { menu = false }, containerColor = C.surface3, shape = RoundedCornerShape(20.dp)) {
                    DropdownMenuItem(text = { Text("Копировать") }, leadingIcon = { Icon(Icons.Outlined.ContentCopy, null) }, onClick = { menu = false; copyToClipboard(ctx, m.content); vm.toast = "Скопировано" })
                    if (!vm.running) DropdownMenuItem(text = { Text("Изменить и отправить заново") }, leadingIcon = { Icon(Icons.Outlined.Edit, null) }, onClick = { menu = false; editing = true })
                }
            }
            if (editing) {
                var t by remember { mutableStateOf(m.content) }
                AppDialog("Изменить сообщение", { editing = false }, "Отправить", t.isNotBlank(), { vm.editMessage(m, t); editing = false }) {
                    Field(t, { t = it }, "Сообщение", singleLine = false, minLines = 3)
                    Text("Ответ агента после этого сообщения будет заменён новым.", color = C.dim, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
fun AssistantText(vm: AppVM, m: Msg) {
    val ctx = LocalContext.current
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        androidx.compose.foundation.text.selection.SelectionContainer { Markdown(m.content) }
        if (m.toolCalls == null) Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            SmallAction(Icons.Outlined.ContentCopy, "Копировать") { copyToClipboard(ctx, m.content); vm.toast = "Скопировано" }
            val speaking = vm.speakingId == m.id
            SmallAction(if (speaking) Icons.Outlined.Stop else Icons.AutoMirrored.Outlined.VolumeUp, "Озвучить", active = speaking) { vm.toggleSpeak(m) }
            val marked = vm.isBookmarked(m)
            SmallAction(if (marked) Icons.Outlined.Bookmark else Icons.Outlined.BookmarkBorder, "В закладки", active = marked) { vm.toggleBookmark(m) }
            if (!vm.running && vm.messages.lastOrNull { it.role == "assistant" && it.toolCalls == null && it.content.isNotBlank() }?.id == m.id) SmallAction(Icons.Outlined.Refresh, "Повторить") { vm.regenerate() }
        }
    }
}

@Composable
fun SmallAction(icon: androidx.compose.ui.graphics.vector.ImageVector, desc: String, active: Boolean = false, onClick: () -> Unit) {
    Box(Modifier.size(38.dp).bounceClick(onClick = onClick).clip(CircleShape).background(if (active) C.container else Color.Transparent), contentAlignment = Alignment.Center) {
        Icon(icon, desc, tint = if (active) C.onContainer else C.dim, modifier = Modifier.size(20.dp))
    }
}

private fun toolSummary(name: String, args: String): String {
    val o = runCatching { JSON.parseToJsonElement(args).jsonObject }.getOrNull() ?: return ""
    fun s(k: String) = o[k]?.jsonPrimitive?.contentOrNull.orEmpty()
    return when (name) {
        "bash" -> s("command"); "read_file", "write_file", "edit_file", "list_dir", "send_file" -> s("path")
        "web_fetch" -> s("url"); "web_search" -> s("query"); "deploy_site" -> s("name"); "html_app" -> s("title"); "delete_site" -> s("name"); "chart" -> s("title"); "plot_function" -> s("title"); "geometry" -> s("title"); "diagram" -> s("title"); "draw_svg" -> s("title"); "calculate" -> s("expression"); "python" -> s("code"); "skill_search" -> s("query"); "skill_install" -> s("repo"); "delegate" -> s("task"); "grep" -> s("pattern"); "glob" -> s("pattern"); "http_request" -> s("url"); "github_api" -> s("path"); "skill_load" -> s("name"); "schedule_create" -> s("name"); "memory_save" -> s("content"); "memory_search" -> s("query"); else -> args
    }.replace("\n", " ")
}

private fun toolTitle(name: String) = when (name) {
    "bash" -> "Терминал"; "web_search" -> "Поиск в интернете"; "web_fetch" -> "Чтение страницы"; "read_file" -> "Чтение файла"; "write_file" -> "Запись файла"
    "edit_file" -> "Правка файла"; "list_dir" -> "Список файлов"; "send_file" -> "Отправка файла"; "memory_save" -> "Запомнил"; "memory_search" -> "Вспоминаю"; "memory_forget" -> "Забыл"
    "delegate" -> "Под-агент"; "grep" -> "Поиск по коду"; "glob" -> "Поиск файлов"; "http_request" -> "HTTP-запрос"; "process" -> "Процессы"; "github_api" -> "GitHub"
    "skill_load" -> "Навык"; "deploy_site" -> "Публикация сайта"; "html_app" -> "Мини-приложение"; "list_sites" -> "Сайты"; "delete_site" -> "Удаление сайта"; "skill_save" -> "Новый навык"; "chart" -> "График"; "plot_function" -> "График функции"; "geometry" -> "Чертёж"; "diagram" -> "Диаграмма"; "draw_svg" -> "Рисунок"; "calculate" -> "Вычисление"; "python" -> "Python"; "skill_search" -> "Поиск навыков"; "skill_install" -> "Установка навыка"
    "schedule_create" -> "Автоматизация"; "schedule_list" -> "Автоматизации"; "schedule_delete" -> "Автоматизация удалена"; else -> name
}

@Composable
fun ToolCard(vm: AppVM, call: ToolCall, result: Msg?) {
    var open by remember { mutableStateOf(false) }
    val live = result == null && vm.running
    val out = result?.content ?: vm.toolOutput[call.id].orEmpty()
    val rot by animateFloatAsState(if (open) 180f else 0f, spring(0.6f, 400f), label = "rot")
    val icon = when (call.name) { "bash" -> Icons.Outlined.Terminal; "web_fetch" -> Icons.Outlined.Language; "web_search" -> Icons.Outlined.Search; "send_file" -> Icons.Outlined.Upload
        "memory_save", "memory_search", "memory_forget" -> Icons.Outlined.Psychology; "delegate" -> Icons.Outlined.AccountTree; "grep", "glob" -> Icons.Outlined.ManageSearch; "http_request" -> Icons.Outlined.Http
        "chart" -> Icons.Outlined.BarChart; "plot_function" -> Icons.Outlined.ShowChart; "geometry" -> Icons.Outlined.Straighten; "diagram" -> Icons.Outlined.AccountTree; "draw_svg" -> Icons.Outlined.Brush; "calculate" -> Icons.Outlined.Calculate; "python" -> Icons.Outlined.Code; "skill_search", "skill_install" -> Icons.Outlined.Extension; "deploy_site", "list_sites", "delete_site" -> Icons.Outlined.Public; "html_app" -> Icons.Outlined.Widgets
        "github_api" -> Icons.Outlined.Hub; "process" -> Icons.Outlined.Memory; "skill_load", "skill_save" -> Icons.Outlined.AutoFixHigh; "schedule_create", "schedule_list", "schedule_delete" -> Icons.Outlined.Schedule; else -> Icons.Outlined.Description }
    val failed = result?.content?.startsWith("Ошибка") == true || Regex("\\[exit [1-9]").containsMatchIn(result?.content ?: "")
    val sheen = rememberInfiniteTransition(label = "sheen").animateFloat(0.4f, 1f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "s")
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(26.dp)).background(C.surface2).animateContentSize(spring(0.8f, 380f))) {
        Row(Modifier.clickable { Haptics.tick(); open = !open }.padding(horizontal = 14.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(38.dp).clip(CircleShape).background(C.container).alpha(if (live) sheen.value else 1f), contentAlignment = Alignment.Center) { Icon(icon, null, tint = C.onContainer, modifier = Modifier.size(20.dp)) }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(toolTitle(call.name), color = C.text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                Text((if (call.name == "bash") "$ " else "") + toolSummary(call.name, call.args), color = C.dim, fontSize = 13.sp, style = if (call.name == "bash") Mono else androidx.compose.ui.text.TextStyle.Default, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            AnimatedContent(if (live) 0 else if (failed) 2 else 1, transitionSpec = { (scaleIn(spring(0.4f, 500f)) + fadeIn()) togetherWith (scaleOut() + fadeOut()) }, label = "st") { st ->
                when (st) {
                    0 -> CircularProgressIndicator(Modifier.size(20.dp), color = C.accent, strokeWidth = 2.5.dp)
                    2 -> Icon(Icons.Outlined.Close, null, tint = C.danger, modifier = Modifier.size(22.dp))
                    else -> Icon(Icons.Outlined.CheckCircle, null, tint = C.ok, modifier = Modifier.size(22.dp))
                }
            }
            Icon(Icons.Outlined.ExpandMore, null, tint = C.dim, modifier = Modifier.padding(start = 6.dp).size(22.dp).rotate(rot))
        }
        if (open || (live && call.name == "bash" && out.isNotEmpty())) {
            Text(out.takeLast(4000).ifEmpty { "…" }, color = C.text.copy(alpha = 0.88f), style = Mono, fontSize = 12.sp, lineHeight = 17.sp,
                modifier = Modifier.padding(start = 8.dp, end = 8.dp, bottom = 8.dp).fillMaxWidth().heightIn(max = 280.dp).clip(RoundedCornerShape(18.dp)).verticalScroll(rememberScrollState(Int.MAX_VALUE)).background(C.code).padding(14.dp))
        }
    }
}

@Composable
fun AttachmentView(vm: AppVM, a: Attach, mine: Boolean) {
    val ctx = LocalContext.current
    if (a.mime.startsWith("image/")) {
        val svg = a.mime.contains("svg")
        var zoom by remember { mutableStateOf(false) }
        // SVG с анимацией (SMIL / CSS) показываем живым в WebView: обычный загрузчик картинок рисует только первый кадр
        val code by produceState<String?>(null, a.id) { if (svg) value = runCatching { vm.api.fileText(a.id) }.getOrNull() }
        val animated = code?.let { Regex("<animate|<set\\b|@keyframes|animation\\s*:", RegexOption.IGNORE_CASE).containsMatchIn(it) } == true
        if (svg && animated) { SvgBlock(code!!, ctx); return }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            AsyncImage(
                ImageRequest.Builder(ctx).data("${vm.api.base}/api/files/${a.id}" + (if (svg) "" else "?w=640")).addHeader("Authorization", "Bearer ${vm.store.token}").crossfade(true).build(),
                a.name, imageLoader = vm.imageLoader, contentScale = if (svg) ContentScale.Fit else ContentScale.Crop,
                modifier = (if (svg) Modifier.fillMaxWidth().heightIn(max = 480.dp) else Modifier.widthIn(max = 260.dp).heightIn(max = 260.dp)).clip(RoundedCornerShape(26.dp)).clickable { Haptics.tick(); zoom = true })
            if (!a.caption.isNullOrBlank() && svg) Text(a.caption, color = C.dim, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 8.dp))
        }
        if (zoom) ImageViewer(vm, a) { zoom = false }
    } else {
        val apk = a.name.endsWith(".apk", true)
        Row(Modifier.widthIn(max = 340.dp).bounceClick { vm.openFile(a) }.clip(RoundedCornerShape(26.dp)).background(if (apk) C.container else C.surface2).padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(46.dp).clip(RoundedCornerShape(16.dp)).background(if (apk) C.accent else C.container), contentAlignment = Alignment.Center) {
                Icon(if (apk) Icons.Outlined.Android else Icons.AutoMirrored.Outlined.InsertDriveFile, null, tint = if (apk) C.onAccent else C.onContainer)
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f, fill = false)) {
                Text(a.name, color = if (apk) C.onContainer else C.text, fontSize = 15.sp, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(buildString { append(humanSize(a.size)); if (!mine) append(if (apk) " · установить" else " · открыть") }, color = C.dim, fontSize = 12.sp)
            }
        }
    }
}

fun humanSize(n: Long) = when { n < 1024 -> "$n Б"; n < 1048576 -> "${n / 1024} КБ"; n < 1073741824 -> "%.1f МБ".format(n / 1048576.0); else -> "%.2f ГБ".format(n / 1073741824.0) }

@Composable
fun SoftChip(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, selected: Boolean, onClick: () -> Unit) {
    val bg by animateColorAsState(if (selected) C.container else C.surface2, label = "chip")
    val fg by animateColorAsState(if (selected) C.onContainer else C.dim, label = "chipfg")
    Row(Modifier.height(38.dp).bounceClick(onClick = onClick).clip(RoundedCornerShape(19.dp)).background(bg).padding(horizontal = 14.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, null, tint = fg, modifier = Modifier.size(18.dp)); Spacer(Modifier.width(7.dp)); Text(label, color = fg, fontSize = 14.sp, fontWeight = FontWeight.Medium)
    }
}

val PERSONAS = listOf("" to "Универсал", "dev" to "Инженер", "teacher" to "Преподаватель", "analyst" to "Аналитик", "translator" to "Переводчик", "writer" to "Писатель", "coach" to "Коуч", "friend" to "Грубый помощник")

@Composable
fun InputBar(vm: AppVM) {
    var text by remember { mutableStateOf(vm.drafts[vm.convId] ?: "") }
    LaunchedEffect(vm.convId) { text = vm.drafts[vm.convId] ?: "" }
    LaunchedEffect(text) { vm.drafts[vm.convId] = text }
    val ctx = LocalContext.current
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetMultipleContents()) { vm.attach(it) }
    val pickImages = rememberLauncherForActivityResult(ActivityResultContracts.GetMultipleContents()) { vm.attach(it) }
    var camUri by remember { mutableStateOf<android.net.Uri?>(null) }
    val takePic = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok -> if (ok) camUri?.let { vm.attach(listOf(it)) } }
    fun launchCamera() {
        val f = java.io.File(java.io.File(ctx.cacheDir, "cam").also { it.mkdirs() }, "photo_${System.currentTimeMillis()}.jpg")
        val uri = androidx.core.content.FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f); camUri = uri
        runCatching { takePic.launch(uri) }.onFailure { vm.toast = "Камера недоступна" }
    }
    LaunchedEffect(vm.cameraRequest) { if (vm.cameraRequest) { vm.cameraRequest = false; launchCamera() } }
    val notifPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    val micPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (ok) vm.startDictation() else vm.toast = "Нужен доступ к микрофону" }
    fun toggleMic() {
        if (vm.dictating) vm.finishDictation { text = (text + " " + it).trim() }
        else if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) vm.startDictation()
        else micPerm.launch(Manifest.permission.RECORD_AUDIO)
    }
    val code = vm.mode == "code"
    LaunchedEffect(vm.pendingText) { vm.pendingText?.let { text = it; vm.pendingText = null } }
    var sheet by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { vm.loadProviders() }
    if (sheet) ModelSheet(vm) { sheet = false }

    LaunchedEffect(Unit) { vm.loadSkills(); vm.loadPrompts() }
    val slash = text.startsWith("/") && !text.contains(' ')
    val builtin = listOf(
        Triple("/сайт", "Сделать сайт и опубликовать", "Сделай и опубликуй сайт: "),
        Triple("/график", "Построить график или диаграмму", "Построй график: "),
        Triple("/реши", "Решить задачу с проверкой", "Реши задачу и проверь вычисления: "),
        Triple("/план", "Составить план работ", "Составь план и пошагово выполни: "),
        Triple("/ревью", "Ревью кода и поиск багов", "Сделай ревью кода текущего проекта: "),
        Triple("/резюме", "Кратко пересказать", "Кратко перескажи: "),
    )
    Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp)) {
        AnimatedVisibility(slash, enter = fadeIn() + expandVertically(), exit = fadeOut() + shrinkVertically()) {
            val q = text.lowercase()
            val cmds = builtin.filter { it.first.startsWith(q) } + vm.prompts.filter { "/${it.name}".lowercase().startsWith(q) }.take(6).map { Triple("/${it.name}", it.text.take(60), it.text) } + vm.skills.filter { "/${it.name}".lowercase().startsWith(q) }.take(6).map { Triple("/${it.name}", it.description.ifBlank { "Навык" }, "Используй навык ${it.name}: ") }
            Column(Modifier.fillMaxWidth().padding(bottom = 8.dp).clip(RoundedCornerShape(24.dp)).background(C.surface2)) {
                cmds.take(7).forEach { (cmd, desc, ins) ->
                    Row(Modifier.fillMaxWidth().clickable { Haptics.tick(); text = ins }.padding(horizontal = 18.dp, vertical = 11.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(cmd, color = C.accent, style = Mono, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                        Spacer(Modifier.width(12.dp)); Text(desc, color = C.dim, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                if (cmds.isEmpty()) Text("Команд не найдено", color = C.dim, modifier = Modifier.padding(16.dp))
            }
        }
        AnimatedVisibility(vm.toast != null, enter = fadeIn() + slideInVertically { it } + scaleIn(initialScale = 0.8f), exit = fadeOut() + slideOutVertically { it / 2 }) {
            Text(vm.toast.orEmpty(), color = C.onContainer, fontSize = 14.sp, modifier = Modifier.padding(bottom = 10.dp).clip(RoundedCornerShape(20.dp)).background(C.container).padding(horizontal = 18.dp, vertical = 11.dp))
        }
        AnimatedVisibility(vm.attachments.any { it.mime.startsWith("image/") } && text.isBlank() && !vm.running, enter = fadeIn() + expandVertically(), exit = fadeOut() + shrinkVertically()) {
            Row(Modifier.horizontalScroll(rememberScrollState()).padding(bottom = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                SoftChip(Icons.Outlined.TextFields, "Распознать текст", false) { vm.send("Распознай и перепиши весь текст с фото") }
                SoftChip(Icons.Outlined.Calculate, "Решить задачу", false) { vm.send("Реши задачу с фото, покажи ход решения и проверь ответ") }
                SoftChip(Icons.Outlined.Image, "Описать", false) { vm.send("Опиши, что на фото") }
            }
        }
        AnimatedVisibility(vm.attachments.isNotEmpty() || vm.uploading > 0, enter = fadeIn() + expandVertically(), exit = fadeOut() + shrinkVertically()) {
            Row(Modifier.horizontalScroll(rememberScrollState()).padding(bottom = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                vm.attachments.forEach { a ->
                    Row(Modifier.height(42.dp).clip(RoundedCornerShape(21.dp)).background(C.surface3).padding(start = 14.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.AttachFile, null, tint = C.dim, modifier = Modifier.size(18.dp)); Spacer(Modifier.width(6.dp))
                        Text(a.name, color = C.text, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 150.dp))
                        Icon(Icons.Outlined.Close, null, tint = C.dim, modifier = Modifier.padding(start = 4.dp).size(34.dp).clip(CircleShape).clickable { Haptics.tick(); vm.removeAttachment(a) }.padding(8.dp))
                    }
                }
                if (vm.uploading > 0) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (vm.uploadPct > 0.01f) CircularProgressIndicator(progress = { vm.uploadPct }, modifier = Modifier.size(26.dp), color = C.accent, strokeWidth = 2.5.dp) else CircularProgressIndicator(Modifier.size(26.dp), color = C.accent, strokeWidth = 2.5.dp)
                    Text(if (vm.uploadPct > 0.01f) "${(vm.uploadPct * 100).toInt()}%" else "Загрузка…", color = C.dim, fontSize = 13.sp)
                }
            }
        }
        RunningBorder(vm.running, 34.dp) {
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(32.dp)).background(C.surface2).padding(6.dp), verticalAlignment = Alignment.Bottom) {
                    Box {
                    var attachMenu by remember { mutableStateOf(false) }
                    var roleMenu by remember { mutableStateOf(false) }
                    DropdownMenu(roleMenu, { roleMenu = false }, containerColor = C.surface3, shape = RoundedCornerShape(22.dp)) {
                        PERSONAS.forEach { (id, label) -> DropdownMenuItem(text = { Text(label, fontWeight = if (id == vm.persona) FontWeight.Bold else FontWeight.Normal) }, trailingIcon = { if (id == vm.persona) Icon(Icons.Outlined.Check, null, tint = C.accent) }, onClick = { roleMenu = false; Haptics.click(); vm.choosePersona(id) }) }
                    }
                    RoundButton(Icons.Outlined.Add, "Прикрепить", { attachMenu = true }, container = Color.Transparent, iconSize = 28.dp)
                    DropdownMenu(attachMenu, { attachMenu = false }, containerColor = C.surface3, shape = RoundedCornerShape(22.dp)) {
                        DropdownMenuItem(text = { Text("Камера") }, leadingIcon = { Icon(Icons.Outlined.PhotoCamera, null) }, onClick = { attachMenu = false; launchCamera() })
                        DropdownMenuItem(text = { Text("Фото из галереи") }, leadingIcon = { Icon(Icons.Outlined.PhotoLibrary, null) }, onClick = { attachMenu = false; pickImages.launch("image/*") })
                        DropdownMenuItem(text = { Text("Файлы") }, leadingIcon = { Icon(Icons.Outlined.AttachFile, null) }, onClick = { attachMenu = false; picker.launch("*/*") })
                        DropdownMenuItem(text = { Text("Спросить про скопированное") }, leadingIcon = { Icon(Icons.Outlined.ContentPaste, null) }, onClick = { attachMenu = false; val clip = (ctx.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager).primaryClip?.getItemAt(0)?.coerceToText(ctx)?.toString().orEmpty(); if (clip.isBlank()) vm.toast = "Буфер обмена пуст" else text = "Объясни и разбери этот текст:\n\n" + clip.take(6000) })
                        HorizontalDivider(color = C.outline, modifier = Modifier.padding(vertical = 4.dp))
                        DropdownMenuItem(text = { Text("Модель: " + vm.modelLabel() + when (vm.effort) { "low" -> " · быстро"; "high" -> " · глубоко"; else -> "" }, maxLines = 1) }, leadingIcon = { Icon(Icons.Outlined.Tune, null) }, onClick = { attachMenu = false; sheet = true })
                        DropdownMenuItem(text = { Text("Роль: " + (PERSONAS.firstOrNull { it.first == vm.persona }?.second ?: "Универсал")) }, leadingIcon = { Icon(Icons.Outlined.Face, null) }, onClick = { attachMenu = false; roleMenu = true })
                        DropdownMenuItem(text = { Text("Озвучка ответов") }, leadingIcon = { Icon(Icons.AutoMirrored.Outlined.VolumeUp, null) }, trailingIcon = { if (vm.autoSpeak) Icon(Icons.Outlined.Check, null, tint = C.accent) }, onClick = { vm.updAutoSpeak(!vm.autoSpeak) })
                    }
                }
                Box(Modifier.weight(1f).heightIn(min = 48.dp).padding(horizontal = 4.dp), contentAlignment = Alignment.CenterStart) {
                    if (vm.dictating) Row(verticalAlignment = Alignment.CenterVertically) { Box(Modifier.width(96.dp)) { Waveform(vm.dictLevel) }; if (vm.dictPartial.isNotBlank()) Text(vm.dictPartial.takeLast(60), color = C.dim, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(start = 8.dp)) }
                    else {
                        if (text.isEmpty()) Text(if (vm.dictBusy) "Распознаю речь…" else if (code) "Задача для агента…" else "Сообщение", color = C.dim, fontSize = 17.sp)
                        BasicTextField(text, { text = it }, textStyle = androidx.compose.ui.text.TextStyle(color = C.text, fontSize = 17.sp, lineHeight = 24.sp, fontFamily = if (code) androidx.compose.ui.text.font.FontFamily.Monospace else null),
                            cursorBrush = SolidColor(C.accent), maxLines = 7, keyboardOptions = KeyboardOptions(capitalization = if (code) KeyboardCapitalization.None else KeyboardCapitalization.Sentences), modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp))
                    }
                }
                if (vm.dictating) RoundButton(Icons.Outlined.Close, "Отмена", { vm.cancelDictation() }, container = Color.Transparent, content = C.dim)
                val hasContent = text.isNotBlank() || vm.attachments.isNotEmpty()
                val state = when { vm.running -> "stop"; vm.dictating -> "done"; hasContent -> "send"; else -> "mic" }
                AnimatedContent(state, transitionSpec = { (scaleIn(spring(0.55f, 500f), initialScale = 0.5f) + fadeIn(tween(120))) togetherWith (scaleOut(targetScale = 0.5f) + fadeOut(tween(90))) }, label = "action") { st ->
                    when (st) {
                        "stop" -> RoundButton(Icons.Outlined.Stop, "Стоп", { vm.stopRun() }, container = C.accent, content = C.onAccent, strong = true)
                        "done" -> RoundButton(Icons.Outlined.Check, "Готово", { toggleMic() }, container = C.ok.copy(alpha = 0.25f), content = C.ok, strong = true)
                        "send" -> RoundButton(Icons.AutoMirrored.Outlined.Send, "Отправить", {
                            if (android.os.Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) notifPerm.launch(Manifest.permission.POST_NOTIFICATIONS)
                            vm.send(text); text = "" }, container = C.accent, content = C.onAccent, strong = true)
                        else -> RoundButton(Icons.Outlined.Mic, "Диктовка", { toggleMic() }, container = C.surface3, content = C.text, iconSize = 26.dp)
                    }
                }
            }
        }
    }
}

@Composable
fun Waveform(level: Float) {
    val bars = remember { mutableStateListOf<Float>().apply { repeat(26) { add(0f) } } }
    LaunchedEffect(level) { bars.removeAt(0); bars.add(level) }
    val blink by rememberInfiniteTransition(label = "rec").animateFloat(0.3f, 1f, infiniteRepeatable(tween(700), RepeatMode.Reverse), label = "b")
    Row(Modifier.fillMaxWidth().height(48.dp), horizontalArrangement = Arrangement.spacedBy(3.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(11.dp).alpha(blink).background(C.danger, CircleShape)); Spacer(Modifier.width(8.dp))
        bars.forEach { b -> Box(Modifier.width(4.dp).height((5 + b * 34).dp).clip(CircleShape).background(C.accent.copy(alpha = 0.45f + b * 0.55f))) }
    }
}

@Composable
fun CheckpointsDialog(vm: AppVM) {
    var confirm by remember { mutableStateOf<Checkpoint?>(null) }
    val df = remember { java.text.SimpleDateFormat("d MMM HH:mm", java.util.Locale.getDefault()) }
    AppDialog("Точки отката", { vm.showCp = false }, "Закрыть", true, { vm.showCp = false }) {
        if (vm.checkpoints.isEmpty()) Text("Пока нет снимков. Они создаются автоматически до и после правок агента.", color = C.dim, fontSize = 14.sp)
        vm.checkpoints.take(30).forEach { c ->
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(C.surface).clickable { Haptics.tick(); confirm = c }.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(c.subject, color = C.text, fontSize = 14.sp, maxLines = 1)
                    Text(df.format(java.util.Date(c.ts * 1000)) + " · " + c.files + " файл., +" + c.ins + " −" + c.del, color = C.dim, fontSize = 12.sp)
                }
                Icon(Icons.Outlined.Restore, null, tint = C.accent)
            }
        }
    }
    confirm?.let { c ->
        AppDialog("Восстановить файлы?", { confirm = null }, "Восстановить", true, { vm.restoreCheckpoint(c.hash); confirm = null; vm.showCp = false }) {
            Text("Рабочая папка чата вернётся к состоянию «${c.subject}». Текущее состояние тоже будет сохранено.", color = C.dim, fontSize = 14.sp)
        }
    }
}
