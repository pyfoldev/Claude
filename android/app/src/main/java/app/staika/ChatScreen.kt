package app.staika

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private fun seed(a: Agent): List<Msg> = when (a.id) {
    "chief" -> listOf(
        Msg.Day("Сегодня 8:00"),
        Msg.Text("Привет! Что требует моего внимания сегодня?", true),
        Msg.Text("За ночь: 41 письмо, 6 требовали вас, остальные разобраны.", false),
        Msg.Text("3 счёта ушли Аналитику, 2 знакомства связал, 1 баг передал Разработчику.", false),
        Msg.Approval(1, "Совет директоров в 14:00", "Календарь: создать событие «Разбор презентации», 14:00–15:00, пригласить 4 человек.", "Внешнее действие"),
        Msg.Doc("Презентация Q3, версия 4", "docs.google.com"),
        Msg.Task("Подготовить отчёт для совета", 0.7f, "В работе"),
    )
    "mail" -> listOf(
        Msg.Day("Сегодня 8:22"),
        Msg.Text("Разобрал 41 письмо. Три ответа готовы к отправке.", false),
        Msg.Approval(2, "Отправить письмо клиенту", "Кому: anna@example.com\nТема: Re: Счёт на оплату\nОтправка с адреса почтальон@ваш-домен", "Отправка письма"),
        Msg.Doc("Черновики ответов", "docs.google.com"),
    )
    "dev" -> listOf(
        Msg.Day("Сегодня 8:05"),
        Msg.Text("Собираю релиз 0.4.2. Тесты прошли, осталась выкатка.", false),
        Msg.Approval(3, "Деплой на сервер", "docker compose up -d api\nПроект: staika-api, версия 0.4.2", "Системное действие"),
        Msg.Task("Выкатить релиз 0.4.2", 0.45f, "В работе"),
    )
    else -> listOf(
        Msg.Day("Сегодня"),
        Msg.Text(a.last, false),
    )
}

@Composable
fun ChatScreen(agentId: String, onBack: () -> Unit, onCall: () -> Unit, onComputer: () -> Unit) {
    val agent = Store.agent(agentId)
    val msgs: SnapshotStateList<Msg> = remember(agentId) { mutableStateListOf<Msg>().also { it.addAll(seed(agent)) } }
    val scope = rememberCoroutineScope()
    val listState = rememberLazyListState()
    var input by remember { mutableStateOf("") }
    var recording by remember { mutableStateOf(false) }
    var attach by remember { mutableStateOf(false) }

    LaunchedEffect(msgs.size) { if (msgs.isNotEmpty()) listState.animateScrollToItem(msgs.lastIndex) }

    fun send() {
        val t = input.trim()
        if (t.isEmpty()) return
        input = ""
        msgs.add(Msg.Text(t, true))
        scope.launch {
            delay(500); msgs.add(Msg.Typing)
            delay(1600); msgs.remove(Msg.Typing)
            msgs.add(Msg.Text("Принял. Берусь за это и вернусь с результатом.", false))
        }
    }

    Column(Modifier.fillMaxSize().background(Color.White).imePadding()) {
        Row(
            Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 16.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BackPill(onBack)
            Spacer(Modifier.width(10.dp))
            Surface(shape = CircleShape, color = Color.White, shadowElevation = 5.dp) {
                Row(Modifier.padding(start = 6.dp, end = 16.dp, top = 6.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Avatar(agent.pal, 32.dp, status = agent.status)
                    Spacer(Modifier.width(8.dp))
                    Column {
                        Text(agent.name, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                        if (agent.status != Status.Idle) Text(agent.status.label, color = C.Muted, fontSize = 11.sp, lineHeight = 12.sp)
                    }
                }
            }
            Spacer(Modifier.weight(1f))
            if (agent.id == "dev" || agent.id == "ops") {
                IconPill(Icons.Rounded.Computer, onComputer); Spacer(Modifier.width(10.dp))
            }
            IconPill(Icons.Rounded.Call, onCall)
        }

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(), state = listState,
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            itemsIndexed(msgs) { i, m ->
                when (m) {
                    is Msg.Day -> Text(m.label, color = C.Muted, fontSize = 13.sp, modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                    is Msg.Text -> Bubble(m.mine) { Text(m.text, color = if (m.mine) Color.White else C.Ink, style = MaterialTheme.typography.bodyLarge) }
                    is Msg.Doc -> DocCard(m)
                    is Msg.Task -> TaskCard(m)
                    is Msg.Approval -> ApprovalCard(m) { d -> msgs[i] = m.copy(decision = d) }
                    Msg.Typing -> TypingBubble()
                }
            }
        }

        // поле ввода
        Row(
            Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 16.dp, vertical = 10.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            Box {
                IconPill(Icons.Rounded.Add, { attach = true }, size = 48.dp)
                DropdownMenu(attach, { attach = false }, containerColor = Color.White, shape = RoundedCornerShape(20.dp)) {
                    DropdownMenuItem({ Text("Фото") }, { attach = false }, leadingIcon = { Icon(Icons.Rounded.Image, null) })
                    DropdownMenuItem({ Text("Файл") }, { attach = false }, leadingIcon = { Icon(Icons.Rounded.AttachFile, null) })
                    DropdownMenuItem({ Text("Камера") }, { attach = false }, leadingIcon = { Icon(Icons.Rounded.PhotoCamera, null) })
                }
            }
            Spacer(Modifier.width(10.dp))
            Surface(Modifier.weight(1f).heightIn(min = 48.dp), shape = RoundedCornerShape(26.dp), color = Color.White, shadowElevation = 5.dp) {
                Row(Modifier.padding(start = 18.dp, end = 5.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.weight(1f).padding(vertical = 10.dp)) {
                        if (recording) DictationWave() else {
                            if (input.isEmpty()) Text("Напишите: ${agent.name}", color = C.Muted, fontSize = 16.sp)
                            androidx.compose.foundation.text.BasicTextField(
                                input, { input = it }, Modifier.fillMaxWidth(), maxLines = 5,
                                textStyle = androidx.compose.ui.text.TextStyle(fontSize = 16.sp, color = C.Ink),
                                cursorBrush = androidx.compose.ui.graphics.SolidColor(C.Ink),
                            )
                        }
                    }
                    val showSend = input.isNotBlank() && !recording
                    Box(
                        Modifier.size(38.dp).clip(CircleShape).background(if (showSend || recording) C.Ink else C.Bubble)
                            .clickable {
                                if (showSend) send()
                                else if (recording) { recording = false; input = "Подготовь отчёт по расходам за неделю" }
                                else recording = true
                            },
                        Alignment.Center,
                    ) {
                        Icon(
                            if (showSend) Icons.Rounded.ArrowUpward else if (recording) Icons.Rounded.Stop else Icons.Rounded.Mic,
                            null, tint = if (showSend || recording) Color.White else C.Muted, modifier = Modifier.size(22.dp),
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
            Modifier.widthIn(max = 300.dp)
                .clip(RoundedCornerShape(topStart = 22.dp, topEnd = 22.dp, bottomStart = if (mine) 22.dp else 6.dp, bottomEnd = if (mine) 6.dp else 22.dp))
                .background(if (mine) C.Ink else C.Bubble).padding(horizontal = 16.dp, vertical = 11.dp),
        ) { content() }
    }
}

@Composable
private fun TypingBubble() {
    val t = rememberInfiniteTransition(label = "t")
    Bubble(false) {
        Row(horizontalArrangement = Arrangement.spacedBy(5.dp), modifier = Modifier.height(22.dp), verticalAlignment = Alignment.CenterVertically) {
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
        Modifier.widthIn(max = 300.dp).clip(RoundedCornerShape(20.dp)).background(C.Bubble).clickable { }.padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(44.dp).clip(RoundedCornerShape(12.dp)).background(Color(0xFFFFC83D)), Alignment.Center) {
            Icon(Icons.Rounded.Description, null, tint = Color.White)
        }
        Spacer(Modifier.width(12.dp))
        Column {
            Text(d.title, fontWeight = FontWeight.Medium, fontSize = 16.sp)
            Text(d.host, color = C.Muted, fontSize = 14.sp)
        }
    }
}

@Composable
private fun TaskCard(t: Msg.Task) {
    Column(Modifier.widthIn(max = 300.dp).clip(RoundedCornerShape(20.dp)).background(C.Bubble).padding(14.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Rounded.TaskAlt, null, tint = C.Ink, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text("Задача", color = C.Muted, fontSize = 13.sp, modifier = Modifier.weight(1f))
            Text(t.status, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.height(6.dp))
        Text(t.title, fontWeight = FontWeight.Medium, fontSize = 16.sp)
        Spacer(Modifier.height(10.dp))
        LinearProgressIndicator(
            progress = { t.progress }, Modifier.fillMaxWidth().height(6.dp).clip(CircleShape),
            color = C.Ink, trackColor = Color.White, strokeCap = androidx.compose.ui.graphics.StrokeCap.Round,
        )
    }
}

@Composable
private fun ApprovalCard(a: Msg.Approval, onDecide: (Decision) -> Unit) {
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(Color.White)
            .border(1.5.dp, if (a.decision == Decision.Pending) C.Warn else C.Line, RoundedCornerShape(24.dp)).padding(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(34.dp).clip(CircleShape).background(C.Warn.copy(alpha = 0.15f)), Alignment.Center) {
                Icon(Icons.Rounded.GppMaybe, null, tint = C.Warn, modifier = Modifier.size(20.dp))
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text("Нужно ваше разрешение", color = C.Muted, fontSize = 12.sp)
                Text(a.title, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
            }
        }
        Spacer(Modifier.height(10.dp))
        Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(C.Bubble).padding(12.dp)) {
            Text(a.detail, fontSize = 13.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace, lineHeight = 19.sp)
        }
        Spacer(Modifier.height(8.dp))
        Text("Тип: ${a.risk}", color = C.Muted, fontSize = 12.sp)
        Spacer(Modifier.height(12.dp))
        when (a.decision) {
            Decision.Pending -> {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Button({ onDecide(Decision.Denied) }, Modifier.weight(1f).height(46.dp), shape = CircleShape,
                        colors = ButtonDefaults.buttonColors(containerColor = C.Bubble, contentColor = C.Ink)) { Text("Отклонить", fontWeight = FontWeight.SemiBold) }
                    Button({ onDecide(Decision.Allowed) }, Modifier.weight(1f).height(46.dp), shape = CircleShape,
                        colors = ButtonDefaults.buttonColors(containerColor = C.Ink, contentColor = Color.White)) { Text("Разрешить", fontWeight = FontWeight.SemiBold) }
                }
                Spacer(Modifier.height(6.dp))
                Text("Разрешать всегда для этого агента", color = C.Muted, fontSize = 13.sp,
                    modifier = Modifier.align(Alignment.CenterHorizontally).clickable { onDecide(Decision.Allowed) }.padding(8.dp))
            }
            Decision.Allowed -> Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.CheckCircle, null, tint = C.Ok, modifier = Modifier.size(20.dp)); Spacer(Modifier.width(8.dp))
                Text("Разрешено, выполняю", color = C.Ok, fontWeight = FontWeight.SemiBold)
            }
            Decision.Denied -> Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.Cancel, null, tint = C.Bad, modifier = Modifier.size(20.dp)); Spacer(Modifier.width(8.dp))
                Text("Отклонено", color = C.Bad, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
fun DictationWave(modifier: Modifier = Modifier, color: Color = C.Ink) {
    val t = rememberInfiniteTransition(label = "w")
    Row(modifier.height(24.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
        Text("Слушаю", color = C.Muted, fontSize = 16.sp); Spacer(Modifier.width(6.dp))
        repeat(22) { i ->
            val h by t.animateFloat(4f, 22f, infiniteRepeatable(tween(420 + (i * 53) % 300, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "b$i")
            Box(Modifier.width(3.dp).height(h.dp).clip(CircleShape).background(color))
        }
    }
}
