package openagent.app.com

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.animation.*
import androidx.compose.animation.core.tween
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.*
import androidx.compose.material3.Text
import androidx.compose.ui.unit.sp
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier

class MainActivity : ComponentActivity() {
    private val vm: AppVM by viewModels()
    private var guardReport by mutableStateOf<String?>(null)

    override fun onStart() { super.onStart(); vm.inForeground = true; vm.onStartedLock(); vm.onAppResume() }
    override fun onStop() { super.onStop(); vm.inForeground = false; vm.onStopped() }
    override fun onNewIntent(intent: android.content.Intent) { super.onNewIntent(intent); handleShare(intent) }
    private fun handleShare(i: android.content.Intent?) {
        if (i == null) return
        when (i.action) {
            "openagent.NEW_CHAT" -> { vm.newChat("chat"); i.action = null; return }
            "openagent.NEW_CODE" -> { vm.newChat("code"); i.action = null; return }
            "openagent.ASK" -> { vm.askShot = i.getStringExtra("shot"); vm.askScreenText = i.getStringExtra("screenText"); vm.askOnStart = i.getStringExtra("text"); i.action = null; return }
            "openagent.VOICE" -> { i.action = null; vm.startVoice(); return }
            "openagent.CAMERA" -> { i.action = null; vm.newChat(vm.mode); vm.cameraRequest = true; return }
        }
        val uris = mutableListOf<android.net.Uri>()
        when (i.action) {
            android.content.Intent.ACTION_SEND -> { @Suppress("DEPRECATION") (i.getParcelableExtra<android.net.Uri>(android.content.Intent.EXTRA_STREAM))?.let { uris.add(it) }; i.getStringExtra(android.content.Intent.EXTRA_TEXT)?.let { vm.pendingText = it } }
            android.content.Intent.ACTION_SEND_MULTIPLE -> @Suppress("DEPRECATION") i.getParcelableArrayListExtra<android.net.Uri>(android.content.Intent.EXTRA_STREAM)?.let { uris.addAll(it) }
            else -> return
        }
        if (vm.user != null) { vm.screen = Screen.Chat; if (uris.isNotEmpty()) vm.attach(uris) } else if (uris.isNotEmpty()) vm.toast = "Войдите, чтобы отправить файлы"
        i.action = null
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prev = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            runCatching { java.io.File(filesDir, "crash.txt").writeText(java.util.Date().toString() + " [" + t.name + "]\n" + android.util.Log.getStackTraceString(e).take(6000)) }
            prev?.uncaughtException(t, e)
        }
        // Защита от «вылета при запуске»: если прошлый запуск не дожил до 5 секунд работы — отключаем необязательные функции и показываем отчёт о сбое
        val guard = getSharedPreferences("guard", MODE_PRIVATE)
        val crashed = guard.getLong("startedAt", 0) > guard.getLong("okAt", 0)
        guard.edit().putLong("startedAt", System.currentTimeMillis()).apply()
        if (crashed) {
            val stt = Store(this)
            stt.clapWake = false; stt.gestureWake = false; stt.callScreen = false; stt.offlineMode = false; stt.gateSessions = false
            runCatching { ClapService.stop(this) }; runCatching { CallScreenService.stop(this) }
            guardReport = runCatching { java.io.File(filesDir, "crash.txt").takeIf { it.exists() }?.readText() }.getOrNull() ?: "Отчёта о сбое нет (сбой произошёл до его записи)."
        }
        enableEdgeToEdge()
        handleShare(intent)
        runCatching { if (vm.user != null || Store(this).token != null) UpdatesWorker.schedule(this, Store(this).notifyAuto) }
        if (!crashed) {
            runCatching { if (Store(this).callScreen) CallScreenService.start(this) }
            runCatching { if (Store(this).clapWake) ClapService.start(this) }
        }
        Haptics.init(this)
        setContent {
            LaunchedEffect(Unit) { kotlinx.coroutines.delay(5000); guard.edit().putLong("okAt", System.currentTimeMillis()).apply() }
            OpenAgentTheme(vm.dynamicColor, vm.fontScale, vm.amoled) {
                androidx.compose.runtime.CompositionLocalProvider(LocalVM provides vm) {
                Box(Modifier.fillMaxSize().background(C.bg)) {
                    Backdrop()
                    guardReport?.let { rep -> AppDialog("Приложение вылетало при запуске", { guardReport = null }, "Скопировать отчёт", true, { copyToClipboard(this@MainActivity, rep); guardReport = null }) { Text("Я отключил хлопок, жест, оффлайн-режим, автоответчик и проверку голосом/лицом — включите их заново в настройках. Отчёт о сбое ниже: скопируйте и пришлите его разработчику.", color = C.dim, fontSize = 13.sp); Text(rep.take(1500), color = C.text, fontSize = 11.sp, fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace) } }
                    LaunchedEffect(vm.askOnStart, vm.user, vm.booting) { val t = vm.askOnStart; if (t != null && vm.user != null && !vm.booting) { vm.askOnStart = null; vm.newChat("chat"); vm.sendWithScreen(t) } }
                    val phase = when { vm.booting -> "boot"; vm.user == null -> "login"; vm.onboarding -> "Onboarding"; else -> vm.screen.name }
                    vm.preview?.let { (u, t) -> SitePreview(vm, u, t) { vm.preview = null } }
                    AnimatedContent(phase, transitionSpec = {
                        val from = initialState; val to = targetState
                        when {
                            to == "Voice" -> (fadeIn(tween(260)) + scaleIn(tween(300, easing = FastOutSlowInEasing), initialScale = 0.9f)) togetherWith fadeOut(tween(160))
                            from == "Voice" -> fadeIn(tween(220)) togetherWith (fadeOut(tween(200)) + scaleOut(tween(260), targetScale = 1.06f))
                            from == "Chat" && to != "boot" && to != "login" -> (slideInHorizontally(tween(320, easing = FastOutSlowInEasing)) { it / 6 } + fadeIn(tween(260))) togetherWith (slideOutHorizontally(tween(320, easing = FastOutSlowInEasing)) { -it / 10 } + fadeOut(tween(180)))
                            to == "Chat" && from != "boot" && from != "login" -> (slideInHorizontally(tween(320, easing = FastOutSlowInEasing)) { -it / 10 } + fadeIn(tween(260))) togetherWith (slideOutHorizontally(tween(320, easing = FastOutSlowInEasing)) { it / 6 } + fadeOut(tween(180)))
                            else -> fadeIn(tween(350)) togetherWith fadeOut(tween(200))
                        }
                    }, label = "root") { p ->
                        when (p) {
                            "boot" -> Box(Modifier.fillMaxSize(), Alignment.Center) { SaturnMark(androidx.compose.ui.unit.Dp(132f)) }
                            "login" -> LoginScreen(vm)
                            "Onboarding" -> OnboardingScreen(vm)
                            "Voice" -> VoiceScreen(vm)
                            "Settings" -> SettingsScreen(vm)
                            "Memory" -> MemoryScreen(vm)
                            "Automations" -> AutomationsScreen(vm)
                            "Skills" -> SkillsScreen(vm)
                            "Files" -> FilesScreen(vm)
                            "Terminal" -> TerminalScreen(vm)
                            "Sites" -> SitesScreen(vm)
                            "Bookmarks" -> BookmarksScreen(vm)
                            "Projects" -> ProjectsScreen(vm)
                            "Prompts" -> PromptsScreen(vm)
                            "Server" -> ServerScreen(vm)
                            "Git" -> GitScreen(vm)
                            "Connections" -> ConnectionsScreen(vm)
                            "Notes" -> NotesScreen(vm)
                            "Tasks" -> TasksScreen(vm)
                            "Secrets" -> SecretsScreen(vm)
                            "Activity" -> ActivityScreen(vm)
                            "Missions" -> MissionsScreen(vm)
                            "Agents" -> AgentsScreen(vm)
                            "Integrations" -> ConnectorsScreen(vm)
                            else -> ChatRoot(vm)
                        }
                    }
                    if (vm.locked && vm.user != null) LockScreen(vm)
                    if (vm.gateOpen && vm.user != null && !vm.locked) BioGate(vm, false)
                    GestureWatcher(vm)
                }
                }
            }
        }
    }
}

@Composable
private fun Orb(size: Int, vm: AppVM) = openagent.app.com.Orb(androidx.compose.ui.unit.Dp(size.toFloat()))
