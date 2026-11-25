package app.notebookai

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

object ClaudeClient {
    private const val MODEL = "claude-haiku-5-5"

    suspend fun generate(apiKey: String, topic: String, words: Int): String = withContext(Dispatchers.IO) {
        val prompt = """Ты школьник, который пишет в рабочей тетради домашнюю работу.
Тема: $topic
Напиши конспект/ответ примерно на $words слов на языке темы. Коротко, как пишут от руки:
заголовок первой строкой, затем пункты "1.", "2." и т.д. Только простой текст:
без markdown, без звёздочек, без эмодзи, без таблиц."""
        val body = JSONObject()
            .put("model", MODEL)
            .put("max_tokens", 1500)
            .put("messages", JSONArray().put(JSONObject().put("role", "user").put("content", prompt)))
        val c = URL("https://api.anthropic.com/v1/messages").openConnection() as HttpURLConnection
        c.requestMethod = "POST"
        c.connectTimeout = 20000
        c.readTimeout = 60000
        c.doOutput = true
        c.setRequestProperty("content-type", "application/json")
        c.setRequestProperty("x-api-key", apiKey)
        c.setRequestProperty("anthropic-version", "2023-06-01")
        c.outputStream.use { it.write(body.toString().toByteArray()) }
        val code = c.responseCode
        val text = (if (code in 200..299) c.inputStream else c.errorStream).bufferedReader().readText()
        if (code !in 200..299) error("API $code: $text")
        val parts = JSONObject(text).getJSONArray("content")
        buildString {
            for (i in 0 until parts.length()) {
                val p = parts.getJSONObject(i)
                if (p.optString("type") == "text") append(p.getString("text"))
            }
        }.trim()
    }
}
