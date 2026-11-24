package openagent.app.com

import android.content.Context
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import kotlinx.coroutines.delay
import java.util.Locale
import java.util.concurrent.atomic.AtomicInteger

/** Системный синтез речи Android: работает без интернета (если у голоса скачан русский пакет). Фразы встают в очередь и звучат по порядку. */
class SysTts(private val ctx: Context) {
    private var tts: TextToSpeech? = null
    @Volatile private var ready = false
    private val pending = AtomicInteger(0)
    private var seq = 0
    private val early = ArrayList<String>()

    private fun init() {
        if (tts != null) return
        tts = TextToSpeech(ctx.applicationContext) { st ->
            val t = tts ?: return@TextToSpeech
            if (st == TextToSpeech.SUCCESS) {
                if (t.setLanguage(Locale("ru", "RU")) < 0) t.setLanguage(Locale.getDefault())
                t.setSpeechRate(1.05f)
                t.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(id: String?) {}
                    override fun onDone(id: String?) { pending.decrementAndGet() }
                    @Deprecated("") override fun onError(id: String?) { pending.decrementAndGet() }
                    override fun onError(id: String?, code: Int) { pending.decrementAndGet() }
                })
                ready = true
                synchronized(early) { early.forEach { say(it) }; early.clear() }
            }
        }
    }
    private fun say(s: String) { pending.incrementAndGet(); if (tts?.speak(s, TextToSpeech.QUEUE_ADD, Bundle(), "u${seq++}") != TextToSpeech.SUCCESS) pending.decrementAndGet() }
    fun enqueue(sentence: String) { init(); synchronized(early) { if (ready) say(sentence) else early.add(sentence) } }
    /** Ждёт, пока доиграет вся очередь. */
    suspend fun awaitDone() { var guard = 0; while ((pending.get() > 0 || synchronized(early) { early.isNotEmpty() }) && guard < 1200) { delay(100); guard++ }; if (guard >= 1200) stop() }
    fun stop() { runCatching { tts?.stop() }; pending.set(0); synchronized(early) { early.clear() } }
}
