package openagent.app.com

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.horizontalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import kotlinx.coroutines.launch
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun PageScaffold(title: String, onBack: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize().systemBarsPadding()) {
        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            FilledTonalIconButton(onBack, Modifier.size(48.dp), colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = C.surface2, contentColor = C.text)) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, null) }
            Spacer(Modifier.width(14.dp))
            Text(title, color = C.text, fontSize = 26.sp, fontWeight = FontWeight.SemiBold)
        }
        content()
    }
}

/** Группа настроек: большой скруглённый контейнер. */
@Composable
fun Group(title: String? = null, content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        if (title != null) Text(title, color = C.accent, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 20.dp, bottom = 8.dp))
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(C.surface2).padding(vertical = 8.dp), content = content)
    }
}

@Composable
fun Row3(icon: ImageVector, title: String, subtitle: String? = null, onClick: (() -> Unit)? = null, trailing: @Composable (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier).padding(horizontal = 20.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(44.dp).clip(CircleShape).background(C.container), contentAlignment = Alignment.Center) { Icon(icon, null, tint = C.onContainer, modifier = Modifier.size(24.dp)) }
        Spacer(Modifier.width(16.dp))
        Column(Modifier.weight(1f)) {
            Text(title, color = C.text, fontSize = 17.sp, fontWeight = FontWeight.Medium)
            if (subtitle != null) Text(subtitle, color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(top = 2.dp))
        }
        trailing?.invoke()
    }
}

@Composable
fun SwitchRow(icon: ImageVector, title: String, subtitle: String?, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row3(icon, title, subtitle, onClick = { onChange(!checked) }) {
        Switch(checked, { Haptics.click(); onChange(it) }, colors = SwitchDefaults.colors(checkedThumbColor = C.onAccent, checkedTrackColor = C.accent, uncheckedThumbColor = C.dim, uncheckedTrackColor = C.surface3, uncheckedBorderColor = C.outline))
    }
}

@Composable
fun SliderRow(icon: ImageVector, title: String, valueLabel: String, value: Float, range: ClosedFloatingPointRange<Float>, onChange: (Float) -> Unit) {
    Column(Modifier.padding(horizontal = 20.dp, vertical = 10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(44.dp).clip(CircleShape).background(C.container), contentAlignment = Alignment.Center) { Icon(icon, null, tint = C.onContainer, modifier = Modifier.size(24.dp)) }
            Spacer(Modifier.width(16.dp))
            Text(title, color = C.text, fontSize = 17.sp, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
            Text(valueLabel, color = C.accent, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
        }
        Slider(value, { if ((it * 20).toInt() != (value * 20).toInt()) Haptics.tick(); onChange(it) }, valueRange = range, modifier = Modifier.padding(top = 2.dp),
            colors = SliderDefaults.colors(thumbColor = C.accent, activeTrackColor = C.accent, inactiveTrackColor = C.surface3))
    }
}

@Composable
fun SettingsScreen(vm: AppVM) {
    val ctx = LocalContext.current
    var server by remember { mutableStateOf(vm.store.server) }
    var pat by remember { mutableStateOf("") }
    var voiceSheet by remember { mutableStateOf(false) }
    if (voiceSheet) VoiceSheet(vm) { voiceSheet = false }
    PageScaffold("Настройки", { vm.screen = Screen.Chat }) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
            Group {
                Row3(Icons.Outlined.Person, vm.user?.email.orEmpty(), if (vm.user?.role == "owner") "Владелец · доступ к серверу (shell)" else "Пользователь · без доступа к shell")
            }
            Group("Внешний вид") {
                SwitchRow(Icons.Outlined.DarkMode, "Чёрный AMOLED", "Глубокий чёрный фон вместо серого", vm.amoled, vm::updAmoled)
                SwitchRow(Icons.Outlined.Palette, "Динамические цвета", "Подхватывать цвета обоев (Android 12+)", vm.dynamicColor, vm::updDynamic)
                SliderRow(Icons.Outlined.TextFields, "Размер текста", "${(vm.fontScale * 100).toInt()}%", vm.fontScale, 0.85f..1.3f, vm::updFontScale)
                SwitchRow(Icons.Outlined.Vibration, "Вибро-отклик", "Лёгкая вибрация на кнопках", vm.haptics, vm::updHaptics)
            }
            run {
                val ctx0 = LocalContext.current
                val crash = remember { runCatching { java.io.File(ctx0.filesDir, "crash.txt").takeIf { it.exists() }?.readText() }.getOrNull() }
                if (crash != null) Group("Диагностика") {
                    Row3(Icons.Outlined.BugReport, "Последний сбой приложения", crash.lineSequence().drop(1).firstOrNull().orEmpty().take(90), onClick = { copyToClipboard(ctx0, crash); vm.toast = "Отчёт скопирован — пришлите его разработчику" }) { Icon(Icons.Outlined.ContentCopy, null, tint = C.dim) }
                }
            }
            Group("Автоответчик") {
                val csPerm = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestMultiplePermissions()) { r -> if (r[android.Manifest.permission.READ_PHONE_STATE] == true && r[android.Manifest.permission.ANSWER_PHONE_CALLS] == true) { vm.updCallScreen(true); vm.toast = "Автоответчик включён" } else vm.toast = "Нужны разрешения «телефон» и «принимать вызовы»" }
                SwitchRow(Icons.Outlined.PhoneCallback, "Брать трубку за меня", "Если не отвечаю дольше N секунд — ассистент берёт, говорит что перезвоню, спрашивает что передать и присылает мне. Экспериментально: зависит от телефона", vm.callScreen) { on ->
                    if (!on) vm.updCallScreen(false) else csPerm.launch(arrayOf(android.Manifest.permission.READ_PHONE_STATE, android.Manifest.permission.ANSWER_PHONE_CALLS, android.Manifest.permission.READ_CALL_LOG, android.Manifest.permission.READ_CONTACTS, android.Manifest.permission.RECORD_AUDIO, android.Manifest.permission.POST_NOTIFICATIONS))
                }
                if (vm.callScreen) { Row3(Icons.Outlined.Timer, "Взять трубку через", "${vm.callDelay} с"); Box(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) { Segmented(listOf("10" to "10 с", "15" to "15 с", "20" to "20 с", "30" to "30 с"), vm.callDelay.toString(), { vm.updCallDelay(it.toInt()) }) } }
                Row3(Icons.Outlined.Person, "Мастер знакомства", "Рассказать о себе заново: имя, город, занятия, стиль общения", onClick = { vm.onboarding = true }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
            }
            Group("Данные и подключения") {
                val permLauncher = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestMultiplePermissions()) { r -> vm.toast = if (r.values.all { it }) "Разрешения выданы" else "Часть разрешений не выдана — звонок и SMS будут открываться через системные экраны" }
                Row3(Icons.Outlined.Call, "Разрешения для звонков и сообщений", "Контакты, звонок, SMS, календарь, геолокация — чтобы агент звонил, писал, ставил встречи и искал рядом", onClick = { permLauncher.launch(arrayOf(android.Manifest.permission.READ_CONTACTS, android.Manifest.permission.CALL_PHONE, android.Manifest.permission.SEND_SMS, android.Manifest.permission.READ_CALENDAR, android.Manifest.permission.WRITE_CALENDAR, android.Manifest.permission.ACCESS_FINE_LOCATION, android.Manifest.permission.ACCESS_COARSE_LOCATION)) }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
                Row3(Icons.Outlined.Extension, "Подключения (MCP)", "Внешние сервисы и инструменты для агента", onClick = { vm.screen = Screen.Connections }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
                run { val c0 = LocalContext.current; Row3(Icons.Outlined.Notifications, "Доступ к уведомлениям", if (OaNotifService.enabled(c0)) "Включён: агент может делать сводку «что я пропустил»" else "Выключен — включите OpenAgent в открывшемся списке", onClick = { runCatching { c0.startActivity(android.content.Intent(android.provider.Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)) } }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) } }
                Row3(Icons.Outlined.Key, "Секреты", "Ключи для команд агента — модель их не видит", onClick = { vm.screen = Screen.Secrets }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
                Row3(Icons.Outlined.CloudDownload, "Резервная копия", "Выгрузить чаты, память, заметки и задачи (JSON)", onClick = { vm.exportBackup() }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
            }
            Group("Groq") {
                var gOpen by remember { mutableStateOf(false) }
                Row3(Icons.Outlined.Bolt, "Groq через телефон", if (vm.groqKeyState.isBlank()) "Ключ не задан — Groq выключен. Сервер к Groq не обращается" else if (vm.groq.connected) "✓ Подключён: запросы к Groq идут с вашего телефона" else "Подключаюсь к серверу…", onClick = { gOpen = true }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
                if (gOpen) {
                    var key by remember { mutableStateOf(vm.groqKeyState) }
                    var res by remember { mutableStateOf("") }
                    val scope = rememberCoroutineScope()
                    AppDialog("Ключ Groq", { gOpen = false }, "Сохранить", true, { vm.saveGroqKey(key); gOpen = false }) {
                        Text("Ключ хранится только на телефоне. Приложение само отправляет запросы в api.groq.com (сервер в Гонконге к нему не подключается), а сервер получает ответы через приложение. Держите приложение открытым.", color = C.dim, fontSize = 13.sp)
                        Field(key, { key = it; res = "" }, "gsk_…", singleLine = true)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            SoftChip(Icons.Outlined.Check, "Проверить ключ", false) { scope.launch { res = "…"; res = vm.groq.test(key) } }
                            if (key.isNotBlank()) SoftChip(Icons.Outlined.DeleteOutline, "Убрать", false) { key = ""; res = "" }
                        }
                        if (res.isNotBlank()) Text(res, color = if (res.startsWith("✓")) C.ok else C.danger, fontSize = 13.sp)
                    }
                }
            }
            Group("Поиск и Perplexity") {
                var pOpen by remember { mutableStateOf(false) }
                Text("Поиск в интернете", color = C.text, fontSize = 15.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp))
                Box(Modifier.padding(horizontal = 16.dp, vertical = 2.dp)) { Segmented(listOf("auto" to "Авто", "exa" to "Exa", "pplx" to "Perplexity"), vm.searchProvider, vm::updSearchProvider) }
                Text(when (vm.searchProvider) { "exa" -> "Только Exa (ключ на сервере), запасные поисковики при сбое"; "pplx" -> "Поиск Perplexity Search API (ключ в приложении), при сбое — запасной"; else -> "Exa, если есть; иначе Perplexity; иначе бесплатные поисковики" },
                    color = C.dim, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 18.dp, vertical = 6.dp))
                Row3(Icons.Outlined.Search, "Ключ Perplexity", if (vm.pplxKeyState.isBlank()) "Не задан — Perplexity выключен" else if (vm.groq.connected) "✓ Подключён: запросы идут с вашего телефона" else "Подключаюсь к серверу…", onClick = { pOpen = true }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
                if (pOpen) {
                    var key by remember { mutableStateOf(vm.pplxKeyState) }
                    var res by remember { mutableStateOf("") }
                    val scope = rememberCoroutineScope()
                    AppDialog("Ключ Perplexity", { pOpen = false }, "Сохранить", true, { vm.savePplxKey(key); pOpen = false }) {
                        Text("Один ключ даёт и Search API (поиск вместо Exa), и Agent API: в списке моделей появится провайдер «Perplexity Agent» — тогда на вопрос отвечает сам агент Perplexity (поиск, рассуждение, источники). Запросы отправляет ваш телефон; ключ хранится только на нём. Держите приложение открытым.", color = C.dim, fontSize = 13.sp)
                        Field(key, { key = it; res = "" }, "pplx-…", singleLine = true)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            SoftChip(Icons.Outlined.Check, "Проверить ключ", false) { scope.launch { res = "…"; res = vm.groq.testPerplexity(key) } }
                            if (key.isNotBlank()) SoftChip(Icons.Outlined.DeleteOutline, "Убрать", false) { key = ""; res = "" }
                        }
                        if (res.isNotBlank()) Text(res, color = if (res.startsWith("✓")) C.ok else C.danger, fontSize = 13.sp)
                    }
                }
            }
            Group("Система") {
                val ctx1 = LocalContext.current
                var diagOpen by remember { mutableStateOf(false) }
                if (vm.user?.role == "owner") Row3(Icons.Outlined.Speed, "Проверка сервера и скорости", vm.health?.let { if (vm.serverOld) "Сервер НЕ обновлён — запустите ./deploy/deploy.sh" else "Сервер v${it.v} · нажмите, чтобы замерить задержки" } ?: "Версия сервера неизвестна", onClick = { diagOpen = true; vm.runDiag() }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
                if (diagOpen) AppDialog("Сервер и скорость", { diagOpen = false }, "Закрыть", true, { diagOpen = false }) {
                    val d = vm.diag
                    if (vm.diagBusy || d == null) Row(verticalAlignment = Alignment.CenterVertically) { CircularProgressIndicator(Modifier.size(22.dp), color = C.accent, strokeWidth = 2.dp); Spacer(Modifier.width(12.dp)); Text("Замеряю…", color = C.dim) }
                    else {
                        fun line(n: String, t: DiagTiming) = (if (t.error != null) "✗ " else "✓ ") + n + ": " + (if (t.error != null) t.error else "${t.ms} мс" + (t.model?.let { " · $it" } ?: ""))
                        Text("Сервер v${d.v}", color = C.text, fontWeight = FontWeight.SemiBold)
                        Text(line("Ответ ИИ (звонок)", d.llm), color = C.text, fontSize = 14.sp)
                        Text(line("Озвучка, первый звук", d.tts), color = C.text, fontSize = 14.sp)
                        Text(line("Распознавание (подключение)", d.stt), color = C.text, fontSize = 14.sp)
                        Text("Ключи: " + d.keys.entries.joinToString(" ") { (if (it.value) "✓" else "✗") + it.key }, color = C.dim, fontSize = 13.sp)
                        d.hints.forEach { Text("• $it", color = C.accent, fontSize = 13.sp) }
                        if (d.hints.isEmpty()) Text("Всё настроено.", color = C.ok, fontSize = 13.sp)
                    }
                }
                val a11yOn = OaAccessibilityService.instance != null
                Row3(Icons.Outlined.PhoneAndroid, "Управление телефоном", if (a11yOn) "Включено: могу закрывать приложения, переключать Wi-Fi/Bluetooth, читать экран" else "Включите службу доступности OpenAgent — тогда агент сможет закрывать приложения и переключать Wi-Fi/Bluetooth", onClick = {
                    runCatching { ctx1.startActivity(android.content.Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)) }
                }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
                Row3(Icons.Outlined.PowerSettingsNew, "Ассистент по кнопке питания", "Выберите OpenAgent «цифровым помощником» — и долгое нажатие питания вызовет окно поверх любого экрана", onClick = {
                    val i = android.content.Intent(android.provider.Settings.ACTION_VOICE_INPUT_SETTINGS).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                    runCatching { ctx1.startActivity(i) }.onFailure { runCatching { ctx1.startActivity(android.content.Intent(android.provider.Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)) } }
                }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
            }
            Group("Агент") {
                SwitchRow(Icons.Outlined.Bolt, "Deepgram (потоковое)", "Потоковое распознавание речи в звонке и диктовке: текст появляется по мере речи", vm.fastSttOn, vm::updFastStt)
                SwitchRow(Icons.Outlined.GraphicEq, "Точное распознавание", "После фразы перераспознать её целиком файлом (Deepgram) — медленнее на 0,5–1 с; обычно не нужно, потоковое уже точное", vm.accurateStt, vm::updAccurateStt)
                if (vm.voiceStats.isNotBlank()) Row3(Icons.Outlined.Timer, "Скорость последнего ответа голоса", vm.voiceStats)
                run { var t by remember { mutableStateOf(false) }; Row3(Icons.Outlined.Animation, "Проверка показа анимированного SVG", "Эталонный рисунок: покажет, работает ли анимация на этом телефоне", onClick = { t = true }) { Icon(Icons.Outlined.PlayArrow, null, tint = C.dim) }; if (t) SvgPlayer(SVG_SELFTEST, 4f / 3f) { t = false } }
                if (vm.sttEngine.isNotBlank()) Row3(Icons.Outlined.Mic, "Последнее распознавание", vm.sttEngine)
                Row3(Icons.Outlined.Mic, "Язык диктовки", "Распознавание речи")
                Box(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) { Segmented(listOf("auto" to "Авто", "ru" to "RU", "en" to "EN", "uk" to "UK", "de" to "DE"), vm.sttLang, vm::updSttLang) }
                var instrOpen by remember { mutableStateOf(false) }
                LaunchedEffect(Unit) { vm.loadInstructions() }
                Row3(Icons.Outlined.Tune, "Мои инструкции", vm.instructions.ifBlank { "Как отвечать: стиль, язык, роль" }.take(80), onClick = { instrOpen = true }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
                if (instrOpen) {
                    var tx by remember { mutableStateOf(vm.instructions) }
                    AppDialog("Мои инструкции", { instrOpen = false }, "Сохранить", true, { vm.saveInstructions(tx.trim()); instrOpen = false }) {
                        Text("Агент будет следовать им в каждом чате. До 700 символов.", color = C.dim, fontSize = 13.sp)
                        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            listOf("Кратко" to "Отвечай максимально кратко, без вступлений.", "Преподаватель" to "Объясняй как преподаватель: просто, с примерами и проверочным вопросом в конце.", "Только код" to "В программировании отвечай кодом с минимумом пояснений.", "Переводчик" to "Если я пишу не по-русски — переведи на русский и ответь.").forEach { (n, v) -> SoftChip(Icons.Outlined.AutoAwesome, n, tx == v) { tx = v } }
                        }
                        Field(tx, { if (it.length <= 700) tx = it }, "Инструкции", singleLine = false, minLines = 4)
                    }
                }
                var notif by remember { mutableStateOf(vm.store.notifyAuto) }
                SwitchRow(Icons.Outlined.NotificationsActive, "Уведомления об автоматизациях", "Сообщать, когда задача по расписанию выполнена (проверка раз в ~15 мин)", notif) { on -> notif = on; vm.store.notifyAuto = on; UpdatesWorker.schedule(ctx, on) }
                SwitchRow(Icons.Outlined.Lock, "Блокировка приложения", "Запрашивать PIN / отпечаток при входе", vm.appLock) { on ->
                    val km = ctx.getSystemService(android.content.Context.KEYGUARD_SERVICE) as android.app.KeyguardManager
                    if (on && !km.isDeviceSecure) vm.toast = "Сначала установите блокировку экрана на телефоне" else vm.updAppLock(on)
                }
                SwitchRow(Icons.Outlined.Shield, "Спрашивать перед рискованным", "Фоновые процессы, боты, git push, удаление — только после вашего «да»", vm.askRisky, vm::updAskRisky)
            }
            Group("Голос") {
                Row3(Icons.Outlined.RecordVoiceOver, "Голос озвучки", vm.voiceName, onClick = { voiceSheet = true }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
                SwitchRow(Icons.AutoMirrored.Outlined.VolumeUp, "Озвучивать ответы", "Читать вслух каждый ответ агента", vm.autoSpeak, vm::updAutoSpeak)
                SliderRow(Icons.Outlined.Timer, "Пауза до конца фразы", "${"%.1f".format(vm.silenceMs / 1000)} с", vm.silenceMs, 500f..2500f, vm::updSilence)
                SliderRow(Icons.Outlined.Mic, "Чувствительность микрофона", "${((0.3f - vm.micThreshold) / 0.27f * 100).toInt().coerceIn(0, 100)}%", 0.3f - vm.micThreshold, 0.03f..0.27f) { vm.updMicThreshold(0.3f - it) }
            }
            Group("GitHub") {
                val gh = vm.user?.github
                val d = vm.device
                if (gh != null) {
                    Row3(Icons.Outlined.Code, "Привязан: $gh", "Агент использует git и gh с вашим токеном")
                    OutlinedButton({ vm.githubUnlink() }, Modifier.padding(horizontal = 20.dp, vertical = 6.dp).fillMaxWidth().height(52.dp), shape = RoundedCornerShape(26.dp)) { Text("Отвязать", color = C.danger, fontSize = 16.sp) }
                } else if (d != null) {
                    Column(Modifier.padding(20.dp)) {
                        Text("Откройте страницу и введите код:", color = C.dim, fontSize = 15.sp)
                        Text(d.userCode, color = C.text, fontSize = 36.sp, fontWeight = FontWeight.Bold, letterSpacing = 5.sp, modifier = Modifier.padding(vertical = 10.dp).clickable { copyToClipboard(ctx, d.userCode); vm.toast = "Код скопирован" })
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Button({ ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(d.verificationUri)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }, Modifier.height(52.dp), shape = RoundedCornerShape(26.dp),
                                colors = ButtonDefaults.buttonColors(C.accent, C.onAccent)) { Text("Открыть GitHub", fontSize = 16.sp) }
                            TextButton({ vm.githubCancel() }) { Text("Отмена", color = C.dim) }
                        }
                        Text("Ожидаю подтверждения…", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(top = 10.dp))
                    }
                } else {
                    Row3(Icons.Outlined.Code, "Не привязан", "Агент сможет клонировать, коммитить и пушить")
                    if (vm.authConfig.githubDeviceFlow) Box(Modifier.padding(horizontal = 20.dp, vertical = 6.dp)) { PrimaryButton("Войти через GitHub") { vm.githubLink() } }
                    OutlinedTextField(pat, { pat = it }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 6.dp), shape = RoundedCornerShape(28.dp), colors = fieldColors(),
                        placeholder = { Text("Personal access token (ghp_…)", color = C.dim) })
                    FilledTonalButton({ vm.githubToken(pat); pat = "" }, Modifier.padding(horizontal = 20.dp, vertical = 6.dp).fillMaxWidth().height(52.dp), enabled = pat.length > 10, shape = RoundedCornerShape(26.dp),
                        colors = ButtonDefaults.filledTonalButtonColors(containerColor = C.container, contentColor = C.onContainer, disabledContainerColor = C.surface3, disabledContentColor = C.dim)) { Text("Привязать по токену", fontSize = 16.sp) }
                }
            }
            Group("Расход токенов") {
                LaunchedEffect(Unit) { vm.loadUsage() }
                val u = vm.usage
                Row3(Icons.Outlined.Savings, if (u == null) "Загрузка…" else "Сегодня: ${(u.today.prompt + u.today.completion) / 1000.0.coerceAtLeast(1.0)}".let { "Сегодня: ${"%.1f".format((u.today.prompt + u.today.completion) / 1000.0)} тыс." }, if (u == null) null else "За 7 дней: ${"%.1f".format((u.week.prompt + u.week.completion) / 1000.0)} тыс. · запросов сегодня: ${u.today.calls}. Экономия включена всегда: дешёвые модели, короткие промпты, обрезка истории.")
            }
            Group("Данные") {
                Row3(Icons.Outlined.Psychology, "Память агента", "Что он запомнил о вас и проектах", onClick = { vm.screen = Screen.Memory; vm.loadMemories() }) { Icon(Icons.Outlined.ChevronRight, null, tint = C.dim) }
                OutlinedTextField(server, { server = it }, singleLine = true, label = { Text("Адрес сервера") }, modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp), shape = RoundedCornerShape(28.dp), colors = fieldColors())
                AnimatedVisibility(server != vm.store.server) {
                    FilledTonalButton({ vm.setServer(server); vm.toast = "Адрес сохранён" }, Modifier.padding(horizontal = 20.dp, vertical = 6.dp).fillMaxWidth().height(52.dp), shape = RoundedCornerShape(26.dp),
                        colors = ButtonDefaults.filledTonalButtonColors(containerColor = C.container, contentColor = C.onContainer)) { Text("Сохранить адрес", fontSize = 16.sp) }
                }
            }
            Button({ vm.logout() }, Modifier.fillMaxWidth().height(60.dp), shape = RoundedCornerShape(30.dp), colors = ButtonDefaults.buttonColors(containerColor = C.danger.copy(alpha = 0.16f), contentColor = C.danger)) {
                Icon(Icons.AutoMirrored.Outlined.Logout, null); Spacer(Modifier.width(10.dp)); Text("Выйти", fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
            }
            Spacer(Modifier.height(28.dp))
        }
    }
}

@Composable
fun MemoryScreen(vm: AppVM) {
    var add by remember { mutableStateOf("") }
    var confirmClear by remember { mutableStateOf(false) }
    PageScaffold("Память", { vm.screen = Screen.Chat }) {
        Row(Modifier.padding(horizontal = 16.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(add, { add = it }, singleLine = true, modifier = Modifier.weight(1f), shape = RoundedCornerShape(28.dp), colors = fieldColors(), placeholder = { Text("Запомни: …", color = C.dim) })
            Spacer(Modifier.width(10.dp))
            FilledIconButton({ vm.addMemory(add); add = "" }, Modifier.size(56.dp), enabled = add.isNotBlank(),
                colors = IconButtonDefaults.filledIconButtonColors(containerColor = C.accent, contentColor = C.onAccent, disabledContainerColor = C.surface3, disabledContentColor = C.dim)) { Icon(Icons.Outlined.Add, "Добавить") }
        }
        if (vm.memories.isNotEmpty()) Row(Modifier.padding(horizontal = 16.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("${vm.memories.size} записей", color = C.dim, fontSize = 14.sp, modifier = Modifier.weight(1f).padding(start = 8.dp))
            SoftChip(Icons.Outlined.DeleteSweep, "Очистить всё", false) { confirmClear = true }
        }
        if (confirmClear) AppDialog("Очистить всю память?", { confirmClear = false }, "Очистить", true, { vm.clearMemories(); confirmClear = false }) { Text("Агент забудет всё, что запомнил о вас. Это нельзя отменить.", color = C.dim) }
        LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (vm.memories.isEmpty()) item { Text("Пока пусто. Агент сохраняет важное автоматически после разговоров.", color = C.dim, fontSize = 15.sp, modifier = Modifier.padding(8.dp)) }
            items(vm.memories, key = { it.id }) { m ->
                Row(Modifier.fillMaxWidth().animateItem().clip(RoundedCornerShape(24.dp)).background(C.surface2).padding(start = 18.dp, top = 8.dp, bottom = 8.dp, end = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(m.content, color = C.text, fontSize = 16.sp, lineHeight = 22.sp)
                        Text("${m.kind} · ${"%.1f".format(m.importance)}", color = C.accent, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
                    }
                    IconButton({ vm.deleteMemory(m) }, Modifier.size(48.dp)) { Icon(Icons.Outlined.DeleteOutline, null, tint = C.dim) }
                }
            }
        }
    }
}
