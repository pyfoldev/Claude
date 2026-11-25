package app.staika

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

@Composable
fun CallScreen(agentId: String, onEnd: () -> Unit) {
    val agent = Store.agent(agentId)
    var sec by remember { mutableIntStateOf(0) }
    var muted by remember { mutableStateOf(false) }
    var speaker by remember { mutableStateOf(true) }
    var phase by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) { while (true) { delay(1000); sec++; if (sec % 4 == 0) phase = (phase + 1) % 3 } }

    val lines = listOf(
        "Вы" to "Что у нас на сегодня по встречам?",
        agent.name to "В 14:00 совет директоров. Презентация готова, ждёт вашего одобрения.",
        "Вы" to "Отправь её команде.",
    )
    val infinite = rememberInfiniteTransition(label = "pulse")
    val ring by infinite.animateFloat(1f, 1.5f, infiniteRepeatable(tween(1800, easing = LinearEasing)), label = "r")
    val ringA by infinite.animateFloat(0.35f, 0f, infiniteRepeatable(tween(1800, easing = LinearEasing)), label = "ra")

    Column(Modifier.fillMaxSize().background(Color.White).statusBarsPadding().navigationBarsPadding().padding(horizontal = 24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Spacer(Modifier.height(16.dp))
        Row(Modifier.clip(CircleShape).background(C.Bubble).padding(horizontal = 14.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Rounded.GraphicEq, null, modifier = Modifier.size(18.dp)); Spacer(Modifier.width(8.dp))
            Text("Claude Haiku 4.5 · голос Владимир", fontSize = 13.sp, fontWeight = FontWeight.Medium)
        }
        Spacer(Modifier.weight(0.7f))
        Box(contentAlignment = Alignment.Center) {
            Box(Modifier.size(190.dp).scale(ring).alpha(ringA).clip(CircleShape).background(C.Accent))
            Avatar(agent.pal, 190.dp, status = Status.Working)
        }
        Spacer(Modifier.height(22.dp))
        Text(agent.name, style = MaterialTheme.typography.headlineMedium)
        Text("%d:%02d".format(sec / 60, sec % 60), color = C.Muted, fontSize = 16.sp)
        Spacer(Modifier.height(18.dp))
        DictationWave(color = C.Accent)
        Spacer(Modifier.weight(0.6f))
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(C.Bubble).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            lines.take(phase + 1).takeLast(2).forEach { (who, text) ->
                Column { Text(who, color = C.Muted, fontSize = 12.sp); Text(text, fontSize = 15.sp) }
            }
        }
        Spacer(Modifier.weight(0.5f))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
            RoundBtn(if (muted) Icons.Rounded.MicOff else Icons.Rounded.Mic, if (muted) "Звук выкл." else "Микрофон", muted) { muted = !muted }
            RoundBtn(Icons.Rounded.VolumeUp, "Динамик", speaker) { speaker = !speaker }
            RoundBtn(Icons.Rounded.Keyboard, "Написать", false) { onEnd() }
            RoundBtn(Icons.Rounded.CallEnd, "Завершить", false, danger = true, onClick = onEnd)
        }
        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun RoundBtn(icon: ImageVector, label: String, active: Boolean, danger: Boolean = false, onClick: () -> Unit) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Box(
            Modifier.size(62.dp).clip(CircleShape).background(if (danger) C.Bad else if (active) C.Ink else C.Bubble).clickable(onClick = onClick),
            Alignment.Center,
        ) { Icon(icon, null, tint = if (danger || active) Color.White else C.Ink, modifier = Modifier.size(28.dp)) }
        Spacer(Modifier.height(6.dp))
        Text(label, fontSize = 12.sp, color = C.Muted, textAlign = TextAlign.Center)
    }
}
