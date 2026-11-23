package openagent.app.com

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.ReceiveChannel

/**
 * Озвучка без плеера: сервер отдаёт сырой звук (24 кГц, 16 бит, моно), а мы пишем его прямо в AudioTrack по мере прихода.
 * Звук начинается через ~100 мс после первых байтов, куски идут встык (без пауз), а конец воспроизведения известен точно —
 * статус «Говорю» сменяется на «Слушаю» сразу, как только затих последний звук.
 */
class PcmPlayer {
    @Volatile private var track: AudioTrack? = null
    @Volatile var playing = false; private set

    fun stopNow() { track?.let { runCatching { it.pause(); it.flush() } }; playing = false }

    /** chunks — очередь кусков по порядку; каждый кусок — поток байтов, закрывающийся в конце. */
    suspend fun play(chunks: ReceiveChannel<ReceiveChannel<ByteArray>>, interrupted: () -> Boolean, onStart: () -> Unit) = withContext(Dispatchers.IO) {
        val rate = 24000
        val minBuf = AudioTrack.getMinBufferSize(rate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val t = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANT).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setAudioFormat(AudioFormat.Builder().setSampleRate(rate).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
            .setBufferSizeInBytes(maxOf(minBuf, rate / 2 * 2)).setTransferMode(AudioTrack.MODE_STREAM).build()
        track = t
        var frames = 0L; var started = false
        try {
            outer@ for (ch in chunks) {
                for (b in ch) {
                    if (!isActive || interrupted()) break@outer
                    var off = 0
                    while (off < b.size) { val n = t.write(b, off, b.size - off); if (n <= 0) break; off += n }
                    frames += b.size / 2
                    if (!started) { started = true; playing = true; t.play(); withContext(Dispatchers.Main) { onStart() } }
                }
            }
            if (started && isActive && !interrupted()) {
                // дожидаемся, пока доиграет всё записанное (точная граница, а не угадывание по таймеру)
                val deadline = System.currentTimeMillis() + frames * 1000 / rate + 1500
                while (isActive && !interrupted() && t.playbackHeadPosition < frames - 120 && System.currentTimeMillis() < deadline) delay(12)
            }
        } finally {
            playing = false
            runCatching { t.pause(); t.flush() }; runCatching { t.release() }
            if (track === t) track = null
        }
    }
}
