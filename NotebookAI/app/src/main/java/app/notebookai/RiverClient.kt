package app.notebookai

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** River AI: OpenAI-совместимый API, https://docs.river.ai/guides/inference/ */
object RiverClient {
    const val DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash"

    suspend fun generate(apiKey: String, model: String, topic: String, words: Int): String = withContext(Dispatchers.IO) {
        val prompt = """Ты школьник, который пишет в рабочей тетради домашнюю работу.
Тема: $topic
Напиши конспект/ответ примерно на $words слов на языке темы. Коротко, как пишут от руки:
заголовок первой строкой, затем пункты "1.", "2." и т.д. Только простой текст:
без markdown, без звёздочек, без эмодзи, без таблиц."""
        val body = JSONObject()
            .put("model", model)
            .put("max_tokens", 6000) // запас на «размышления» модели
            .put("messages", JSONArray().put(JSONObject().put("role", "user").put("content", prompt)))
        val c = URL("https://api.river.ai/v1/chat/completions").openConnection() as HttpURLConnection
        c.requestMethod = "POST"
        c.connectTimeout = 20000
        c.readTimeout = 120000
        c.doOutput = true
        c.setRequestProperty("Content-Type", "application/json")
        c.setRequestProperty("Authorization", "Bearer $apiKey")
        c.outputStream.use { it.write(body.toString().toByteArray()) }
        val code = c.responseCode
        val text = (if (code in 200..299) c.inputStream else c.errorStream).bufferedReader().readText()
        if (code !in 200..299) error("River API $code: $text")
        val content = JSONObject(text).getJSONArray("choices").getJSONObject(0)
            .getJSONObject("message").optString("content", "")
        content.replace("**", "").replace("#", "").trim().ifEmpty { error("Пустой ответ модели") }
    }
}
