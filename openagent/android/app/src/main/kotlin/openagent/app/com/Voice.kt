package openagent.app.com

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.*
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.PanTool
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat

@Composable
fun VoiceScreen(vm: AppVM) {
    val ctx = LocalContext.current
    val perm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (ok) vm.startVoice() else { vm.toast = "Нужен доступ к микрофону"; vm.stopVoice() } }
    LaunchedEffect(Unit) {
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) vm.startVoice()
        else perm.launch(Manifest.permission.RECORD_AUDIO)
    }
    BackHandler { vm.stopVoice() }
    val view = androidx.compose.ui.platform.LocalView.current
    DisposableEffect(Unit) { view.keepScreenOn = true; vm.voiceMuted = false; vm.voiceStartedAt = System.currentTimeMillis(); onDispose { view.keepScreenOn = false } }
    DisposableEffect(Unit) { onDispose { if ((ctx as? android.app.Activity)?.isChangingConfigurations != true) vm.stopVoice() } }
    var secs by remember { mutableStateOf(0L) }
    LaunchedEffect(Unit) { while (true) { secs = (System.currentTimeMillis() - vm.voiceStartedAt) / 1000; kotlinx.coroutines.delay(1000) } }
    val state = vm.voiceState
    LaunchedEffect(state) { if (state != VoiceState.Idle) Haptics.tick() }
    val statsLine = vm.voiceStats
    val label = when (state) { VoiceState.Listening -> "Слушаю"; VoiceState.Thinking -> "Думаю"; VoiceState.Speaking -> "Говорю"; VoiceState.Idle -> "Подключение" }
    val hint = when (state) { VoiceState.Listening -> "Говорите — отвечу, когда закончите"; VoiceState.Speaking, VoiceState.Thinking -> "Нажмите на шар, чтобы перебить"; else -> "" }
    val pseudo = remember { Animatable(0f) }
    LaunchedEffect(state) {
        while (state == VoiceState.Speaking || state == VoiceState.Thinking) {
            pseudo.animateTo(if (state == VoiceState.Speaking) 0.25f + kotlin.random.Random.nextFloat() * 0.55f else 0.1f, tween(200))
        }
        pseudo.snapTo(0f)
    }
    val level = if (state == VoiceState.Listening) vm.voiceLevel else pseudo.value
    SideEffect { FxLevel.level = if (state == VoiceState.Listening || state == VoiceState.Speaking) level else 0f }
    DisposableEffect(Unit) { onDispose { FxLevel.level = 0f } }
    val orb = when (state) { VoiceState.Listening -> OrbState.Listening; VoiceState.Thinking -> OrbState.Thinking; VoiceState.Speaking -> OrbState.Speaking; else -> OrbState.Idle }

    val hasText = vm.voiceReply.isNotBlank() || vm.voiceCaption.isNotBlank()
    val orbSize by androidx.compose.animation.core.animateDpAsState(if (hasText) 190.dp else 300.dp, tween(300), label = "orbsize")
    val breathe by rememberInfiniteTransition(label = "sat").animateFloat(0.9f, 1f, infiniteRepeatable(tween(1100, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "satb")
    val satScale = if (state == VoiceState.Thinking) breathe else 1f
    Column(Modifier.fillMaxSize().systemBarsPadding().padding(horizontal = 24.dp, vertical = 16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text("%d:%02d".format(secs / 60, secs % 60), color = C.dim, fontSize = 15.sp)
        // средняя часть занимает всё свободное место и прокручивается — длинный ответ не сдвигает кнопки
        Column(Modifier.weight(1f).fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
            Box(Modifier.size(orbSize).clip(CircleShape).clickable(indication = null, interactionSource = remember { MutableInteractionSource() }) { Haptics.heavy(); vm.voiceInterrupt() }, contentAlignment = Alignment.Center) {
                val pulse by animateFloatAsState(1f + 0.16f * level, tween(90), label = "pulse")
                SaturnMark(72.dp, modifier = Modifier.graphicsLayer { scaleX = satScale * pulse; scaleY = satScale * pulse }, alpha = 0.95f)
            }
            Spacer(Modifier.height(12.dp))
            AnimatedContent(label, transitionSpec = { (fadeIn(tween(300)) + slideInVertically { it / 2 }) togetherWith (fadeOut(tween(150)) + slideOutVertically { -it / 2 }) }, label = "vl") {
                Text(it, color = C.text, fontSize = 30.sp, fontWeight = FontWeight.Bold)
            }
            if (!hasText) Text(hint, color = C.dim, fontSize = 15.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 6.dp))
            AnimatedVisibility(vm.voiceCaption.isNotBlank(), enter = fadeIn() + expandVertically(), exit = fadeOut()) {
                Text("«${vm.voiceCaption}»", color = C.onContainer, fontSize = 15.sp, textAlign = TextAlign.Center, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 12.dp).clip(RoundedCornerShape(22.dp)).background(C.container).padding(horizontal = 18.dp, vertical = 10.dp))
            }
            if (vm.voiceReply.isNotBlank()) {
                val scroll = rememberScrollState()
                LaunchedEffect(vm.voiceReply) { scroll.animateScrollTo(scroll.maxValue) }
                Box(Modifier.weight(1f, fill = false).fillMaxWidth().padding(top = 12.dp)) {
                    Text(vm.voiceReply, color = C.text, fontSize = 17.sp, lineHeight = 24.sp, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().verticalScroll(scroll).padding(horizontal = 8.dp))
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(22.dp), verticalAlignment = Alignment.CenterVertically) {
            AnimatedVisibility(state == VoiceState.Speaking || state == VoiceState.Thinking, enter = scaleIn() + fadeIn(), exit = scaleOut() + fadeOut()) {
                RoundButton(Icons.Outlined.PanTool, "Перебить", { vm.voiceInterrupt() }, size = 76.dp, container = C.container, content = C.onContainer, iconSize = 32.dp, strong = true)
            }
            RoundButton(if (vm.voiceMuted) Icons.Outlined.MicOff else Icons.Outlined.Mic, "Микрофон", { vm.toggleMute() }, size = 76.dp, container = if (vm.voiceMuted) C.danger else C.container, content = if (vm.voiceMuted) Color.Black else C.onContainer, iconSize = 32.dp, strong = true)
            RoundButton(Icons.Outlined.Close, "Завершить", { vm.stopVoice() }, size = 76.dp, container = C.danger, content = Color.Black, iconSize = 34.dp, strong = true)
        }
        Spacer(Modifier.height(12.dp))
    }
}
