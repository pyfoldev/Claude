package openagent.app.com

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat

/** Держит процесс живым, пока агент работает в фоне, чтобы прогресс чата не терялся. */
class RunService : Service() {
    override fun onBind(i: Intent?): IBinder? = null

    private fun goForeground() {
        Notifier.ensureChannels(this)
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE)
        val n: Notification = NotificationCompat.Builder(this, Notifier.RUN)
            .setSmallIcon(R.drawable.ic_stat).setContentTitle("Агент работает").setContentText("Выполняю задачу на сервере…")
            .setOngoing(true).setContentIntent(open).setOnlyAlertOnce(true).setPriority(NotificationCompat.PRIORITY_LOW).build()
        // сначала с типом, при отказе — без него; главное — ВСЕГДА вызвать startForeground, иначе система убьёт приложение
        val ok = runCatching { ServiceCompat.startForeground(this, 1, n, if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC else 0) }.isSuccess
        if (!ok) runCatching { startForeground(1, n) }
    }

    override fun onCreate() { super.onCreate(); alive = true; goForeground() }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        goForeground()                                  // повторный вызов безопасен и гарантирует выполнение требования системы
        pending = false
        if (stopWanted) { stopWanted = false; stopForeground(STOP_FOREGROUND_REMOVE); stopSelf() }
        return START_NOT_STICKY
    }

    override fun onDestroy() { alive = false; super.onDestroy() }

    companion object {
        @Volatile private var alive = false
        @Volatile private var pending = false
        @Volatile private var stopWanted = false
        fun start(ctx: Context) {
            stopWanted = false
            if (alive) return
            pending = true
            runCatching { androidx.core.content.ContextCompat.startForegroundService(ctx, Intent(ctx, RunService::class.java)) }.onFailure { pending = false }
        }
        fun stop(ctx: Context) {
            if (alive) runCatching { ctx.stopService(Intent(ctx, RunService::class.java)) }
            else if (pending) stopWanted = true         // служба ещё стартует: остановим её сами после startForeground, а не раньше
        }
    }
}

object Notifier {
    const val RUN = "run"; const val DONE = "done"
    fun ensureChannels(ctx: Context) {
        if (Build.VERSION.SDK_INT < 26) return
        val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.createNotificationChannel(NotificationChannel(RUN, "Работа агента", NotificationManager.IMPORTANCE_LOW))
        nm.createNotificationChannel(NotificationChannel(DONE, "Готовые ответы", NotificationManager.IMPORTANCE_DEFAULT))
    }
    fun remind(ctx: Context, text: String) {
        if (Build.VERSION.SDK_INT >= 26) (ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(NotificationChannel("remind", "Напоминания", NotificationManager.IMPORTANCE_HIGH))
        val open = PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE)
        val n = NotificationCompat.Builder(ctx, "remind").setSmallIcon(R.drawable.ic_stat).setContentTitle("Напоминание").setContentText(text.take(120)).setStyle(NotificationCompat.BigTextStyle().bigText(text.take(400)))
            .setPriority(NotificationCompat.PRIORITY_HIGH).setDefaults(NotificationCompat.DEFAULT_ALL).setContentIntent(open).setAutoCancel(true).build()
        runCatching { (ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).notify((System.currentTimeMillis() % 100000).toInt() + 100, n) }
    }
    fun done(ctx: Context, title: String, text: String) {
        ensureChannels(ctx)
        val open = PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE)
        val n = NotificationCompat.Builder(ctx, DONE).setSmallIcon(R.drawable.ic_stat).setContentTitle(title).setContentText(text.take(120))
            .setStyle(NotificationCompat.BigTextStyle().bigText(text.take(400))).setContentIntent(open).setAutoCancel(true).build()
        runCatching { (ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).notify(2, n) }
    }
}
