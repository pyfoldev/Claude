package openagent.app.com

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

/**
 * Groq работает ЧЕРЕЗ ТЕЛЕФОН: сервер (Гонконг) к Groq не ходит. Приложение держит соединение с сервером; когда агенту нужен Groq,
 * сервер присылает запрос (без ключа), приложение добавляет ваш ключ Groq, отправляет запрос в api.groq.com и построчно возвращает ответ.
 * Ключ хранится только на телефоне. Разрешён только хост api.groq.com.
 */
class GroqBridge(private val api: Api, private val store: Store, private val scope: CoroutineScope) {
    companion object {
        @Volatile private var inst: GroqBridge? = null
        /** Один мост на весь процесс: у главного окна и окна ассистента (кнопка питания) раньше были свои, и они по кругу выбивали друг друга с сервера — Groq то пропадал, то возвращался, ответы шли через медленный запасной канал. */
        fun shared(api: Api, store: Store): GroqBridge = inst ?: synchronized(this) { inst ?: GroqBridge(api, store, CoroutineScope(SupervisorJob() + Dispatchers.IO)).also { inst = it } }
    }
    var connected by mutableStateOf(false); private set
    private var job: Job? = null
    @Volatile private var ws: WebSocket? = null
    private val calls = ConcurrentHashMap<String, Call>()
    private val http = OkHttpClient.Builder().connectTimeout(15, TimeUnit.SECONDS).readTimeout(120, TimeUnit.SECONDS).build()

    private fun keyFor(host: String) = when (host) { "api.groq.com" -> store.groqKey; "api.perplexity.ai" -> store.pplxKey; else -> "" }
    private fun hosts() = listOf("api.groq.com", "api.perplexity.ai").filter { keyFor(it).isNotBlank() }

    fun start() {
        if (job?.isActive == true) return
        job = scope.launch(Dispatchers.IO) {
            var backoff = 800L
            while (isActive) {
                if (hosts().isEmpty() || store.token == null) { connected = false; delay(2500); continue }
                val t0 = System.currentTimeMillis()
                runCatching { session() }
                connected = false
                backoff = if (System.currentTimeMillis() - t0 > 20_000) 800L else minOf(backoff * 2, 15_000L)
                delay(backoff)
            }
        }
    }
    fun stop() { job?.cancel(); job = null; ws?.cancel(); ws = null; connected = false; calls.values.forEach { it.cancel() }; calls.clear() }
    fun restart() { stop(); start() }

    suspend fun awaitUp(ms: Long): Boolean { val end = System.currentTimeMillis() + ms; while (!connected && System.currentTimeMillis() < end) delay(40); return connected }

    private suspend fun session() = suspendCancellableCoroutine<Unit> { c ->
        val w = api.wsClient.newWebSocket(api.bridgeSocket(), object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                val o = runCatching { JSONObject(text) }.getOrNull() ?: return
                when (o.optString("t")) {
                    "hello" -> { webSocket.send(JSONObject().put("t", "caps").put("hosts", org.json.JSONArray(hosts())).toString()); connected = true }
                    "req" -> handle(webSocket, o)
                    "abort" -> calls.remove(o.optString("id"))?.cancel()
                }
            }
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { connected = false; if (c.isActive) c.resume(Unit) {} }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) { connected = false; if (c.isActive) c.resume(Unit) {} }
        })
        ws = w
        c.invokeOnCancellation { w.cancel() }
    }

    private fun send(w: WebSocket, o: JSONObject) { w.send(o.toString()) }

    private fun handle(w: WebSocket, o: JSONObject) {
        val id = o.optString("id"); val url = o.optString("url")
        val host = runCatching { java.net.URI(url).host }.getOrNull().orEmpty()
        if (!url.startsWith("https://") || host !in listOf("api.groq.com", "api.perplexity.ai")) { send(w, JSONObject().put("t", "err").put("id", id).put("message", "хост не разрешён")); return }
        val key = keyFor(host)
        if (key.isBlank()) { send(w, JSONObject().put("t", "err").put("id", id).put("message", "в приложении не задан ключ для $host")); return }
        val rb = Request.Builder().url(url)
        o.optJSONObject("headers")?.let { h -> h.keys().forEach { k -> if (!k.equals("authorization", true) && !k.equals("host", true) && !k.equals("content-length", true)) rb.header(k, h.optString(k)) } }
        rb.header("Authorization", "Bearer $key")
        val method = o.optString("method", "POST").uppercase()
        val body = if (o.isNull("body")) null else o.optString("body")
        rb.method(method, if (method == "GET") null else (body ?: "").toRequestBody("application/json".toMediaType()))
        val call = http.newCall(rb.build()); calls[id] = call
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: java.io.IOException) { calls.remove(id); send(w, JSONObject().put("t", "err").put("id", id).put("message", "Groq: ${e.message ?: "нет связи"}")) }
            override fun onResponse(call: Call, response: Response) {
                response.use { r ->
                    val h = JSONObject(); listOf("content-type", "retry-after").forEach { n -> r.header(n)?.let { h.put(n, it) } }
                    send(w, JSONObject().put("t", "head").put("id", id).put("status", r.code).put("headers", h))
                    try {
                        val src = r.body!!.source()
                        while (true) { val line = src.readUtf8Line() ?: break; send(w, JSONObject().put("t", "data").put("id", id).put("s", line + "\n")) }
                        send(w, JSONObject().put("t", "end").put("id", id))
                    } catch (e: Exception) { if (!call.isCanceled()) send(w, JSONObject().put("t", "err").put("id", id).put("message", "Groq: ${e.message}")) }
                    finally { calls.remove(id) }
                }
            }
        })
    }

    /** Проверка ключа Perplexity прямо с телефона (один запрос Search API). */
    suspend fun testPerplexity(key: String): String = withContext(Dispatchers.IO) {
        runCatching {
            http.newCall(Request.Builder().url("https://api.perplexity.ai/search").header("Authorization", "Bearer ${key.trim()}")
                .post("{\"query\":\"test\",\"max_results\":1}".toRequestBody("application/json".toMediaType())).build()).execute().use { r ->
                val txt = r.body?.string().orEmpty()
                if (r.isSuccessful) "✓ Ключ работает" else "✗ Perplexity ответил ${r.code}: " + txt.take(100)
            }
        }.getOrElse { "✗ Нет связи с Perplexity: ${it.message}" }
    }

    /** Проверка ключа Groq прямо с телефона. */
    suspend fun test(key: String): String = withContext(Dispatchers.IO) {
        runCatching {
            http.newCall(Request.Builder().url("https://api.groq.com/openai/v1/models").header("Authorization", "Bearer ${key.trim()}").build()).execute().use { r ->
                val txt = r.body?.string().orEmpty()
                if (r.isSuccessful) { val n = runCatching { org.json.JSONObject(txt).getJSONArray("data").length() }.getOrDefault(0); "✓ Ключ работает (моделей: $n)" }
                else "✗ Groq ответил ${r.code}: " + runCatching { JSONObject(txt).getJSONObject("error").getString("message") }.getOrDefault(txt.take(100))
            }
        }.getOrElse { "✗ Нет связи с Groq: ${it.message}" }
    }
}
