package openagent.app.com

import android.content.Context
import kotlinx.coroutines.*
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import okio.source
import java.util.concurrent.TimeUnit

@Serializable data class AuthConfig(val captchaUrl: String? = null, val googleClientId: String? = null, val githubDeviceFlow: Boolean = false)
@Serializable data class User(val id: Int, val email: String, val name: String? = null, val role: String = "user", val github: String? = null)
@Serializable data class AuthResp(val token: String, val user: User)
@Serializable data class Conv(val id: Int, val title: String, val mode: String = "chat", val pinned: Boolean = false, val persona: String = "", val projectId: Int? = null, val updatedAt: Long = 0, val running: Boolean = false)
@Serializable data class ToolCall(val id: String, val name: String, val args: String = "")
@Serializable data class Attach(val id: String, val name: String, val mime: String = "", val size: Long = 0, val caption: String? = null)
@Serializable data class Msg(
    val id: Long, val role: String, val content: String = "",
    val toolCalls: List<ToolCall>? = null, val toolCallId: String? = null, val toolName: String? = null,
    val attachments: List<Attach>? = null, val createdAt: Long = 0,
    val cid: Long = 0,   // только на устройстве: ключ «оптимистичного» сообщения, чтобы при замене настоящим оно не мигало и не дублировалось
)
@Serializable data class MsgsResp(val messages: List<Msg>, val running: Boolean = false, val partial: String = "", val mode: String = "chat", val incremental: Boolean = false, val hasMore: Boolean = false)
@Serializable data class ChatHit(val id: Int, val title: String, val mode: String = "chat", val snippet: String = "")
@Serializable data class ChatExport(val name: String, val markdown: String)
@Serializable data class ProviderAdded(val id: String, val models: List<String> = emptyList(), val warning: String? = null)
@Serializable data class ProviderPreset(val name: String, val baseUrl: String, val models: String = "", val keyUrl: String = "", val note: String? = null)
@Serializable data class SnippetResult(val output: String = "", val exit: Int = 0)
@Serializable data class SysMem(val total: Long = 0, val used: Long = 0, val swapTotal: Long = 0, val swapUsed: Long = 0)
@Serializable data class SysDisk(val total: Long = 0, val used: Long = 0, val percent: Int = 0)
@Serializable data class SysProc(val pid: Int = 0, val name: String = "", val cpu: Double = 0.0, val mem: Double = 0.0)
@Serializable data class SysService(val name: String, val active: String = "")
@Serializable data class SysInfo(val host: String = "", val uptime: Double = 0.0, val load: List<Double> = emptyList(), val cores: Int = 1, val cpu: Int? = null, val mem: SysMem = SysMem(), val disk: SysDisk? = null,
    val procs: List<SysProc> = emptyList(), val ports: List<String> = emptyList(), val services: List<SysService> = emptyList())
@Serializable data class GitFile(val code: String = "", val file: String = "")
@Serializable data class GitCommit(val hash: String = "", val subject: String = "", val author: String = "", @SerialName("when") val ago: String = "")
@Serializable data class GitInfo(val repo: Boolean = false, val path: String = "", val branch: String = "", val status: List<GitFile> = emptyList(), val log: List<GitCommit> = emptyList(), val remote: String = "", val ahead: Int = 0, val behind: Int = 0, val diffstat: String = "")
@Serializable data class GitResult(val ok: Boolean = false, val output: String = "")
@Serializable data class GitRepo(val path: String = "", val name: String = "")
@Serializable data class UpdateItem(val id: Int, val title: String = "", val updatedAt: Long = 0, val preview: String = "")
@Serializable data class Checkpoint(val hash: String, val subject: String = "", val ts: Long = 0, val files: Int = 0, val ins: Int = 0, val del: Int = 0)
@Serializable data class CheckpointFile(val code: String = "", val file: String = "")
@Serializable data class Project(val id: Int, val name: String, val slug: String = "", val repo: String? = null, val chats: Int = 0, val files: Int = 0)
@Serializable data class PromptItem(val id: Int, val name: String, val text: String)
@Serializable data class Created(val id: Int = 0, val hookUrl: String? = null, val slug: String? = null)
@Serializable data class Site(val slug: String, val title: String = "", val kind: String = "site", val size: Long = 0, val url: String, val updatedAt: Long = 0)
@Serializable data class UsageDay(val prompt: Long = 0, val completion: Long = 0, val calls: Int = 0, val cached: Long = 0)
@Serializable data class Usage(val today: UsageDay = UsageDay(), val week: UsageDay = UsageDay())
@Serializable data class Mem(val id: Int, val content: String, val kind: String = "fact", val importance: Double = 0.5, @SerialName("updated_at") val updatedAt: Long = 0)
@Serializable data class DeviceCode(
    @SerialName("device_code") val deviceCode: String = "", @SerialName("user_code") val userCode: String = "",
    @SerialName("verification_uri") val verificationUri: String = "", val interval: Int = 5,
)
@Serializable data class GhPoll(val status: String, val login: String? = null, val error: String? = null)

@Serializable data class ProviderInfo(val id: String, val name: String, val builtin: Boolean = false, val baseUrl: String = "", val effort: Boolean = false, val keyHint: String? = null, val models: List<String> = emptyList())
@Serializable data class Schedule(val id: Int, val name: String, val prompt: String, val mode: String = "code", val everyMin: Int? = null, val nextRun: Long? = null, val enabled: Boolean = true, val lastRun: Long? = null, val runs: Int = 0, val hookUrl: String? = null, val watchUrl: String? = null)
@Serializable data class McpPreset(val id: String, val name: String, val desc: String = "", val url: String = "", val auth: String = "none", val hint: String = "")
@Serializable data class McpServer(val id: Int, val name: String, val url: String = "", val enabled: Boolean = true, val auth: Boolean = false)
@Serializable data class McpList(val presets: List<McpPreset> = emptyList(), val servers: List<McpServer> = emptyList())
@Serializable data class McpResult(val id: Int = 0, val tools: List<String> = emptyList(), val error: String? = null)
@Serializable data class NoteItem(val id: Int, val title: String = "", val text: String = "", val summary: String? = null, val source: String = "text", val updatedAt: Long = 0)
@Serializable data class TodoItem(val id: Int, val text: String, val done: Boolean = false, val due: Long? = null)
@Serializable data class ActivityItem(val ts: Long = 0, val convId: Int = 0, val title: String = "", val tool: String = "", val summary: String = "", val outward: Boolean = false)
@Serializable data class MissionItem(val id: Int, val goal: String = "", val status: String = "active", val notes: String = "", val everyMin: Int = 60, val steps: Int = 0, val updatedAt: Long = 0)
@Serializable data class MailAccount(val id: Int, val email: String = "", val imapHost: String = "")
@Serializable data class MailHint(val hint: String = "", val known: Boolean = false)
@Serializable data class Profile(val name: String = "", val city: String = "", val home: String = "", val job: String = "", val interests: String = "", val about: String = "", val style: String = "", val address: String = "", val humor: String = "")
@Serializable data class UrlResp(val url: String? = null)
@Serializable data class CompareResult(val provider: String? = null, val model: String = "", val label: String = "", val text: String? = null, val error: String? = null, val ms: Long = 0)
@Serializable data class Skill(val id: Int, val name: String, val description: String = "", val content: String = "", val source: String? = null)
@Serializable data class RepoHit(val repo: String, val description: String = "", val stars: Int = 0, val topics: List<String> = emptyList(), val url: String = "")
@Serializable data class InstallResult(val repo: String = "", val installed: List<String> = emptyList(), val skipped: List<String> = emptyList(), val note: String? = null)
@Serializable data class FsItem(val name: String, val dir: Boolean, val size: Long = 0, val mtime: Double = 0.0)
@Serializable data class FsList(val path: String, val parent: String = "", val items: List<FsItem> = emptyList())

@Serializable data class VoiceInfo(val id: String, val title: String, val description: String = "", val languages: List<String> = emptyList(), val sample: String? = null, val uses: Long = 0)
@Serializable data class CurrentVoice(val id: String, val name: String)

sealed interface StreamEvent {
    data class Snapshot(val partial: String) : StreamEvent
    data class Delta(val text: String) : StreamEvent
    data class Message(val msg: Msg) : StreamEvent
    data class ToolOutput(val id: String, val text: String) : StreamEvent
    data class Status(val text: String) : StreamEvent
    data class Checkpoint(val hash: String, val changed: Int) : StreamEvent
    data class Phone(val id: String, val args: JsonObject) : StreamEvent
    data class Replace(val id: Long, val content: String) : StreamEvent
    data class Flush(val done: CompletableDeferred<Unit>) : StreamEvent
    data object Done : StreamEvent
    data class Error(val text: String) : StreamEvent
}

@Serializable data class Health(val ok: Boolean = true, val v: Int = 0, val features: List<String> = emptyList())
@Serializable data class DiagTiming(val ms: Long = 0, val model: String? = null, val error: String? = null)
@Serializable data class Diag(val v: Int = 0, val keys: Map<String, Boolean> = emptyMap(), val llm: DiagTiming = DiagTiming(), val tts: DiagTiming = DiagTiming(), val stt: DiagTiming = DiagTiming(), val hints: List<String> = emptyList())

/** Модель по умолчанию — DeepSeek V4.1 Flash на river.ai (режима «Авто» больше нет). */
const val DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash"

class ApiException(message: String, val code: Int = 0) : Exception(message)

val JSON = Json { ignoreUnknownKeys = true; coerceInputValues = true; explicitNulls = false; encodeDefaults = true }

class Store(ctx: Context) {
    private val p = ctx.getSharedPreferences("openagent", Context.MODE_PRIVATE)
    var token: String? get() = p.getString("token", null); set(v) = p.edit().putString("token", v).apply()
    var server: String
        get() = p.getString("server", null) ?: BuildConfig.SERVER_URL
        set(v) = p.edit().putString("server", v.trim().trimEnd('/')).apply()
    var autoSpeak: Boolean get() = p.getBoolean("autospeak", false); set(v) = p.edit().putBoolean("autospeak", v).apply()
    var pplxKey: String get() = p.getString("pplxKey", "") ?: ""; set(v) = p.edit().putString("pplxKey", v.trim()).apply()
    var searchProvider: String get() = p.getString("searchProv", "auto") ?: "auto"; set(v) = p.edit().putString("searchProv", v).apply()
    var groqKey: String get() = p.getString("groqKey", "") ?: ""; set(v) = p.edit().putString("groqKey", v.trim()).apply()
    var groqOn: Boolean get() = p.getBoolean("groqOn", true); set(v) = p.edit().putBoolean("groqOn", v).apply()
    var onboarded: Boolean get() = p.getBoolean("onboarded", false); set(v) = p.edit().putBoolean("onboarded", v).apply()
    var profileName: String get() = p.getString("profileName", "") ?: ""; set(v) = p.edit().putString("profileName", v).apply()
    var callScreen: Boolean get() = p.getBoolean("callScreen", false); set(v) = p.edit().putBoolean("callScreen", v).apply()
    var callDelay: Int get() = p.getInt("callDelay", 15); set(v) = p.edit().putInt("callDelay", v).apply()
    var accurateStt: Boolean get() = p.getBoolean("accurateStt", false); set(v) = p.edit().putBoolean("accurateStt", v).apply()
    var fastStt: Boolean get() = p.getBoolean("fastStt", true); set(v) = p.edit().putBoolean("fastStt", v).apply()
    var amoled: Boolean get() = p.getBoolean("amoled", false); set(v) = p.edit().putBoolean("amoled", v).apply()
    var dynamicColor: Boolean get() = p.getBoolean("dynamic", false); set(v) = p.edit().putBoolean("dynamic", v).apply()
    var haptics: Boolean get() = p.getBoolean("haptics", true); set(v) = p.edit().putBoolean("haptics", v).apply()
    var fontScale: Float get() = p.getFloat("fontScale", 1f); set(v) = p.edit().putFloat("fontScale", v).apply()
    var provider: String get() = p.getString("provider", "river") ?: "river"; set(v) = p.edit().putString("provider", v).apply()
    var model: String get() = p.getString("model", DEFAULT_MODEL) ?: DEFAULT_MODEL; set(v) = p.edit().putString("model", v).apply()
    var notifyAuto: Boolean get() = p.getBoolean("notifyAuto", true); set(v) = p.edit().putBoolean("notifyAuto", v).apply()
    var updatesSeen: Long get() = p.getLong("updatesSeen", 0L); set(v) = p.edit().putLong("updatesSeen", v).apply()
    var sttLang: String get() = p.getString("sttLang", "auto") ?: "auto"; set(v) = p.edit().putString("sttLang", v).apply()
    /** Режим голоса: "agent" — Deepgram Voice Agent (Claude Haiku 4.5 + «Владимир»); "gigaam" — распознавание GigaAM Multilingual 600M + ответ модели + озвучка Deepgram Flux. */
    /** Вызов ассистента двойным хлопком (фоновое прослушивание: YAMNet на телефоне, аудио никуда не отправляется). */
    /** Защита голосом/лицом: проверка перед голосовым сеансом, жест ✌️, строгость. Отпечатки лежат в BioVault (зашифрованы Keystore). */
    var gateSessions: Boolean get() = p.getBoolean("gateSessions", false); set(v) = p.edit().putBoolean("gateSessions", v).apply()
    var gestureWake: Boolean get() = p.getBoolean("gestureWake", false); set(v) = p.edit().putBoolean("gestureWake", v).apply()
    var bioStrict: String get() = p.getString("bioStrict", "normal") ?: "normal"; set(v) = p.edit().putString("bioStrict", v).apply()
    var offlineMode: Boolean get() = p.getBoolean("offlineMode", false); set(v) = p.edit().putBoolean("offlineMode", v).apply()
    var chatModel: String get() = p.getString("chatModel", "lfm") ?: "lfm"; set(v) = p.edit().putString("chatModel", v).apply()
    var phoneModelUrl: String get() = p.getString("phoneModelUrl", "") ?: ""; set(v) = p.edit().putString("phoneModelUrl", v).apply()
    var clapWake: Boolean get() = p.getBoolean("clapWake", false); set(v) = p.edit().putBoolean("clapWake", v).apply()
    var clapSens: String get() = p.getString("clapSens", "normal") ?: "normal"; set(v) = p.edit().putString("clapSens", v).apply()
    var voiceMode: String get() = p.getString("voiceMode", "agent") ?: "agent"; set(v) = p.edit().putString("voiceMode", v).apply()
    var dictAuto: Boolean get() = p.getBoolean("dictAuto", true); set(v) = p.edit().putBoolean("dictAuto", v).apply()
    var bargeIn: Int get() = p.getInt("bargeIn", 0); set(v) = p.edit().putInt("bargeIn", v).apply()   // 0 авто (по наушникам), 1 вкл, 2 выкл
    var appLock: Boolean get() = p.getBoolean("appLock", false); set(v) = p.edit().putBoolean("appLock", v).apply()
    var bookmarksJson: String get() = p.getString("bookmarks", "[]") ?: "[]"; set(v) = p.edit().putString("bookmarks", v).apply()
    var lastConv: Int get() = p.getInt("lastConv", 0); set(v) = p.edit().putInt("lastConv", v).apply()
    var askRisky: Boolean get() = p.getBoolean("askRisky", true); set(v) = p.edit().putBoolean("askRisky", v).apply()
    var effort: String get() = p.getString("effort", "auto") ?: "auto"; set(v) = p.edit().putString("effort", v).apply()
    var mode: String get() = p.getString("mode", "chat") ?: "chat"; set(v) = p.edit().putString("mode", v).apply()
    var silenceMs: Float get() = p.getFloat("silenceMs", 450f); set(v) = p.edit().putFloat("silenceMs", v).apply()
    var micThreshold: Float get() = p.getFloat("micThr", 0.12f); set(v) = p.edit().putFloat("micThr", v).apply()
}

object SharedHttp {
    val base: OkHttpClient by lazy { OkHttpClient.Builder().connectTimeout(20, TimeUnit.SECONDS).readTimeout(5, TimeUnit.MINUTES).writeTimeout(10, TimeUnit.MINUTES).build() }
    val stream: OkHttpClient by lazy { base.newBuilder().readTimeout(0, TimeUnit.MILLISECONDS).build() }
    val ws: OkHttpClient by lazy { base.newBuilder().readTimeout(0, TimeUnit.MILLISECONDS).pingInterval(20, TimeUnit.SECONDS).build() }
}

class Api(private val store: Store) {
    private val http get() = SharedHttp.base      // клиенты общие на процесс: пул соединений живёт между окнами (главное, ассистент), без повторных TLS-рукопожатий
    private val streamHttp get() = SharedHttp.stream
    private val jsonType = "application/json".toMediaType()

    val base get() = store.server
    /** WebSocket потокового распознавания (Deepgram через наш сервер). */
    val wsClient: OkHttpClient get() = SharedHttp.ws
    fun bridgeSocket(): Request = Request.Builder().url(base.replaceFirst("https://", "wss://").replaceFirst("http://", "ws://") + "/api/llm-bridge").apply { store.token?.let { header("Authorization", "Bearer $it") } }.build()
    fun sttSocket(lang: String, silenceMs: Int = 600, engine: String = ""): Request =
        Request.Builder().url(base.replaceFirst("https://", "wss://").replaceFirst("http://", "ws://") + "/api/stt-stream?lang=$lang&silence=$silenceMs" + (if (engine.isNotBlank()) "&engine=$engine" else ""))
            .apply { store.token?.let { header("Authorization", "Bearer $it") } }.build()
    /** Голосовой агент (Deepgram Voice Agent через наш сервер): поток PCM в обе стороны. */
    fun voiceAgentSocket(lang: String, translate: String = ""): Request =
        Request.Builder().url(base.replaceFirst("https://", "wss://").replaceFirst("http://", "ws://") + "/api/voice-agent?lang=$lang" + (if (translate.isNotBlank()) "&translate=$translate" else ""))
            .apply { store.token?.let { header("Authorization", "Bearer $it") } }.build()
    private fun req(path: String) = Request.Builder().url(base + path).apply { store.token?.let { header("Authorization", "Bearer $it") } }

    private fun Response.text(): String {
        val body = body?.string().orEmpty()
        if (!isSuccessful) {
            val msg = runCatching { JSON.parseToJsonElement(body).jsonObject["error"]?.jsonPrimitive?.content }.getOrNull()
            throw ApiException(msg ?: "Ошибка сервера ($code)", code)
        }
        return body
    }

    private suspend fun exec(r: Request, client: OkHttpClient = http): String = withContext(Dispatchers.IO) {
        try { client.newCall(r).execute().use { it.text() } }
        catch (e: ApiException) { throw e }
        catch (e: java.io.IOException) { throw ApiException("Нет связи с сервером: ${e.message}") }
    }

    private fun jsonBody(vararg kv: Pair<String, Any?>): RequestBody = buildJsonObject {
        kv.forEach { (k, v) -> when (v) { null -> {}; is Boolean -> put(k, v); is Number -> put(k, v); is List<*> -> putJsonArray(k) { v.forEach { add(it.toString()) } }; else -> put(k, v.toString()) } }
    }.toString().toRequestBody(jsonType)

    private suspend inline fun <reified T> get(path: String): T = JSON.decodeFromString(exec(req(path).build()))
    private suspend inline fun <reified T> post(path: String, vararg kv: Pair<String, Any?>): T = JSON.decodeFromString(exec(req(path).post(jsonBody(*kv)).build()))

    // auth
    suspend fun config(): AuthConfig = get("/auth/config")
    suspend fun sendCode(email: String, captcha: String?) { exec(req("/auth/send-code").post(jsonBody("email" to email, "captcha" to captcha)).build()) }
    suspend fun verify(email: String, code: String): AuthResp = post("/auth/verify", "email" to email, "code" to code)
    suspend fun google(idToken: String): AuthResp = post("/auth/google", "idToken" to idToken)
    suspend fun me(): User = get("/api/me")
    suspend fun health(): Health = get("/health")
    suspend fun diag(): Diag = get("/api/diag")

    // chats
    suspend fun conversations(): List<Conv> = get("/api/conversations")
    suspend fun newConversation(mode: String): Conv = post("/api/conversations", "mode" to mode)
    suspend fun deleteConversation(id: Int) { exec(req("/api/conversations/$id").delete().build()) }
    suspend fun renameConversation(id: Int, title: String) { exec(req("/api/conversations/$id").patch(jsonBody("title" to title)).build()) }
    suspend fun messages(id: Int, after: Long = 0, before: Long = 0): MsgsResp = get("/api/conversations/$id/messages" + if (after > 0) "?after=$after" else if (before > 0) "?before=$before" else "")
    suspend fun setPersona(id: Int, p: String) { exec(req("/api/conversations/$id").patch(jsonBody("persona" to p)).build()) }
    suspend fun pinConversation(id: Int, pinned: Boolean) { exec(req("/api/conversations/$id").patch(jsonBody("pinned" to pinned)).build()) }
    suspend fun searchChats(q: String): List<ChatHit> = get("/api/conversations/search?q=" + java.net.URLEncoder.encode(q, "UTF-8"))
    suspend fun exportChat(id: Int): ChatExport = get("/api/conversations/$id/export")
    suspend fun regenerate(id: Int, provider: String, model: String, effort: String, askRisky: Boolean) { exec(req("/api/conversations/$id/regenerate").post(jsonBody("provider" to provider, "model" to model, "effort" to effort, "autonomy" to (if (askRisky) "ask" else "auto"), "search" to store.searchProvider)).build()) }
    suspend fun editMessage(id: Int, messageId: Long, text: String, provider: String, model: String, effort: String, askRisky: Boolean) { exec(req("/api/conversations/$id/edit").post(jsonBody("messageId" to messageId, "text" to text, "provider" to provider, "model" to model, "effort" to effort, "autonomy" to (if (askRisky) "ask" else "auto"), "search" to store.searchProvider)).build()) }
    suspend fun sites(): List<Site> = get("/api/sites")
    suspend fun deleteSite(slug: String) { exec(req("/api/sites/$slug").delete().build()) }
    suspend fun updates(since: Long): List<UpdateItem> = get("/api/updates?since=$since")
    suspend fun system(): SysInfo = get("/api/system")
    suspend fun gitRepos(): List<GitRepo> = get("/api/git/repos")
    suspend fun git(path: String): GitInfo = get("/api/git?path=" + java.net.URLEncoder.encode(path, "UTF-8"))
    suspend fun gitAction(action: String, path: String, message: String = ""): GitResult = post("/api/git/$action", "path" to path, "message" to message)
    suspend fun phoneResult(id: String, text: String) { exec(req("/api/phone/result").post(jsonBody("id" to id, "text" to text)).build()) }
    suspend fun checkpoints(convId: Int): List<Checkpoint> = get("/api/conversations/$convId/checkpoints")
    suspend fun checkpointFiles(convId: Int, hash: String): List<CheckpointFile> = get("/api/conversations/$convId/checkpoints/$hash")
    suspend fun restoreCheckpoint(convId: Int, hash: String) { exec(req("/api/conversations/$convId/restore").post(jsonBody("hash" to hash)).build()) }
    suspend fun projects(): List<Project> = get("/api/projects")
    suspend fun createProject(name: String, repo: String): Created = post("/api/projects", "name" to name, "repo" to repo)
    suspend fun deleteProject(id: Int) { exec(req("/api/projects/$id").delete().build()) }
    suspend fun setProject(convId: Int, projectId: Int?) { exec(req("/api/conversations/$convId").patch(jsonBody("projectId" to projectId)).build()) }
    suspend fun prompts(): List<PromptItem> = get("/api/prompts")
    suspend fun savePrompt(name: String, text: String) { exec(req("/api/prompts").post(jsonBody("name" to name, "text" to text)).build()) }
    suspend fun deletePrompt(id: Int) { exec(req("/api/prompts/$id").delete().build()) }
    suspend fun usage(): Usage = get("/api/usage")
    suspend fun send(id: Int, text: String, files: List<String>, voice: Boolean = false, provider: String = "river", model: String = DEFAULT_MODEL, effort: String = "auto", askRisky: Boolean = true) {
        exec(req("/api/conversations/$id/send").post(jsonBody("text" to text, "files" to files, "voice" to voice, "provider" to provider, "model" to model, "effort" to effort, "autonomy" to (if (askRisky) "ask" else "auto"), "search" to store.searchProvider)).build())
    }
    suspend fun stop(id: Int) { exec(req("/api/conversations/$id/stop").post("{}".toRequestBody(jsonType)).build()) }

    /** SSE-стрим. Блокирующее чтение не прерывается отменой корутины, поэтому соединение закрывает «сторож»: иначе события старого чата «просачивались» бы в новый. */
    suspend fun stream(id: Int, wait: Boolean = false, onEvent: (StreamEvent) -> Unit): Unit = coroutineScope {
        val call = streamHttp.newCall(req("/api/conversations/$id/stream" + if (wait) "?wait=1" else "").build())
        val watcher = launch(Dispatchers.Default) { try { awaitCancellation() } finally { call.cancel() } }
        try {
            withContext(Dispatchers.IO) {
                try {
                    call.execute().use { resp ->
                        if (!resp.isSuccessful) throw ApiException("stream ${resp.code}", resp.code)
                        val src = resp.body!!.source()
                        while (true) {
                            val line = src.readUtf8Line() ?: break
                            if (!line.startsWith("data:")) continue
                            val o = runCatching { JSON.parseToJsonElement(line.substring(5).trim()).jsonObject }.getOrNull() ?: continue
                            val ev = when (o["type"]?.jsonPrimitive?.content) {
                                "snapshot" -> StreamEvent.Snapshot(o["partial"]?.jsonPrimitive?.content.orEmpty())
                                "delta" -> StreamEvent.Delta(o["text"]!!.jsonPrimitive.content)
                                "message" -> StreamEvent.Message(JSON.decodeFromJsonElement(o["message"]!!))
                                "phone" -> StreamEvent.Phone(o["id"]?.jsonPrimitive?.content.orEmpty(), (o["args"] as? JsonObject) ?: JsonObject(emptyMap()))
                                "checkpoint" -> StreamEvent.Checkpoint(o["hash"]?.jsonPrimitive?.content.orEmpty(), o["changed"]?.jsonPrimitive?.intOrNull ?: 0)
                                "status" -> StreamEvent.Status(o["text"]?.jsonPrimitive?.content.orEmpty())
                                "tool_output" -> StreamEvent.ToolOutput(o["id"]!!.jsonPrimitive.content, o["text"]!!.jsonPrimitive.content)
                                "replace" -> StreamEvent.Replace(o["id"]?.jsonPrimitive?.longOrNull ?: 0L, o["content"]?.jsonPrimitive?.content.orEmpty())
                                "done" -> StreamEvent.Done
                                "error" -> StreamEvent.Error(o["error"]?.jsonPrimitive?.content.orEmpty())
                                else -> null
                            } ?: continue
                            onEvent(ev)
                            if (ev is StreamEvent.Done || ev is StreamEvent.Error) break
                        }
                    }
                } catch (e: java.io.IOException) { if (!call.isCanceled()) throw ApiException("Соединение прервано") }
            }
        } finally { watcher.cancel() }
    }

    // files
    suspend fun upload(name: String, mime: String, body: RequestBody): Attach {
        val mp = MultipartBody.Builder().setType(MultipartBody.FORM).addFormDataPart("file", name, body).build()
        val list: List<Attach> = JSON.decodeFromString(exec(req("/api/files").post(mp).build()))
        return list.first()
    }
    suspend fun download(id: String, name: String, dir: File): File = withContext(Dispatchers.IO) {
        dir.mkdirs()
        val out = File(dir, name.replace('/', '_'))
        http.newCall(req("/api/files/$id").build()).execute().use { r ->
            if (!r.isSuccessful) throw ApiException("Не удалось скачать (${r.code})")
            r.body!!.byteStream().use { i -> out.outputStream().use { o -> i.copyTo(o) } }
        }
        out
    }

    // voice
    /** Точное файловое распознавание (Deepgram) для записанного в RtSession звука (WAV). */
    suspend fun sttWav(wav: ByteArray, lang: String): String {
        val mp = MultipartBody.Builder().setType(MultipartBody.FORM).addFormDataPart("audio", "speech.wav", wav.toRequestBody("audio/wav".toMediaType())).apply { if (lang != "auto") addFormDataPart("language", lang) }.build()
        return JSON.parseToJsonElement(exec(req("/api/stt").post(mp).build())).jsonObject["text"]?.jsonPrimitive?.content.orEmpty()
    }
    suspend fun stt(file: File, lang: String = "auto"): String {
        val mp = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("audio", file.name, file.asRequestBodyCompat("audio/mp4".toMediaType())).apply { if (lang != "auto") addFormDataPart("language", lang) }.build()
        return JSON.parseToJsonElement(exec(req("/api/stt").post(mp).build())).jsonObject["text"]?.jsonPrimitive?.content.orEmpty()
    }
    // voices
    suspend fun voices(q: String, lang: String, page: Int): List<VoiceInfo> = get("/api/voices?lang=$lang&page=$page&q=" + java.net.URLEncoder.encode(q, "UTF-8"))
    suspend fun currentVoice(): CurrentVoice = get("/api/voice")
    suspend fun setVoice(id: String, name: String) { exec(req("/api/voice").post(jsonBody("id" to id, "name" to name)).build()) }
    private val ttsHttp = http.newBuilder().callTimeout(25, TimeUnit.SECONDS).readTimeout(20, TimeUnit.SECONDS).build()
    /** null — озвучивать нечего (только знаки препинания) или сервер не успел: очередь не должна зависать. */
    /** Адрес потоковой озвучки (GET) + заголовки: MediaPlayer играет, не дожидаясь конца синтеза. */
    private var streamSupported: Boolean? = null
    /** Есть ли на сервере потоковая озвучка (старый сервер отвечает 404 → тогда играем через файл, как раньше). */
    suspend fun ttsStreamSupported(): Boolean {
        streamSupported?.let { return it }
        val r = runCatching { withContext(Dispatchers.IO) { ttsHttp.newCall(req("/api/tts-stream?text=").build()).execute().use { it.code != 404 && it.code != 405 } } }
        r.getOrNull()?.let { streamSupported = it }
        return r.getOrDefault(false)
    }
    fun ttsStream(text: String, voice: String): Pair<String, Map<String, String>> =
        (base + "/api/tts-stream?text=" + java.net.URLEncoder.encode(text, "UTF-8") + (if (voice.isNotBlank()) "&voice=$voice" else "")) to
            (store.token?.let { mapOf("Authorization" to "Bearer $it") } ?: emptyMap())
    /** Сырой звук озвучки (24 кГц/16 бит/моно) отдаётся кусками по мере синтеза. */
    suspend fun ttsPcm(text: String, voice: String, onBytes: (ByteArray) -> Unit) = withContext(Dispatchers.IO) {
        val enc = { s: String -> java.net.URLEncoder.encode(s, "UTF-8") }
        ttsHttp.newCall(req("/api/tts-stream?fmt=pcm&text=${enc(text)}" + (if (voice.isNotBlank()) "&voice=${enc(voice)}" else "")).build()).execute().use { r ->
            if (r.code == 204) return@use
            if (!r.isSuccessful) throw ApiException("TTS ${r.code}")
            val src = r.body!!.source(); val buf = ByteArray(4096); var carry: Byte? = null
            while (true) {
                val n = src.read(buf, 0, buf.size); if (n <= 0) break
                val a = if (carry != null) ByteArray(n + 1).also { it[0] = carry!!; System.arraycopy(buf, 0, it, 1, n) } else buf.copyOf(n)
                carry = if (a.size % 2 == 1) a[a.size - 1] else null
                onBytes(if (carry != null) a.copyOf(a.size - 1) else a)
            }
        }
    }
    suspend fun tts(text: String, out: File, voice: String): File? = withContext(Dispatchers.IO) {
        ttsHttp.newCall(req("/api/tts").post(jsonBody("text" to text, "voice" to voice.ifBlank { null })).build()).execute().use { r ->
            if (r.code == 204) return@withContext null
            if (!r.isSuccessful) throw ApiException(runCatching { JSON.parseToJsonElement(r.body!!.string()).jsonObject["error"]?.jsonPrimitive?.content }.getOrNull() ?: "TTS ${r.code}")
            out.outputStream().use { o -> r.body!!.byteStream().copyTo(o) }
        }
        out
    }

    // github
    suspend fun ghStart(): DeviceCode = post("/api/github/device/start")
    suspend fun ghPoll(code: String): GhPoll = post("/api/github/device/poll", "deviceCode" to code)
    suspend fun ghToken(token: String): String = JSON.parseToJsonElement(exec(req("/api/github/token").post(jsonBody("token" to token)).build())).jsonObject["login"]!!.jsonPrimitive.content
    suspend fun ghUnlink() { exec(req("/api/github").delete().build()) }

    // providers
    suspend fun providers(): List<ProviderInfo> = get("/api/providers")
    suspend fun addProvider(name: String, url: String, key: String, effort: Boolean, models: String): ProviderAdded = post("/api/providers", "name" to name, "baseUrl" to url, "apiKey" to key, "effort" to effort, "models" to models)
    suspend fun presets(): List<ProviderPreset> = get("/api/provider-presets")
    suspend fun instructions(): String = JSON.parseToJsonElement(exec(req("/api/instructions").build())).jsonObject["text"]?.jsonPrimitive?.content.orEmpty()
    suspend fun setInstructions(t: String) { exec(req("/api/instructions").post(jsonBody("text" to t)).build()) }
    suspend fun runSnippet(lang: String, code: String): SnippetResult = post("/api/run", "lang" to lang, "code" to code)
    suspend fun deleteProvider(id: String) { exec(req("/api/providers/$id").delete().build()) }

    // automations
    suspend fun schedules(): List<Schedule> = get("/api/schedules")
    suspend fun addSchedule(name: String, prompt: String, everyMin: Int?, mode: String, webhook: Boolean): Created = post("/api/schedules", "name" to name, "prompt" to prompt, "everyMin" to everyMin, "mode" to mode, "webhook" to webhook)
    suspend fun toggleSchedule(id: Int, on: Boolean) { exec(req("/api/schedules/$id").patch(jsonBody("enabled" to on)).build()) }
    suspend fun runSchedule(id: Int) { exec(req("/api/schedules/$id/run").post("{}".toRequestBody(jsonType)).build()) }
    suspend fun deleteSchedule(id: Int) { exec(req("/api/schedules/$id").delete().build()) }
    suspend fun addDaily(name: String, prompt: String, time: String, mode: String): Created = post("/api/schedules", "name" to name, "prompt" to prompt, "atTime" to time, "tzOffsetMin" to (java.util.TimeZone.getDefault().getOffset(System.currentTimeMillis()) / 60000), "mode" to mode)
    suspend fun addWatch(name: String, prompt: String, everyMin: Int, url: String, text: String): Created = post("/api/schedules", "name" to name, "prompt" to prompt, "everyMin" to everyMin, "mode" to "chat", "watchUrl" to url, "watchText" to text)
    // подключения (MCP)
    suspend fun mcp(): McpList = get("/api/mcp")
    suspend fun addMcp(name: String, url: String, token: String, header: String): McpResult = post("/api/mcp", "name" to name, "url" to url, "token" to token, "header" to header)
    suspend fun testMcp(id: Int): McpResult = post("/api/mcp/$id/test")
    suspend fun toggleMcp(id: Int, on: Boolean) { exec(req("/api/mcp/$id").patch(jsonBody("enabled" to on)).build()) }
    suspend fun deleteMcp(id: Int) { exec(req("/api/mcp/$id").delete().build()) }
    // заметки / задачи / секреты
    suspend fun notes(): List<NoteItem> = get("/api/notes")
    suspend fun addNote(text: String) { exec(req("/api/notes").post(jsonBody("text" to text)).build()) }
    suspend fun noteAudio(file: File): NoteItem {
        val mp = MultipartBody.Builder().setType(MultipartBody.FORM).addFormDataPart("audio", file.name, file.asRequestBodyCompat("audio/mp4".toMediaType())).build()
        return JSON.decodeFromString(exec(req("/api/notes/audio").post(mp).build()))
    }
    suspend fun deleteNote(id: Int) { exec(req("/api/notes/$id").delete().build()) }
    suspend fun todos(): List<TodoItem> = get("/api/todos")
    suspend fun addTodo(text: String) { exec(req("/api/todos").post(jsonBody("text" to text)).build()) }
    suspend fun setTodo(id: Int, done: Boolean) { exec(req("/api/todos/$id").patch(jsonBody("done" to done)).build()) }
    suspend fun deleteTodo(id: Int) { exec(req("/api/todos/$id").delete().build()) }
    suspend fun secrets(): List<String> = get("/api/secrets")
    suspend fun saveSecret(name: String, value: String) { exec(req("/api/secrets").post(jsonBody("name" to name, "value" to value)).build()) }
    suspend fun deleteSecret(name: String) { exec(req("/api/secrets/" + java.net.URLEncoder.encode(name, "UTF-8")).delete().build()) }
    suspend fun shareChat(id: Int): UrlResp = post("/api/conversations/$id/share")
    suspend fun unshareChat(id: Int) { exec(req("/api/conversations/$id/share").delete().build()) }
    suspend fun compare(text: String, targets: List<Pair<String, String>>): List<CompareResult> = withContext(Dispatchers.IO) {
        val body = buildJsonObject { put("text", text); putJsonArray("targets") { targets.forEach { (p, m) -> add(buildJsonObject { put("provider", p); put("model", m) }) } } }.toString().toRequestBody(jsonType)
        JSON.decodeFromString<List<CompareResult>>(exec(req("/api/compare").post(body).build()))
    }
    suspend fun profile(): Profile = get("/api/profile")
    suspend fun saveProfile(p: Profile) { exec(req("/api/profile").post(jsonBody("name" to p.name, "city" to p.city, "home" to p.home, "job" to p.job, "interests" to p.interests, "about" to p.about, "style" to p.style, "address" to p.address, "humor" to p.humor)).build()) }
    suspend fun missions(): List<MissionItem> = get("/api/missions")
    suspend fun setMission(id: Int, status: String) { exec(req("/api/missions/$id").patch(jsonBody("status" to status)).build()) }
    suspend fun deleteMission(id: Int) { exec(req("/api/missions/$id").delete().build()) }
    suspend fun mailAccounts(): List<MailAccount> = get("/api/mail")
    suspend fun mailHint(email: String): MailHint = get("/api/mail/hint?email=" + java.net.URLEncoder.encode(email, "UTF-8"))
    suspend fun addMail(email: String, password: String, imap: String, smtp: String) { exec(req("/api/mail").post(jsonBody("email" to email, "password" to password, "imapHost" to imap.ifBlank { null }, "smtpHost" to smtp.ifBlank { null })).build()) }
    suspend fun deleteMail(id: Int) { exec(req("/api/mail/$id").delete().build()) }
    suspend fun fileText(id: String): String = exec(req("/api/files/$id").build())
    suspend fun activity(): List<ActivityItem> = get("/api/activity?days=14")
    suspend fun exportAll(): String = exec(req("/api/export").build())

    // skills
    suspend fun skills(): List<Skill> = get("/api/skills")
    suspend fun saveSkill(name: String, description: String, content: String) { exec(req("/api/skills").post(jsonBody("name" to name, "description" to description, "content" to content)).build()) }
    suspend fun searchSkills(q: String): List<RepoHit> = get("/api/skills/search?q=" + java.net.URLEncoder.encode(q, "UTF-8"))
    suspend fun installSkill(repo: String): InstallResult = post("/api/skills/install", "repo" to repo)
    suspend fun deleteSkill(id: Int) { exec(req("/api/skills/$id").delete().build()) }

    // files
    suspend fun fsList(path: String): FsList = get("/api/fs?path=" + java.net.URLEncoder.encode(path, "UTF-8"))
    suspend fun fsRead(path: String): String = JSON.parseToJsonElement(exec(req("/api/fs/file?path=" + java.net.URLEncoder.encode(path, "UTF-8")).build())).jsonObject["text"]!!.jsonPrimitive.content
    suspend fun fsWrite(path: String, text: String) { exec(req("/api/fs/file").put(jsonBody("path" to path, "text" to text)).build()) }
    suspend fun fsDelete(path: String) { exec(req("/api/fs?path=" + java.net.URLEncoder.encode(path, "UTF-8")).delete().build()) }
    suspend fun fsDownload(path: String, name: String, dir: File): File = withContext(Dispatchers.IO) {
        dir.mkdirs(); val out = File(dir, name)
        http.newCall(req("/api/fs/file?download=1&path=" + java.net.URLEncoder.encode(path, "UTF-8")).build()).execute().use { r ->
            if (!r.isSuccessful) throw ApiException("Не удалось скачать (${r.code})")
            r.body!!.byteStream().use { i -> out.outputStream().use { o -> i.copyTo(o) } }
        }; out
    }

    /** Терминал: стримит вывод команды, по завершении возвращает (новый cwd, код). */
    suspend fun runCommand(command: String, cwd: String, onChunk: (String) -> Unit): Pair<String, Int> = coroutineScope { withContext(Dispatchers.IO) {
        val call = streamHttp.newCall(req("/api/exec").post(jsonBody("command" to command, "cwd" to cwd)).build())
        val watcher = launch(Dispatchers.Default) { try { awaitCancellation() } finally { call.cancel() } }
        val all = StringBuilder()
        call.execute().use { r ->
            if (!r.isSuccessful) throw ApiException(runCatching { JSON.parseToJsonElement(r.body!!.string()).jsonObject["error"]?.jsonPrimitive?.content }.getOrNull() ?: "Ошибка ${r.code}", r.code)
            val src = r.body!!.source()
            val buf = okio.Buffer()
            while (src.read(buf, 4096) != -1L) {
                val s = buf.readUtf8(); all.append(s)
                onChunk(s)
            }
        }
        val m = all.lastIndexOf("__OA_CWD__")
        val res = if (m >= 0) { val t = all.substring(m + 10).trim(); val i = t.lastIndexOf(' '); t.substring(0, i) to (t.substring(i + 1).toIntOrNull() ?: 0) } else cwd to 0
        watcher.cancel()
        res
    } }

    // memory
    suspend fun memories(): List<Mem> = get("/api/memories")
    suspend fun deleteMemory(id: Int) { exec(req("/api/memories/$id").delete().build()) }
    suspend fun clearMemories() { exec(req("/api/memories").delete().build()) }
    suspend fun addMemory(text: String) { exec(req("/api/memories").post(jsonBody("content" to text, "importance" to 0.8)).build()) }
}

private fun File.asRequestBodyCompat(type: MediaType): RequestBody = object : RequestBody() {
    override fun contentType() = type
    override fun contentLength() = length()
    override fun writeTo(sink: okio.BufferedSink) { inputStream().use { sink.writeAll(it.source()) } }
}
