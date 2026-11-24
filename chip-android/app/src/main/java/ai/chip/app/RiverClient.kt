package ai.chip.app

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class RiverSettings(val baseUrl: String, val apiKey: String, val model: String)

data class ChipReply(val emotion: Emotion, val emojis: String, val offline: Boolean = false)

class SettingsStore(context: Context) {
    private val p = context.getSharedPreferences("settings", Context.MODE_PRIVATE)
    fun load() = RiverSettings(
        p.getString("baseUrl", DEFAULT_URL)!!,
        p.getString("apiKey", "")!!,
        p.getString("model", DEFAULT_MODEL)!!,
    )
    fun save(s: RiverSettings) = p.edit()
        .putString("baseUrl", s.baseUrl.trim()).putString("apiKey", s.apiKey.trim()).putString("model", s.model.trim()).apply()

    companion object {
        // Placeholder values: confirm the real river.ai endpoint and model in Settings.
        const val DEFAULT_URL = "https://api.river.ai/v1"
        const val DEFAULT_MODEL = "river"
    }
}

/**
 * Talks to river.ai through an OpenAI-compatible /chat/completions endpoint.
 * The model only classifies the mood and picks an emotion id plus emoji; it never writes text for the user.
 */
class RiverClient {
    private val system = """
        Ты мозг милого облачка Chip. Chip не говорит словами: он отвечает только эмоцией и эмодзи.
        По последнему сообщению пользователя выбери, какую эмоцию Chip должен показать в ответ.
        Допустимые id эмоций: ${Emotions.idList}.
        Подсказки: радость - успехи и хорошие новости; любовь - нежность и симпатия; смех - шутки; грусть - печаль, проблемы;
        злость - раздражение; удивление - неожиданные новости; страх - тревога; сон - усталость, ночь;
        размышление - вопросы и сомнения; смущение - комплименты; круто - хвастовство, уверенность; привет - приветствие и прощание.
        Если пользователь грустит, лучше показать поддержку (грусть или любовь), а не радость.
        Ответь ТОЛЬКО JSON без пояснений: {"emotion":"<id>","emojis":"<1-3 эмодзи>"}
    """.trimIndent()

    suspend fun reply(settings: RiverSettings, history: List<Pair<Boolean, String>>): ChipReply = withContext(Dispatchers.IO) {
        val lastUser = history.lastOrNull { it.first }?.second.orEmpty()
        if (settings.apiKey.isBlank()) return@withContext offline(lastUser)
        try {
            val msgs = JSONArray().put(JSONObject().put("role", "system").put("content", system))
            history.takeLast(8).forEach { (fromUser, text) ->
                msgs.put(JSONObject().put("role", if (fromUser) "user" else "assistant").put("content", text))
            }
            val body = JSONObject().put("model", settings.model).put("messages", msgs).put("temperature", 0.3).put("max_tokens", 60)
            val url = URL(settings.baseUrl.trimEnd('/') + "/chat/completions")
            val c = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"; connectTimeout = 15000; readTimeout = 25000; doOutput = true
                setRequestProperty("Content-Type", "application/json")
                setRequestProperty("Authorization", "Bearer ${settings.apiKey}")
            }
            c.outputStream.use { it.write(body.toString().toByteArray()) }
            if (c.responseCode !in 200..299) return@withContext offline(lastUser)
            val text = c.inputStream.bufferedReader().readText()
            val content = JSONObject(text).getJSONArray("choices").getJSONObject(0).getJSONObject("message").getString("content")
            parse(content) ?: offline(lastUser)
        } catch (e: Exception) {
            offline(lastUser)
        }
    }

    private fun offline(text: String): ChipReply {
        val e = Emotions.guess(text)
        return ChipReply(e, e.emojis, offline = true)
    }

    internal fun parse(content: String): ChipReply? {
        val json = Regex("\\{[^{}]*\\}").find(content)?.value
        if (json != null) {
            try {
                val o = JSONObject(json)
                val e = Emotions.find(o.optString("emotion"))
                if (e != null) return ChipReply(e, o.optString("emojis").ifBlank { e.emojis })
            } catch (_: Exception) {}
        }
        val lower = content.lowercase()
        val e = Emotions.all.firstOrNull { lower.contains(it.id) } ?: return null
        return ChipReply(e, e.emojis)
    }
}
