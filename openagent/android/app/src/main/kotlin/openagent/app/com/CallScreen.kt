package openagent.app.com

import android.Manifest
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.os.Build
import android.os.IBinder
import android.telecom.TelecomManager
import android.telephony.PhoneStateListener
import android.telephony.TelephonyCallback
import android.telephony.TelephonyManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import java.io.File

/**
 * Автоответчик: если вы не берёте трубку дольше N секунд, ассистент сам берёт её, говорит, что вас нет на месте и вы перезвоните,
 * спрашивает, что передать, записывает ответ звонящего, расшифровывает и присылает вам уведомлением + заметкой.
 * Экспериментально: Android не даёт приложениям звук разговора, поэтому ассистент говорит через громкую связь, а слышит звонящего через микрофон телефона.
 */
class CallScreenService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var job: Job? = null
    private var tm: TelephonyManager? = null
    private var cb: Any? = null
    @Volatile private var busy = false

    override fun onBind(i: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Notifier.ensureChannels(this)
        if (Build.VERSION.SDK_INT >= 26) (getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager).createNotificationChannel(android.app.NotificationChannel("callscreen", "Автоответчик", android.app.NotificationManager.IMPORTANCE_LOW))
        val open = android.app.PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), android.app.PendingIntent.FLAG_IMMUTABLE)
        val n = NotificationCompat.Builder(this, "callscreen").setSmallIcon(R.drawable.ic_stat).setContentTitle("Автоответчик включён").setContentText("Возьму трубку, если вы не ответите за ${Store(this).callDelay} с").setOngoing(true).setContentIntent(open).setPriority(NotificationCompat.PRIORITY_LOW).build()
        val ok = runCatching { androidx.core.app.ServiceCompat.startForeground(this, 4, n, if (Build.VERSION.SDK_INT >= 30) android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE else 0) }.isSuccess
        if (!ok) runCatching { startForeground(4, n) }
        register()
        return START_STICKY
    }

    private fun register() {
        if (cb != null || ContextCompat.checkSelfPermission(this, Manifest.permission.READ_PHONE_STATE) != PackageManager.PERMISSION_GRANTED) return
        val t = getSystemService(Context.TELEPHONY_SERVICE) as TelephonyManager; tm = t
        if (Build.VERSION.SDK_INT >= 31) {
            val c = object : TelephonyCallback(), TelephonyCallback.CallStateListener { override fun onCallStateChanged(state: Int) = onState(state, "") }
            cb = c; t.registerTelephonyCallback(mainExecutor, c)
        } else @Suppress("DEPRECATION") {
            val l = object : PhoneStateListener() { @Deprecated("") override fun onCallStateChanged(state: Int, number: String?) = onState(state, number.orEmpty()) }
            cb = l; t.listen(l, PhoneStateListener.LISTEN_CALL_STATE)
        }
    }

    private fun onState(state: Int, numberHint: String) {
        when (state) {
            TelephonyManager.CALL_STATE_RINGING -> if (!busy) {
                job?.cancel()
                job = scope.launch {
                    delay(Store(this@CallScreenService).callDelay.coerceIn(8, 60) * 1000L)
                    if (tm?.callState == TelephonyManager.CALL_STATE_RINGING) screen(numberHint)
                }
            }
            TelephonyManager.CALL_STATE_IDLE -> if (!busy) job?.cancel()
            else -> if (!busy) job?.cancel()        // сняли трубку сами
        }
    }

    private fun lastIncomingNumber(): String? {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CALL_LOG) != PackageManager.PERMISSION_GRANTED) return null
        return runCatching { contentResolver.query(android.provider.CallLog.Calls.CONTENT_URI, arrayOf(android.provider.CallLog.Calls.NUMBER), null, null, "${android.provider.CallLog.Calls.DATE} DESC")?.use { if (it.moveToFirst()) it.getString(0) else null } }.getOrNull()
    }
    private fun nameOf(number: String): String? {
        if (number.isBlank() || ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) return null
        return runCatching { contentResolver.query(android.net.Uri.withAppendedPath(android.provider.ContactsContract.PhoneLookup.CONTENT_FILTER_URI, android.net.Uri.encode(number)), arrayOf(android.provider.ContactsContract.PhoneLookup.DISPLAY_NAME), null, null, null)?.use { if (it.moveToFirst()) it.getString(0) else null } }.getOrNull()
    }

    private suspend fun speak(api: Api, voice: String, text: String) {
        val f = runCatching { api.tts(text, File(cacheDir, "cs_${System.nanoTime()}.mp3"), voice) }.getOrNull() ?: return
        suspendCancellableCoroutine<Unit> { c ->
            val mp = MediaPlayer().apply {
                setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                setDataSource(f.absolutePath); setOnCompletionListener { release(); if (c.isActive) c.resume(Unit) {} }; setOnErrorListener { m, _, _ -> m.release(); if (c.isActive) c.resume(Unit) {}; true }
                prepare(); start()
            }
            c.invokeOnCancellation { runCatching { mp.release() } }
        }
        f.delete()
    }

    @android.annotation.SuppressLint("MissingPermission")
    private suspend fun screen(hint: String) {
        busy = true
        val store = Store(this); val api = Api(store)
        val number = hint.ifBlank { lastIncomingNumber().orEmpty() }
        val who = nameOf(number) ?: number.ifBlank { "неизвестный номер" }
        var transcript = ""
        try {
            val telecom = getSystemService(Context.TELECOM_SERVICE) as TelecomManager
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.ANSWER_PHONE_CALLS) != PackageManager.PERMISSION_GRANTED) { Notifier.done(this, "Автоответчик", "Нет разрешения «принимать вызовы» — включите в настройках"); return }
            telecom.acceptRingingCall()
            delay(1200)
            val am = getSystemService(Context.AUDIO_SERVICE) as AudioManager
            runCatching { if (Build.VERSION.SDK_INT >= 31) am.availableCommunicationDevices.firstOrNull { it.type == android.media.AudioDeviceInfo.TYPE_BUILTIN_SPEAKER }?.let { am.setCommunicationDevice(it) } else @Suppress("DEPRECATION") { am.isSpeakerphoneOn = true } }
            val owner = store.profileName.ifBlank { "владелец этого телефона" }
            val voice = runCatching { api.currentVoice().id }.getOrDefault("")
            speak(api, voice, "Здравствуйте! Это голосовой ассистент. $owner сейчас не может ответить и перезвонит вам позже. Что ему передать?")
            val rec = Recorder(this)
            if (rec.start()) {
                var spoke = false; var quiet = 0; var total = 0
                while (total < 20000) {
                    delay(100); total += 100
                    val l = rec.level()
                    if (l > 0.08f) { spoke = true; quiet = 0 } else if (spoke) quiet += 100
                    if (spoke && quiet >= 1600) break
                    if (!spoke && total > 9000) break
                }
                val f = rec.stop()
                if (spoke && f != null) transcript = runCatching { api.stt(f, "ru") }.getOrDefault("").trim()
                f?.delete()
            }
            speak(api, voice, if (transcript.isBlank()) "Не расслышал, но передам, что вы звонили. До свидания!" else "Спасибо, передам. До свидания!")
            runCatching { if (Build.VERSION.SDK_INT >= 28) telecom.endCall() }
            runCatching { if (Build.VERSION.SDK_INT >= 31) am.clearCommunicationDevice() else @Suppress("DEPRECATION") { am.isSpeakerphoneOn = false } }
        } catch (e: CancellationException) { throw e } catch (e: Throwable) { transcript = transcript.ifBlank { "(ошибка автоответчика: ${e.message})" } }
        finally {
            val msg = if (transcript.isBlank()) "Звонил: $who. Сообщение не оставил." else "Звонил: $who. Сообщение: $transcript"
            Notifier.done(this, "Пропущенный звонок", msg)
            runCatching { api.addNote("📞 $msg") }
            busy = false
        }
    }

    override fun onDestroy() {
        job?.cancel(); scope.cancel()
        runCatching { if (Build.VERSION.SDK_INT >= 31) (cb as? TelephonyCallback)?.let { tm?.unregisterTelephonyCallback(it) } else @Suppress("DEPRECATION") (cb as? PhoneStateListener)?.let { tm?.listen(it, PhoneStateListener.LISTEN_NONE) } }
        super.onDestroy()
    }

    companion object {
        fun start(ctx: Context) { runCatching { ContextCompat.startForegroundService(ctx, Intent(ctx, CallScreenService::class.java)) } }
        fun stop(ctx: Context) { runCatching { ctx.stopService(Intent(ctx, CallScreenService::class.java)) } }
    }
}
