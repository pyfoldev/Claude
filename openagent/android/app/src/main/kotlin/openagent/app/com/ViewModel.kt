package openagent.app.com

import android.app.Application
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import androidx.compose.runtime.*
import androidx.core.content.FileProvider
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.serialization.encodeToString
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.RequestBody.Companion.asRequestBody
import okio.BufferedSink
import okio.buffer
import okio.source
import java.io.File

/** Окно помощника поднимает свой экземпляр VM: ему не нужно открывать последний чат. */
object AssistFlag { @Volatile var on = false }
enum class Screen { Chat, Voice, Settings, Memory, Automations, Skills, Files, Terminal, Sites, Bookmarks, Server, Git, Projects, Prompts, Connections, Notes, Tasks, Secrets, Activity, Missions }
enum class VoiceState { Idle, Listening, Thinking, Speaking }

/** runCatching, который не глотает отмену корутины (иначе остановка звонка не останавливает прослушивание). */
inline fun <T> tryC(block: () -> T): Result<T> = try { Result.success(block()) } catch (e: CancellationException) { throw e } catch (e: Throwable) { Result.failure(e) }

class AppVM(app: Application) : AndroidViewModel(app) {
    val store = Store(app)
    // ---- проекты / промпты / экспорт ----
    val projects = mutableStateListOf<Project>()
    var currentProject by mutableStateOf<Int?>(null)
    var newChatProject by mutableStateOf<Int?>(null)
    fun loadProjects() = viewModelScope.launch { runCatching { api.projects() }.onSuccess { projects.clear(); projects.addAll(it) }.onFailure(::err) }
    fun createProject(name: String, repo: String) = viewModelScope.launch { runCatching { api.createProject(name, repo) }.onFailure(::err); loadProjects().join() }
    fun deleteProject(p: Project) = viewModelScope.launch { runCatching { api.deleteProject(p.id) }.onFailure(::err); if (currentProject == p.id) currentProject = null; if (newChatProject == p.id) newChatProject = null; loadProjects() }
    fun useProject(p: Project?) {
        val id = convId
        if (id == null) { newChatProject = p?.id; currentProject = p?.id; toast = if (p != null) "Новый чат будет в проекте «${p.name}»" else "Без проекта"; return }
        viewModelScope.launch { runCatching { api.setProject(id, p?.id) }.onSuccess { currentProject = p?.id; toast = if (p != null) "Чат привязан к «${p.name}»" else "Проект снят" }.onFailure(::err) }
    }
    val prompts = mutableStateListOf<PromptItem>()
    fun loadPrompts() = viewModelScope.launch { runCatching { api.prompts() }.onSuccess { prompts.clear(); prompts.addAll(it) }.onFailure(::err) }
    fun savePrompt(n: String, t: String) = viewModelScope.launch { runCatching { api.savePrompt(n, t) }.onFailure(::err); loadPrompts().join() }
    fun deletePrompt(p: PromptItem) = viewModelScope.launch { runCatching { api.deletePrompt(p.id) }; prompts.remove(p) }
    fun exportChatText(): String = buildString {
        append("# ").append(convs.firstOrNull { it.id == convId }?.title ?: "Чат").append("\n\n")
        messages.forEach { m -> if (m.role == "user" && m.content.isNotBlank()) append("**Вы:** ").append(m.content).append("\n\n") else if (m.role == "assistant" && m.content.isNotBlank()) append(m.content).append("\n\n") }
    }
    var voiceMuted by mutableStateOf(false)
    var voiceStartedAt by mutableStateOf(0L)
    /** Снимок экрана по просьбе агента: системный (при вызове ассистента) либо через службу доступности; уходит на сервер, там описывается vision-моделью. */
    private suspend fun grabScreen(): String {
        val app = getApplication<Application>()
        var f: File? = AssistData.shot?.takeIf { it.exists() && System.currentTimeMillis() - it.lastModified() < 15 * 60_000 }
        val txt = AssistData.text
        if (f == null) {
            val bmp = OaAccessibilityService.instance?.screenshot()
            if (bmp != null) f = withContext(Dispatchers.IO) {
                val k = 1400f / maxOf(bmp.width, bmp.height)
                val b = if (k < 1f) android.graphics.Bitmap.createScaledBitmap(bmp, (bmp.width * k).toInt(), (bmp.height * k).toInt(), true) else bmp
                File(File(app.cacheDir, "cam").also { it.mkdirs() }, "screen_${System.currentTimeMillis()}.jpg").also { out -> out.outputStream().use { b.compress(android.graphics.Bitmap.CompressFormat.JPEG, 80, it) } }
            }
        }
        if (f == null) return if (txt.isNotBlank()) "text:\n${txt.take(2500)}" else "Нет доступа к экрану: вызовите помощника долгим нажатием кнопки питания либо включите службу доступности OpenAgent (Настройки → Управление телефоном)."
        val up = api.upload(f.name, "image/jpeg", f.asRequestBody("image/jpeg".toMediaType()))
        AssistData.shot = null                                   // снимок использован — следующий раз сделаем свежий
        return "screenshot:${up.id}" + if (txt.isNotBlank()) "\n${txt.take(1500)}" else ""
    }

    var askOnStart by mutableStateOf<String?>(null)
    var askShot: String? = null
    var askScreenText: String? = null
    /** Вопрос из окна-ассистента: прикладывает скриншот экрана (если есть) и отправляет. */
    fun sendWithScreen(text: String) {
        val shot = askShot?.let { java.io.File(it) }?.takeIf { it.exists() }; val st = askScreenText?.takeIf { it.isNotBlank() }
        askShot = null; askScreenText = null
        val full = if (st != null) "$text\n\n[Текст, найденный на экране: ${st.take(1500)}]" else text
        if (shot == null) { send(full); return }
        viewModelScope.launch {
            val app = getApplication<Application>()
            runCatching { attach(listOf(androidx.core.content.FileProvider.getUriForFile(app, "${app.packageName}.files", shot))) }
            var w = 0; while ((uploading > 0 || attachments.isEmpty()) && w < 150) { delay(100); w++ }
            send(full)
        }
    }
    var showCp by mutableStateOf(false)
    var cpCount by mutableStateOf(0)
    var checkpoints by mutableStateOf<List<Checkpoint>>(emptyList())
    fun loadCheckpoints() { val id = convId ?: return; viewModelScope.launch { runCatching { api.checkpoints(id) }.onSuccess { checkpoints = it }.onFailure(::err) } }
    fun restoreCheckpoint(h: String) { val id = convId ?: return; viewModelScope.launch { runCatching { api.restoreCheckpoint(id, h) }.onSuccess { toast = "Файлы восстановлены" }.onFailure(::err) } }
    val api = Api(store)
    private val recorder = Recorder(app)
    private val player = Player()

    // настройки
    var dynamicColor by mutableStateOf(store.dynamicColor)
    var autoSpeak by mutableStateOf(store.autoSpeak)
    var haptics by mutableStateOf(store.haptics.also { Haptics.enabled = it })
    var provider by mutableStateOf(store.provider)
    var model by mutableStateOf(store.model)
    val imageLoader = coil.ImageLoader.Builder(app).components { add(coil.decode.SvgDecoder.Factory()) }
        .diskCache { coil.disk.DiskCache.Builder().directory(java.io.File(app.cacheDir, "img")).maxSizeBytes(300L * 1024 * 1024).build() }
        .memoryCache { coil.memory.MemoryCache.Builder(app).maxSizePercent(0.25).build() }
        .respectCacheHeaders(false).crossfade(true).build()
    var effort by mutableStateOf(store.effort)
    var askRisky by mutableStateOf(store.askRisky)
    fun updAskRisky(v: Boolean) { askRisky = v; store.askRisky = v }
    val providers = mutableStateListOf<ProviderInfo>()
    var mode by mutableStateOf(store.mode)
    fun selectModel(p: String, m: String) { provider = p; model = m; store.provider = p; store.model = m }
    /** Для своего провайдера без выбранной модели — берём первую из списка. */
    fun ensureModel() { val p = providers.firstOrNull { it.id == provider } ?: return; if (!p.builtin && model.isBlank()) p.models.firstOrNull()?.let { selectModel(provider, it) } }
    fun updEffort(e: String) { effort = e; store.effort = e }
    fun loadProviders() = viewModelScope.launch { runCatching { api.providers() }.onSuccess { providers.clear(); providers.addAll(it); ensureModel() } }
    fun addProvider(name: String, url: String, key: String, effortParam: Boolean, models: String, done: (Boolean) -> Unit) = viewModelScope.launch {
        runCatching { api.addProvider(name, url, key, effortParam, models) }.onSuccess { r ->
            loadProvidersNow()
            selectModel(r.id, r.models.firstOrNull().orEmpty())   // сразу выбираем первую модель — без ошибки «выберите модель»
            toast = r.warning ?: "Подключено: ${r.models.size} мод."
            Haptics.success(); done(true)
        }.onFailure { err(it); done(false) }
    }
    val presets = mutableStateListOf<ProviderPreset>()
    fun loadPresets() = viewModelScope.launch { if (presets.isEmpty()) runCatching { api.presets() }.onSuccess { presets.addAll(it) } }
    private suspend fun loadProvidersNow() { runCatching { api.providers() }.onSuccess { providers.clear(); providers.addAll(it) } }
    fun deleteProvider(id: String) = viewModelScope.launch { runCatching { api.deleteProvider(id) }; if (provider == id) selectModel("river", "fast"); loadProvidersNow() }
    /** Короткое имя текущей модели для чипа */
    /** Читаемое имя модели: GPT-6 Luna, Claude Haiku 5.5, остальное — из id. */
    fun prettyModel(id: String): String = when (id.substringAfterLast('/')) {
        "gpt-6-luna" -> "GPT-6 Luna"; "claude-haiku-5-5", "claude-haiku-5-5:free" -> "Claude Haiku 5.5"
        else -> id.substringAfterLast('/').replace('-', ' ').take(24)
    }
    fun modelLabel(): String {
        val p = providers.firstOrNull { it.id == provider }
        return when {
            provider == "perplexity" -> when (model) { "openai/gpt-6-luna" -> "GPT-6 Luna · Perplexity"; "anthropic/claude-haiku-5-5" -> "Claude Haiku 5.5 · Perplexity"; "agent-fast" -> "Perplexity · быстрый"; "agent-medium" -> "Perplexity · глубокий"; "agent-high" -> "Perplexity · максимум"; else -> "Perplexity Agent" }
            model.isBlank() -> p?.name ?: "Выбрать модель"
            else -> prettyModel(model)
        }
    }
    var fontScale by mutableStateOf(store.fontScale)
    var silenceMs by mutableStateOf(store.silenceMs)
    var micThreshold by mutableStateOf(store.micThreshold)
    var amoled by mutableStateOf(store.amoled)
    fun updAmoled(v: Boolean) { amoled = v; store.amoled = v }
    var sttLang by mutableStateOf(store.sttLang)
    fun updSttLang(v: String) { sttLang = v; store.sttLang = v }
    val drafts = HashMap<Int?, String>()
    fun updDynamic(v: Boolean) { dynamicColor = v; store.dynamicColor = v }
    fun updAutoSpeak(v: Boolean) { autoSpeak = v; store.autoSpeak = v }
    fun updHaptics(v: Boolean) { haptics = v; store.haptics = v; Haptics.enabled = v; if (v) Haptics.click() }
    fun updFontScale(v: Float) { fontScale = v; store.fontScale = v }
    fun updSilence(v: Float) { silenceMs = v; store.silenceMs = v }
    fun updMicThreshold(v: Float) { micThreshold = v; store.micThreshold = v }

    // auth
    var booting by mutableStateOf(true); internal set
    var user by mutableStateOf<User?>(null); internal set
    var authConfig by mutableStateOf(AuthConfig()); private set
    var authBusy by mutableStateOf(false)
    var authError by mutableStateOf<String?>(null)
    var codeSent by mutableStateOf(false)

    // navigation / data
    var screen by mutableStateOf(Screen.Chat)
    val convs = mutableStateListOf<Conv>()
    var convId by mutableStateOf<Int?>(null); internal set
    val messages = mutableStateListOf<Msg>()
    var partial by mutableStateOf("")
    var running by mutableStateOf(false)
    val toolOutput = mutableStateMapOf<String, String>()
    val attachments = mutableStateListOf<Attach>()
    var uploading by mutableStateOf(0)
    var toast by mutableStateOf<String?>(null)
    var loadingChat by mutableStateOf(false)

    private var streamJob: Job? = null

    // ---- Groq через телефон ----
    val groq = GroqBridge.shared(api, store)
    var groqKeyState by mutableStateOf(store.groqKey)
    fun saveGroqKey(k: String) { store.groqKey = k; groqKeyState = store.groqKey; groq.restart() }
    var pplxKeyState by mutableStateOf(store.pplxKey)
    fun savePplxKey(k: String) { store.pplxKey = k; pplxKeyState = store.pplxKey; groq.restart(); viewModelScope.launch { delay(1800); loadProviders() } }
    var searchProvider by mutableStateOf(store.searchProvider)
    fun updSearchProvider(v: String) { searchProvider = v; store.searchProvider = v }
    // ---- версия сервера, диагностика ----
    var health by mutableStateOf<Health?>(null)
    val serverOld get() = health?.let { "stt-stream" !in it.features } == true
    private var oldWarned = false
    val serverNoPplx get() = health?.let { "pplx" !in it.features } == true
    init { viewModelScope.launch { androidx.compose.runtime.snapshotFlow { groq.connected }.collect { if (it) { delay(400); loadProviders() } } } }   // как только телефон подключился к серверу — обновляем список провайдеров
    var diag by mutableStateOf<Diag?>(null)
    var diagBusy by mutableStateOf(false)
    fun runDiag() { if (diagBusy) return; diagBusy = true; diag = null; viewModelScope.launch { runCatching { api.diag() }.onSuccess { diag = it }.onFailure { toast = "Диагностика: ${it.message}" }; diagBusy = false } }
    // ---- плавное появление текста: сервер присылает кусками, на экране текст «течёт» ровно ----
    var shown by mutableStateOf("")
    init { groq.start() }
    init { viewModelScope.launch { while (true) {
        val p = partial
        if (p.isEmpty()) { if (shown.isNotEmpty()) shown = ""; delay(33); continue }
        if (!p.startsWith(shown)) shown = p
        else if (shown.length < p.length) { val backlog = p.length - shown.length; shown = p.substring(0, shown.length + (backlog / 5).coerceIn(2, 90).coerceAtMost(backlog)) }
        delay(30)
    } } }
    init { if (provider == "river" && (model.isBlank() || model in listOf("auto", "fast", "smart", "solve", "code"))) { model = DEFAULT_MODEL; store.model = DEFAULT_MODEL }; viewModelScope.launch { boot() } }

    var inForeground = true

    // блокировка приложения
    var appLock by mutableStateOf(store.appLock)
    var locked by mutableStateOf(store.appLock)
    private var stoppedAt = 0L
    fun updAppLock(on: Boolean) { appLock = on; store.appLock = on; if (!on) locked = false }
    fun onStopped() { stoppedAt = System.currentTimeMillis()   // звонок в фоне НЕ обрываем: им управляет служба с кнопкой «Завершить»
        if (dictating) { runCatching { dictRt?.cancel() }; dictRt = null; runCatching { dictJob?.cancel() }; runCatching { recorder.cancel() }; dictating = false; dictPartial = ""; dictLevel = 0f } }   // приложение свернули — микрофон не должен оставаться включённым
    fun onStartedLock() { if (appLock && stoppedAt > 0 && System.currentTimeMillis() - stoppedAt > 20_000) locked = true }

    // ---- защита голосом/лицом, жест ----
    var hasVoice by mutableStateOf(VoicePrint.enrolled(app)); var hasFace by mutableStateOf(FacePrint.enrolled(app))
    var gateSessions by mutableStateOf(store.gateSessions); var gestureWake by mutableStateOf(store.gestureWake); var bioStrict by mutableStateOf(store.bioStrict)
    var gateOpen by mutableStateOf(false)
    private var gatePassUntil = 0L; private var gateThen: (() -> Unit)? = null
    fun refreshBio() {
        val a = getApplication<Application>(); hasVoice = VoicePrint.enrolled(a); hasFace = FacePrint.enrolled(a)
        if (!hasVoice && !hasFace && gateSessions) updGateSessions(false)
    }
    fun updGateSessions(v: Boolean) { gateSessions = v; store.gateSessions = v }
    fun updGestureWake(v: Boolean) { gestureWake = v; store.gestureWake = v }
    fun updBioStrict(v: String) { bioStrict = v; store.bioStrict = v }
    private fun needGate() = gateSessions && (hasVoice || hasFace) && System.currentTimeMillis() > gatePassUntil
    private fun requireGate(then: () -> Unit) { gateThen = then; gateOpen = true }
    fun gatePassed() { gatePassUntil = System.currentTimeMillis() + 10 * 60_000L; gateOpen = false; val t = gateThen; gateThen = null; t?.invoke() }
    fun gateCancel() { gateOpen = false; gateThen = null; toast = "Сеанс отменён: проверка не пройдена"; if (screen == Screen.Voice) screen = Screen.Chat }

    var cameraRequest by mutableStateOf(false)
    // «поделиться в OpenAgent»
    var pendingText by mutableStateOf<String?>(null)

    // закладки
    @kotlinx.serialization.Serializable data class Bookmark(val msgId: Long, val convId: Int, val title: String, val text: String, val ts: Long)
    val bookmarks = mutableStateListOf<Bookmark>().also { l -> runCatching { l.addAll(JSON.decodeFromString<List<Bookmark>>(store.bookmarksJson)) } }
    private fun saveBookmarks() { store.bookmarksJson = JSON.encodeToString(bookmarks.toList()) }
    fun isBookmarked(m: Msg) = bookmarks.any { it.msgId == m.id && it.convId == convId }
    fun toggleBookmark(m: Msg) {
        val cid = convId ?: return
        val ex = bookmarks.firstOrNull { it.msgId == m.id && it.convId == cid }
        if (ex != null) bookmarks.remove(ex) else { bookmarks.add(0, Bookmark(m.id, cid, convs.firstOrNull { it.id == cid }?.title ?: "Чат", m.content.take(1200), System.currentTimeMillis())); toast = "Добавлено в закладки" }
        saveBookmarks()
    }
    fun removeBookmark(b: Bookmark) { bookmarks.remove(b); saveBookmarks() }

    // инструкции пользователя
    var instructions by mutableStateOf("")
    fun loadInstructions() = viewModelScope.launch { runCatching { api.instructions() }.onSuccess { instructions = it } }
    fun saveInstructions(t: String) = viewModelScope.launch { runCatching { api.setInstructions(t) }.onSuccess { instructions = t; toast = "Инструкции сохранены" }.onFailure(::err) }

    // запуск кода из блока в чате
    fun runSnippet(lang: String, code: String, done: (String) -> Unit) = viewModelScope.launch {
        runCatching { api.runSnippet(lang, code) }.onSuccess { done(it.output.ifBlank { "(нет вывода)" } + if (it.exit != 0) "\n[exit ${it.exit}]" else "") }.onFailure { done("Ошибка: ${it.message}") }
    }

    private suspend fun boot() = coroutineScope {
        // мгновенно показываем сохранённое, пока сеть отвечает
        if (store.token != null) loadConvsCache()?.let { convs.addAll(it) }
        val cfg = async { runCatching { authConfig = api.config() } }
        launch { runCatching { api.health() }.onSuccess { health = it; if ("stt-stream" !in it.features) rtOk = false } }
        val me = async { if (store.token != null) runCatching { user = api.me() }.onFailure { if ((it as? ApiException)?.code == 401) store.token = null } }
        val list = async { if (store.token != null) refreshConvs() }
        me.await()
        if (user != null) {
            val skipLast = AssistFlag.on; AssistFlag.on = false       // окно ассистента: всегда новый чат, а не последний открытый
            if (!skipLast && convs.isNotEmpty() && convId == null) store.lastConv.takeIf { it > 0 && convs.any { c -> c.id == it } }?.let { openChat(it) }
            launch { loadCurrentVoice() }
        }
        booting = false
        cfg.await(); list.await()
        if (user != null && convId == null && store.lastConv > 0 && convs.any { it.id == store.lastConv }) openChat(store.lastConv)
    }

    /** Возврат в приложение: быстро подтянуть прогресс чата и список чатов. */
    fun onAppResume() {
        if (user == null || booting) return
        viewModelScope.launch {
            launch { refreshConvs() }
            val id = convId ?: return@launch
            val r = syncChat(id) ?: return@launch
            if (r.running) attachStream(id) else if (running) { running = false; partial = "" }
        }
    }

    private fun filesDir() = getApplication<Application>().filesDir
    private fun chatCache(id: Int) = File(filesDir(), "chat_$id.json")
    private fun saveChatCache(id: Int) { val snap = messages.takeLast(120).toList(); viewModelScope.launch(Dispatchers.IO) { runCatching { chatCache(id).writeText(JSON.encodeToString(snap)) } } }
    private fun loadChatCache(id: Int): List<Msg>? = runCatching { JSON.decodeFromString<List<Msg>>(chatCache(id).readText()) }.getOrNull()
    private fun loadConvsCache(): List<Conv>? = runCatching { JSON.decodeFromString<List<Conv>>(File(filesDir(), "convs.json").readText()) }.getOrNull()

    /** Подтянуть только новые сообщения (или всё, если кэша нет). */
    /** Настоящее пользовательское сообщение занимает место временного (то же содержимое): ключ списка сохраняется, поэтому нет ни анимации «второго» сообщения, ни дубля. */
    private fun adoptTemp(m: Msg): Msg {
        if (m.role != "user") return m
        val t = messages.firstOrNull { it.id < 0 && it.content == m.content } ?: messages.firstOrNull { it.id < 0 }
        messages.removeAll { it.id < 0 }
        return if (t != null) m.copy(cid = t.id) else m
    }

    private suspend fun syncChat(id: Int): MsgsResp? {
        val firstTemp = messages.indexOfFirst { it.id < 0 }
        val lastId = (if (firstTemp >= 0) messages.take(firstTemp) else messages).lastOrNull { it.id > 0 }?.id ?: 0L   // курсор — до временного сообщения: настоящее тоже должно подтянуться
        val r = runCatching { api.messages(id, lastId) }.getOrNull() ?: return null
        if (convId != id) return r
        if (r.incremental) { r.messages.forEach { m0 -> val m = adoptTemp(m0); if (messages.none { it.id == m.id }) { messages.add(m); if (m.cid == 0L) freshIds.add(m.id) } } }
        else { val tmp = messages.filter { it.id < 0 && running }; messages.clear(); val used = HashSet<Long>(); messages.addAll(r.messages.map { m -> val t = if (m.role == "user") tmp.firstOrNull { it.id !in used && it.content == m.content }?.also { used.add(it.id) } else null; if (t != null) m.copy(cid = t.id) else m }); messages.addAll(tmp.filter { it.id !in used }) }
        partial = r.partial
        saveChatCache(id)
        return r
    }

    private fun err(e: Throwable) { toast = e.message ?: "Ошибка" }

    // ---------- вход ----------
    fun sendCode(email: String, captcha: String?) = viewModelScope.launch {
        authBusy = true; authError = null
        runCatching { api.sendCode(email.trim(), captcha) }.onSuccess { codeSent = true }.onFailure { authError = it.message }
        authBusy = false
    }
    fun verify(email: String, code: String) = viewModelScope.launch {
        authBusy = true; authError = null
        runCatching { api.verify(email.trim(), code.trim()) }.onSuccess { loggedIn(it) }.onFailure { authError = it.message }
        authBusy = false
    }
    fun google(idToken: String) = viewModelScope.launch {
        authBusy = true; authError = null
        runCatching { api.google(idToken) }.onSuccess { loggedIn(it) }.onFailure { authError = it.message }
        authBusy = false
    }
    fun authFail(msg: String) { authError = msg }
    private suspend fun loggedIn(r: AuthResp) { store.token = r.token; user = r.user; refreshConvs(); loadCurrentVoice() }
    fun logout() {
        stopVoice(); streamJob?.cancel()
        store.token = null; user = null; convs.clear(); messages.clear(); convId = null; codeSent = false; screen = Screen.Chat
    }
    fun refreshMe() = viewModelScope.launch { runCatching { user = api.me() } }
    fun setServer(url: String) { store.server = url; viewModelScope.launch { runCatching { authConfig = api.config() } } }

    // ---------- чаты ----------
    suspend fun refreshConvs() {
        runCatching { api.conversations() }.onSuccess { convs.clear(); convs.addAll(it); viewModelScope.launch(Dispatchers.IO) { runCatching { File(filesDir(), "convs.json").writeText(JSON.encodeToString(it)) } } }
    }

    fun newChat(m: String = mode) {
        mode = m; store.mode = m; persona = ""; statusText = ""; freshIds.clear(); noAnimIds.clear()
        streamJob?.cancel(); convId = null; messages.clear(); hasMoreOld = false; partial = ""; running = false; toolOutput.clear(); attachments.clear(); screen = Screen.Chat
    }

    var hasMoreOld by mutableStateOf(false); private set
    private var loadingOlder = false
    /** Подгружает более старые сообщения чата (сервер отдаёт историю страницами) — вызывается, когда долистали до верха. */
    fun loadOlder() {
        val id = convId ?: return; if (loadingOlder || !hasMoreOld) return
        val first = messages.firstOrNull { it.id > 0 }?.id ?: return
        loadingOlder = true
        viewModelScope.launch {
            runCatching { api.messages(id, before = first) }.onSuccess { r ->
                if (convId == id) { val have = messages.map { it.id }.toHashSet(); messages.addAll(0, r.messages.filter { it.id !in have }); hasMoreOld = r.hasMore }
            }.onFailure { err(it) }
            loadingOlder = false
        }
    }

    fun openChat(id: Int) = viewModelScope.launch {
        streamJob?.cancel()
        convs.firstOrNull { it.id == id }?.let { mode = it.mode; persona = it.persona; currentProject = it.projectId }
        freshIds.clear(); noAnimIds.clear(); statusText = ""
        convId = id; store.lastConv = id; screen = Screen.Chat; messages.clear(); hasMoreOld = false; partial = ""; running = false; toolOutput.clear(); attachments.clear()
        loadChatCache(id)?.let { messages.addAll(it) }   // сразу показываем сохранённое
        loadingChat = messages.isEmpty()
        runCatching { api.messages(id) }.onSuccess {
            if (convId == id) { messages.clear(); messages.addAll(it.messages); hasMoreOld = it.hasMore; partial = it.partial; running = it.running; saveChatCache(id) }
            if (it.running) attachStream(id)
        }.onFailure { if (messages.isEmpty()) err(it) }
        loadingChat = false
    }

    fun deleteChat(id: Int) = viewModelScope.launch {
        runCatching { api.deleteConversation(id) }.onFailure(::err)
        if (convId == id) newChat()
        refreshConvs()
    }

    fun rename(id: Int, title: String) = viewModelScope.launch { runCatching { api.renameConversation(id, title) }; refreshConvs() }

    /**
     * Следит за работой агента: при обрыве соединения переподключается и дочитывает пропущенное.
     * События потока приходят с IO-потока; чтобы UI не мигал и не лагал, они копятся и применяются на главном потоке
     * одним снимком состояния примерно раз в кадр (≈30 к/с).
     */
    private fun attachStream(id: Int, wait: Boolean = false) {
        streamJob?.cancel()
        streamJob = viewModelScope.launch {
            running = true; streamConv = id
            val doneAtStart = onTurnDone              // колбэк именно ЭТОГО хода (поток следующего хода не должен закрывать чужую очередь озвучки)
            RunService.start(getApplication())
            var fails = 0; var finishedNormally = false
            try {
                coroutineScope {
                    val events = Channel<StreamEvent>(Channel.UNLIMITED)
                    val applier = launch {
                        for (first in events) {
                            delay(32)
                            val batch = arrayListOf(first)
                            while (true) batch.add(events.tryReceive().getOrNull() ?: break)
                            try { androidx.compose.runtime.snapshots.Snapshot.withMutableSnapshot { applyBatch(batch) } } catch (e: CancellationException) { throw e } catch (e: Throwable) { android.util.Log.w("OA", "applyBatch: ${e.message}") }   // сбой одного события не должен убивать поток (и терять «done»)
                            batch.forEach { if (it is StreamEvent.Flush) it.done.complete(Unit) }
                        }
                    }
                    try {
                        var first = wait
                        while (isActive && convId == id) {
                            val streamed = try { api.stream(id, first) { ev -> events.trySend(ev) }; true } catch (e: CancellationException) { throw e } catch (e: Throwable) { false }
                            first = false
                            CompletableDeferred<Unit>().also { events.trySend(StreamEvent.Flush(it)); it.await() }
                            val r = syncChat(id)
                            if (r == null) { fails++; if (fails > 40) break } else {
                                fails = 0
                                if (!r.running) {
                                    // поток оборвался до «done», а ответ уже готов: дочитываем озвучку и закрываем очередь — иначе звонок навсегда «говорит»
                                    val lastAns = messages.lastOrNull { it.role == "assistant" && it.content.isNotBlank() }?.content
                                    if (voiceReply.isBlank() && lastAns != null) onTurnText?.invoke(lastAns)
                                    running = false; partial = ""; finishedNormally = true; onTurnDone?.invoke(); break
                                }
                            }
                            delay(if (streamed) 400L else minOf(1000L * (fails + 1), 4000L))
                        }
                    } finally { events.close(); applier.cancel() }
                }
            } finally {
                doneAtStart?.invoke()                        // голосовой ход не должен зависнуть, как бы ни закончился поток
                RunService.stop(getApplication())
                if (finishedNormally && !inForeground) {
                    val last = messages.lastOrNull { it.role == "assistant" && it.content.isNotBlank() }?.content.orEmpty()
                    Notifier.done(getApplication(), convs.firstOrNull { it.id == id }?.title ?: "OpenAgent", last.ifBlank { "Задача выполнена" })
                }
                withContext(NonCancellable) { refreshConvs() }
            }
        }
    }

    private var onTurnText: ((String) -> Unit)? = null
    private var onTurnDone: (() -> Unit)? = null

    var statusText by mutableStateOf("")
    private var streamConv: Int? = null

    // Сообщения, которые только что появились в открытом чате: анимируем их один раз; всё остальное (история, повторный показ при прокрутке) — без анимации.
    private val freshIds = HashSet<Long>()
    private val noAnimIds = HashSet<Long>()
    fun consumeFresh(id: Long): Boolean = freshIds.remove(id) && !noAnimIds.remove(id)

    private fun applyBatch(batch: List<StreamEvent>) {
        if (streamConv != null && convId != streamConv) return   // события устаревшего потока
        // подряд идущие куски текста склеиваем в один
        val deltas = StringBuilder()
        for (ev in batch) if (ev is StreamEvent.Delta) deltas.append(ev.text)
        var deltaApplied = false
        for (ev in batch) {
            if (ev is StreamEvent.Delta) { if (!deltaApplied) { deltaApplied = true; statusText = ""; partial += deltas.toString(); onTurnText?.invoke(deltas.toString()) } }
            else applyEvent(ev)
        }
    }

    private fun applyEvent(ev: StreamEvent) {
        when (ev) {
            is StreamEvent.Snapshot -> partial = ev.partial
            is StreamEvent.Status -> statusText = ev.text
            is StreamEvent.Checkpoint -> cpCount++
            is StreamEvent.Phone -> viewModelScope.launch {
                val action = (ev.args["action"] as? kotlinx.serialization.json.JsonPrimitive)?.content
                val res = if (action == "screen") runCatching { grabScreen() }.getOrElse { "Не удалось сделать снимок экрана: ${it.message}" } else withContext(Dispatchers.Default) { PhoneControl.run(getApplication(), ev.args) }
                runCatching { api.phoneResult(ev.id, res) }
            }
            is StreamEvent.Replace -> { val i = messages.indexOfFirst { it.id == ev.id }; if (i >= 0) { noAnimIds.add(ev.id); messages[i] = messages[i].copy(content = ev.content) } }
            is StreamEvent.Delta -> { statusText = ""; partial += ev.text; onTurnText?.invoke(ev.text) }
            is StreamEvent.Message -> {
                val m = adoptTemp(ev.msg)                                                   // «оптимистичное» сообщение заменяется настоящим на месте, без мигания
                if (messages.none { it.id == m.id }) {
                    if (m.role == "assistant" && partial.isNotEmpty()) noAnimIds.add(m.id)  // ответ «подхватывает» стримящийся текст — без вспышки
                    if (m.cid == 0L) freshIds.add(m.id); messages.add(m)
                    if (m.role == "tool") Haptics.tick()
                }
                if (m.role == "assistant") partial = ""
            }
            is StreamEvent.ToolOutput -> toolOutput[ev.id] = ((toolOutput[ev.id] ?: "") + ev.text).takeLast(6000)
            is StreamEvent.Error -> { statusText = ""; running = false; onTurnDone?.invoke() }
            is StreamEvent.Flush -> {}
            StreamEvent.Done -> {
                statusText = ""; running = false; partial = ""; onTurnDone?.invoke(); Haptics.success()
                convId?.let { id -> if (mode == "chat" && voiceState == VoiceState.Idle) viewModelScope.launch { delay(9000); if (convId == id && !running) syncChat(id) } }   // фоновая проверка ответа могла дописать поправку
                if (autoSpeak && voiceState == VoiceState.Idle) messages.lastOrNull { it.role == "assistant" && it.content.isNotBlank() && it.toolCalls == null }?.let { toggleSpeak(it) }
            }
        }
    }

    // ---------- оффлайн-режим: всё на телефоне ----------
    var offlineMode by mutableStateOf(store.offlineMode)
    fun updOffline(v: Boolean) { offlineMode = v; store.offlineMode = v; if (v) { toast = if (Offline.ready(getApplication(), Offline.CHAT)) "Оффлайн-режим: отвечаю на телефоне" else "Загрузите модели: Настройки → Оффлайн-режим"; if (voiceJob?.isActive == true) stopVoice() } else { Offline.unload(Offline.CHAT) } }
    private var offlineJob: Job? = null
    private fun sendOffline(t: String) {
        val app = getApplication<Application>()
        val hist = messages.filter { it.content.isNotBlank() && (it.role == "user" || it.role == "assistant") && it.toolCalls == null }.takeLast(16).map { it.role to it.content }
        val temp = Msg(id = -System.nanoTime().coerceAtLeast(1), role = "user", content = t, createdAt = System.currentTimeMillis())
        freshIds.add(temp.id); messages.add(temp); running = true; partial = ""; statusText = ""
        offlineJob = viewModelScope.launch {
            val sb = StringBuilder()
            val ans = try { Offline.reply(app, t, hist, { statusText = it }) { d -> sb.append(d); partial = sb.toString() } } catch (e: CancellationException) { throw e } catch (e: Throwable) { "Ошибка: ${e.message}" }
            val m = Msg(id = -System.nanoTime().coerceAtLeast(1), role = "assistant", content = ans, createdAt = System.currentTimeMillis())
            noAnimIds.add(m.id); messages.add(m); partial = ""; statusText = ""; running = false
            if (autoSpeak && ans.isNotBlank()) toggleSpeak(m)
            onTurnDone?.invoke()
        }
    }

    fun send(text: String, voice: Boolean = false) {
        ensureModel()
        val t = text.trim()
        if ((t.isEmpty() && attachments.isEmpty()) || running) return
        if (offlineMode) { if (t.isNotEmpty()) sendOffline(t); return }
        // мгновенно показываем сообщение пользователя (без ожидания сервера) — экран не «моргает» пустотой
        val temp = Msg(id = -System.nanoTime().coerceAtLeast(1), role = "user", content = t, attachments = attachments.toList().ifEmpty { null }, createdAt = System.currentTimeMillis())
        freshIds.add(temp.id); messages.add(temp); running = true; partial = ""; statusText = ""
        viewModelScope.launch {
            try {
                val newConv = convId == null
                val id = convId ?: api.newConversation(mode).also { convId = it.id; store.lastConv = it.id; refreshConvs(); newChatProject?.let { pid -> runCatching { api.setProject(it.id, pid); currentProject = pid } } }.id
                if (newConv && persona.isNotBlank()) runCatching { api.setPersona(id, persona) }
                val files = attachments.map { it.id }
                attachments.clear()
                if (!voice && (store.groqKey.isNotBlank() || store.pplxKey.isNotBlank())) groq.awaitUp(1200)   // Groq/Perplexity идут через телефон — соединение должно быть поднято
                attachStream(id, wait = true)                       // поток открываем сразу, параллельно с отправкой: экономим один круг до сервера
                api.send(id, t, files, voice, provider, model, effort, askRisky)
            } catch (e: Throwable) { streamJob?.cancel(); messages.remove(temp); running = false; err(e); onTurnDone?.invoke() }
        }
    }

    // ---------- роли (персоны) ----------
    var persona by mutableStateOf("")
    fun choosePersona(p: String) {
        persona = p
        val id = convId ?: return
        viewModelScope.launch { runCatching { api.setPersona(id, p) }; refreshConvs() }
    }

    fun stopRun() { if (offlineMode) { Offline.stopRequested = true; Offline.stop(); return }; val id = convId ?: return; viewModelScope.launch { runCatching { api.stop(id) } } }

    // ---------- повтор / правка / закрепление / поиск / экспорт ----------
    fun regenerate() {
        val id = convId ?: return; if (running) return
        val last = messages.lastOrNull { it.role == "user" } ?: return
        viewModelScope.launch {
            messages.removeAll { it.id >= last.id }; running = true; partial = ""
            runCatching { api.regenerate(id, provider, model, effort, askRisky); attachStream(id) }.onFailure { running = false; err(it); syncChat(id) }
        }
    }
    fun editMessage(m: Msg, text: String) {
        val id = convId ?: return; if (running || text.isBlank()) return
        viewModelScope.launch {
            messages.removeAll { it.id >= m.id }; running = true; partial = ""
            runCatching { api.editMessage(id, m.id, text.trim(), provider, model, effort, askRisky); attachStream(id) }.onFailure { running = false; err(it); syncChat(id) }
        }
    }
    fun pin(c: Conv) = viewModelScope.launch { runCatching { api.pinConversation(c.id, !c.pinned) }; refreshConvs() }
    val chatHits = mutableStateListOf<ChatHit>()
    var chatSearching by mutableStateOf(false)
    private var searchJob: Job? = null
    fun searchChats(q: String) {
        searchJob?.cancel()
        if (q.trim().length < 2) { chatHits.clear(); chatSearching = false; return }
        searchJob = viewModelScope.launch { delay(300); chatSearching = true; runCatching { api.searchChats(q.trim()) }.onSuccess { chatHits.clear(); chatHits.addAll(it) }; chatSearching = false }
    }
    fun exportChat(id: Int) = viewModelScope.launch {
        runCatching {
            val e = api.exportChat(id)
            val ctx = getApplication<Application>()
            val f = File(File(ctx.cacheDir, "dl").also { it.mkdirs() }, e.name.ifBlank { "chat.md" }).also { it.writeText(e.markdown) }
            val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
            ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/markdown").putExtra(Intent.EXTRA_STREAM, uri).putExtra(Intent.EXTRA_TEXT, e.markdown.take(4000)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), "Экспорт чата").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }.onFailure(::err)
    }

    // ---------- монитор сервера ----------
    var sys by mutableStateOf<SysInfo?>(null)
    val cpuHistory = mutableStateListOf<Int>()
    fun loadSystem() = viewModelScope.launch {
        runCatching { api.system() }.onSuccess { s ->
            sys = s
            val c = s.cpu ?: ((s.load.firstOrNull() ?: 0.0) / s.cores * 100).toInt().coerceIn(0, 100)
            cpuHistory.add(c); if (cpuHistory.size > 40) cpuHistory.removeAt(0)
        }
    }

    // ---------- git ----------
    val gitRepos = mutableStateListOf<GitRepo>()
    var gitInfo by mutableStateOf<GitInfo?>(null)
    var gitBusy by mutableStateOf(false)
    fun loadGitRepos() = viewModelScope.launch { runCatching { api.gitRepos() }.onSuccess { gitRepos.clear(); gitRepos.addAll(it) }.onFailure(::err) }
    fun openGit(path: String) = viewModelScope.launch { gitCurrent = path; gitBusy = true; runCatching { api.git(path) }.onSuccess { gitInfo = it }.onFailure(::err); gitBusy = false }
    fun gitDo(action: String, message: String = "") {
        val p = gitCurrent
        viewModelScope.launch {
            gitBusy = true
            runCatching { api.gitAction(action, p, message) }.onSuccess { toast = (if (it.ok) "✓ " else "✗ ") + it.output.lineSequence().firstOrNull { l -> l.isNotBlank() }.orEmpty().take(120); if (it.ok) Haptics.success() }.onFailure(::err)
            gitBusy = false; openGit(p)
        }
    }
    var gitCurrent by mutableStateOf(".")

    // ---------- сайты и расход ----------
    val sites = mutableStateListOf<Site>()
    fun loadSites() = viewModelScope.launch { runCatching { api.sites() }.onSuccess { sites.clear(); sites.addAll(it) }.onFailure(::err) }
    fun deleteSite(s: Site) = viewModelScope.launch { runCatching { api.deleteSite(s.slug) }.onFailure(::err); sites.remove(s) }
    var usage by mutableStateOf<Usage?>(null)
    fun loadUsage() = viewModelScope.launch { runCatching { api.usage() }.onSuccess { usage = it } }
    var preview by mutableStateOf<Pair<String, String>?>(null)   // (url, title) для полноэкранного превью

    // ---------- файлы ----------
    fun attach(uris: List<Uri>) {
        val cr = getApplication<Application>().contentResolver
        uris.forEach { uri ->
            viewModelScope.launch {
                uploading++
                try {
                    var name = "file"; var size = -1L
                    cr.query(uri, null, null, null, null)?.use { c ->
                        if (c.moveToFirst()) {
                            c.getColumnIndex(OpenableColumns.DISPLAY_NAME).takeIf { it >= 0 }?.let { name = c.getString(it) ?: name }
                            c.getColumnIndex(OpenableColumns.SIZE).takeIf { it >= 0 }?.let { size = c.getLong(it) }
                        }
                    }
                    var mime = cr.getType(uri) ?: "application/octet-stream"
                    var small: ByteArray? = null
                    if (mime.startsWith("image/") && mime != "image/gif") small = withContext(Dispatchers.IO) { shrinkImage(cr, uri) }
                    if (small != null) { mime = "image/jpeg"; name = name.substringBeforeLast('.') + ".jpg"; size = small.size.toLong() }
                    val body = if (small != null) small.toRequestBody("image/jpeg".toMediaType()) else object : RequestBody() {
                        override fun contentType() = mime.toMediaTypeOrNull()
                        override fun contentLength() = size
                        override fun writeTo(sink: BufferedSink) { cr.openInputStream(uri)!!.use { sink.writeAll(it.source()) } }
                    }
                    uploadTotal += maxOf(size, 0L)
                    attachments.add(api.upload(name, mime, counting(body)))
                } catch (e: Throwable) { err(e) } finally { uploading--; if (uploading == 0) { uploadTotal = 0L; uploadSent = 0L; uploadPct = 0f } }
            }
        }
    }
    // прогресс отправки файлов (общий по всем загружаемым)
    var uploadPct by mutableStateOf(0f)
    private var uploadTotal = 0L
    private var uploadSent = 0L
    private fun counting(body: RequestBody): RequestBody = object : RequestBody() {
        override fun contentType() = body.contentType()
        override fun contentLength() = body.contentLength()
        override fun writeTo(sink: BufferedSink) {
            val cs = object : okio.ForwardingSink(sink) {
                override fun write(source: okio.Buffer, byteCount: Long) { super.write(source, byteCount); uploadSent += byteCount; if (uploadTotal > 0) uploadPct = (uploadSent.toFloat() / uploadTotal).coerceIn(0f, 1f) }
            }.buffer()
            body.writeTo(cs); cs.flush()
        }
    }
    private fun shrinkImage(cr: android.content.ContentResolver, uri: Uri): ByteArray? = runCatching {
        val bytes = cr.openInputStream(uri)!!.use { it.readBytes() }                  // один раз читаем (облачные URI не скачиваются повторно)
        if (bytes.size > 80_000_000) return@runCatching null
        val o = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
        android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size, o)
        var sample = 1; while (maxOf(o.outWidth, o.outHeight) / (sample * 2) >= 1600) sample *= 2      // декодируем сразу уменьшенным — быстро и мало памяти
        var bmp = android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size, android.graphics.BitmapFactory.Options().apply { inSampleSize = sample }) ?: return@runCatching null
        val rot = runCatching { androidx.exifinterface.media.ExifInterface(java.io.ByteArrayInputStream(bytes)).rotationDegrees }.getOrDefault(0)
        val k = 1600f / maxOf(bmp.width, bmp.height)
        if (k < 1f || rot != 0) {
            val m = android.graphics.Matrix().apply { if (k < 1f) postScale(k, k); if (rot != 0) postRotate(rot.toFloat()) }
            bmp = android.graphics.Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, m, true)
        }
        val out = java.io.ByteArrayOutputStream(); bmp.compress(android.graphics.Bitmap.CompressFormat.JPEG, 82, out); out.toByteArray()
    }.getOrNull()
    fun removeAttachment(a: Attach) { attachments.remove(a) }

    /** Большие файлы качает системный менеджер загрузок: фоном, с докачкой при обрыве, прогрессом в шторке и сохранением в «Загрузки». */
    private fun bigDownload(a: Attach): Boolean = runCatching {
        val ctx = getApplication<Application>()
        val dm = ctx.getSystemService(Context.DOWNLOAD_SERVICE) as android.app.DownloadManager
        val name = a.name.replace(Regex("[/\\\\:*?\"<>|]"), "_").ifBlank { "file" }
        val r = android.app.DownloadManager.Request(android.net.Uri.parse(api.base + "/api/files/" + a.id))
            .addRequestHeader("Authorization", "Bearer " + (store.token ?: ""))
            .setTitle(name).setDescription("OpenAgent")
            .setNotificationVisibility(android.app.DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setAllowedOverMetered(true).setAllowedOverRoaming(true)
        if (a.mime.isNotBlank()) r.setMimeType(a.mime)
        if (android.os.Build.VERSION.SDK_INT >= 29) r.setDestinationInExternalPublicDir(android.os.Environment.DIRECTORY_DOWNLOADS, name)
        else r.setDestinationInExternalFilesDir(ctx, android.os.Environment.DIRECTORY_DOWNLOADS, name)
        dm.enqueue(r)
        toast = "Скачивание ${name} (${a.size / 1_000_000} МБ) идёт в фоне — прогресс в шторке, файл появится в «Загрузки»"
        true
    }.getOrDefault(false)

    fun openFile(a: Attach) = viewModelScope.launch {
        if (a.size > 20_000_000 && bigDownload(a)) return@launch
        toast = "Скачиваю ${a.name}…"
        runCatching {
            val ctx = getApplication<Application>()
            runCatching { File(ctx.cacheDir, "dl").listFiles()?.filter { System.currentTimeMillis() - it.lastModified() > 86_400_000L }?.forEach { it.delete() } }   // старые скачанные копии не копим
            val f = api.download(a.id, a.name, File(ctx.cacheDir, "dl"))
            val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
            val mime = if (a.name.endsWith(".apk")) "application/vnd.android.package-archive" else a.mime.ifBlank { "*/*" }
            val i = Intent(Intent.ACTION_VIEW).setDataAndType(uri, mime).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
            runCatching { ctx.startActivity(i) }.onFailure {
                ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType(mime).putExtra(Intent.EXTRA_STREAM, uri)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), a.name).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            toast = null
        }.onFailure(::err)
    }

    // ---------- диктовка ----------
    var dictating by mutableStateOf(false); internal set
    var dictLevel by mutableStateOf(0f); private set
    var dictBusy by mutableStateOf(false); private set
    private var dictJob: Job? = null

    var dictPartial by mutableStateOf(""); private set
    private var dictRt: RtSession? = null
    fun startDictation(): Boolean {
        if (fastSttOn && rtOk) {                                  // диктовка тоже через Deepgram: текст виден по мере речи
            val lang = if (sttLang == "auto") "ru" else sttLang
            val rt = RtSession(getApplication(), api.sttSocket(lang, 1500), api.wsClient, { dictLevel = it }, { dictPartial = it })
            if (rt.start()) { dictRt = rt; dictating = true; dictPartial = ""; return true }
            rtOk = false
        }
        if (!recorder.start()) { toast = "Не удалось включить микрофон"; return false }
        dictating = true
        dictJob = viewModelScope.launch { while (isActive) { dictLevel = recorder.level(); delay(60) } }
        return true
    }
    fun finishDictation(onText: (String) -> Unit) {
        val rt = dictRt
        if (rt != null) {
            dictRt = null; dictating = false; dictLevel = 0f; dictBusy = true
            viewModelScope.launch {
                val live = runCatching { rt.finish() }.getOrDefault("")
                val t = if (live.isBlank()) live else refined(rt, live)
                val e = rt.error; rt.cancel(); dictPartial = ""; dictBusy = false
                if (t.isNotBlank()) onText(t) else if (e != null) toast = "Распознавание: $e"
            }
            return
        }
        dictJob?.cancel(); dictating = false; dictLevel = 0f
        val f = recorder.stop() ?: return
        viewModelScope.launch {
            dictBusy = true
            runCatching { api.stt(f, if (sttLang == "auto") "ru" else sttLang) }.onSuccess { if (it.isNotBlank()) onText(it) }.onFailure(::err)
            f.delete(); dictBusy = false
        }
    }
    fun cancelDictation() { dictRt?.cancel(); dictRt = null; dictPartial = ""; dictJob?.cancel(); dictating = false; dictLevel = 0f; recorder.cancel() }

    // ---------- голос (выбор) ----------
    var voiceId by mutableStateOf("")
    var voiceName by mutableStateOf("Спокойный женский голос")
    val voices = mutableStateListOf<VoiceInfo>()
    var voicesLoading by mutableStateOf(false)
    fun loadCurrentVoice() = viewModelScope.launch { runCatching { api.currentVoice() }.onSuccess { voiceId = it.id; voiceName = it.name } }
    fun searchVoices(q: String, lang: String) = viewModelScope.launch {
        voicesLoading = true
        runCatching { api.voices(q, lang, 1) }.onSuccess { voices.clear(); voices.addAll(it) }.onFailure(::err)
        voicesLoading = false
    }
    fun chooseVoice(v: VoiceInfo) = viewModelScope.launch {
        runCatching { api.setVoice(v.id, v.title) }.onSuccess { voiceId = v.id; voiceName = v.title; toast = "Голос: ${v.title}" }.onFailure(::err)
    }
    private var previewJob: Job? = null
    fun previewVoice(v: VoiceInfo) {
        previewJob?.cancel(); player.stop()
        val url = v.sample ?: return
        previewJob = viewModelScope.launch {
            runCatching {
                val f = withContext(Dispatchers.IO) { File(getApplication<Application>().cacheDir, "pv_${System.nanoTime()}.mp3").also { out -> java.net.URL(url).openStream().use { i -> out.outputStream().use { o -> i.copyTo(o) } } } }
                player.play(f); f.delete()
            }.onFailure { if (it !is CancellationException) err(it) }
        }
    }
    fun stopPreview() { previewJob?.cancel(); player.stop() }

    // ---------- озвучка: нарезка на фразы и конвейер ----------
    /** Режет поток текста на куски растущего размера: первый короткий (быстрый старт), дальше длиннее (меньше швов и пауз). */
    private class Chunker(val out: Channel<String>) {
        private val buf = StringBuilder(); private var n = 0
        private fun target() = when (n) { 0 -> 10; 1 -> 45; 2 -> 90; else -> 130 }
        fun push(t: String) {
            buf.append(t.replace(Regex("[•·▪●○◦►▶■□→✓✔★☆*_#`~]"), " "))
            // списки/переносы строк → связный поток предложений: без крошечных кусков и пауз между пунктами
            val flat = Regex("[ \\t]*\\n+[ \\t]*").replace(buf) { m -> val i = m.range.first; if (i > 0 && buf[i - 1] in ".!?…:;,") " " else ". " }
            if (flat.length != buf.length || flat != buf.toString()) { buf.setLength(0); buf.append(flat) }
            while (true) {
                val min = target()
                var cut = -1
                val enders = if (n == 0) ".!?…,;:" else ".!?…"    // первый кусок режем и по запятой — озвучка стартует раньше
                for (i in (min - 1).coerceAtLeast(0) until buf.length - 1) {
                    if (buf[i] in enders && buf[i + 1].isWhitespace()) { cut = i; break }
                }
                if (cut < 0 && n == 0 && buf.length >= 38) cut = buf.lastIndexOf(' ', 38).takeIf { it >= 16 } ?: -1   // первую фразу без знаков препинания режем рано — озвучка стартует быстрее
                if (cut < 0 && buf.length >= min * 2 + 60) cut = buf.lastIndexOfAny(charArrayOf(',', ' '), min * 2 + 40).takeIf { it > min } ?: -1
                if (cut < 0) break
                val s = buf.substring(0, cut + 1).trim(); buf.delete(0, cut + 1)
                if (s.isNotBlank()) { out.trySend(s); n++ }
            }
        }
        fun flush() { val s = buf.toString().trim(); if (s.isNotBlank()) out.trySend(s); buf.clear(); out.close() }
    }

    /** Загружает озвучку на 3 куска вперёд и играет строго по порядку, голос всегда один и тот же. */
    private val pcmOk get() = health?.features?.contains("tts-pcm") == true && pcmFailures < 2
    private var pcmFailures = 0
    /** Основной путь озвучки: сырой звук в AudioTrack (быстрый старт, точный конец). Запасной — прежний путь через плеер. */
    private suspend fun playQueuePcm(q: Channel<String>, interrupted: () -> Boolean, onStart: () -> Unit) = coroutineScope {
        val chunks = Channel<ReceiveChannel<ByteArray>>(3)
        val fetcher = launch {
            for (s in q) {
                if (!s.any { it.isLetterOrDigit() }) continue
                val ch = Channel<ByteArray>(Channel.UNLIMITED)
                chunks.send(ch)                                    // порядок кусков фиксируем сразу, байты придут позже
                launch(Dispatchers.IO) {
                    runCatching { api.ttsPcm(s, voiceId) { ch.trySend(it) } }.onFailure { if (++pcmFailures == 2) toast = "Озвучка недоступна — проверьте FISH_API_KEY и обновите сервер" }
                    ch.close()
                }
            }
            chunks.close()
        }
        try { player.pcm.play(chunks, interrupted, onStart) } finally { fetcher.cancel() }
    }

    private suspend fun playQueue(q: Channel<String>, interrupted: () -> Boolean, onStart: () -> Unit) = coroutineScope {
        if (pcmOk) { playQueuePcm(q, interrupted, onStart); return@coroutineScope }
        val app = getApplication<Application>()
        val streaming = api.ttsStreamSupported()
        var ttsFailed = 0
        val ready = Channel<Deferred<android.media.MediaPlayer?>>(2)
        val fetcher = launch {
            for (s in q) {
                ready.send(async {
                    if (!s.any { it.isLetterOrDigit() }) null else {
                        // потоковая озвучка: плеер стартует с первыми байтами; при сбое — старый путь через файл
                        val (url, h) = api.ttsStream(s, voiceId)
                        (if (streaming) withTimeoutOrNull(6000) { player.prepareRemote(app, url, h) } else null) ?: runCatching {
                            api.tts(s, File(app.cacheDir, "v_${System.nanoTime()}.mp3"), voiceId)?.let { f -> withContext(Dispatchers.IO) { player.prepare(f) }.also { f.delete() } }
                        }.onFailure { err(it) }.getOrNull().also { if (it == null && ++ttsFailed == 2) toast = "Озвучка недоступна — проверьте FISH_API_KEY и обновите сервер" }
                    }
                })
            }
            ready.close()
        }
        try {
            for (d in ready) {
                val p = d.await() ?: continue
                if (interrupted()) { runCatching { p.release() }; continue }
                onStart(); player.playPrepared(p)
            }
        } finally {
            fetcher.cancel()
            while (true) { val d = ready.tryReceive().getOrNull() ?: break; runCatching { if (d.isCompleted) d.getCompleted()?.release() else d.cancel() } }
        }
    }

    // ---------- озвучка сообщений ----------
    var speakingId by mutableStateOf<Long?>(null); private set
    private var speakJob: Job? = null

    fun toggleSpeak(m: Msg) {
        if (speakingId == m.id) { stopSpeaking(); return }
        stopSpeaking(); stopPreview()
        speakingId = m.id
        speakJob = viewModelScope.launch {
            try {
                val q = Channel<String>(Channel.UNLIMITED)
                Chunker(q).apply { push(m.content.replace(Regex("```[\\s\\S]*?```"), " ") + "\n"); flush() }
                playQueue(q, { false }) {}
            } catch (e: CancellationException) { throw e } catch (e: Throwable) { err(e) }
            finally { if (speakingId == m.id) speakingId = null }
        }
    }
    fun stopSpeaking() { speakJob?.cancel(); player.stop(); speakingId = null }

    // ---------- голосовой режим ----------
    var voiceState by mutableStateOf(VoiceState.Idle); internal set
    var voiceLevel by mutableStateOf(0f); internal set
    var voiceCaption by mutableStateOf("")
    var voiceReply by mutableStateOf("")
    var voiceStats by mutableStateOf("")      // тайминги последнего ответа (после распознавания): помогает понять, где теряется время
    private var voiceJob: Job? = null

    fun startVoice() {
        if (offlineMode) { toast = "Голосовой звонок работает только с интернетом — в оффлайн-режиме пишите текстом"; return }
        if (voiceJob?.isActive != true && needGate()) { if (!gateOpen) requireGate { startVoice() }; return }
        if (serverOld && !oldWarned) { oldWarned = true; toast = "Сервер не обновлён: звонок и распознавание будут медленнее. Запустите ./deploy/deploy.sh" }
        screen = Screen.Voice
        if (voiceJob?.isActive == true) return
        VoiceService.start(getApplication()) { stopVoice() }
        ClapState.paused = true
        stopSpeaking()
        voiceJob = viewModelScope.launch {
            try { if (agentVoiceOk) agentVoiceLoop() else voiceLoop() } catch (e: CancellationException) { throw e } catch (e: Throwable) { err(e) }
            finally { recorder.cancel(); player.stop(); voiceState = VoiceState.Idle; voiceLevel = 0f }
        }
    }
    // ---- голосовой агент: Deepgram Voice Agent (Claude Haiku 4.5 + голос «Владимир»); если сервер/ключ не поддерживает — прежний режим ----
    // ---- камера и переводчик в звонке ----
    var cameraOn by mutableStateOf(false)
    var cameraFront by mutableStateOf(false)
    var translateTo by mutableStateOf("")            // "" — обычный режим; "en", "es", "fr", "de", "it", "nl", "ja" — синхронный перевод русский ↔ язык
    /** Меняет режим перевода; идущий звонок перезапускается с новым режимом. */
    fun setTranslate(to: String) {
        if (translateTo == to) return
        translateTo = to
        if (voiceJob?.isActive == true) { runCatching { agentSession?.cancel() }; agentSession = null; voiceJob?.cancel(); voiceJob = null; startVoice() }
    }
    private suspend fun cameraFrame(): String {
        val f = CallCamera.takeFrame(getApplication()) ?: return "Камера в звонке выключена или не готова. Скажи пользователю включить камеру кнопкой в окне звонка."
        val up = api.upload(f.name, "image/jpeg", f.asRequestBody("image/jpeg".toMediaType()))
        return "screenshot:${up.id}"
    }
    private var agentFailed = false
    var clapWake by mutableStateOf(store.clapWake)
    var clapSens by mutableStateOf(store.clapSens)
    fun updClapWake(v: Boolean) { clapWake = v; store.clapWake = v; if (v) ClapService.start(getApplication()) else ClapService.stop(getApplication()) }
    fun updClapSens(v: String) { clapSens = v; store.clapSens = v }
    var voiceMode by mutableStateOf(store.voiceMode)           // "agent" | "gigaam"
    /** Переключение режима голоса; идущий звонок перезапускается в новом режиме. */
    fun chooseVoiceMode(m: String) {
        if (voiceMode == m) return
        voiceMode = m; store.voiceMode = m
        if (voiceJob?.isActive == true) { runCatching { agentSession?.cancel() }; agentSession = null; voiceJob?.cancel(); voiceJob = null; startVoice() }
    }
    val gigaamAvailable get() = health?.features?.contains("stt-gigaam") == true
    private val agentVoiceOk get() = !agentFailed && voiceMode == "agent" && health?.features?.contains("voice-agent") == true
    @Volatile private var agentSession: AgentVoiceSession? = null
    private suspend fun agentVoiceLoop() {
        val lang = if (sttLang == "auto") "ru" else sttLang
        voiceState = VoiceState.Idle; voiceCaption = ""; voiceReply = ""
        val s = AgentVoiceSession(api.voiceAgentSocket(lang, translateTo), api.wsClient,
            onState = { voiceState = it },
            onUser = { voiceCaption = it; voiceReply = "" },
            onAgent = { voiceReply = it },
            onLevel = { if (voiceState == VoiceState.Listening) voiceLevel = it },
            onPhone = { id, args -> viewModelScope.launch {
                val a = kotlinx.serialization.json.Json.parseToJsonElement(args.toString()) as kotlinx.serialization.json.JsonObject
                val act = (a["action"] as? kotlinx.serialization.json.JsonPrimitive)?.content
                val res = when (act) {
                    "screen" -> runCatching { grabScreen() }.getOrElse { "Не удалось сделать снимок экрана: ${it.message}" }
                    "camera_frame" -> runCatching { cameraFrame() }.getOrElse { "Не удалось снять кадр: ${it.message}" }
                    else -> withContext(Dispatchers.Default) { PhoneControl.run(getApplication(), a) }
                }
                agentSession?.phoneResult(id, res)
            } },
            onStatus = { statusText = it },
        )
        agentSession = s
        try {
            if (!s.start()) { toast = "Нет доступа к микрофону"; stopVoice(); return }
            s.await()
            val e = s.error
            if (e != null && !s.ready) {                       // агент так и не запустился — возвращаемся к обычному голосовому режиму
                agentFailed = true; toast = "Голосовой агент недоступен: ${e.take(80)} — включён обычный режим"
                s.cancel(); agentSession = null
                voiceLoop()
            } else { if (e != null) toast = e.take(100); stopVoice() }
        } finally { s.cancel(); agentSession = null }
    }
    @Volatile private var typedVoiceText: String? = null
    /** Текст, набранный в окне звонка: обрабатывается как сказанная фраза (прерывает прослушивание/ответ). */
    fun voiceSendText(t: String) {
        val s = t.trim(); if (s.isBlank()) return
        agentSession?.let { it.sendText(s); voiceCaption = s; voiceMuted = false; it.setMuted(false); return }
        typedVoiceText = s; voiceMuted = false
        if (voiceJob?.isActive != true || voiceState == VoiceState.Listening) { voiceJob?.cancel(); voiceJob = null; startVoice() }
        else { stopRun(); player.stop(); interrupted = true }
    }
    /** Мьют: если сейчас слушаем — сразу прерываем прослушивание (иначе распознаватель продолжит слушать). */
    fun toggleMute() {
        voiceMuted = !voiceMuted
        agentSession?.let { it.setMuted(voiceMuted); return }
        if (voiceState == VoiceState.Listening) { voiceJob?.cancel(); voiceJob = null; startVoice() }
    }
    /** Полная остановка звонка: прослушивание, запись, озвучка и ещё идущий ответ — ничего не должно остаться в фоне. */
    fun stopVoice() {
        val wasActive = voiceJob?.isActive == true
        voiceJob?.cancel(); voiceJob = null
        VoiceService.stop(getApplication())
        ClapState.paused = false
        runCatching { recorder.cancel() }; runCatching { player.stop() }
        runCatching { agentSession?.cancel() }; agentSession = null
        if (wasActive && running) stopRun()
        onTurnText = null; onTurnDone = null; typedVoiceText = null
        voiceState = VoiceState.Idle; voiceLevel = 0f; voiceCaption = ""; voiceReply = ""; voiceMuted = false; cameraOn = false
        if (screen == Screen.Voice) screen = Screen.Chat
    }

    /** Тап по орбу: прервать речь/ответ и сразу слушать. */
    fun voiceInterrupt() {
        agentSession?.let { it.interrupt(); return }
        if (voiceState == VoiceState.Speaking || voiceState == VoiceState.Thinking) {
            stopRun(); player.stop(); interrupted = true
        }
    }
    @Volatile private var interrupted = false

    private var srvSttBad = false   // Google на устройстве — только если не работает и сервер (Deepgram)
    var accurateStt by mutableStateOf(store.accurateStt)
    fun updAccurateStt(v: Boolean) { accurateStt = v; store.accurateStt = v }
    /** Какой движок реально распознал последнюю фразу — показывается в настройках, чтобы было видно, не сработал ли запасной. */
    var sttEngine by mutableStateOf("")
    /** Потоковый текст — для подписи по мере речи; итоговый текст перераспознаём целым файлом (Deepgram) с заданным языком: заметно точнее. */
    private suspend fun refined(s: RtSession, live: String): String {
        sttEngine = "Deepgram" + (s.model.takeIf { it.isNotBlank() }?.let { " ($it)" } ?: "")
        if (!accurateStt) return live
        val wav = s.wav() ?: return live
        val lang = if (sttLang == "auto") "ru" else sttLang
        val t = withTimeoutOrNull(9000) { runCatching { api.sttWav(wav, lang) }.getOrNull() }?.trim().orEmpty()
        if (t.isBlank()) return live
        sttEngine = "Deepgram (файл, точный) + поток"
        return t
    }
    private val fastStt by lazy { FastStt(getApplication()) }
    private var fastOk = true
    private var rtOk = true
    /** Один сеанс потокового распознавания для звонка: слушаем до паузы (VAD на устройстве) и получаем итог от Deepgram. */
    private suspend fun rtListen(keepWhile: () -> Boolean = { true }): String {
        val lang = if (sttLang == "auto") "ru" else sttLang
        val s = RtSession(getApplication(), api.sttSocket(lang, silenceMs.toInt(), if (voiceMode == "gigaam") "gigaam" else ""), api.wsClient, { voiceLevel = it }, { voiceCaption = it })
        if (!s.start()) throw FastStt.Unavailable("микрофон занят")
        try {
            var total = 0; var quiet = 0; var spoke = false
            while (currentCoroutineContext().isActive) {
                delay(50); total += 50
                if (!keepWhile()) return ""
                s.error?.let { if (!spoke) throw FastStt.Unavailable(it) }
                if (s.level > micThreshold) { spoke = true; quiet = 0 } else if (spoke) quiet += 50
                if (spoke && (quiet >= silenceMs.toInt() || s.turnEnded || (s.eager && quiet >= 300))) break   // eager — ранний сигнал сервера «фраза, похоже, закончена»
                if (!spoke && total > 15000) return ""
                if (total > 60000) break
            }
            val live = s.finish()
            if (live.isNotBlank()) sttEngine = "Deepgram" + (s.model.takeIf { it.isNotBlank() }?.let { " ($it)" } ?: "")
            return live   // в звонке — без перераспознавания: скорость важнее (точный режим только для диктовки)
        } finally { s.cancel() }
    }
    var fastSttOn by mutableStateOf(store.fastStt)
    fun updFastStt(v: Boolean) { fastSttOn = v; store.fastStt = v; fastOk = true; rtOk = true; srvSttBad = false }

    private suspend fun voiceLoop() {
        while (currentCoroutineContext().isActive) {
            // 1. слушаем (быстро: распознавание на устройстве; запасной путь — запись + сервер)
            voiceState = VoiceState.Listening; voiceCaption = ""
            val typed = typedVoiceText; typedVoiceText = null
            if (typed == null && voiceMuted) { voiceLevel = 0f; delay(200); continue }
            var text = ""
            if (typed != null) { text = typed }
            else if (fastSttOn && rtOk) {                       // основной путь: Deepgram (поток, текст по мере речи)
                val r = tryC { rtListen() }
                voiceLevel = 0f
                if (r.isSuccess) { text = r.getOrNull().orEmpty().trim(); if (text.isBlank()) continue }
                else { rtOk = false; if (!serverOld) toast = "Потоковое распознавание недоступно: ${r.exceptionOrNull()?.message?.take(70)} — включён запасной вариант"; continue }
            }
            else if (srvSttBad && fastOk && fastStt.available()) {            // запасной путь 1: распознавание Google на устройстве
                sttEngine = "Google на устройстве (запасной)"
                val r = tryC { fastStt.listen(sttLang, { voiceLevel = it }, { voiceCaption = it }) }
                voiceLevel = 0f
                if (r.isSuccess) text = r.getOrNull().orEmpty().trim() else { fastOk = false; continue }
                if (text.isBlank()) continue
            } else {                                             // запасной путь 2: запись + сервер (Deepgram)
                val file = listenUtterance() ?: continue
                voiceState = VoiceState.Thinking
                sttEngine = "Deepgram (запись + сервер)"
                text = tryC { api.stt(file, if (sttLang == "auto") "ru" else sttLang) }.getOrElse { srvSttBad = true; err(it); delay(1500); "" }
                file.delete()
            }
            voiceState = VoiceState.Thinking
            if (text.isBlank()) continue
            voiceCaption = text
            // 3. отправляем и озвучиваем по предложениям по мере появления
            interrupted = false
            voiceReply = ""
            val q = Channel<String>(Channel.UNLIMITED)
            val chunker = Chunker(q)
            val tHeard = System.currentTimeMillis(); var tText = 0L; var statsSet = false
            onTurnText = { d -> if (tText == 0L) tText = System.currentTimeMillis(); voiceReply += d; chunker.push(d) }
            onTurnDone = { chunker.flush() }
            if (running) { stopRun(); while (running) delay(100) }
            send(text, voice = true)
            run {
                // пока агент молча работает (открывает приложения, ищет) — продолжаем слушать: можно перебить или уточнить голосом
                // (задания — отдельные, не дочерние: зависший микрофон/плеер не должен держать цикл звонка)
                val barge = viewModelScope.launch { bargeListen() }
                val tSend = System.currentTimeMillis()
                // страховка: как только агент закончил (running=false) — дочитываем остаток и закрываем очередь озвучки
                val watch = viewModelScope.launch { var seen = false; while (isActive) { delay(200); if (running) seen = true else if (seen || System.currentTimeMillis() - tSend > 10_000) { delay(600); chunker.flush(); break } } }
                val pq = viewModelScope.launch {
                    playQueue(q, { interrupted }) { voiceState = VoiceState.Speaking; if (!statsSet) { statsSet = true; val tA = System.currentTimeMillis(); voiceStats = "первое слово ${if (tText > 0) (tText - tHeard) / 100 / 10.0 else 0.0} с · до звука ${(tA - tHeard) / 100 / 10.0} с" } }
                }
                // жёсткая страховка: агент закончил, звук не играет, а озвучка всё ещё «идёт» — принудительно завершаем, чтобы звонок вернулся к прослушиванию
                val killer = viewModelScope.launch {
                    var idle = 0L
                    while (isActive) {
                        delay(300)
                        if (!running && !player.active()) idle += 300 else idle = 0L
                        if (idle >= (if (q.isClosedForSend) 3500L else 9000L)) { pq.cancel(); break }
                    }
                }
                try { pq.join() } finally { pq.cancel(); barge.cancel(); watch.cancel(); killer.cancel() }
            }
            onTurnText = null; onTurnDone = null
            if (interrupted) continue
        }
    }

    private suspend fun bargeListen() {
        while (currentCoroutineContext().isActive) {
            if (voiceState != VoiceState.Thinking || voiceMuted || !rtOk) { delay(250); continue }
            val t = tryC { rtListen { voiceState == VoiceState.Thinking } }.getOrNull().orEmpty().trim()
            if (t.isNotBlank() && voiceState == VoiceState.Thinking) { typedVoiceText = t; interrupted = true; stopRun(); player.stop(); return }
        }
    }

    /** Ждёт речь и тишину, возвращает файл записи (или null, если никто не говорил). */
    private suspend fun listenUtterance(): File? {
        if (!recorder.start()) { toast = "Нет доступа к микрофону"; stopVoice(); return null }
        var spoke = false; var quietMs = 0; var totalMs = 0
        while (currentCoroutineContext().isActive) {
            delay(60)
            val l = recorder.level(); voiceLevel = l
            totalMs += 60
            if (voiceMuted) { spoke = false; quietMs = 0; totalMs = 0; continue }
            if (l > micThreshold) { spoke = true; quietMs = 0 } else quietMs += 60
            if (spoke && quietMs >= silenceMs) break
            if (!spoke && totalMs > 30000) break
            if (totalMs > 60000) break
        }
        voiceLevel = 0f
        val f = recorder.stop()
        return if (spoke && f != null) f else { f?.delete(); null }
    }

    // ---------- автоматизации / навыки / файлы / терминал ----------
    // ---- подключения (MCP), заметки, задачи, секреты, сравнение, поделиться ----
    val mcpPresets = mutableStateListOf<McpPreset>(); val mcpServers = mutableStateListOf<McpServer>()
    var mcpBusy by mutableStateOf(false)
    fun loadMcp() = viewModelScope.launch { runCatching { api.mcp() }.onSuccess { mcpPresets.clear(); mcpPresets.addAll(it.presets); mcpServers.clear(); mcpServers.addAll(it.servers) }.onFailure(::err) }
    fun addMcp(name: String, url: String, token: String, header: String) = viewModelScope.launch {
        mcpBusy = true
        runCatching { api.addMcp(name, url, token, header) }.onSuccess { toast = if (it.error != null) "Добавлено, но: ${it.error}" else "Подключено · инструментов: ${it.tools.size}" }.onFailure(::err)
        mcpBusy = false; loadMcp().join()
    }
    fun toggleMcp(s: McpServer, on: Boolean) = viewModelScope.launch { runCatching { api.toggleMcp(s.id, on) }.onFailure(::err); loadMcp().join() }
    fun deleteMcp(s: McpServer) = viewModelScope.launch { runCatching { api.deleteMcp(s.id) }.onFailure(::err); loadMcp().join() }
    fun testMcp(s: McpServer) = viewModelScope.launch { mcpBusy = true; runCatching { api.testMcp(s.id) }.onSuccess { toast = if (it.error != null) "Ошибка: ${it.error}" else "Работает · инструментов: ${it.tools.size}" }.onFailure(::err); mcpBusy = false }
    var onboarding by mutableStateOf(!store.onboarded)
    fun loadProfile(done: (Profile) -> Unit) = viewModelScope.launch { runCatching { api.profile() }.onSuccess(done) }
    fun finishOnboarding(p: Profile?) {
        store.onboarded = true; onboarding = false
        if (p != null) { store.profileName = p.name; viewModelScope.launch { runCatching { api.saveProfile(p) }.onFailure(::err).onSuccess { toast = "Спасибо! Профиль сохранён" } } }
    }
    var callScreen by mutableStateOf(store.callScreen); var callDelay by mutableStateOf(store.callDelay)
    fun updCallScreen(v: Boolean) { callScreen = v; store.callScreen = v; val c = getApplication<Application>(); if (v) CallScreenService.start(c) else CallScreenService.stop(c) }
    fun updCallDelay(v: Int) { callDelay = v; store.callDelay = v }
    val missions = mutableStateListOf<MissionItem>()
    fun loadMissions() = viewModelScope.launch { runCatching { api.missions() }.onSuccess { missions.clear(); missions.addAll(it) }.onFailure(::err) }
    fun setMission(m: MissionItem, status: String) = viewModelScope.launch { runCatching { api.setMission(m.id, status) }.onFailure(::err); loadMissions().join() }
    fun deleteMission(m: MissionItem) = viewModelScope.launch { runCatching { api.deleteMission(m.id) }; missions.remove(m) }
    val mailAccounts = mutableStateListOf<MailAccount>(); var mailHint by mutableStateOf(""); var mailBusy by mutableStateOf(false)
    fun loadMail() = viewModelScope.launch { runCatching { api.mailAccounts() }.onSuccess { mailAccounts.clear(); mailAccounts.addAll(it) } }
    fun loadMailHint(email: String) = viewModelScope.launch { runCatching { api.mailHint(email) }.onSuccess { mailHint = it.hint } }
    fun addMail(email: String, pass: String, imap: String, smtp: String, done: (Boolean) -> Unit) = viewModelScope.launch {
        mailBusy = true
        val ok = runCatching { api.addMail(email.trim(), pass.trim(), imap.trim(), smtp.trim()) }.onFailure(::err).isSuccess
        mailBusy = false; if (ok) { toast = "Почта подключена"; loadMail().join() }; done(ok)
    }
    fun deleteMail(a: MailAccount) = viewModelScope.launch { runCatching { api.deleteMail(a.id) }; mailAccounts.remove(a) }
    val activity = mutableStateListOf<ActivityItem>()
    fun loadActivity() = viewModelScope.launch { runCatching { api.activity() }.onSuccess { activity.clear(); activity.addAll(it) }.onFailure(::err) }
    val notes = mutableStateListOf<NoteItem>(); var noteBusy by mutableStateOf(false)
    fun loadNotes() = viewModelScope.launch { runCatching { api.notes() }.onSuccess { notes.clear(); notes.addAll(it) }.onFailure(::err) }
    fun addNote(t: String) = viewModelScope.launch { runCatching { api.addNote(t) }.onFailure(::err); loadNotes().join() }
    fun noteFromAudio(f: File) = viewModelScope.launch { noteBusy = true; runCatching { api.noteAudio(f) }.onSuccess { toast = "Заметка сохранена" }.onFailure(::err); noteBusy = false; runCatching { f.delete() }; loadNotes().join() }
    fun deleteNote(n: NoteItem) = viewModelScope.launch { runCatching { api.deleteNote(n.id) }; notes.remove(n) }
    val todos = mutableStateListOf<TodoItem>()
    fun loadTodos() = viewModelScope.launch { runCatching { api.todos() }.onSuccess { todos.clear(); todos.addAll(it) }.onFailure(::err) }
    fun addTodo(t: String) = viewModelScope.launch { runCatching { api.addTodo(t) }.onFailure(::err); loadTodos().join() }
    fun setTodo(t: TodoItem, done: Boolean) = viewModelScope.launch { runCatching { api.setTodo(t.id, done) }.onFailure(::err); loadTodos().join() }
    fun deleteTodo(t: TodoItem) = viewModelScope.launch { runCatching { api.deleteTodo(t.id) }; todos.remove(t) }
    val secretNames = mutableStateListOf<String>()
    fun loadSecrets() = viewModelScope.launch { runCatching { api.secrets() }.onSuccess { secretNames.clear(); secretNames.addAll(it) }.onFailure(::err) }
    fun saveSecret(n: String, v: String) = viewModelScope.launch { runCatching { api.saveSecret(n, v) }.onFailure(::err); loadSecrets().join() }
    fun deleteSecret(n: String) = viewModelScope.launch { runCatching { api.deleteSecret(n) }; secretNames.remove(n) }
    fun shareChat(id: Int) = viewModelScope.launch {
        runCatching { api.shareChat(id) }.onSuccess { r ->
            val u = r.url ?: return@onSuccess; val ctx = getApplication<Application>()
            copyToClipboard(ctx, u); toast = "Ссылка скопирована"
            ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, u), "Поделиться чатом").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }.onFailure(::err)
    }
    var showCompare by mutableStateOf(false); var compareBusy by mutableStateOf(false); val compareOut = mutableStateListOf<CompareResult>()
    fun compare(text: String, targets: List<Pair<String, String>>) = viewModelScope.launch {
        compareBusy = true; compareOut.clear()
        runCatching { api.compare(text, targets) }.onSuccess { compareOut.addAll(it) }.onFailure(::err)
        compareBusy = false
    }
    var showResearch by mutableStateOf(false)
    fun deepResearch(topic: String) { newChat("chat"); effort = "high"; send("Проведи глубокое исследование: $topic\n\nИщи в нескольких источниках (web_search, затем web_fetch лучших страниц), сверяй факты между собой, отмечай противоречия и неопределённость. Итог: краткое резюме, ключевые находки списком, выводы и ссылки на источники.") }
    fun exportBackup() = viewModelScope.launch {
        runCatching {
            val ctx = getApplication<Application>(); val json = api.exportAll()
            val f = File(File(ctx.cacheDir, "dl").also { it.mkdirs() }, "openagent-backup.json").also { it.writeText(json) }
            val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
            ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("application/json").putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), "Резервная копия").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }.onFailure(::err)
    }
    fun addDaily(name: String, prompt: String, time: String, mode: String) = viewModelScope.launch { runCatching { api.addDaily(name, prompt, time, mode) }.onFailure(::err); loadSchedules().join() }
    fun addWatch(name: String, prompt: String, every: Int, url: String, text: String) = viewModelScope.launch { runCatching { api.addWatch(name, prompt, every, url, text) }.onFailure(::err); loadSchedules().join() }

    val schedules = mutableStateListOf<Schedule>()
    fun loadSchedules() = viewModelScope.launch { runCatching { api.schedules() }.onSuccess { schedules.clear(); schedules.addAll(it) }.onFailure(::err) }
    fun addSchedule(name: String, prompt: String, every: Int, mode: String, webhook: Boolean = false) = viewModelScope.launch { runCatching { api.addSchedule(name, prompt, if (webhook) null else every, mode, webhook) }.onFailure(::err); loadSchedules().join() }
    fun toggleSchedule(s: Schedule, on: Boolean) = viewModelScope.launch { runCatching { api.toggleSchedule(s.id, on) }; loadSchedules() }
    fun runSchedule(s: Schedule) = viewModelScope.launch { runCatching { api.runSchedule(s.id) }.onSuccess { toast = "Запущено — смотрите в списке чатов"; refreshConvs() }.onFailure(::err); loadSchedules() }
    fun deleteSchedule(s: Schedule) = viewModelScope.launch { runCatching { api.deleteSchedule(s.id) }; schedules.remove(s) }

    val skills = mutableStateListOf<Skill>()
    fun loadSkills() = viewModelScope.launch { runCatching { api.skills() }.onSuccess { skills.clear(); skills.addAll(it) }.onFailure(::err) }
    fun saveSkill(n: String, d: String, c: String) = viewModelScope.launch { runCatching { api.saveSkill(n, d, c) }.onFailure(::err); loadSkills().join() }
    val repoHits = mutableStateListOf<RepoHit>()
    var repoSearching by mutableStateOf(false)
    var installing by mutableStateOf<String?>(null)
    fun searchRepos(q: String) = viewModelScope.launch {
        repoSearching = true
        runCatching { api.searchSkills(q) }.onSuccess { repoHits.clear(); repoHits.addAll(it) }.onFailure(::err)
        repoSearching = false
    }
    fun installRepo(repo: String) = viewModelScope.launch {
        installing = repo
        runCatching { api.installSkill(repo) }.onSuccess {
            toast = if (it.installed.isEmpty()) "В ${it.repo} навыков не найдено" else "Установлено из ${it.repo}: ${it.installed.size} шт."
            Haptics.success(); loadSkills()
        }.onFailure(::err)
        installing = null
    }
    fun deleteSkill(s: Skill) = viewModelScope.launch { runCatching { api.deleteSkill(s.id) }; skills.remove(s) }

    var fsDir by mutableStateOf<FsList?>(null)
    var fsRoot by mutableStateOf("")
    var fsLoading by mutableStateOf(false)
    fun fsOpen(path: String) = viewModelScope.launch {
        fsLoading = true
        runCatching { api.fsList(path) }.onSuccess { fsDir = it; if (fsRoot.isEmpty()) fsRoot = it.path }.onFailure(::err)
        fsLoading = false
    }
    suspend fun fsReadFile(path: String): String? = runCatching { api.fsRead(path) }.onFailure(::err).getOrNull()
    fun fsSave(path: String, text: String) = viewModelScope.launch { runCatching { api.fsWrite(path, text) }.onSuccess { toast = "Сохранено" }.onFailure(::err) }
    fun fsRemove(path: String) = viewModelScope.launch { runCatching { api.fsDelete(path) }.onFailure(::err); fsDir?.let { fsOpen(it.path) } }
    fun fsShare(path: String, name: String) = viewModelScope.launch {
        runCatching {
            val ctx = getApplication<Application>()
            val f = api.fsDownload(path, name, File(ctx.cacheDir, "dl"))
            val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
            val mime = if (name.endsWith(".apk")) "application/vnd.android.package-archive" else "*/*"
            val i = Intent(Intent.ACTION_VIEW).setDataAndType(uri, mime).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
            runCatching { ctx.startActivity(i) }.onFailure {
                ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType(mime).putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), name).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
        }.onFailure(::err)
    }

    class TermLine(val text: String, val kind: Int) // 0 вывод, 1 команда, 2 ошибка
    val term = mutableStateListOf<TermLine>()
    var termCwd by mutableStateOf(".")
    var termBusy by mutableStateOf(false)
    private var termJob: Job? = null
    fun termRun(cmd: String) {
        if (cmd.isBlank() || termBusy) return
        term.add(TermLine("$cmd", 1)); termBusy = true
        termJob = viewModelScope.launch {
            val raw = StringBuilder()
            val idx = term.size; term.add(TermLine("", 0))
            try {
                val (cwd, rc) = api.runCommand(cmd, termCwd) { chunk ->
                    raw.append(chunk)
                    val shown = raw.toString().substringBefore("__OA_CWD__").trimEnd()
                    if (idx < term.size) term[idx] = TermLine(shown.takeLast(20000), 0)
                }
                termCwd = cwd
                if (rc != 0) term.add(TermLine("exit $rc", 2))
            } catch (e: CancellationException) { term.add(TermLine("прервано", 2)) } catch (e: Throwable) { term.add(TermLine(e.message ?: "ошибка", 2)) }
            finally { termBusy = false }
        }
    }
    fun termStop() { termJob?.cancel() }

    // ---------- GitHub / память ----------
    var device by mutableStateOf<DeviceCode?>(null); internal set
    private var ghJob: Job? = null
    fun githubLink() = viewModelScope.launch {
        runCatching { api.ghStart() }.onSuccess { d ->
            device = d
            ghJob?.cancel()
            ghJob = viewModelScope.launch {
                while (isActive) {
                    delay((d.interval.coerceAtLeast(5) * 1000).toLong())
                    val r = runCatching { api.ghPoll(d.deviceCode) }.getOrNull() ?: continue
                    if (r.status == "ok") { device = null; refreshMe(); toast = "GitHub привязан: ${r.login}"; break }
                    if (r.status == "error") { device = null; toast = "GitHub: ${r.error}"; break }
                }
            }
        }.onFailure(::err)
    }
    fun githubCancel() { ghJob?.cancel(); device = null }
    fun githubToken(t: String) = viewModelScope.launch { runCatching { api.ghToken(t.trim()) }.onSuccess { toast = "GitHub привязан: $it"; refreshMe() }.onFailure(::err) }
    fun githubUnlink() = viewModelScope.launch { runCatching { api.ghUnlink() }; refreshMe() }

    val memories = mutableStateListOf<Mem>()
    fun loadMemories() = viewModelScope.launch { runCatching { api.memories() }.onSuccess { memories.clear(); memories.addAll(it) }.onFailure(::err) }
    fun deleteMemory(m: Mem) = viewModelScope.launch { runCatching { api.deleteMemory(m.id) }; memories.remove(m) }
    fun clearMemories() = viewModelScope.launch { runCatching { api.clearMemories() }.onFailure(::err); memories.clear() }
    fun addMemory(t: String) = viewModelScope.launch { runCatching { api.addMemory(t) }.onFailure(::err); loadMemories() }

    override fun onCleared() { recorder.cancel(); player.stop() }
}

