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

/** Проверка «это вы»: по голосу или лицу (что записано), запасной вход — пароль/отпечаток телефона. lock=true — разблокировка приложения, иначе — старт голосовой сессии. */
@Composable
fun BioGate(vm: AppVM, lock: Boolean) {
    val ctx = LocalContext.current; val scope = rememberCoroutineScope()
    val voice = vm.hasVoice; val face = vm.hasFace
    var method by remember { mutableStateOf(if (voice) "voice" else "face") }
    var msg by remember { mutableStateOf("") }; var busy by remember { mutableStateOf(false) }; var level by remember { mutableFloatStateOf(0f) }
    var streak by remember { mutableIntStateOf(0) }
    val pass = { if (lock) vm.locked = false else vm.gatePassed() }
    val perm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (!ok) msg = "Нужен доступ" else msg = "" }
    val cred = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { r -> if (r.resultCode == Activity.RESULT_OK) pass() }
    val km = remember { ctx.getSystemService(Context.KEYGUARD_SERVICE) as android.app.KeyguardManager }
    fun askDevice() {
        if (!km.isDeviceSecure) { msg = "На телефоне не установлена блокировка экрана"; return }
        @Suppress("DEPRECATION") val i = km.createConfirmDeviceCredentialIntent("OpenAgent", "Подтвердите, что это вы")
        if (i != null) runCatching { cred.launch(i) }
    }
    fun checkVoice() {
        if (busy) return
        if (!hasMic(ctx)) { perm.launch(Manifest.permission.RECORD_AUDIO); return }
        busy = true; msg = "Говорите…"
        scope.launch {
            val pcm = VoicePrint.record(3500) { level = it }
            if (pcm == null) { msg = "Не слышу речи — скажите любую фразу громче"; busy = false; level = 0f; return@launch }
            msg = "Проверяю…"
            val sc = withContext(Dispatchers.Default) { runCatching { VoicePrint.verify(ctx, pcm) }.getOrDefault(-1f) }
            val thr = BioThr.voice(vm.bioStrict)
            if (sc >= thr) pass() else { msg = "Голос не подошёл (%.2f из нужных %.2f). Попробуйте ещё раз ближе к микрофону".format(sc, thr); Haptics.heavy() }
            busy = false; level = 0f
        }
    }
    LaunchedEffect(method) { streak = 0; msg = ""; if (method == "face" && !hasCam(ctx)) perm.launch(Manifest.permission.CAMERA) }
    Column(Modifier.fillMaxSize().background(C.bg).systemBarsPadding().pointerInput(Unit) { detectTapGestures { } }.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Spacer(Modifier.height(12.dp)); AppLogo(72.dp); Spacer(Modifier.height(14.dp))
        Text(if (lock) "OpenAgent заблокирован" else "Подтвердите, что это вы", color = C.text, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Text(if (lock) "Разблокируйте голосом или лицом" else "Голосовой сеанс начнётся после проверки", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp, bottom = 16.dp))
        if (voice && face) Segmented(listOf("voice" to "Голос", "face" to "Лицо"), method, { method = it })
        Spacer(Modifier.height(16.dp))
        Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
            if (method == "face") {
                if (hasCam(ctx)) {
                    Box(Modifier.fillMaxWidth().aspectRatio(0.8f).clip(RoundedCornerShape(28.dp))) {
                        FrontCamera(Modifier.fillMaxSize(), fps = 3) { bmp ->
                            val sc = runCatching { FacePrint.verify(ctx, bmp) }.getOrNull()
                            if (sc == null) { streak = 0; msg = "Лица не видно — смотрите в камеру" }
                            else if (sc >= BioThr.face(vm.bioStrict)) { streak++; msg = "Узнаю…"; if (streak >= 2) { streak = -99; pass() } }
                            else { streak = 0; msg = "Не вы (%.2f из нужных %.2f)".format(sc, BioThr.face(vm.bioStrict)) }
                        }
                    }
                } else PillButton("Разрешить камеру", { perm.launch(Manifest.permission.CAMERA) }, icon = Icons.Outlined.Videocam)
            } else {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(Modifier.size((110 + 50 * level).dp).clip(androidx.compose.foundation.shape.CircleShape).background(C.container), contentAlignment = Alignment.Center) { androidx.compose.material3.Icon(Icons.Outlined.Mic, null, tint = C.onContainer, modifier = Modifier.size(44.dp)) }
                    Spacer(Modifier.height(24.dp))
                    PillButton(if (busy) "Слушаю…" else "Сказать фразу", { checkVoice() }, enabled = !busy, icon = Icons.Outlined.Mic)
                }
            }
        }
        if (msg.isNotBlank()) Text(msg, color = C.dim, fontSize = 14.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(vertical = 10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextButton({ askDevice() }) { Text("Пароль / отпечаток телефона", color = C.onContainer) }
            if (!lock) TextButton({ vm.gateCancel() }) { Text("Отмена", color = C.dim) }
        }
    }
}

/** Запись голоса: три фразы по ~4 с → средний вектор говорящего. */
@Composable
fun VoiceEnrollDialog(vm: AppVM, onClose: () -> Unit) {
    val ctx = LocalContext.current; val scope = rememberCoroutineScope()
    val phrases = listOf("Привет, ассистент, это мой голос, и я хочу, чтобы он открывал приложение", "Сегодня хорошая погода, поэтому я, пожалуй, схожу погулять в парк", "Запомни мой голос: только я могу начинать разговор с тобой")
    val embs = remember { mutableStateListOf<FloatArray>() }
    var busy by remember { mutableStateOf(false) }; var msg by remember { mutableStateOf("") }; var level by remember { mutableFloatStateOf(0f) }
    val perm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (!ok) msg = "Нужен доступ к микрофону" }
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Column(Modifier.fillMaxSize().background(C.bg).systemBarsPadding().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text("Запись голоса", color = C.text, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Text("Фраза ${minOf(embs.size + 1, 3)} из 3 — скажите вслух, спокойно, как обычно", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp))
            Spacer(Modifier.height(28.dp))
            Text("«${phrases[minOf(embs.size, 2)]}»", color = C.text, fontSize = 20.sp, lineHeight = 28.sp, textAlign = TextAlign.Center)
            Spacer(Modifier.weight(1f))
            Box(Modifier.size((110 + 50 * level).dp).clip(androidx.compose.foundation.shape.CircleShape).background(C.container), contentAlignment = Alignment.Center) { androidx.compose.material3.Icon(Icons.Outlined.Mic, null, tint = C.onContainer, modifier = Modifier.size(44.dp)) }
            if (msg.isNotBlank()) Text(msg, color = C.dim, fontSize = 14.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 16.dp))
            Spacer(Modifier.weight(1f))
            PillButton(if (busy) "Слушаю…" else "Записать", {
                if (!hasMic(ctx)) { perm.launch(Manifest.permission.RECORD_AUDIO); return@PillButton }
                busy = true; msg = ""
                scope.launch {
                    val pcm = VoicePrint.record(5000) { level = it }
                    if (pcm == null) { msg = "Не слышу речи — повторите громче"; busy = false; level = 0f; return@launch }
                    val e = withContext(Dispatchers.Default) { runCatching { VoicePrint.embed(ctx, pcm) }.getOrNull() }
                    if (e == null) msg = "Не получилось обработать запись" else {
                        embs.add(e)
                        if (embs.size >= 3) {
                            val c = centroid(embs.toList()); val worst = embs.minOf { cosine(it, c) }
                            if (worst < 0.6f) { msg = "Записи сильно отличаются (%.2f) — давайте заново".format(worst); embs.clear() }
                            else { BioVault.save(ctx, "voice", c); vm.refreshBio(); vm.toast = "Голос записан"; onClose() }
                        }
                    }
                    busy = false; level = 0f
                }
            }, enabled = !busy, icon = Icons.Outlined.Mic)
            TextButton(onClose) { Text("Отмена", color = C.dim) }
        }
    }
}

/** Запись лица: несколько кадров с камеры → средний вектор. */
@Composable
fun FaceEnrollDialog(vm: AppVM, onClose: () -> Unit) {
    val ctx = LocalContext.current
    val embs = remember { mutableStateListOf<FloatArray>() }
    var msg by remember { mutableStateOf("Смотрите в камеру, не торопясь поворачивайте голову чуть влево и вправо") }
    var lastAt by remember { mutableLongStateOf(0L) }
    val perm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (!ok) msg = "Нужен доступ к камере" }
    LaunchedEffect(Unit) { if (!hasCam(ctx)) perm.launch(Manifest.permission.CAMERA) }
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Column(Modifier.fillMaxSize().background(C.bg).systemBarsPadding().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text("Запись лица", color = C.text, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Text("Снято ${embs.size} из 6 кадров", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(top = 6.dp, bottom = 16.dp))
            if (hasCam(ctx)) Box(Modifier.weight(1f).fillMaxWidth().clip(RoundedCornerShape(28.dp))) {
                FrontCamera(Modifier.fillMaxSize(), fps = 3) { bmp ->
                    val now = SystemClock.elapsedRealtime()
                    if (embs.size < 6 && now - lastAt > 600) {
                        val f = runCatching { FacePrint.align(ctx, bmp) }.getOrNull()
                        if (f == null) msg = "Лица не видно или оно далеко — приблизьтесь и смотрите в камеру" else {
                            lastAt = now
                            runCatching { FacePrint.embed(ctx, f) }.getOrNull()?.let { embs.add(it) }
                            if (embs.size >= 6) {
                                val c = centroid(embs.toList()); val worst = embs.minOf { cosine(it, c) }
                                if (worst < 0.55f) { msg = "Кадры сильно отличаются — попробуйте при хорошем свете"; embs.clear() }
                                else { BioVault.save(ctx, "face", c); vm.refreshBio(); vm.toast = "Лицо записано"; onClose() }
                            } else msg = "Хорошо, ещё немного…"
                        }
                    }
                }
            } else Box(Modifier.weight(1f), contentAlignment = Alignment.Center) { PillButton("Разрешить камеру", { perm.launch(Manifest.permission.CAMERA) }, icon = Icons.Outlined.Videocam) }
            Text(msg, color = C.dim, fontSize = 14.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(vertical = 14.dp))
            TextButton(onClose) { Text("Отмена", color = C.dim) }
        }
    }
}

/** Кнопки записи голоса и лица — для настроек и мастера знакомства. */
@Composable
fun BioEnrollRows(vm: AppVM) {
    var dlg by remember { mutableStateOf("") }
    if (dlg == "voice") VoiceEnrollDialog(vm) { dlg = "" }
    if (dlg == "face") FaceEnrollDialog(vm) { dlg = "" }
    Row3(Icons.Outlined.RecordVoiceOver, "Мой голос", if (vm.hasVoice) "Записан (ReDimNet2)" else "Не записан", trailing = {
        Row { TextButton({ dlg = "voice" }) { Text(if (vm.hasVoice) "Перезаписать" else "Записать", color = C.onContainer) }
            if (vm.hasVoice) TextButton({ BioVault.clear(vm.getApplication<android.app.Application>(), "voice"); vm.refreshBio() }) { Text("Удалить", color = C.dim) } }
    })
    Row3(Icons.Outlined.Face, "Моё лицо", if (vm.hasFace) "Записано (MobileFaceNet)" else "Не записано", trailing = {
        Row { TextButton({ dlg = "face" }) { Text(if (vm.hasFace) "Перезаписать" else "Записать", color = C.onContainer) }
            if (vm.hasFace) TextButton({ BioVault.clear(vm.getApplication<android.app.Application>(), "face"); vm.refreshBio() }) { Text("Удалить", color = C.dim) } }
    })
}

@Composable
fun BioSettings(vm: AppVM) {
    val ctx = LocalContext.current
    val camPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (ok) vm.updGestureWake(true) else vm.toast = "Нужен доступ к камере" }
    BioEnrollRows(vm)
    if (vm.hasVoice || vm.hasFace) {
        SwitchRow(Icons.Outlined.VerifiedUser, "Сеансы только по моему голосу/лицу", "Перед голосовым звонком (в том числе вызванным хлопком или жестом) — проверка, что это вы. Действует 10 минут", vm.gateSessions, vm::updGateSessions)
        Text("Строгость проверки", color = C.dim, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 18.dp, vertical = 4.dp))
        Box(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) { Segmented(listOf("soft" to "Мягко", "normal" to "Обычно", "strict" to "Строго"), vm.bioStrict, vm::updBioStrict) }
        Text("Голос и лицо записываются в виде чисел-отпечатков (не записей и не фото), хранятся на телефоне под ключом Keystore. Это удобная блокировка, а не защита от целенаправленного взлома: запись голоса или фото владельца её обманут. Запасной вход — пароль телефона.", color = C.dim, fontSize = 12.sp, lineHeight = 16.sp, modifier = Modifier.padding(horizontal = 18.dp, vertical = 4.dp))
    }
    SwitchRow(Icons.Outlined.PanTool, "Включение жестом ✌️", "Показали «викторию» в камеру — открывается голосовой звонок. Работает, пока приложение открыто на экране (Android не даёт камере работать в фоне)", vm.gestureWake) { on ->
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
            if (streak >= 4) { streak = 0; cooldown = now + 6000; android.os.Handler(android.os.Looper.getMainLooper()).post { vm.voiceMuted = false; vm.startVoice() } }
        }
        onDispose { stop() }
    }
}
