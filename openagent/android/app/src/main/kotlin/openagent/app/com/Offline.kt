package openagent.app.com

import android.content.Context
import android.net.Uri
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import okhttp3.Request
import java.io.File
import java.io.RandomAccessFile

/** Оффлайн-режим: чат — Ministral 3 3B Instruct, управление телефоном — наша дообученная Qwen3-0.6B. Всё считается на телефоне (llama.cpp). */
object Offline {
    class Spec(val id: String, val title: String, val file: String, val size: Long, val url: (Store) -> String)

    val CHAT = Spec("chat", "Чат — Ministral 3 3B Instruct", "ministral-3-3b-q4.gguf", 2_147_023_008L) { "https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512-GGUF/resolve/main/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf" }
    val PHONE = Spec("phone", "Управление телефоном — OpenAgent Phone 0.6B", "phone.gguf", 444_000_000L) { it.phoneModelUrl.ifBlank { it.server.trimEnd('/') + "/models/phone.gguf" } }
    val ALL = listOf(CHAT, PHONE)

    val progress = mutableStateMapOf<String, Float>()      // 0..1 — идёт загрузка
    val error = mutableStateOf("")
    val tick = mutableStateOf(0)                           // меняется, когда состав файлов поменялся — для перерисовки
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val jobs = HashMap<String, Job>()
    private fun dir(ctx: Context) = File(ctx.filesDir, "models").also { it.mkdirs() }
    fun file(ctx: Context, s: Spec) = File(dir(ctx), s.file)
    fun ready(ctx: Context, s: Spec): Boolean { tick.value; return file(ctx, s).let { it.exists() && it.length() > 1_000_000 } }
    fun sizeMb(ctx: Context, s: Spec) = file(ctx, s).length() / 1_000_000

    /** Запасной источник phone.gguf: части по 50 МБ в репозитории проекта (если сервер файл не раздаёт). */
    private const val PARTS = 9
    private fun partUrl(i: Int) = "https://raw.githubusercontent.com/pyfoldev/Claude/ccr-a3a4ce88-j9zjtg/dist/phone-gguf/phone.gguf.part%02d".format(i)

    /** Скачивает один файл в dest с докачкой; onBytes(скачано всего по файлу, размер). */
    private fun fetch(url: String, dest: File, expect: Long, alive: () -> Boolean, onBytes: (Long, Long) -> Unit) {
        val have = if (dest.exists()) dest.length() else 0L
        val rq = Request.Builder().url(url).apply { if (have > 0) header("Range", "bytes=$have-") }.build()
        SharedHttp.stream.newCall(rq).execute().use { r ->
            if (r.code == 416) return
            if (!r.isSuccessful) throw IllegalStateException("HTTP ${r.code}")
            val resumed = r.code == 206
            val total = (r.body?.contentLength() ?: -1L).let { if (it > 0) it + (if (resumed) have else 0) else expect }
            RandomAccessFile(dest, "rw").use { raf ->
                if (resumed) raf.seek(have) else raf.setLength(0)
                var done = if (resumed) have else 0L; val buf = ByteArray(256 * 1024); var lastUi = 0L
                val src = r.body!!.byteStream()
                while (true) {
                    val n = src.read(buf); if (n < 0) break
                    raf.write(buf, 0, n); done += n
                    val now = System.currentTimeMillis(); if (now - lastUi > 400) { lastUi = now; onBytes(done, total) }
                    if (!alive()) return
                }
                if (total > 0 && done < total) throw IllegalStateException("Загрузка оборвалась на ${done * 100 / total}% — нажмите ещё раз, продолжу с этого места")
            }
        }
    }

    /** Загрузка с докачкой: прерванная (сеть, выгрузка из памяти) продолжается с того же места. */
    fun download(ctx: Context, store: Store, s: Spec) {
        if (jobs[s.id]?.isActive == true) return
        error.value = ""; progress[s.id] = 0f
        jobs[s.id] = scope.launch {
            val part = File(dir(ctx), s.file + ".part")
            try {
                var viaParts = false
                try { fetch(s.url(store), part, s.size, { isActive }) { d, t -> progress[s.id] = (d.toFloat() / t).coerceIn(0f, 1f) } }
                catch (e: CancellationException) { throw e }
                catch (e: Throwable) { if (s.id != "phone") throw e; viaParts = true }
                if (viaParts) {          // сервер файл не отдал — берём части из репозитория и склеиваем
                    part.delete()
                    for (i in 0 until PARTS) {
                        val pf = File(dir(ctx), s.file + ".p%02d".format(i))
                        if (!pf.exists() || pf.length() < 50_000_000L && i < PARTS - 1) fetch(partUrl(i), pf, 50_000_000L, { isActive }) { d, t -> progress[s.id] = ((i + d.toFloat() / t) / PARTS).coerceIn(0f, 1f) }
                    }
                    part.outputStream().use { o -> for (i in 0 until PARTS) { val pf = File(dir(ctx), s.file + ".p%02d".format(i)); pf.inputStream().use { it.copyTo(o) }; pf.delete() } }
                }
                if (part.exists()) { file(ctx, s).delete(); part.renameTo(file(ctx, s)) }
                withContext(Dispatchers.Main) { tick.value++ }
            } catch (e: CancellationException) { throw e } catch (e: Throwable) { error.value = e.message ?: "Ошибка загрузки" }
            finally { progress.remove(s.id) }
        }
    }
    fun cancel(s: Spec) { jobs[s.id]?.cancel(); progress.remove(s.id) }

    /** Своя копия файла (например, phone.gguf со своего компьютера) через системный выбор файла. */
    fun importFile(ctx: Context, s: Spec, uri: Uri) {
        progress[s.id] = 0f; error.value = ""
        scope.launch {
            try {
                val part = File(dir(ctx), s.file + ".part")
                ctx.contentResolver.openInputStream(uri)!!.use { i -> part.outputStream().use { o -> val buf = ByteArray(256 * 1024); var done = 0L; while (true) { val n = i.read(buf); if (n < 0) break; o.write(buf, 0, n); done += n; progress[s.id] = (done.toFloat() / s.size).coerceIn(0f, 0.99f) } } }
                file(ctx, s).delete(); part.renameTo(file(ctx, s)); unload(s)
                withContext(Dispatchers.Main) { tick.value++ }
            } catch (e: Throwable) { error.value = "Не удалось скопировать файл: ${e.message}" } finally { progress.remove(s.id) }
        }
    }
    fun delete(ctx: Context, s: Spec) { cancel(s); unload(s); file(ctx, s).delete(); File(dir(ctx), s.file + ".part").delete(); tick.value++ }

    // ---- движки ----
    private val engines = HashMap<String, LocalLlm>()
    @Synchronized private fun engine(ctx: Context, s: Spec, nCtx: Int): LocalLlm? {
        engines[s.id]?.let { return it }
        if (!ready(ctx, s)) return null
        val threads = (Runtime.getRuntime().availableProcessors() - 2).coerceIn(2, 6)
        return LocalLlm.load(file(ctx, s).absolutePath, nCtx, threads)?.also { engines[s.id] = it }
    }
    @Synchronized fun unload(s: Spec) { engines.remove(s.id)?.close() }
    fun stop() { engines.values.forEach { it.stop() } }
    @Volatile var stopRequested = false

    // ---- управление телефоном ----
    private val PHONE_PROMPT = { t: String -> "<|im_start|>user\n$t<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n" }
    class PhoneResult(val actions: List<JsonObject>, val ms: Long)

    /** Фраза → действия (или null — это не команда телефону либо модель не уверена). Числа сверяются алгоритмом, как на сервере. */
    suspend fun phoneActions(ctx: Context, text: String): PhoneResult? = withContext(Dispatchers.Default) {
        val m = engine(ctx, PHONE, 512) ?: return@withContext null
        val t0 = System.currentTimeMillis()
        val out = runCatching { m.generate(PHONE_PROMPT(text.take(300)), 160, 0f) }.getOrNull()?.trim() ?: return@withContext null
        val arr = runCatching { Json.parseToJsonElement(out).jsonArray }.getOrNull() ?: return@withContext null
        val acts = arr.map { it as? JsonObject ?: return@withContext null }
        if (acts.isEmpty() || acts.size > 4) return@withContext null
        for (a in acts) if (SlotCheck.validate(a) != null) return@withContext null
        if (!SlotCheck.slotsOk(acts, text) || !SlotCheck.groundedOk(acts, text)) return@withContext null
        PhoneResult(acts, System.currentTimeMillis() - t0)
    }

    private fun describe(a: JsonObject): String {
        fun s(k: String) = a[k]?.jsonPrimitive?.contentOrNull.orEmpty()
        return when (s("action")) { "call" -> "позвонить: ${s("to")}"; "message" -> "написать ${s("to")} в ${s("app")}: «${s("text")}»"; "close_app" -> "закрыть ${s("app")}"; else -> s("action") }
    }
    /** Опасное требует «да»: звонок, сообщение, закрытие приложения. */
    private val RISKY = setOf("call", "message", "close_app")
    private var pending: List<JsonObject>? = null
    private fun isYes(t: String) = Regex("^(да|ага|угу|давай|ок|окей|подтверждаю|выполняй|делай|конечно|yes)\\b", RegexOption.IGNORE_CASE).containsMatchIn(t.trim())

    private suspend fun execute(ctx: Context, acts: List<JsonObject>): String { val out = ArrayList<String>(); for (a in acts) out.add(PhoneControl.run(ctx, a)); return out.joinToString("\n") }

    // ---- чат ----
    private fun chatPrompt(history: List<Pair<String, String>>): String {
        val date = java.text.SimpleDateFormat("d MMMM yyyy, EEEE", java.util.Locale("ru")).format(java.util.Date())
        val sys = "Ты — OpenAgent, ассистент на телефоне владельца. Сейчас работаешь без интернета, прямо на устройстве. Отвечай по-человечески, кратко и по делу, на языке собеседника. Сегодня $date. Ты не можешь искать в сети и не знаешь новостей; если для ответа нужен интернет или свежие данные — так и скажи. Команды вроде «открой приложение», «поставь будильник», «включи фонарик» обрабатываются отдельно; если просят что-то с телефоном, чего не получилось сделать, предложи сформулировать проще."
        val sb = StringBuilder("[SYSTEM_PROMPT]").append(sys).append("[/SYSTEM_PROMPT]")
        // окно контекста небольшое — берём хвост диалога по размеру
        var budget = 7000; val keep = ArrayList<Pair<String, String>>()
        for (m in history.asReversed()) { budget -= m.second.length; if (budget < 0 && keep.isNotEmpty()) break; keep.add(0, m) }
        for ((role, text) in keep) { if (role == "user") sb.append("[INST]").append(text).append("[/INST]") else sb.append(text).append("</s>") }
        return sb.toString()
    }

    /** Ответ на сообщение полностью на телефоне. history — прошлые реплики без текущей. onDelta получает кусочки ответа чата. */
    suspend fun reply(ctx: Context, text: String, history: List<Pair<String, String>>, onStatus: (String) -> Unit, onDelta: (String) -> Unit): String {
        stopRequested = false
        pending?.let { p -> pending = null; if (isYes(text)) { onStatus("Выполняю…"); return execute(ctx, p) } }
        if (ready(ctx, PHONE)) {
            onStatus("Разбираю команду…")
            val r = phoneActions(ctx, text)
            if (r != null) {
                val risky = r.actions.filter { it.jsonPrimitive("action") in RISKY }
                if (risky.isNotEmpty()) { pending = r.actions; return "Подтвердите: ${r.actions.joinToString("; ") { describe(it) }}. Скажите «да», чтобы выполнить." }
                onStatus("Выполняю…")
                return execute(ctx, r.actions)
            }
        }
        if (!ready(ctx, CHAT)) return "Оффлайн-модель чата ещё не загружена: Настройки → Оффлайн-режим."
        onStatus("Думаю…")
        return withContext(Dispatchers.Default) {
            val m = engine(ctx, CHAT, 4096) ?: return@withContext "Не удалось загрузить модель — возможно, не хватает памяти телефона."
            val sb = StringBuilder()
            try { m.generate(chatPrompt(history + ("user" to text)), 700, 0.5f, 0.9f, 1.05f) { piece -> sb.append(piece); onDelta(piece); !stopRequested } }
            catch (e: Throwable) { return@withContext "Ошибка модели: ${e.message}" }
            sb.toString().trim().ifBlank { "…" }
        }
    }
    private fun JsonObject.jsonPrimitive(k: String) = this[k]?.jsonPrimitive?.contentOrNull
}
