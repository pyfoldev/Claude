package app.staika

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun CallScreen(agentId: String, onEnd: () -> Unit) {
    val agent = Repo.agent(agentId)
    val ctx = LocalContext.current
    val session = remember(agentId) { CallSession(ctx.applicationContext, agentId) }
    var started by remember { mutableStateOf(false) }
    val permission = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) { started = true; session.start() } else { Repo.say("Нужен доступ к микрофону"); onEnd() }
    }
    LaunchedEffect(agentId) {
        if (androidx.core.content.ContextCompat.checkSelfPermission(ctx, android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED) { started = true; session.start() }
        else permission.launch(android.Manifest.permission.RECORD_AUDIO)
    }
    DisposableEffect(agentId) { onDispose { session.end() } }
    LaunchedEffect(session.state, session.error) {
        if (session.state == CallSession.State.Ended && started) {
            session.error?.let { Repo.say(it) }
            kotlinx.coroutines.delay(if (session.error != null) 0 else 300); onEnd()
        }
    }

    val infinite = rememberInfiniteTransition(label = "pulse")
    val ring by infinite.animateFloat(1f, 1.35f, infiniteRepeatable(tween(1800, easing = LinearEasing)), label = "r")
    val ringA by infinite.animateFloat(0.16f, 0f, infiniteRepeatable(tween(1800, easing = LinearEasing)), label = "ra")

    Column(
        Modifier.fillMaxSize().background(Color.White).statusBarsPadding().navigationBarsPadding().padding(horizontal = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(16.dp))
        Row(Modifier.clip(CircleShape).background(C.Bubble).padding(horizontal = 14.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.GraphicEq, null, modifier = Modifier.size(18.dp)); Spacer(Modifier.width(8.dp))
            Text(Prefs.voiceModel, fontSize = 14.sp, fontWeight = FontWeight.Medium)
        }
        Spacer(Modifier.weight(0.8f))
        Box(contentAlignment = Alignment.Center) {
            if (session.state == CallSession.State.Live) Box(Modifier.size(190.dp).scale(ring).alpha(ringA).clip(CircleShape).background(C.Accent))
            if (agent != null) Avatar(agent.pal, 190.dp, status = if (session.agentSpeaking) Status.Working else null)
        }
        Spacer(Modifier.height(20.dp))
        Text(agent?.name.orEmpty(), style = MaterialTheme.typography.headlineMedium)
        Text(
            when (session.state) {
                CallSession.State.Connecting -> "Соединяю…"
                CallSession.State.Live -> "%d:%02d".format(session.seconds / 60, session.seconds % 60)
                CallSession.State.Ended -> "Завершён"
            },
            color = C.Muted, fontSize = 17.sp,
        )
        Spacer(Modifier.height(14.dp))
        if (session.state == CallSession.State.Live) DictationWave(color = C.Accent, label = if (session.agentSpeaking) "Говорит" else "Слушаю")
        Spacer(Modifier.weight(0.5f))
        Column(Modifier.fillMaxWidth().heightIn(max = 190.dp).clip(RoundedCornerShape(26.dp)).background(C.Bubble).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (session.lines.isEmpty()) Text("Говорите, расшифровка появится здесь.", color = C.Muted, fontSize = 15.sp)
            session.lines.takeLast(3).forEach { (who, text) ->
                Column { Text(who, color = C.Muted, fontSize = 13.sp); Text(text, fontSize = 16.sp, lineHeight = 21.sp, maxLines = 4) }
            }
        }
        Spacer(Modifier.weight(0.4f))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
            RoundBtn(if (session.muted) Icons.Outlined.MicOff else Icons.Outlined.Mic, if (session.muted) "Звук выкл." else "Микрофон", session.muted) { session.mute(!session.muted) }
            RoundBtn(Icons.Outlined.VolumeUp, "Динамик", session.speaker) { session.useSpeaker(!session.speaker) }
            RoundBtn(Icons.Outlined.CallEnd, "Завершить", false, danger = true) { session.end(); onEnd() }
        }
        Spacer(Modifier.height(22.dp))
    }
}

@Composable
private fun RoundBtn(icon: ImageVector, label: String, active: Boolean, danger: Boolean = false, onClick: () -> Unit) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Box(
            Modifier.size(66.dp).bounceClick(down = 0.88f, onClick = onClick).clip(CircleShape).background(if (danger) C.Bad else if (active) C.Ink else C.Bubble),
            Alignment.Center,
        ) { Icon(icon, null, tint = if (danger || active) Color.White else C.Ink, modifier = Modifier.size(28.dp)) }
        Spacer(Modifier.height(6.dp))
        Text(label, fontSize = 13.sp, color = C.Muted, textAlign = TextAlign.Center)
    }
}
