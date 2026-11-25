package app.staika

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateList
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject

/** Состояние приложения: данные сервера и события в реальном времени. */
object Repo {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    var loggedIn by mutableStateOf(false)
    var me by mutableStateOf<Me?>(null)
    val agents = mutableStateListOf<Agent>()
    val messages = mutableStateMapOf<String, SnapshotStateList<Msg>>()
    val tasks = mutableStateListOf<TaskItem>()
    var models by mutableStateOf<List<ModelOpt>>(emptyList())
    var loaded by mutableStateOf(false)
    var connected by mutableStateOf(true)
    var toast by mutableStateOf<String?>(null)
    var googleClientId by mutableStateOf("")

    private var socket: WebSocket? = null
    private var reconnect: Job? = null
    private var toastJob: Job? = null
    private var wantSocket = false

    fun say(text: String) {
        toast = text
        toastJob?.cancel()
        toastJob = scope.launch { delay(3500); toast = null }
    }

    fun agent(id: String?) = agents.firstOrNull { it.id == id }
    fun chief() = agents.firstOrNull { it.chief }

    /** Закреплённые сверху: главный и два последних по активности. */
    fun pinned(): List<Agent> {
        val sorted = agents.sortedByDescending { it.lastAt }
        val c = chief()
        return (listOfNotNull(c) + sorted.filter { it != c }.take(if (c != null) 2 else 3))
    }

    // ---------- вход и выход ----------
    fun start() {
        loggedIn = Prefs.access != null || Prefs.refresh != null
        if (loggedIn) { scope.launch { bootstrap() }; openSocket() }
    }

    fun onLoggedIn(user: Me) {
        me = user; loggedIn = true; loaded = false
        scope.launch { bootstrap() }
        openSocket()
    }

    fun onSessionExpired() { scope.launch { clear() } }

    fun logout() { scope.launch { Api.logout(); clear() } }

    private fun clear() {
        wantSocket = false; socket?.close(1000, null); socket = null
        loggedIn = false; me = null; agents.clear(); messages.clear(); tasks.clear(); loaded = false
        Prefs.access = null; Prefs.refresh = null
    }

    // ---------- загрузка ----------
    suspend fun bootstrap() {
        try {
            me = parseMe(Api.obj("GET", "/api/profile"))
            applyAgents(Api.arr("GET", "/api/agents"))
            models = Api.arr("GET", "/api/models").let { a -> (0 until a.length()).map { a.getJSONObject(it).let { m -> ModelOpt(m.getString("id"), m.getString("label"), m.optString("provider")) } } }
            loaded = true; connected = true
            // перезагружаем открытые чаты после переподключения
            messages.keys.toList().forEach { loadMessages(it, force = true) }
        } catch (e: ApiError) {
            if (e.code == "network") connected = false else if (e.status != 401) say(e.message ?: "Ошибка")
            loaded = true
        }
    }

    private fun applyAgents(a: JSONArray) {
        val list = (0 until a.length()).map { parseAgent(a.getJSONObject(it)) }
        agents.clear(); agents.addAll(list)
    }

    fun parseAgent(j: JSONObject): Agent {
        val p = j.optJSONObject("perms")
        return Agent(
            j.getString("id"), j.getString("name"), j.optString("role"), Pal.of(j.optString("pal")), statusOf(j.optString("status")),
            j.optString("lastText"), j.optLong("lastAt"), j.optBoolean("chief"), j.optString("parentId").takeIf { it.isNotEmpty() },
            j.optString("model"), Perms(p?.optBoolean("server") ?: false, p?.optBoolean("browser") ?: false, p?.optBoolean("mail") ?: false),
        )
    }

    private fun upsertAgent(a: Agent) {
        val i = agents.indexOfFirst { it.id == a.id }
        if (i >= 0) agents[i] = a else agents.add(a)
    }

    fun parseMsg(j: JSONObject): Msg {
        val id = j.getString("id"); val at = j.optLong("createdAt"); val c = j.optJSONObject("content") ?: JSONObject()
        return when (j.optString("type")) {
            "approval" -> Msg.Approval(id, at, c.optString("approvalId"), c.optString("title"), c.optString("detail"), c.optString("risk"),
                when (c.optString("decision")) { "Allowed" -> Decision.Allowed; "Denied" -> Decision.Denied; else -> Decision.Pending })
            "task" -> Msg.Task(id, at, c.optString("title"), c.optDouble("progress", 0.0).toFloat(), c.optString("status"))
            "doc" -> Msg.Doc(id, at, c.optString("title"), c.optString("host"))
            "system" -> Msg.System(id, at, c.optString("text"))
            else -> Msg.Text(id, at, c.optString("text"), j.optString("sender") == "user")
        }
    }

    suspend fun loadMessages(agentId: String, force: Boolean = false) {
        if (!force && messages.containsKey(agentId)) return
        try {
            val a = Api.arr("GET", "/api/agents/$agentId/messages?limit=100")
            val list = (0 until a.length()).map { parseMsg(a.getJSONObject(it)) }
            val target = messages.getOrPut(agentId) { mutableStateListOf() }
            target.clear(); target.addAll(list)
        } catch (e: ApiError) { say(e.message ?: "Не удалось загрузить чат") }
    }

    suspend fun loadTasks() {
        try {
            val a = Api.arr("GET", "/api/tasks")
            val list = (0 until a.length()).map { a.getJSONObject(it).let { t ->
                TaskItem(t.getString("id"), t.optString("title"), t.optString("toAgent"), t.optString("status"), t.optDouble("progress", 0.0).toFloat(), t.optLong("updatedAt"))
            } }
            tasks.clear(); tasks.addAll(list)
        } catch (e: ApiError) { say(e.message ?: "Ошибка") }
    }

    private fun putMsg(agentId: String, m: Msg) {
        val l = messages[agentId] ?: return   // чат ещё не открывали: подгрузится при открытии
        val i = l.indexOfFirst { it.id == m.id }
        if (i >= 0) l[i] = m else l.add(m)
    }

    // ---------- действия ----------
    fun send(agentId: String, text: String) {
        scope.launch {
            try {
                val j = Api.obj("POST", "/api/agents/$agentId/messages", JSONObject().put("text", text))
                loadMessagesIfMissing(agentId)
                putMsg(agentId, parseMsg(j))
            } catch (e: ApiError) { say(e.message ?: "Не удалось отправить") }
        }
    }

    private suspend fun loadMessagesIfMissing(agentId: String) { if (!messages.containsKey(agentId)) loadMessages(agentId) }

    fun decide(agentId: String, m: Msg.Approval, allow: Boolean, always: Boolean = false) {
        scope.launch {
            try {
                Api.obj("POST", "/api/approvals/${m.approvalId}/decision", JSONObject().put("allow", allow).put("always", always))
                putMsg(agentId, m.copy(decision = if (allow) Decision.Allowed else Decision.Denied))
            } catch (e: ApiError) {
                say(if (e.code == "already_decided") "Решение уже принято" else e.message ?: "Ошибка")
                loadMessages(agentId, force = true)
            }
        }
    }

    suspend fun createAgent(name: String, role: String, pal: Pal, model: String, asChief: Boolean, underChief: Boolean, perms: Perms): Agent? = try {
        val body = JSONObject().put("name", name).put("role", role).put("pal", pal.name).put("model", model).put("chief", asChief)
            .put("perms", JSONObject().put("server", perms.server).put("browser", perms.browser).put("mail", perms.mail))
        if (underChief) chief()?.let { body.put("parentId", it.id) }
        val a = parseAgent(Api.obj("POST", "/api/agents", body))
        upsertAgent(a); a
    } catch (e: ApiError) { say(e.message ?: "Не удалось создать агента"); null }

    suspend fun updateAgent(a: Agent, name: String, role: String, pal: Pal, model: String, perms: Perms) {
        try {
            val body = JSONObject().put("name", name).put("role", role).put("pal", pal.name).put("model", model).put("parentId", a.parentId ?: "")
                .put("perms", JSONObject().put("server", perms.server).put("browser", perms.browser).put("mail", perms.mail))
            upsertAgent(parseAgent(Api.obj("PUT", "/api/agents/${a.id}", body)))
        } catch (e: ApiError) { say(e.message ?: "Ошибка") }
    }

    suspend fun deleteAgent(id: String) {
        try { Api.obj("DELETE", "/api/agents/$id"); agents.removeAll { it.id == id }; messages.remove(id) } catch (e: ApiError) { say(e.message ?: "Ошибка") }
    }

    // ---------- события в реальном времени ----------
    private fun openSocket() {
        wantSocket = true
        reconnect?.cancel()
        reconnect = scope.launch {
            var delayMs = 1000L
            while (wantSocket) {
                val token = Api.freshToken()
                if (token == null) { delay(2000); continue }
                val req = Request.Builder().url(Api.wsUrl("/ws?token=$token")).build()
                val done = kotlinx.coroutines.CompletableDeferred<Unit>()
                socket = Api.http.newWebSocket(req, object : WebSocketListener() {
                    override fun onOpen(webSocket: WebSocket, response: Response) {
                        scope.launch { delayMs = 1000L; connected = true; bootstrap() }
                    }
                    override fun onMessage(webSocket: WebSocket, text: String) { scope.launch { handleEvent(text) } }
                    override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { done.complete(Unit) }
                    override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) { done.complete(Unit) }
                })
                done.await()
                if (!wantSocket) return@launch
                connected = false
                delay(delayMs); delayMs = (delayMs * 2).coerceAtMost(15_000L)
            }
        }
    }

    private fun handleEvent(text: String) {
        val j = try { JSONObject(text) } catch (e: Exception) { return }
        val d = j.optJSONObject("data") ?: return
        when (j.optString("type")) {
            "message.created", "message.updated" -> putMsg(d.optString("agentId"), parseMsg(d))
            "agent.updated" -> upsertAgent(parseAgent(d))
        }
    }
}
