package openagent.app.com

import android.app.Notification
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/** Срабатывание напоминания (поставлено агентом через AlarmManager.setAlarmClock). */
class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, i: Intent) { Notifier.remind(ctx, i.getStringExtra("text").orEmpty().ifBlank { "Напоминание" }) }
}

/** Читает уведомления других приложений (нужен ручной доступ в настройках Android), чтобы агент мог сделать сводку «что я пропустил». Хранит только последние 200 в памяти. */
class OaNotifService : NotificationListenerService() {
    data class Item(val app: String, val title: String, val text: String, val time: Long)
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName == packageName || sbn.isOngoing) return
        val e = sbn.notification.extras
        val title = e.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val text = (e.getCharSequence(Notification.EXTRA_BIG_TEXT) ?: e.getCharSequence(Notification.EXTRA_TEXT))?.toString().orEmpty()
        if (title.isBlank() && text.isBlank()) return
        val label = runCatching { packageManager.getApplicationLabel(packageManager.getApplicationInfo(sbn.packageName, 0)).toString() }.getOrDefault(sbn.packageName)
        synchronized(buf) { buf.addLast(Item(label, title, text, sbn.postTime)); while (buf.size > 200) buf.removeFirst() }
    }
    companion object {
        private val buf = ArrayDeque<Item>()
        fun recent(): List<Item> = synchronized(buf) { buf.toList() }
        fun enabled(ctx: Context) = androidx.core.app.NotificationManagerCompat.getEnabledListenerPackages(ctx).contains(ctx.packageName)
    }
}

/** Держит голосовой звонок живым в фоне (микрофон разрешён только службе переднего плана): когда агент открывает другое приложение, вы продолжаете с ним говорить. В шторке — кнопка «Завершить». */
class VoiceService : android.app.Service() {
    override fun onBind(i: Intent?): android.os.IBinder? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "stop") { val f = onEnd; onEnd = null; stopForeground(STOP_FOREGROUND_REMOVE); stopSelf(); f?.invoke(); return START_NOT_STICKY }
        if (Build.VERSION.SDK_INT >= 26) (getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager).createNotificationChannel(android.app.NotificationChannel("voice", "Голосовой режим", android.app.NotificationManager.IMPORTANCE_LOW))
        val open = android.app.PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), android.app.PendingIntent.FLAG_IMMUTABLE)
        val end = android.app.PendingIntent.getService(this, 1, Intent(this, VoiceService::class.java).setAction("stop"), android.app.PendingIntent.FLAG_IMMUTABLE)
        val n = androidx.core.app.NotificationCompat.Builder(this, "voice").setSmallIcon(R.drawable.ic_stat).setContentTitle("Голосовой режим").setContentText("Слушаю — можно говорить, даже когда я работаю в другом приложении")
            .setOngoing(true).setContentIntent(open).addAction(0, "Завершить", end).setPriority(androidx.core.app.NotificationCompat.PRIORITY_LOW).build()
        val ok = runCatching { androidx.core.app.ServiceCompat.startForeground(this, 3, n, if (Build.VERSION.SDK_INT >= 30) android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE else 0) }.isSuccess
        if (!ok) runCatching { startForeground(3, n) }
        return START_NOT_STICKY
    }
    companion object {
        @Volatile var onEnd: (() -> Unit)? = null
        fun start(ctx: Context, end: () -> Unit) { onEnd = end; runCatching { androidx.core.content.ContextCompat.startForegroundService(ctx, Intent(ctx, VoiceService::class.java)) } }
        fun stop(ctx: Context) { onEnd = null; runCatching { ctx.stopService(Intent(ctx, VoiceService::class.java)) } }
    }
}
