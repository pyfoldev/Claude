package openagent.app.com

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import android.widget.RemoteViews

/** Плитка быстрых настроек: открывает окно ассистента (как долгое нажатие кнопки питания). */
class OaTileService : TileService() {
    override fun onStartListening() { qsTile?.apply { state = Tile.STATE_INACTIVE; label = "OpenAgent"; updateTile() } }
    override fun onClick() {
        val i = Intent(this, AssistActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        if (Build.VERSION.SDK_INT >= 34) startActivityAndCollapse(PendingIntent.getActivity(this, 0, i, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT))
        else @Suppress("DEPRECATION") startActivityAndCollapse(i)
    }
}

/** Виджет рабочего стола: три кнопки — новый чат, голос, камера. */
class OaWidget : AppWidgetProvider() {
    override fun onUpdate(ctx: Context, mgr: AppWidgetManager, ids: IntArray) {
        val v = RemoteViews(ctx.packageName, R.layout.widget_quick)
        fun pi(action: String, code: Int) = PendingIntent.getActivity(ctx, code, Intent(ctx, MainActivity::class.java).setAction(action).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        v.setOnClickPendingIntent(R.id.w_chat, pi("openagent.NEW_CHAT", 1))
        v.setOnClickPendingIntent(R.id.w_voice, pi("openagent.VOICE", 2))
        v.setOnClickPendingIntent(R.id.w_camera, pi("openagent.CAMERA", 3))
        ids.forEach { mgr.updateAppWidget(it, v) }
    }
}
