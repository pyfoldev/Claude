package openagent.app.com

/** Локальная языковая модель (llama.cpp, GGUF) прямо на телефоне. */
class LocalLlm private constructor(private var h: Long) {
    fun interface Sink { fun onToken(piece: String): Boolean }
    private external fun nGenerate(h: Long, prompt: String, maxTokens: Int, temp: Float, topP: Float, repeat: Float, cb: Sink): String
    private external fun nFree(h: Long)
    private external fun nStop(h: Long)

    /** Один запрос за раз. Токены уходят в sink по мере генерации; sink вернёт false — остановка. */
    @Synchronized fun generate(prompt: String, maxTokens: Int, temp: Float = 0f, topP: Float = 0.9f, repeat: Float = 1.0f, sink: Sink = Sink { true }): String {
        val r = nGenerate(h, prompt, maxTokens, temp, topP, repeat, sink)
        if (r.startsWith("\u0001ERR")) throw IllegalStateException(r.removePrefix("\u0001ERR").trim())
        return r
    }
    fun stop() { if (h != 0L) nStop(h) }
    @Synchronized fun close() { if (h != 0L) { nFree(h); h = 0 } }

    private external fun nLoad(path: String, nCtx: Int, threads: Int): Long
    companion object {
        init { System.loadLibrary("oallm") }
        fun load(path: String, nCtx: Int, threads: Int): LocalLlm? {
            val probe = LocalLlm(0); val h = probe.nLoad(path, nCtx, threads)
            return if (h == 0L) null else LocalLlm(h)
        }
    }
}
