package ai.chip.app

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

data class Message(val id: Long, val fromUser: Boolean, val text: String = "", val emotionId: String? = null, val emojis: String = "")

class ChatViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("chat", 0)
    private val settingsStore = SettingsStore(app)
    private val client = RiverClient()

    val messages = mutableStateListOf<Message>()
    var thinking by mutableStateOf(false); private set
    var settings by mutableStateOf(settingsStore.load()); private set
    var offlineHint by mutableStateOf(false); private set

    init {
        load()
        if (messages.isEmpty()) messages += Message(System.nanoTime(), false, emotionId = "hello", emojis = "👋☁️")
    }

    fun send(raw: String) {
        val text = raw.trim()
        if (text.isEmpty() || thinking) return
        messages += Message(System.nanoTime(), true, text)
        save()
        thinking = true
        viewModelScope.launch {
            val started = System.currentTimeMillis()
            val history = messages.filter { it.text.isNotEmpty() || !it.fromUser }.map {
                it.fromUser to (if (it.fromUser) it.text else "[${Emotions.byId(it.emotionId).ru}] ${it.emojis}")
            }
            val r = client.reply(settings, history)
            val wait = 900 - (System.currentTimeMillis() - started)
            if (wait > 0) delay(wait)
            offlineHint = r.offline
            messages += Message(System.nanoTime(), false, emotionId = r.emotion.id, emojis = r.emojis)
            thinking = false
            save()
        }
    }

    fun clear() {
        messages.clear()
        messages += Message(System.nanoTime(), false, emotionId = "hello", emojis = "👋☁️")
        save()
    }

    fun saveSettings(s: RiverSettings) { settingsStore.save(s); settings = settingsStore.load() }

    private fun save() {
        val a = JSONArray()
        messages.takeLast(200).forEach {
            a.put(JSONObject().put("id", it.id).put("u", it.fromUser).put("t", it.text).put("e", it.emotionId ?: "").put("j", it.emojis))
        }
        prefs.edit().putString("messages", a.toString()).apply()
    }

    private fun load() {
        try {
            val a = JSONArray(prefs.getString("messages", "[]"))
            for (i in 0 until a.length()) {
                val o = a.getJSONObject(i)
                messages += Message(o.getLong("id"), o.getBoolean("u"), o.getString("t"), o.getString("e").ifEmpty { null }, o.getString("j"))
            }
        } catch (_: Exception) {}
    }
}
