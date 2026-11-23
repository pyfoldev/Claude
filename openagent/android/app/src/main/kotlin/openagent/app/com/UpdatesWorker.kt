package openagent.app.com

import android.content.Context
import androidx.work.*
import java.util.concurrent.TimeUnit

/** Раз в ~15 минут спрашивает сервер, не завершились ли автоматизации, и показывает уведомление. */
class UpdatesWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val store = Store(applicationContext)
        if (store.token == null || !store.notifyAuto) return Result.success()
        return runCatching {
            val api = Api(store)
            val since = store.updatesSeen.takeIf { it > 0 } ?: System.currentTimeMillis().also { store.updatesSeen = it }
            val list = api.updates(since)
            list.sortedBy { it.updatedAt }.forEach { Notifier.done(applicationContext, it.title.removePrefix("⏱").removePrefix("◷").trim().ifBlank { "Автоматизация" } + " — готово", it.preview.ifBlank { "Откройте чат, чтобы увидеть результат" }) }
            if (list.isNotEmpty()) store.updatesSeen = list.maxOf { it.updatedAt }
            Result.success()
        }.getOrElse { Result.retry() }
    }

    companion object {
        private const val NAME = "oa-updates"
        fun schedule(ctx: Context, on: Boolean) {
            val wm = WorkManager.getInstance(ctx)
            if (!on) { wm.cancelUniqueWork(NAME); return }
            wm.enqueueUniquePeriodicWork(NAME, ExistingPeriodicWorkPolicy.UPDATE,
                PeriodicWorkRequestBuilder<UpdatesWorker>(15, TimeUnit.MINUTES).setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build())
        }
    }
}
