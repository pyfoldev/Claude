package openagent.app.com

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Matrix
import android.os.SystemClock
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.Executors

/** Передняя камера: кадры уходят в onFrame из фонового потока не чаще fps раз в секунду; pv != null — ещё и превью. Возвращает функцию остановки. */
fun bindFrontCamera(ctx: Context, owner: LifecycleOwner, pv: PreviewView?, fps: Int, onFrame: (Bitmap) -> Unit): () -> Unit {
    val exec = Executors.newSingleThreadExecutor()
    val fut = ProcessCameraProvider.getInstance(ctx)
    var last = 0L
    fut.addListener({
        runCatching {
            val p = fut.get(); p.unbindAll()
            val an = ImageAnalysis.Builder().setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888).build()
            an.setAnalyzer(exec) { px ->
                try {
                    val now = SystemClock.elapsedRealtime()
                    if (now - last >= 1000L / fps) {
                        last = now
                        var b = px.toBitmap(); val rot = px.imageInfo.rotationDegrees
                        if (rot != 0) b = Bitmap.createBitmap(b, 0, 0, b.width, b.height, Matrix().apply { postRotate(rot.toFloat()) }, true)
                        onFrame(b)
                    }
                } catch (_: Throwable) {} finally { px.close() }
            }
            if (pv != null) { val pr = Preview.Builder().build().also { it.setSurfaceProvider(pv.surfaceProvider) }; p.bindToLifecycle(owner, CameraSelector.DEFAULT_FRONT_CAMERA, pr, an) }
            else p.bindToLifecycle(owner, CameraSelector.DEFAULT_FRONT_CAMERA, an)
        }
    }, ContextCompat.getMainExecutor(ctx))
    return { runCatching { fut.get().unbindAll() }; exec.shutdown() }
}

@Composable
fun FrontCamera(modifier: Modifier, fps: Int = 4, onFrame: (Bitmap) -> Unit) {
    val ctx = LocalContext.current; val owner = LocalLifecycleOwner.current
    val view = remember { PreviewView(ctx).apply { scaleType = PreviewView.ScaleType.FILL_CENTER } }
    val cb = rememberUpdatedState(onFrame)
    DisposableEffect(Unit) { val stop = bindFrontCamera(ctx, owner, view, fps) { cb.value(it) }; onDispose { stop() } }
    AndroidView(factory = { view }, modifier = modifier)
}

private fun hasCam(ctx: Context) = ContextCompat.checkSelfPermission(ctx, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
private fun hasMic(ctx: Context) = ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

/** Проверка «это вы»: фон приложения + анимированная иконка (как Face ID). Камера работает скрыто, без превью. lock=true — разблокировка приложения, иначе — старт голосовой сессии. */
@Composable
fun BioGate(vm: AppVM, lock: Boolean) {
    val ctx = LocalContext.current; val scope = rememberCoroutineScope(); val owner = LocalLifecycleOwner.current
    val voice = vm.hasVoice; val face = vm.hasFace
    var method by remember { mutableStateOf(if (face) "face" else "voice") }
    var msg by remember { mutableStateOf("") }; var busy by remember { mutableStateOf(false) }; var level by remember { mutableFloatStateOf(0f) }
    var state by remember { mutableIntStateOf(BIO_WORK) }; var camOk by remember { mutableStateOf(hasCam(ctx)) }; var micOk by remember { mutableStateOf(hasMic(ctx)) }
    val pass = { if (lock) vm.locked = false else vm.gatePassed() }
    val succeed: () -> Unit = { state = BIO_OK; msg = "Готово"; scope.launch { kotlinx.coroutines.delay(550); pass() } }
    val camPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> camOk = ok; if (!ok) msg = "Нужен доступ к камере" }
    val micPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> micOk = ok; if (!ok) msg = "Нужен доступ к микрофону" }
    val cred = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { r -> if (r.resultCode == Activity.RESULT_OK) pass() }
    val km = remember { ctx.getSystemService(Context.KEYGUARD_SERVICE) as android.app.KeyguardManager }
    fun askDevice() {
        if (!km.isDeviceSecure) { msg = "На телефоне нет блокировки экрана"; return }
        @Suppress("DEPRECATION") val i = km.createConfirmDeviceCredentialIntent("OpenAgent", "Подтвердите, что это вы")
        if (i != null) runCatching { cred.launch(i) }
    }
    fun checkVoice() {
        if (busy || state == BIO_OK) return
        if (!micOk) { micPerm.launch(Manifest.permission.RECORD_AUDIO); return }
        busy = true; state = BIO_WORK; msg = "Скажите что-нибудь"
        scope.launch {
            val pcm = VoicePrint.record(5000) { level = it }
            level = 0f
            if (pcm == null) { state = BIO_FAIL; msg = "Не услышал речь — нажмите и повторите"; busy = false; return@launch }
            msg = "Проверяю…"
            val sc = withContext(Dispatchers.Default) { runCatching { VoicePrint.verify(ctx, pcm) }.getOrDefault(-1f) }
            val thr = BioThr.voice(vm.bioStrict)
            if (sc >= thr) succeed() else { state = BIO_FAIL; msg = "Не совпало (%.0f%%, нужно %.0f%%) — нажмите и повторите".format(sc * 100, thr * 100); Haptics.heavy() }
            busy = false
        }
    }
    LaunchedEffect(method, micOk) {
        state = BIO_WORK; msg = ""
        if (method == "voice") { if (micOk) checkVoice() else micPerm.launch(Manifest.permission.RECORD_AUDIO) }
        else if (!camOk) camPerm.launch(Manifest.permission.CAMERA)
    }
    if (method == "face" && camOk) DisposableEffect(Unit) {
        var streak = 0; var fails = 0; var done = false
        val stop = bindFrontCamera(ctx, owner, null, 4) { bmp ->
            if (done) return@bindFrontCamera
            val sc = runCatching { FacePrint.verify(ctx, bmp) }.getOrNull()
            val thr = BioThr.face(vm.bioStrict)
            if (sc == null) { streak = 0; state = BIO_WORK; msg = if (BioDiag.status.isBlank() || BioDiag.status.startsWith("лиц", true)) "Посмотрите в камеру" else BioDiag.status }
            else if (sc >= thr) { streak++; if (streak >= 2) { done = true; android.os.Handler(android.os.Looper.getMainLooper()).post { succeed() } } }
            else { streak = 0; fails++; state = if (fails >= 3) BIO_FAIL else BIO_WORK; msg = if (fails >= 3) "Не узнаю (%.0f%%, нужно %.0f%%)".format(sc * 100, thr * 100) else "Смотрите прямо в камеру" }
        }
        onDispose { stop() }
    }
    Column(Modifier.fillMaxSize().background(C.bg).systemBarsPadding().pointerInput(Unit) { detectTapGestures { } }.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Spacer(Modifier.weight(1f))
        if (method == "face") FaceIdIcon(state, 148.dp)
        else Box(Modifier.pointerInput(Unit) { detectTapGestures { checkVoice() } }) { VoiceIdIcon(level, state, listening = busy, size = 160.dp) }
        Spacer(Modifier.height(28.dp))
        Text(if (lock) "Разблокировать" else "Это вы?", color = C.text, fontSize = 20.sp, fontWeight = FontWeight.Medium)
        Text(msg.ifBlank { if (method == "face") "Посмотрите в камеру" else "Скажите что-нибудь" }, color = C.dim, fontSize = 14.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 8.dp).heightIn(min = 40.dp))
        Spacer(Modifier.weight(1f))
        if (voice && face) TextButton({ method = if (method == "face") "voice" else "face" }) { Text(if (method == "face") "Проверить голосом" else "Проверить лицом", color = C.onContainer) }
        TextButton({ askDevice() }) { Text("Пароль телефона", color = C.dim) }
        if (!lock) TextButton({ vm.gateCancel() }) { Text("Отмена", color = C.dim) }
    }
}

/** Запись голоса: три фразы, запись стартует сама. */
@Composable
fun VoiceEnrollDialog(vm: AppVM, onClose: () -> Unit) {
    val ctx = LocalContext.current
    val phrases = listOf("Привет, ассистент, это мой голос, и я хочу, чтобы он открывал приложение", "Сегодня хорошая погода, поэтому я, пожалуй, схожу погулять в парк", "Запомни мой голос: только я могу начинать разговор с тобой")
    val embs = remember { mutableStateListOf<FloatArray>() }
    var msg by remember { mutableStateOf("") }; var level by remember { mutableFloatStateOf(0f) }; var state by remember { mutableIntStateOf(BIO_WORK) }
    var micOk by remember { mutableStateOf(hasMic(ctx)) }; var attempt by remember { mutableIntStateOf(0) }; var listening by remember { mutableStateOf(false) }
    val perm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> micOk = ok; if (!ok) msg = "Нужен доступ к микрофону" }
    LaunchedEffect(Unit) { if (!micOk) perm.launch(Manifest.permission.RECORD_AUDIO) }
    LaunchedEffect(micOk, attempt) {
        if (!micOk || embs.size >= 3) return@LaunchedEffect
        state = BIO_WORK; msg = ""; listening = true
        val pcm = VoicePrint.record(7000) { level = it }
        listening = false; level = 0f
        if (pcm == null) { state = BIO_FAIL; msg = "Не услышал — нажмите на иконку и повторите"; return@LaunchedEffect }
        val e = withContext(Dispatchers.Default) { runCatching { VoicePrint.embed(ctx, pcm) }.getOrNull() }
        if (e == null) { state = BIO_FAIL; msg = "Не получилось обработать запись"; return@LaunchedEffect }
        embs.add(e)
        if (embs.size >= 3) {
            val c = centroid(embs.toList()); val worst = embs.minOf { cosine(it, c) }
            if (worst < 0.5f) { state = BIO_FAIL; msg = "Записи слишком разные — начнём заново"; embs.clear(); kotlinx.coroutines.delay(1200); attempt++ }
            else { BioVault.save(ctx, "voice", c); vm.refreshBio(); state = BIO_OK; kotlinx.coroutines.delay(700); vm.toast = "Голос записан"; onClose() }
        } else { state = BIO_OK; kotlinx.coroutines.delay(500); attempt++ }
    }
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Column(Modifier.fillMaxSize().background(C.bg).systemBarsPadding().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Spacer(Modifier.weight(1f))
            Box(Modifier.pointerInput(Unit) { detectTapGestures { if (!listening && embs.size < 3) attempt++ } }) { VoiceIdIcon(level, state, listening, 160.dp) }
            Spacer(Modifier.height(28.dp))
            if (embs.size < 3) Text("«${phrases[embs.size]}»", color = C.text, fontSize = 18.sp, lineHeight = 26.sp, textAlign = TextAlign.Center)
            Text(msg.ifBlank { "Прочитайте вслух" }, color = C.dim, fontSize = 14.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 12.dp))
            Spacer(Modifier.height(20.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { repeat(3) { i -> Box(Modifier.size(8.dp).clip(androidx.compose.foundation.shape.CircleShape).background(if (i < embs.size) C.onContainer else C.container)) } }
            Spacer(Modifier.weight(1f))
            TextButton(onClose) { Text("Отмена", color = C.dim) }
        }
    }
}

/** Запись лица: камера работает скрыто, на экране только иконка и точки прогресса. */
@Composable
fun FaceEnrollDialog(vm: AppVM, onClose: () -> Unit) {
    val ctx = LocalContext.current; val owner = LocalLifecycleOwner.current
    val embs = remember { mutableStateListOf<FloatArray>() }
    var msg by remember { mutableStateOf("Смотрите в камеру и слегка поворачивайте голову") }
    var state by remember { mutableIntStateOf(BIO_WORK) }; var camOk by remember { mutableStateOf(hasCam(ctx)) }
    val perm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> camOk = ok; if (!ok) msg = "Нужен доступ к камере" }
    LaunchedEffect(Unit) { if (!camOk) perm.launch(Manifest.permission.CAMERA) }
    if (camOk) DisposableEffect(Unit) {
        var lastAt = 0L; var done = false
        val stop = bindFrontCamera(ctx, owner, null, 3) { bmp ->
            val now = SystemClock.elapsedRealtime()
            if (done || now - lastAt < 600) return@bindFrontCamera
            val f = runCatching { FacePrint.align(ctx, bmp) }.getOrNull()
            if (f == null) { msg = "Лица не видно — посмотрите в камеру"; return@bindFrontCamera }
            lastAt = now
            runCatching { FacePrint.embed(ctx, f) }.getOrNull()?.let { embs.add(it) }
            if (embs.size >= 6) {
                val c = centroid(embs.toList()); val worst = embs.minOf { cosine(it, c) }
                if (worst < 0.5f) { msg = "Кадры слишком разные — нужен свет получше"; state = BIO_FAIL; embs.clear() }
                else { done = true; BioVault.save(ctx, "face", c); android.os.Handler(android.os.Looper.getMainLooper()).post { vm.refreshBio(); state = BIO_OK; msg = "Лицо записано" } }
            } else { state = BIO_WORK; msg = "Хорошо, ещё немного" }
        }
        onDispose { stop() }
    }
    LaunchedEffect(state) { if (state == BIO_OK) { kotlinx.coroutines.delay(900); vm.toast = "Лицо записано"; onClose() } }
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Column(Modifier.fillMaxSize().background(C.bg).systemBarsPadding().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Spacer(Modifier.weight(1f))
            FaceIdIcon(state, 160.dp)
            Spacer(Modifier.height(28.dp))
            Text(msg, color = C.text, fontSize = 16.sp, textAlign = TextAlign.Center)
            Spacer(Modifier.height(20.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { repeat(6) { i -> Box(Modifier.size(8.dp).clip(androidx.compose.foundation.shape.CircleShape).background(if (i < embs.size || state == BIO_OK) C.onContainer else C.container)) } }
            Spacer(Modifier.weight(1f))
            TextButton(onClose) { Text("Отмена", color = C.dim) }
        }
    }
}

/** Компактные строки «Голос» и «Лицо»: нажатие — записать, если уже записано — перезаписать или удалить. */
@Composable
fun BioEnrollRows(vm: AppVM) {
    var dlg by remember { mutableStateOf("") }; var manage by remember { mutableStateOf("") }
    val app = vm.getApplication<android.app.Application>()
    if (dlg == "voice") VoiceEnrollDialog(vm) { dlg = "" }
    if (dlg == "face") FaceEnrollDialog(vm) { dlg = "" }
    if (manage.isNotEmpty()) androidx.compose.material3.AlertDialog(onDismissRequest = { manage = "" }, containerColor = C.bg,
        title = { Text(if (manage == "voice") "Голос" else "Лицо", color = C.text) },
        confirmButton = { TextButton({ dlg = manage; manage = "" }) { Text("Перезаписать", color = C.onContainer) } },
        dismissButton = { TextButton({ BioVault.clear(app, manage); vm.refreshBio(); manage = "" }) { Text("Удалить", color = C.dim) } })
    Row3(Icons.Outlined.RecordVoiceOver, "Голос", if (vm.hasVoice) "Записан" else "Не записан", onClick = { if (vm.hasVoice) manage = "voice" else dlg = "voice" }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
    Row3(Icons.Outlined.Face, "Лицо", if (vm.hasFace) "Записано" else "Не записано", onClick = { if (vm.hasFace) manage = "face" else dlg = "face" }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
}

/** Единый раздел «Защита и вызов»: голос, лицо, проверка, хлопок, жест. */
@Composable
fun BioSettings(vm: AppVM) {
    val ctx = LocalContext.current
    val camPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (ok) vm.updGestureWake(true) else vm.toast = "Нужен доступ к камере" }
    val micPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (ok) vm.updClapWake(true) else vm.toast = "Нужен доступ к микрофону" }
    BioEnrollRows(vm)
    if (vm.hasVoice || vm.hasFace) {
        SwitchRow(Icons.Outlined.VerifiedUser, "Проверять перед сеансом", null, vm.gateSessions, vm::updGateSessions)
        if (vm.gateSessions) Box(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) { Segmented(listOf("soft" to "Мягко", "normal" to "Обычно", "strict" to "Строго"), vm.bioStrict, vm::updBioStrict) }
    }
    SwitchRow(Icons.Outlined.GraphicEq, "Хлопок ×2", if (vm.clapWake) ClapState.summary() else "Два хлопка — звонок", vm.clapWake) { on ->
        if (on && !hasMic(ctx)) micPerm.launch(Manifest.permission.RECORD_AUDIO) else vm.updClapWake(on)
    }
    if (vm.clapWake) Box(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) { Segmented(listOf("low" to "Строго", "normal" to "Обычно", "high" to "Чутко"), vm.clapSens, vm::updClapSens) }
    SwitchRow(Icons.Outlined.PanTool, "Жест ✌️", if (vm.gestureWake && BioDiag.status.isNotBlank()) BioDiag.status else "Покажите в камеру — звонок", vm.gestureWake) { on ->
        if (on && !hasCam(ctx)) camPerm.launch(Manifest.permission.CAMERA) else vm.updGestureWake(on)
    }
}

/** Слушает жест ✌️ фронтальной камерой, пока приложение на экране и не идёт звонок/проверка. */
@Composable
fun GestureWatcher(vm: AppVM) {
    val ctx = LocalContext.current; val owner = LocalLifecycleOwner.current
    val active = vm.gestureWake && vm.user != null && !vm.locked && !vm.gateOpen && vm.screen != Screen.Voice && !vm.cameraOn && !vm.booting && !vm.onboarding && hasCam(ctx)
    DisposableEffect(active) {
        if (!active) return@DisposableEffect onDispose {}
        var streak = 0; var cooldown = 0L
        val stop = bindFrontCamera(ctx, owner, null, 6) { bmp ->
            val now = SystemClock.elapsedRealtime()
            val v = now > cooldown && runCatching { GestureRec.isVictory(ctx, bmp) }.getOrDefault(false)
            streak = if (v) streak + 1 else 0
            if (streak >= 3) { streak = 0; cooldown = now + 6000; android.os.Handler(android.os.Looper.getMainLooper()).post { vm.voiceMuted = false; vm.startVoice() } }
        }
        onDispose { stop() }
    }
}
