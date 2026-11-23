package openagent.app.com

import android.app.Application
import androidx.compose.runtime.Composable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onRoot
import androidx.test.core.app.ApplicationProvider
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File

@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w411dp-h891dp-xxhdpi")
class ScreenshotTest {
    @get:Rule val rule = androidx.compose.ui.test.junit4.createAndroidComposeRule<androidx.activity.ComponentActivity>()
    private val out = File(System.getProperty("shots") ?: "/tmp/shots").also { it.mkdirs() }

    private fun vm(): AppVM = AppVM(ApplicationProvider.getApplicationContext<Application>()).also {
        it.booting = false
        it.user = User(1, "goboto57@gmail.com", "Артём", "owner", "octocat")
        it.convs.addAll(listOf(Conv(1, "Сборка APK для проекта", "code", updatedAt = System.currentTimeMillis()), Conv(2, "Новости о Kotlin", "chat", updatedAt = System.currentTimeMillis() - 30 * 3600_000L), Conv(3, "Настройка сервера", "code", running = true, updatedAt = System.currentTimeMillis() - 4 * 86400_000L), Conv(4, "Погода и курсы валют", "chat", updatedAt = System.currentTimeMillis() - 40 * 86400_000L)))
    }

    private fun shot(name: String, dynamic: Boolean = false, content: @Composable () -> Unit) {
        rule.setContent { OpenAgentTheme(dynamic, 1f) { androidx.compose.foundation.layout.Box(androidx.compose.ui.Modifier.fillMaxSizeBg()) { Backdrop(); content() } } }
        rule.mainClock.advanceTimeBy(1500)
        val view = rule.activity.window.decorView
        val w = view.width.takeIf { it > 0 } ?: 1080; val h = view.height.takeIf { it > 0 } ?: 2400
        val bmp = android.graphics.Bitmap.createBitmap(w, h, android.graphics.Bitmap.Config.ARGB_8888)
        android.graphics.Canvas(bmp).also { it.drawColor(android.graphics.Color.BLACK) }.let { view.draw(it) }
        File(out, "$name.png").outputStream().use { bmp.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
    }

    @Test fun login() { val v = vm(); v.user = null; shot("01_login") { LoginScreen(v) } }
    @Test fun emptyChat() { val v = vm(); shot("02_empty_chat") { ChatScreen(v) {} } }
    @Test fun emptyCode() { val v = vm(); v.mode = "code"; shot("03_empty_code") { ChatScreen(v) {} } }
    @Test fun chatConversation() {
        val v = vm(); v.convId = 2; v.running = true; v.partial = "Сейчас посмотрю свежие данные"
        v.messages.addAll(listOf(
            Msg(1, "user", "Какая последняя версия Kotlin и когда вышла?"),
            Msg(2, "assistant", "", toolCalls = listOf(ToolCall("c1", "web_search", "{\"query\":\"latest Kotlin release\"}"))),
            Msg(3, "tool", "Результаты поиска…", toolCallId = "c1", toolName = "web_search"),
            Msg(4, "assistant", "На сегодня актуальна **Kotlin 2.4** — вышла в 2026 году.\n\n- Улучшен K2-компилятор\n- Новые API корутин\n\n```kotlin\nfun main() = println(\"Hello\")\n```"),
            Msg(5, "user", "Спасибо! А что нового в Compose?"),
        ))
        shot("04_chat") { ChatScreen(v) {} }
    }
    @Test fun codeConversation() {
        val v = vm(); v.mode = "code"; v.convId = 1; v.running = true
        v.messages.addAll(listOf(
            Msg(1, "user", "Склонируй репозиторий и собери APK"),
            Msg(2, "assistant", "План: клонирую, собираю debug-APK, отправляю файл.", toolCalls = listOf(ToolCall("c1", "bash", "{\"command\":\"git clone https://github.com/me/app && cd app && ./gradlew assembleDebug\"}"))),
            Msg(3, "tool", "BUILD SUCCESSFUL in 1m 12s\n[exit 0]", toolCallId = "c1", toolName = "bash"),
            Msg(4, "assistant", "", toolCalls = listOf(ToolCall("c2", "send_file", "{\"path\":\"app/build/outputs/apk/debug/app-debug.apk\"}"))),
            Msg(5, "tool", "Файл отправлен", toolCallId = "c2", toolName = "send_file"),
            Msg(6, "assistant", "", attachments = listOf(Attach("f1", "app-debug.apk", "application/vnd.android.package-archive", 18524777))),
            Msg(7, "assistant", "Готово! APK собран и отправлен выше."),
        ))
        v.toolOutput["c9"] = "> Task :app:compileDebugKotlin\n"
        shot("05_code") { ChatScreen(v) {} }
    }
    @Test fun agentCards() {
        val v = vm(); v.mode = "code"; v.convId = 1
        v.messages.addAll(listOf(
            Msg(1, "user", "Разверни проект и запусти тесты"),
            Msg(2, "assistant", "", toolCalls = listOf(ToolCall("t1", "todo_write", "{\"todos\":[{\"text\":\"Клонировать репозиторий\",\"status\":\"done\"},{\"text\":\"Установить зависимости\",\"status\":\"in_progress\"},{\"text\":\"Запустить тесты\",\"status\":\"pending\"}]}"))),
            Msg(3, "tool", "ok", toolCallId = "t1", toolName = "todo_write"),
            Msg(4, "assistant", "", toolCalls = listOf(ToolCall("d1", "delegate", "{\"task\":\"Изучи структуру проекта и найди точки входа\"}"), ToolCall("d2", "grep", "{\"pattern\":\"TODO\"}"))),
            Msg(5, "tool", "Отчёт…", toolCallId = "d1", toolName = "delegate"),
            Msg(6, "tool", "a.kt:3:TODO", toolCallId = "d2", toolName = "grep"),
            Msg(7, "assistant", "", toolCalls = listOf(ToolCall("a1", "ask_user", "{\"question\":\"Какую версию Node использовать?\",\"options\":[\"Node 20 LTS\",\"Node 22\",\"Как в .nvmrc\"]}"))),
        ))
        shot("09_cards") { ChatScreen(v) {} }
    }
    @Test fun automations() { val v = vm(); v.schedules.addAll(listOf(Schedule(1, "Проверка диска", "Проверь свободное место на сервере и сообщи, если меньше 10%", "code", 60, System.currentTimeMillis() + 3600000, true, null, 4), Schedule(2, "Новости Kotlin", "Найди новости Kotlin за сутки", "chat", 1440, null, false, null, 0))); shot("10_automations") { AutomationsScreen(v) } }
    @Test fun skills() { val v = vm(); v.skills.addAll(listOf(Skill(1, "android-apk", "Сборка Android APK на сервере", "x"), Skill(2, "github-pr", "Ветка, коммит и Pull Request", "x"), Skill(3, "server-health", "Диагностика состояния сервера", "x"))); shot("11_skills") { SkillsScreen(v) } }
    @Test fun files() { val v = vm(); v.fsRoot = "/srv/ws/1"; v.fsDir = FsList("/srv/ws/1/code/3/app", "/srv/ws/1/code/3", listOf(FsItem("src", true), FsItem("build", true), FsItem("build.gradle.kts", false, 1840), FsItem("app-debug.apk", false, 18524777), FsItem("notes.md", false, 920), FsItem("logo.png", false, 52000))); shot("12_files") { FilesScreen(v) } }
    @Test fun terminal() { val v = vm(); v.term.addAll(listOf(AppVM.TermLine("uname -a", 1), AppVM.TermLine("Linux srv 6.1.0 #1 SMP x86_64 GNU/Linux", 0), AppVM.TermLine("git status", 1), AppVM.TermLine("On branch main\nnothing to commit, working tree clean", 0), AppVM.TermLine("exit 1", 2))); shot("13_terminal") { TerminalScreen(v) } }
    @Test fun table() {
        val v = vm(); v.convId = 2
        v.messages.addAll(listOf(Msg(1, "user", "Сравни модели"), Msg(2, "assistant", "Вот сравнение:\n\n| Модель | Код | Задачи |\n|---|---|---|\n| GLM-5.3 | 8/8 | **13/14** |\n| Qwen3.8 | 7/8 | 14/14 |\n| DeepSeek Flash | 8/8 | 12/14 |\n\nИтог: `Qwen` лучше для задач.")))
        shot("14_table") { ChatScreen(v) {} }
    }
    @Test fun newCards() {
        val v = vm(); v.convId = 1; v.mode = "code"
        v.messages.addAll(listOf(
            Msg(1, "user", "Сделай сайт для кофейни"),
            Msg(2, "assistant", "", toolCalls = listOf(ToolCall("d1", "deploy_site", "{\"name\":\"coffee\"}"))),
            Msg(3, "tool", "Опубликовано: https://openagents.duckdns.org/s/coffee/ (файлов: 3). Покажи пользователю ссылку.", toolCallId = "d1", toolName = "deploy_site"),
            Msg(4, "assistant", "", toolCalls = listOf(ToolCall("a1", "ask_user", "{\"question\":\"Что добавить на сайт?\",\"type\":\"multi\",\"options\":[\"Меню\",\"Галерея\",\"Форма заказа\"]}"))),
            Msg(5, "tool", "Вопрос показан", toolCallId = "a1", toolName = "ask_user"),
        ))
        shot("15_newcards") { ChatScreen(v) {} }
    }
    @Test fun drawer2() { val v = vm(); v.convId = 1; v.convs[1] = v.convs[1].copy(pinned = true); shot("16_drawer2") { androidx.compose.material3.ModalDrawerSheet(drawerContainerColor = C.bg) { DrawerContent(v) {} } } }
    @Test fun codeRun() {
        val v = vm(); v.convId = 2
        v.messages.addAll(listOf(Msg(1, "user", "Напиши сумму чисел"), Msg(2, "assistant", "Вот код:\n\n```python\nprint(sum(range(10)))\n```\n\nСписок:\n• Первое\n• Второе")))
        shot("17_coderun") { androidx.compose.runtime.CompositionLocalProvider(LocalVM provides v) { ChatScreen(v) {} } }
    }
    @Test fun workGroup() {
        val v = vm(); v.mode = "code"; v.convId = 1
        v.messages.addAll(listOf(
            Msg(1, "user", "Найди новости про Kotlin и сохрани в файл"),
            Msg(2, "assistant", "", toolCalls = listOf(ToolCall("a", "web_search", "{\"query\":\"kotlin news\"}"), ToolCall("b", "web_fetch", "{\"url\":\"https://kotlinlang.org/blog\"}"))),
            Msg(3, "tool", "Результаты:\n1. Kotlin 2.4\n   https://kotlinlang.org/blog\n2. JetBrains\n   https://blog.jetbrains.com/kotlin", toolCallId = "a", toolName = "web_search"),
            Msg(4, "tool", "# Blog https://kotlinlang.org/blog", toolCallId = "b", toolName = "web_fetch"),
            Msg(5, "assistant", "", toolCalls = listOf(ToolCall("c", "write_file", "{\"path\":\"news.md\"}"), ToolCall("d", "bash", "{\"command\":\"cat news.md | head\"}"))),
            Msg(6, "tool", "Записано 420 байт", toolCallId = "c", toolName = "write_file"),
            Msg(7, "tool", "# Новости\n[exit 0]", toolCallId = "d", toolName = "bash"),
            Msg(8, "assistant", "Готово: сохранил **5 новостей** в `news.md`."),
        ))
        shot("18_workgroup") { ChatScreen(v) {} }
    }
    @Test fun server() {
        val v = vm(); v.sys = SysInfo("srv-1", 360000.0, listOf(0.42, 0.55, 0.61), 4, 37, SysMem(16L shl 30, 6L shl 30), SysDisk(250L shl 30, 160L shl 30, 64), listOf(SysProc(1, "node", 12.5, 2.0), SysProc(2, "caddy", 3.1, 0.5), SysProc(3, "java", 48.0, 9.0)), listOf("22", "80", "443", "8787"), listOf(SysService("openagent", "active"), SysService("caddy", "active"), SysService("docker", "inactive")))
        listOf(20, 25, 40, 33, 52, 47, 60, 37).forEach { v.cpuHistory.add(it) }
        shot("19_server") { ServerScreen(v) }
    }
    @Test fun git() {
        val v = vm(); v.gitInfo = GitInfo(true, "/ws/proj", "feature/login", listOf(GitFile("M", "app/Main.kt"), GitFile("A", "app/Login.kt"), GitFile("?", "notes.txt")), listOf(GitCommit("a1b2c3d", "Add login screen", "Артём", "2 hours ago"), GitCommit("9f8e7d6", "Fix crash on start", "Артём", "yesterday")), "https://github.com/me/app", 2, 0, "3 files changed, 40 insertions(+)")
        shot("20_git") { GitScreen(v) }
    }
    @Test fun voiceLong() { val v = vm(); v.voiceState = VoiceState.Listening; v.voiceCaption = "Привет."; v.voiceReply = "Привет, Goboto! Всё на месте: сервис работает, health 200, разрешён email zxcyosp1@gmail.com. Что дальше? Могу открыть приложение, поставить таймер, поискать новости или рассказать подробнее про любую из задач, которые мы делали раньше. Скажите, что нужно, и я сразу займусь. Ещё одно предложение, чтобы текст точно не поместился на экран и пришлось прокручивать область ответа вниз."; shot("06b_voice_long") { VoiceScreen(v) } }
    @Test fun emojiChat() {
        val v = vm(); v.convId = 2
        v.messages.addAll(listOf(Msg(1, "user", "Привет 👋 как дела? ☕"), Msg(2, "assistant", "Отлично 😄 Вот план на день:\n\n- ☀️ утро: зарядка 💪\n- 🍕 обед\n- 🚀 проект готов ✅\n\nЕсли что-то пойдёт не так ⚠️ — дай знать 🙂")))
        shot("06c_emoji") { ChatScreen(v) {} }
    }
    @Test fun voice() { val v = vm(); v.voiceState = VoiceState.Listening; v.voiceLevel = 0.5f; v.voiceCaption = "Какая сегодня погода?"; shot("06_voice") { VoiceScreen(v) } }
    @Test fun settings() { val v = vm(); shot("07_settings") { SettingsScreen(v) } }
    @Test fun drawer() { val v = vm(); v.convId = 1; shot("08_drawer") { androidx.compose.material3.ModalDrawerSheet(drawerContainerColor = C.bg) { DrawerContent(v) {} } } }

    @Test fun drawerNew() { val v = vm(); v.convId = 1; shot("20_drawer_new") { androidx.compose.material3.ModalDrawerSheet(drawerContainerColor = C.bg) { DrawerContent(v) {} } } }
    @Test fun connections() {
        val v = vm()
        v.mcpPresets.addAll(listOf(McpPreset("context7", "Context7", "Свежая документация библиотек", "https://mcp.context7.com/mcp", "none"), McpPreset("github", "GitHub", "Репозитории, issues, PR", "https://api.githubcopilot.com/mcp/", "bearer"), McpPreset("custom", "Свой сервер", "Любой MCP по HTTPS", "", "bearer")))
        v.mcpServers.add(McpServer(1, "DeepWiki", "https://mcp.deepwiki.com/mcp", true))
        shot("21_connections") { ConnectionsScreen(v) }
    }
    @Test fun notes() { val v = vm(); v.notes.addAll(listOf(NoteItem(1, "Идея про приложение", "Сделать виджет и плитку", "Идея: добавить виджет. Действия: нарисовать макет.", "voice", System.currentTimeMillis()), NoteItem(2, "Купить", "молоко, хлеб", null, "text", System.currentTimeMillis()))); shot("22_notes") { NotesScreen(v) } }
    @Test fun tasks() { val v = vm(); v.todos.addAll(listOf(TodoItem(1, "Выкатить сервер"), TodoItem(2, "Проверить виджет"), TodoItem(3, "Купить хлеб", true))); shot("23_tasks") { TasksScreen(v) } }
    @Test fun secrets() { val v = vm(); v.secretNames.addAll(listOf("GITHUB_TOKEN", "SMTP_PASS")); shot("24_secrets") { SecretsScreen(v) } }
    @Test fun activity() { val v = vm(); v.activity.addAll(listOf(ActivityItem(System.currentTimeMillis(), 1, "Такси", "phone", "message · Айгерим · «Буду через 10 минут»", true), ActivityItem(System.currentTimeMillis() - 3600_000, 1, "Сервер", "bash", "systemctl status openagent", false), ActivityItem(System.currentTimeMillis() - 7200_000, 2, "Покупки", "phone", "open_url · https://kaspi.kz/shop/search", false))); shot("26_activity") { ActivityScreen(v) } }
    @Test fun logo() { shot("27_logo") { androidx.compose.foundation.layout.Row(androidx.compose.ui.Modifier.fillMaxSize(), horizontalArrangement = androidx.compose.foundation.layout.Arrangement.SpaceEvenly, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) { AppLogo(androidx.compose.ui.unit.Dp(150f)); SaturnMark(androidx.compose.ui.unit.Dp(90f)) } } }
    @Test fun missions() { val v = vm(); v.missions.addAll(listOf(MissionItem(1, "Найти квартиру до 400 000 ₸ в Бостандыкском районе и присылать новые варианты", "active", "[2026-11-20 10:01] Нашёл 4 свежих объявления, 2 подходят по цене; следующая проверка через час", 60, 3, 0), MissionItem(2, "Выяснить, какой ноутбук взять для монтажа до 600 000 ₸", "blocked", "[2026-11-20 09:30] Нужен выбор: MacBook Air M3 или ASUS Zenbook с OLED?", 240, 2, 0))); shot("28_missions") { MissionsScreen(v) } }
    @Test fun onboarding() { val v = vm(); shot("29_onboarding") { OnboardingScreen(v) } }
}

private fun androidx.compose.ui.Modifier.fillMaxSizeBg() = this.then(androidx.compose.ui.Modifier.fillMaxSize()).then(androidx.compose.ui.Modifier.background(C.bg))
