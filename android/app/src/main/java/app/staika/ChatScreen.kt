package app.staika

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
fun ChatScreen(agentId: String, onBack: () -> Unit, onCall: () -> Unit, onSettings: () -> Unit) {
    val agent = Repo.agent(agentId)
    if (agent == null) { Box(Modifier.fillMaxSize().background(Color.White)); return }
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val listState = rememberLazyListState()
    var input by remember { mutableStateOf("") }
    var recording by remember { mutableStateOf(false) }
    var attach by remember { mutableStateOf(false) }
    var dictation by remember { mutableStateOf<Dictation?>(null) }
    var baseText by remember { mutableStateOf("") }

    LaunchedEffect(agentId) { Repo.loadMessages(agentId) }
    DisposableEffect(agentId) { onDispose { dictation?.stop() } }

    // сообщения с разделителями по дням и индикатором «печатает»
    val raw = Repo.messages[agentId]
    val items: List<Msg> = remember(raw?.toList(), agent.status) {
        buildList {
            var lastDay = ""
            raw?.forEach { m ->
                val d = dayLabel(m.at)
                if (d != lastDay) { add(Msg.Day("day-${m.at}", m.at, d + ", " + java.text.SimpleDateFormat("HH:mm", java.util.Locale("ru")).format(java.util.Date(m.at)))); lastDay = d }
                add(m)
            }
            if (agent.status == Status.Working) add(Msg.Typing)
        }
    }
    LaunchedEffect(items.size) { if (items.isNotEmpty()) listState.animateScrollToItem(items.lastIndex) }

    fun send() {
        val t = input.trim()
        if (t.isEmpty()) return
        input = ""
        Repo.send(agentId, t)
    }

    fun startDictation() {
        baseText = input
        val d = Dictation(
            onText = { t -> input = (baseText + " " + t).trim() },
            onEnd = { err -> recording = false; err?.let { Repo.say(it) } },
        )
        dictation = d; recording = true; d.start()
    }
    val permission = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) startDictation() else Repo.say("Нужен доступ к микрофону")
    }
    fun toggleMic() {
        if (recording) { dictation?.stop(); return }
        if (androidx.core.content.ContextCompat.checkSelfPermission(ctx, android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED) startDictation()
        else permission.launch(android.Manifest.permission.RECORD_AUDIO)
    }

    Column(Modifier.fillMaxSize().background(Color.White).imePadding()) {
        Row(
            Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 14.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BackPill(onBack)
            Spacer(Modifier.width(10.dp))
            Row(
                Modifier.shadow(4.dp, CircleShape, ambientColor = C.Shadow, spotColor = C.Shadow).clip(CircleShape).background(Color.White)
                    .border(1.dp, C.Line, CircleShape).bounceClick(down = 0.97f, onClick = onSettings)
                    .padding(start = 7.dp, end = 18.dp, top = 6.dp, bottom = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Avatar(agent.pal, 36.dp, status = agent.status)
                Spacer(Modifier.width(9.dp))
                Column {
                    Text(agent.name, fontWeight = FontWeight.SemiBold, fontSize = 18.sp, lineHeight = 21.sp)
                    if (agent.status != Status.Idle) Text(agent.status.label, color = C.Muted, fontSize = 13.sp, lineHeight = 14.sp)
                }
            }
            Spacer(Modifier.weight(1f))
            IconPill(Icons.Outlined.Call, onCall)
        }

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(), state = listState,
            contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            itemsIndexed(items, key = { _, m -> m.id }) { _, m ->
                Box(Modifier.animateItem().appear(0, 14.dp)) {
                    when (m) {
                        is Msg.Day -> Text(m.label, color = C.Muted, fontSize = 14.sp, modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp), textAlign = TextAlign.Center)
                        is Msg.Text -> Bubble(m.mine) { Text(m.text, color = if (m.mine) Color.White else C.Ink, fontSize = 17.sp, lineHeight = 23.sp) }
                        is Msg.System -> Text(m.text, color = C.Muted, fontSize = 14.sp, lineHeight = 20.sp, modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp), textAlign = TextAlign.Center)
                        is Msg.Doc -> DocCard(m)
                        is Msg.Task -> TaskCard(m)
                        is Msg.Approval -> ApprovalCard(m) { d, always -> Repo.decide(agentId, m, d == Decision.Allowed, always) }
                        Msg.Typing -> TypingBubble()
                    }
                }
            }
        }

        Row(
            Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 14.dp, vertical = 8.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            Box {
                IconPill(Icons.Outlined.Add, { attach = true }, size = 50.dp)
                DropdownMenu(attach, { attach = false }, containerColor = Color.White, shape = RoundedCornerShape(22.dp)) {
                    DropdownMenuItem({ Text("Фото и файлы скоро") }, { attach = false }, enabled = false, leadingIcon = { Icon(Icons.Outlined.AttachFile, null) })
                }
            }
            Spacer(Modifier.width(10.dp))
            Row(
                Modifier.weight(1f).heightIn(min = 50.dp).shadow(4.dp, RoundedCornerShape(26.dp), ambientColor = C.Shadow, spotColor = C.Shadow)
                    .clip(RoundedCornerShape(26.dp)).background(Color.White).border(1.dp, C.Line, RoundedCornerShape(26.dp))
                    .padding(start = 18.dp, end = 5.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.weight(1f).padding(vertical = 11.dp).animateContentSize()) {
                    if (input.isEmpty() && !recording) Text("Напишите: ${agent.name}", color = C.Muted, fontSize = 17.sp)
                    if (recording && input.isEmpty()) DictationWave()
                    BasicTextField(
                        input, { input = it }, Modifier.fillMaxWidth(), maxLines = 5,
                        textStyle = TextStyle(fontFamily = Inter, fontSize = 17.sp, color = C.Ink),
                        cursorBrush = SolidColor(C.Ink),
                    )
                }
                val showSend = input.isNotBlank() && !recording
                val dark = showSend || recording
                val bg by animateColorAsState(if (dark) C.Ink else Color(0xFFEDEDF0), tween(220), label = "micBg")
                Box(
                    Modifier.size(40.dp).clip(CircleShape).background(bg).bounceClick(down = 0.88f) { if (showSend) send() else toggleMic() },
                    Alignment.Center,
                ) {
                    AnimatedContent(
                        if (showSend) 1 else if (recording) 2 else 0,
                        transitionSpec = { (scaleIn(spring(0.6f, 500f)) + fadeIn(tween(120))) togetherWith (scaleOut(tween(120)) + fadeOut(tween(100))) },
                        label = "micIcon",
                    ) { st ->
                        Icon(
                            when (st) { 1 -> Icons.Outlined.ArrowUpward; 2 -> Icons.Outlined.Stop; else -> Icons.Outlined.Mic },
                            null, tint = if (st == 0) C.Muted else Color.White, modifier = Modifier.size(23.dp),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun Bubble(mine: Boolean, content: @Composable () -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start) {
        Box(
            Modifier.widthIn(max = 310.dp)
                .clip(RoundedCornerShape(topStart = 22.dp, topEnd = 22.dp, bottomStart = if (mine) 22.dp else 6.dp, bottomEnd = if (mine) 6.dp else 22.dp))
                .background(if (mine) C.Ink else C.Bubble).padding(horizontal = 16.dp, vertical = 11.dp),
        ) { content() }
    }
}

@Composable
private fun TypingBubble() {
    val t = rememberInfiniteTransition(label = "t")
    Bubble(false) {
        Row(horizontalArrangement = Arrangement.spacedBy(5.dp), modifier = Modifier.height(23.dp), verticalAlignment = Alignment.CenterVertically) {
            repeat(3) { i ->
                val a by t.animateFloat(0.25f, 1f, infiniteRepeatable(tween(600, delayMillis = i * 160), RepeatMode.Reverse), label = "d$i")
                Box(Modifier.size(8.dp).clip(CircleShape).background(C.Muted.copy(alpha = a)))
            }
        }
    }
}

@Composable
private fun DocCard(d: Msg.Doc) {
    Row(
        Modifier.widthIn(max = 310.dp).clip(RoundedCornerShape(20.dp)).background(C.Bubble).bounceClick(down = 0.97f) { }.padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(46.dp).clip(RoundedCornerShape(12.dp)).background(Color(0xFFFFC83D)), Alignment.Center) {
            Icon(Icons.Outlined.Description, null, tint = Color.White, modifier = Modifier.size(26.dp))
        }
        Spacer(Modifier.width(12.dp))
        Column {
            Text(d.title, fontWeight = FontWeight.Medium, fontSize = 17.sp)
            Text(d.host, color = C.Muted, fontSize = 15.sp)
        }
    }
}

@Composable
private fun TaskCard(t: Msg.Task) {
    var p by remember { mutableFloatStateOf(0f) }
    LaunchedEffect(t.progress) { p = t.progress }
    val anim by animateFloatAsState(p, tween(900, easing = EaseOutCubic), label = "progress")
    Column(Modifier.widthIn(max = 310.dp).clip(RoundedCornerShape(20.dp)).background(C.Bubble).padding(14.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.TaskAlt, null, tint = C.Ink, modifier = Modifier.size(21.dp))
            Spacer(Modifier.width(8.dp))
            Text("Задача", color = C.Muted, fontSize = 14.sp, modifier = Modifier.weight(1f))
            Text(t.status, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.height(6.dp))
        Text(t.title, fontWeight = FontWeight.Medium, fontSize = 17.sp)
        Spacer(Modifier.height(10.dp))
        ProgressBar(anim, track = Color.White)
    }
}

@Composable
private fun ApprovalCard(a: Msg.Approval, onDecide: (Decision, Boolean) -> Unit) {
    val border by animateColorAsState(if (a.decision == Decision.Pending) C.Warn else C.Line, tween(400), label = "ab")
    Column(
        Modifier.fillMaxWidth().animateContentSize(spring(0.8f, 400f)).clip(RoundedCornerShape(24.dp)).background(Color.White)
            .border(1.5.dp, border, RoundedCornerShape(24.dp)).padding(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(38.dp).clip(CircleShape).background(C.Warn.copy(alpha = 0.14f)), Alignment.Center) {
                Icon(Icons.Outlined.GppMaybe, null, tint = C.Warn, modifier = Modifier.size(22.dp))
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text("Нужно ваше разрешение", color = C.Muted, fontSize = 13.sp)
                Text(a.title, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
            }
        }
        Spacer(Modifier.height(10.dp))
        Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(C.Bubble).padding(12.dp)) {
            Text(a.detail, fontSize = 14.sp, fontFamily = FontFamily.Monospace, lineHeight = 20.sp)
        }
        Spacer(Modifier.height(8.dp))
        Text("Тип: ${a.risk}", color = C.Muted, fontSize = 13.sp)
        Spacer(Modifier.height(12.dp))
        when (a.decision) {
            Decision.Pending -> {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(Modifier.weight(1f).height(48.dp).bounceClick { onDecide(Decision.Denied, false) }.clip(CircleShape).background(C.Bubble), Alignment.Center) {
                        Text("Отклонить", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                    }
                    Box(Modifier.weight(1f).height(48.dp).bounceClick { onDecide(Decision.Allowed, false) }.clip(CircleShape).background(C.Ink), Alignment.Center) {
                        Text("Разрешить", color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                    }
                }
                Text("Разрешать всегда для этого агента", color = C.Muted, fontSize = 14.sp,
                    modifier = Modifier.align(Alignment.CenterHorizontally).bounceClick { onDecide(Decision.Allowed, a.risk != "Необратимое действие") }.padding(top = 10.dp, bottom = 2.dp))
            }
            Decision.Allowed -> Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.CheckCircle, null, tint = C.Ok, modifier = Modifier.size(22.dp)); Spacer(Modifier.width(8.dp))
                Text("Разрешено, выполняю", color = C.Ok, fontWeight = FontWeight.SemiBold)
            }
            Decision.Denied -> Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.Cancel, null, tint = C.Bad, modifier = Modifier.size(22.dp)); Spacer(Modifier.width(8.dp))
                Text("Отклонено", color = C.Bad, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
fun DictationWave(modifier: Modifier = Modifier, color: Color = C.Ink, label: String = "Слушаю") {
    val t = rememberInfiniteTransition(label = "w")
    Row(modifier.height(24.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(label, color = C.Muted, fontSize = 17.sp); Spacer(Modifier.width(6.dp))
        repeat(20) { i ->
            val h by t.animateFloat(4f, 22f, infiniteRepeatable(tween(420 + (i * 53) % 300, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "b$i")
            Box(Modifier.width(3.dp).height(h.dp).clip(CircleShape).background(color))
        }
    }
}
