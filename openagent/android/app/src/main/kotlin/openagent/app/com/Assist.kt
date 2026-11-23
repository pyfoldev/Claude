package openagent.app.com

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.service.voice.VoiceInteractionService
import android.service.voice.VoiceInteractionSession
import android.service.voice.VoiceInteractionSessionService
import android.speech.RecognitionService
import android.speech.SpeechRecognizer
import androidx.activity.ComponentActivity
import androidx.activity.viewModels
import androidx.activity.enableEdgeToEdge
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.PanTool
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.material.icons.filled.Terminal
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.runtime.*
import kotlinx.coroutines.launch
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Системный ассистент: если выбрать OpenAgent «цифровым помощником» (Настройки → Приложения → Приложения по умолчанию),
 * долгое нажатие кнопки питания (или жест) вызывает компактное окно поверх любого экрана.
 */
class OaInteractionService : VoiceInteractionService()

class OaSessionService : VoiceInteractionSessionService() {
    override fun onNewSession(args: Bundle?): VoiceInteractionSession = OaSession(this)
}

/** Данные об экране под окном ассистента: система присылает скриншот и текст ДО показа нашего окна (поэтому окно «не мешает»). */
object AssistData {
    var shot by mutableStateOf<java.io.File?>(null)
    var text by mutableStateOf("")
    fun clear() { shot = null; text = "" }
}

class OaSession(ctx: Context) : VoiceInteractionSession(ctx) {
    override fun onShow(args: Bundle?, showFlags: Int) {
        super.onShow(args, showFlags)
        AssistData.clear()
        Thread { runCatching { val st = Store(context); if (st.token != null) SharedHttp.base.newCall(okhttp3.Request.Builder().url(st.server + "/health").build()).execute().close() } }.start()    // прогрев: соединение с сервером поднимается, пока открывается окно
        runCatching { startAssistantActivity(Intent(context, AssistActivity::class.java)) }
            .onFailure { runCatching { context.startActivity(Intent(context, AssistActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }; hide() }
        // собственное окно сессии (пустое) не должно перекрывать наше окно и «глотать» нажатия
        runCatching { setUiEnabled(false) }
    }
    override fun onHandleScreenshot(screenshot: android.graphics.Bitmap?) {
        if (screenshot == null) return
        runCatching {
            val k = 1400f / maxOf(screenshot.width, screenshot.height)
            val bmp = if (k < 1f) android.graphics.Bitmap.createScaledBitmap(screenshot, (screenshot.width * k).toInt(), (screenshot.height * k).toInt(), true) else screenshot
            val f = java.io.File(java.io.File(context.cacheDir, "cam").also { it.mkdirs() }, "screen_${System.currentTimeMillis()}.jpg")
            f.outputStream().use { bmp.compress(android.graphics.Bitmap.CompressFormat.JPEG, 80, it) }
            AssistData.shot = f
        }
    }
    override fun onHandleAssist(state: AssistState) {
        runCatching {
            val st = state.assistStructure ?: return
            val sb = StringBuilder()
            fun walk(n: android.app.assist.AssistStructure.ViewNode, d: Int) {
                if (sb.length > 2500 || d > 30) return
                n.text?.toString()?.takeIf { it.isNotBlank() }?.let { sb.append(it.take(300)).append('\n') }
                for (i in 0 until n.childCount) walk(n.getChildAt(i), d + 1)
            }
            for (i in 0 until st.windowNodeCount) walk(st.getWindowNodeAt(i).rootViewNode, 0)
            AssistData.text = sb.toString().trim()
        }
    }
    override fun onTaskFinished(intent: Intent?, taskId: Int) { hide() }
}

/** Окно помощника = обычный голосовой звонок прямо поверх текущего экрана: приложение не открывается. Экран смотрим только по просьбе. */
class AssistActivity : ComponentActivity() {
    private val vm: AppVM by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        AssistFlag.on = true                      // до создания VM: не открывать последний чат
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val st = Store(this)
        setContent {
            OpenAgentTheme(st.dynamicColor, 1f, st.amoled) {
                androidx.compose.runtime.CompositionLocalProvider(LocalVM provides vm) {
                    AssistCall(vm, onClose = { vm.stopVoice(); finish() }, openApp = {
                        startActivity(Intent(this@AssistActivity, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); finish()
                    })
                }
            }
        }
    }
    override fun onDestroy() { if (!isChangingConfigurations) vm.stopVoice(); super.onDestroy() }
}

@Composable
private fun AssistCall(vm: AppVM, onClose: () -> Unit, openApp: () -> Unit) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    var micOk by remember { mutableStateOf(androidx.core.content.ContextCompat.checkSelfPermission(ctx, android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED) }
    val perm = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) { micOk = it }
    LaunchedEffect(Unit) { if (!micOk) perm.launch(android.Manifest.permission.RECORD_AUDIO) }
    val ready = !vm.booting && vm.user != null && micOk
    LaunchedEffect(ready) { if (ready) { vm.voiceMuted = false; vm.newChat("chat"); vm.startVoice() } }
    val view = androidx.compose.ui.platform.LocalView.current
    DisposableEffect(Unit) { view.keepScreenOn = true; onDispose { view.keepScreenOn = false } }

    val state = vm.voiceState
    val pseudo = remember { androidx.compose.animation.core.Animatable(0f) }
    LaunchedEffect(state) {
        while (state == VoiceState.Speaking) { pseudo.animateTo(0.25f + kotlin.random.Random.nextFloat() * 0.55f, androidx.compose.animation.core.tween(200)) }
        pseudo.snapTo(0f)
    }
    val level = if (state == VoiceState.Listening) vm.voiceLevel else pseudo.value
    SideEffect { FxLevel.level = if (state == VoiceState.Listening || state == VoiceState.Speaking) level else 0f }
    DisposableEffect(Unit) { onDispose { FxLevel.level = 0f } }
    val orb = when (state) { VoiceState.Listening -> OrbState.Listening; VoiceState.Thinking -> OrbState.Thinking; VoiceState.Speaking -> OrbState.Speaking; else -> OrbState.Idle }
    val label = when { vm.booting -> "Подключаюсь…"; vm.user == null -> "Войдите в приложение"; !micOk -> "Нужен доступ к микрофону"; vm.voiceMuted -> "Микрофон выключен"
        state == VoiceState.Listening -> "Слушаю"; state == VoiceState.Thinking -> "Думаю"; state == VoiceState.Speaking -> "Говорю"; else -> "Подключаюсь…" }

    Box(Modifier.fillMaxSize()) {
        // затемнение — отдельный слой под панелью: тап мимо панели закрывает окно, нажатия внутри панели идут кнопкам
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent, Color.Black.copy(alpha = 0.7f))))
            .clickable(indication = null, interactionSource = remember { MutableInteractionSource() }) { onClose() })
        Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().navigationBarsPadding().imePadding().padding(12.dp).clip(RoundedCornerShape(38.dp))
            .pointerInput(Unit) { detectTapGestures { } }) {
            Box(Modifier.matchParentSize()) { Backdrop() }
            Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 18.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(Modifier.size(120.dp).clickable(indication = null, interactionSource = remember { MutableInteractionSource() }) { vm.voiceInterrupt() }, contentAlignment = Alignment.Center) {
                    val pulse by androidx.compose.animation.core.animateFloatAsState(1f + 0.16f * level, androidx.compose.animation.core.tween(90), label = "pulse")
                    SaturnMark(52.dp, modifier = Modifier.graphicsLayer { scaleX = pulse; scaleY = pulse }, alpha = 0.95f)
                }
                Text(label, color = C.text, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
                if (vm.user == null && !vm.booting) {
                    Box(Modifier.clip(RoundedCornerShape(24.dp)).background(C.accent).clickable { openApp() }.padding(horizontal = 22.dp, vertical = 12.dp)) { Text("Открыть OpenAgent", color = C.onAccent, fontSize = 16.sp, fontWeight = FontWeight.Medium) }
                }
                if (vm.voiceCaption.isNotBlank()) Text("«${vm.voiceCaption}»", color = C.dim, fontSize = 14.sp, textAlign = TextAlign.Center, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                if (vm.voiceReply.isNotBlank()) {
                    val scroll = rememberScrollState()
                    LaunchedEffect(vm.voiceReply) { scroll.animateScrollTo(scroll.maxValue) }
                    Box(Modifier.fillMaxWidth().heightIn(max = 150.dp)) {
                        Text(vm.voiceReply, color = C.text, fontSize = 16.sp, lineHeight = 22.sp, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().verticalScroll(scroll))
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(18.dp), verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 6.dp, bottom = 4.dp)) {
                    if (state == VoiceState.Speaking || state == VoiceState.Thinking)
                        RoundButton(Icons.Outlined.PanTool, "Перебить", { vm.voiceInterrupt() }, size = 60.dp, container = C.container, content = C.onContainer, iconSize = 26.dp, strong = true)
                    RoundButton(if (vm.voiceMuted) Icons.Outlined.MicOff else Icons.Outlined.Mic, "Микрофон", { vm.toggleMute() }, size = 60.dp, container = if (vm.voiceMuted) C.danger else C.container, content = if (vm.voiceMuted) Color.Black else C.onContainer, iconSize = 26.dp, strong = true)
                    RoundButton(Icons.Outlined.Close, "Завершить", onClose, size = 60.dp, container = C.danger, content = Color.Black, iconSize = 28.dp, strong = true)
                }
                // текстовое поле: можно написать вместо того, чтобы говорить
                var typed by remember { mutableStateOf("") }
                fun sendTyped() { if (typed.isNotBlank()) { vm.voiceSendText(typed); typed = "" } }
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(30.dp)).background(C.surface2.copy(alpha = 0.92f)).padding(start = 20.dp, end = 6.dp, top = 6.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.weight(1f).heightIn(min = 44.dp), contentAlignment = Alignment.CenterStart) {
                        if (typed.isEmpty()) Text("Написать…", color = C.dim, fontSize = 17.sp)
                        BasicTextField(typed, { typed = it }, textStyle = androidx.compose.ui.text.TextStyle(color = C.text, fontSize = 17.sp), cursorBrush = SolidColor(C.accent), maxLines = 3,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send), keyboardActions = KeyboardActions(onSend = { sendTyped() }),
                            modifier = Modifier.fillMaxWidth().onFocusChanged { if (it.isFocused && !vm.voiceMuted && vm.voiceState == VoiceState.Listening) vm.toggleMute() })
                    }
                    Box(Modifier.size(44.dp).clip(CircleShape).background(if (typed.isNotBlank()) C.accent else C.surface3).clickable(enabled = typed.isNotBlank()) { sendTyped() }, contentAlignment = Alignment.Center) {
                        Icon(Icons.AutoMirrored.Outlined.Send, null, tint = if (typed.isNotBlank()) C.onAccent else C.dim, modifier = Modifier.size(22.dp))
                    }
                }
            }
        }
    }
}
