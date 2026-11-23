package openagent.app.com

import android.accessibilityservice.AccessibilityService
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.camera2.CameraManager
import android.media.AudioManager
import android.net.Uri
import android.provider.AlarmClock
import android.provider.Settings
import android.view.accessibility.AccessibilityNodeInfo
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.delay
import kotlinx.serialization.json.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody

/** Служба доступности: нужна для действий, которые Android не даёт приложениям напрямую (закрыть приложение, Wi-Fi/Bluetooth, чтение экрана). Включается пользователем вручную. */
class OaAccessibilityService : AccessibilityService() {
    override fun onServiceConnected() { super.onServiceConnected(); instance = this }
    override fun onAccessibilityEvent(e: android.view.accessibility.AccessibilityEvent?) {}
    override fun onInterrupt() {}
    override fun onUnbind(intent: Intent?): Boolean { if (instance === this) instance = null; return super.onUnbind(intent) }

    fun global(a: Int) = performGlobalAction(a)

    /** Скриншот через службу доступности (Android 11+). null — недоступно. */
    suspend fun screenshot(): android.graphics.Bitmap? {
        if (android.os.Build.VERSION.SDK_INT < 30) return null
        return kotlinx.coroutines.suspendCancellableCoroutine { c ->
            takeScreenshot(android.view.Display.DEFAULT_DISPLAY, mainExecutor, object : TakeScreenshotCallback {
                override fun onSuccess(r: ScreenshotResult) {
                    val bmp = runCatching { android.graphics.Bitmap.wrapHardwareBuffer(r.hardwareBuffer, r.colorSpace)?.copy(android.graphics.Bitmap.Config.ARGB_8888, false) }.getOrNull()
                    runCatching { r.hardwareBuffer.close() }
                    if (c.isActive) c.resume(bmp) {}
                }
                override fun onFailure(code: Int) { if (c.isActive) c.resume(null) {} }
            })
        }
    }

    private fun walk(n: AccessibilityNodeInfo?, out: MutableList<AccessibilityNodeInfo>, depth: Int = 0) {
        if (n == null || depth > 40 || out.size > 1500) return
        out.add(n)
        for (i in 0 until n.childCount) walk(n.getChild(i), out, depth + 1)
    }
    fun nodes(): List<AccessibilityNodeInfo> { val l = ArrayList<AccessibilityNodeInfo>(); walk(rootInActiveWindow, l); return l }

    fun find(words: List<String>): AccessibilityNodeInfo? {
        val ws = words.map { it.lowercase() }
        return nodes().firstOrNull { n ->
            val t = ((n.text?.toString() ?: "") + " " + (n.contentDescription?.toString() ?: "")).lowercase()
            ws.any { t.contains(it) }
        }
    }
    fun clickNode(n: AccessibilityNodeInfo): Boolean {
        var c: AccessibilityNodeInfo? = n
        while (c != null) { if (c.isClickable && c.isEnabled) return c.performAction(AccessibilityNodeInfo.ACTION_CLICK); c = c.parent }
        return false
    }
    // ---- жесты и ввод ----
    private suspend fun gesture(path: android.graphics.Path, ms: Long): Boolean = kotlinx.coroutines.suspendCancellableCoroutine { c ->
        val g = android.accessibilityservice.GestureDescription.Builder().addStroke(android.accessibilityservice.GestureDescription.StrokeDescription(path, 0, ms.coerceAtLeast(1))).build()
        val ok = dispatchGesture(g, object : GestureResultCallback() {
            override fun onCompleted(d: android.accessibilityservice.GestureDescription?) { if (c.isActive) c.resume(true) {} }
            override fun onCancelled(d: android.accessibilityservice.GestureDescription?) { if (c.isActive) c.resume(false) {} }
        }, null)
        if (!ok && c.isActive) c.resume(false) {}
    }
    suspend fun tapAt(x: Float, y: Float, hold: Long = 60) = gesture(android.graphics.Path().apply { moveTo(x, y) }, hold)
    suspend fun swipe(x1: Float, y1: Float, x2: Float, y2: Float, ms: Long = 350) = gesture(android.graphics.Path().apply { moveTo(x1, y1); lineTo(x2, y2) }, ms)
    /** direction — куда листаем контент: down = вниз по ленте (палец движется вверх). */
    suspend fun scroll(direction: String): Boolean {
        val w = resources.displayMetrics.widthPixels.toFloat(); val h = resources.displayMetrics.heightPixels.toFloat()
        return when (direction) {
            "up" -> swipe(w / 2, h * 0.30f, w / 2, h * 0.72f)
            "left" -> swipe(w * 0.2f, h / 2, w * 0.8f, h / 2)
            "right" -> swipe(w * 0.8f, h / 2, w * 0.2f, h / 2)
            else -> swipe(w / 2, h * 0.72f, w / 2, h * 0.30f)
        }
    }
    private fun center(n: AccessibilityNodeInfo): Pair<Float, Float> { val r = android.graphics.Rect(); n.getBoundsInScreen(r); return r.exactCenterX() to r.exactCenterY() }
    fun findBest(q: String): AccessibilityNodeInfo? {
        val k = q.lowercase().trim(); if (k.isBlank()) return null
        val all = nodes().filter { it.isVisibleToUser }
        fun label(n: AccessibilityNodeInfo) = ((n.text?.toString() ?: "") + " " + (n.contentDescription?.toString() ?: "")).lowercase().trim()
        return all.firstOrNull { label(it) == k } ?: all.firstOrNull { n -> val t = label(n); t.contains(k) && (n.isClickable || n.parent?.isClickable == true) } ?: all.firstOrNull { label(it).contains(k) }
            ?: all.firstOrNull { (it.hintText?.toString() ?: "").lowercase().contains(k) || (it.viewIdResourceName ?: "").lowercase().contains(k) }
    }
    suspend fun tapNode(n: AccessibilityNodeInfo, hold: Long = 60): Boolean {
        if (hold <= 60 && clickNode(n)) return true
        val (x, y) = center(n); return tapAt(x, y, hold)
    }
    fun typeText(text: String, field: String, append: Boolean): Boolean {
        val all = nodes()
        val target = (if (field.isNotBlank()) findBest(field) else null)?.takeIf { it.isEditable } ?: all.firstOrNull { it.isEditable && it.isFocused } ?: all.firstOrNull { it.isEditable && it.isVisibleToUser } ?: return false
        target.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
        val cur = if (append) (target.text?.toString() ?: "") else ""
        val args = android.os.Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, cur + text) }
        return target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }
    fun pressEnter(): Boolean {
        val f = nodes().firstOrNull { it.isEditable && it.isFocused }
        if (f != null && android.os.Build.VERSION.SDK_INT >= 30 && f.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id)) return true
        val b = find(listOf("найти", "поиск", "search", "отправить", "send", "go", "перейти")) ?: return false
        return clickNode(b)
    }
    /** Экран для модели: подписи + координаты, чтобы можно было нажимать и по тексту, и по точке. */
    @Volatile private var lastItems: List<Pair<Float, Float>> = emptyList()
    fun itemAt(i: Int): Pair<Float, Float>? = lastItems.getOrNull(i - 1)
    /** Ждёт, пока экран перестанет меняться (анимации, загрузка), но не дольше maxMs. */
    suspend fun settle(maxMs: Long = 1800) {
        var prev = screenMap(); var waited = 0L
        while (waited < maxMs) { kotlinx.coroutines.delay(250); waited += 250; val cur = screenMap(); if (cur == prev) return; prev = cur }
    }
    /** Экран для модели: пронумерованные элементы с подписью и координатами — нажимать надёжнее всего по номеру [n]. */
    fun screenMap(): String {
        val seen = HashSet<String>(); val out = StringBuilder(); val items = ArrayList<Pair<Float, Float>>()
        val w = resources.displayMetrics.widthPixels; val h = resources.displayMetrics.heightPixels
        out.append("Экран ${w}x$h. Элементы пронумерованы: tap{index:N} — самый точный способ нажать.\n")
        for (n in nodes()) {
            if (!n.isVisibleToUser) continue
            var t = (n.text?.toString()?.takeIf { it.isNotBlank() } ?: n.contentDescription?.toString()?.takeIf { it.isNotBlank() } ?: n.hintText?.toString()?.takeIf { it.isNotBlank() } ?: n.tooltipText?.toString()?.takeIf { it.isNotBlank() })?.replace('\n', ' ')?.take(70)
            val kind = when { n.isEditable -> "поле ввода"; n.isClickable || n.parent?.isClickable == true -> "кнопка"; n.isScrollable -> "прокручивается"; else -> "" }
            if (t == null && kind == "кнопка") t = n.viewIdResourceName?.substringAfter('/')?.let { "id:$it" }      // иконка без подписи: хотя бы имя ресурса (send, search…)
            if (t == null && kind != "поле ввода" && kind != "прокручивается") continue
            val r = android.graphics.Rect(); n.getBoundsInScreen(r)
            if (r.width() <= 0 || r.height() <= 0) continue
            val x = r.exactCenterX().coerceIn(1f, w - 1f); val y = r.exactCenterY().coerceIn(1f, h - 1f)
            val key = "${t}|${x.toInt()}|${y.toInt()}"
            if (!seen.add(key)) continue
            items.add(x to y)
            out.append("[${items.size}] ${t ?: "(без подписи)"}${if (kind.isNotEmpty()) " ($kind)" else ""} @${x.toInt()},${y.toInt()}\n")
            if (items.size >= 70) break
        }
        lastItems = items
        return out.toString().take(4200)
    }
    fun screenText(): String = nodes().mapNotNull { n -> (n.text?.toString() ?: n.contentDescription?.toString())?.takeIf { it.isNotBlank() } }.distinct().joinToString("\n").take(3500)

    companion object { @Volatile var instance: OaAccessibilityService? = null }
}

object PhoneControl {
    private val ALIAS = mapOf("ютуб" to "youtube", "ютьюб" to "youtube", "телеграм" to "telegram", "телега" to "telegram", "ватсап" to "whatsapp", "вотсап" to "whatsapp",
        "инстаграм" to "instagram", "тикток" to "tiktok", "хром" to "chrome", "браузер" to "chrome", "камера" to "camera", "камеру" to "camera", "галерея" to "gallery", "галерею" to "gallery",
        "настройки" to "settings", "карты" to "maps", "музыка" to "music", "часы" to "clock", "калькулятор" to "calculator", "почта" to "mail", "контакты" to "contacts", "телефон" to "phone")

    private data class App(val label: String, val pkg: String)
    private fun launchable(ctx: Context): List<App> {
        val pm = ctx.packageManager
        val i = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        return pm.queryIntentActivities(i, 0).map { App(it.loadLabel(pm).toString(), it.activityInfo.packageName) }.distinctBy { it.pkg }
    }
    private fun findApp(ctx: Context, q: String): App? {
        val raw = q.trim().lowercase(); if (raw.isBlank()) return null
        val key = ALIAS[raw] ?: raw
        val apps = launchable(ctx)
        return apps.firstOrNull { it.label.lowercase() == raw || it.label.lowercase() == key }
            ?: apps.firstOrNull { it.label.lowercase().contains(key) || it.label.lowercase().contains(raw) }
            ?: apps.firstOrNull { it.pkg.lowercase().contains(key) }
    }
    private fun start(ctx: Context, i: Intent): Boolean = runCatching { ctx.startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); true }.getOrDefault(false)
    private fun a11y() = OaAccessibilityService.instance
    private const val NEED_A11Y = "Нужна служба доступности: Настройки OpenAgent → «Управление телефоном» → включить OpenAgent."

    suspend fun run(ctx: Context, a: JsonObject): String {
        fun s(k: String) = a[k]?.jsonPrimitive?.contentOrNull.orEmpty()
        fun i(k: String) = a[k]?.jsonPrimitive?.intOrNull
        fun b(k: String) = a[k]?.jsonPrimitive?.booleanOrNull
        return runCatching { when (s("action")) {
            "open_app" -> {
                val app = findApp(ctx, s("app")) ?: return "Приложение «${s("app")}» не найдено. Установлено, например: " + launchable(ctx).take(15).joinToString { it.label }
                val intent = ctx.packageManager.getLaunchIntentForPackage(app.pkg) ?: return "У «${app.label}» нет окна запуска"
                if (start(ctx, intent)) "Открыл ${app.label}" else "Не удалось открыть ${app.label} (Android не разрешает запуск из фона — откройте OpenAgent и повторите)"
            }
            "close_app" -> {
                val app = findApp(ctx, s("app")) ?: return "Приложение «${s("app")}» не найдено"
                runCatching { (ctx.getSystemService(Context.ACTIVITY_SERVICE) as android.app.ActivityManager).killBackgroundProcesses(app.pkg) }
                val svc = a11y() ?: return "Фоновые процессы ${app.label} остановлены. Полностью закрыть открытое приложение можно со службой доступности. $NEED_A11Y"
                if (!start(ctx, Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${app.pkg}")))) return "Не удалось открыть настройки приложения"
                delay(900)
                val stop = svc.find(listOf("остановить", "force stop", "принудительно", "завершить"))
                if (stop == null || !svc.clickNode(stop)) { svc.global(AccessibilityService.GLOBAL_ACTION_HOME); return "Не нашёл кнопку «Остановить» для ${app.label}" }
                delay(700)
                svc.find(listOf("ok", "ок", "остановить", "force stop"))?.let { svc.clickNode(it) }
                delay(400); svc.global(AccessibilityService.GLOBAL_ACTION_HOME)
                "Закрыл ${app.label}"
            }
            "alarm" -> {
                val h = i("hour") ?: return "Не указан час"; val m = i("minute") ?: 0
                val intent = Intent(AlarmClock.ACTION_SET_ALARM).putExtra(AlarmClock.EXTRA_HOUR, h).putExtra(AlarmClock.EXTRA_MINUTES, m).putExtra(AlarmClock.EXTRA_MESSAGE, s("label")).putExtra(AlarmClock.EXTRA_SKIP_UI, true)
                if (start(ctx, intent)) "Будильник на %02d:%02d установлен".format(h, m) else "Приложение «Часы» не приняло команду"
            }
            "timer" -> {
                val sec = i("seconds") ?: return "Не указана длительность"
                val intent = Intent(AlarmClock.ACTION_SET_TIMER).putExtra(AlarmClock.EXTRA_LENGTH, sec).putExtra(AlarmClock.EXTRA_MESSAGE, s("label")).putExtra(AlarmClock.EXTRA_SKIP_UI, true)
                if (start(ctx, intent)) "Таймер на ${if (sec >= 60) "${sec / 60} мин ${sec % 60} с" else "$sec с"} запущен" else "Приложение «Часы» не приняло команду"
            }
            "stopwatch" -> stopwatch(ctx, s("op").ifBlank { "start" })
            "flashlight" -> {
                val cm = ctx.getSystemService(Context.CAMERA_SERVICE) as CameraManager
                val id = cm.cameraIdList.firstOrNull { cm.getCameraCharacteristics(it).get(android.hardware.camera2.CameraCharacteristics.FLASH_INFO_AVAILABLE) == true } ?: return "На телефоне нет вспышки"
                val on = b("on") ?: true
                cm.setTorchMode(id, on); if (on) "Фонарик включён" else "Фонарик выключен"
            }
            "toggle" -> toggle(ctx, s("target").lowercase(), b("on"))
            "volume" -> {
                val am = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
                val stream = when (s("target")) { "ring" -> AudioManager.STREAM_RING; "alarm" -> AudioManager.STREAM_ALARM; else -> AudioManager.STREAM_MUSIC }
                val lvl = (i("level") ?: return "Не указан уровень").coerceIn(0, 100)
                am.setStreamVolume(stream, (am.getStreamMaxVolume(stream) * lvl / 100f).toInt(), AudioManager.FLAG_SHOW_UI); "Громкость $lvl%"
            }
            "brightness" -> {
                if (!Settings.System.canWrite(ctx)) { start(ctx, Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS, Uri.parse("package:${ctx.packageName}"))); return "Нужно разрешение «Изменение системных настроек» — открыл экран, включите его для OpenAgent и повторите." }
                val lvl = (i("level") ?: return "Не указан уровень").coerceIn(0, 100)
                Settings.System.putInt(ctx.contentResolver, Settings.System.SCREEN_BRIGHTNESS_MODE, Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL)
                Settings.System.putInt(ctx.contentResolver, Settings.System.SCREEN_BRIGHTNESS, (255 * lvl / 100f).toInt().coerceAtLeast(2)); "Яркость $lvl%"
            }
            "open_url" -> if (start(ctx, Intent(Intent.ACTION_VIEW, Uri.parse(s("url").let { if (it.startsWith("http")) it else "https://$it" })))) "Открыл ссылку" else "Не удалось открыть ссылку"
            "system" -> system(ctx, s("op"))
            "read_screen" -> a11y()?.screenMap()?.ifBlank { "Экран пуст или недоступен для чтения" } ?: NEED_A11Y
            "tap", "long_press" -> {
                val svc = a11y() ?: return NEED_A11Y
                val hold = if (s("action") == "long_press") 750L else 60L
                val idxPoint = i("index")?.let { svc.itemAt(it) ?: return "Нет элемента [${i("index")}] — сначала вызовите read_screen" }
                val before = svc.screenMap()
                var node: AccessibilityNodeInfo? = null
                var desc: String
                var ok: Boolean
                if (idxPoint != null) { ok = svc.tapAt(idxPoint.first, idxPoint.second, hold); desc = "Нажал [${i("index")}]" }
                else if (s("text").isNotBlank()) {
                    node = svc.findBest(s("text"))
                    if (node == null && b("scroll") == true) { repeat(5) { if (node == null) { svc.scroll("down"); delay(500); node = svc.findBest(s("text")) } } }
                    val nn = node ?: return "Не нашёл на экране «${s("text")}»${if (b("scroll") == true) " даже после прокрутки" else " (можно scroll:true)"}. Экран:\n" + svc.screenMap()
                    ok = svc.tapNode(nn, hold); desc = "Нажал «${s("text")}»"
                } else {
                    val x = i("x") ?: return "Нужен index, text или x,y"; val y = i("y") ?: return "Нужен index, text или x,y"
                    ok = svc.tapAt(x.toFloat(), y.toFloat(), hold); desc = "Нажал ($x,$y)"
                }
                svc.settle(); var after = svc.screenMap()
                if (after == before && hold <= 60 && node != null) {                // системный клик не изменил экран — повторяем жестом в центре элемента
                    val r = android.graphics.Rect(); node!!.getBoundsInScreen(r); svc.tapAt(r.exactCenterX(), r.exactCenterY(), 80); svc.settle(); after = svc.screenMap(); desc += " (повтор жестом)"
                }
                (if (!ok) "Жест не выполнен. " else "") + desc + (if (after == before) "\n⚠ Экран не изменился — нажатие могло не сработать (или элемент не реагирует). Проверьте по списку и нажмите точнее: tap{index}." else "") + "\nЭкран теперь:\n" + after.take(2400)
            }
            "scroll", "swipe" -> {
                val svc = a11y() ?: return NEED_A11Y
                val times = (i("times") ?: 1).coerceIn(1, 6)
                val ok = if (i("x") != null && i("y") != null && i("x2") != null && i("y2") != null) svc.swipe(i("x")!!.toFloat(), i("y")!!.toFloat(), i("x2")!!.toFloat(), i("y2")!!.toFloat())
                    else { var r = true; repeat(times) { r = svc.scroll(s("direction").lowercase().ifBlank { "down" }) && r; delay(350) }; r }
                svc.settle(); (if (ok) "Прокрутил" else "Жест не выполнен") + "\nЭкран теперь:\n" + svc.screenMap().take(2400)
            }
            "type" -> {
                val svc = a11y() ?: return NEED_A11Y
                val ok = svc.typeText(s("text"), s("field"), b("append") == true)
                if (!ok) return "Не нашёл поле ввода. Нажмите на него (tap) и повторите. Экран:\n" + svc.screenMap().take(1500)
                if (b("submit") == true) { delay(300); svc.pressEnter() }
                svc.settle(); "Ввёл текст" + (if (b("submit") == true) " и отправил" else "") + "\nЭкран теперь:\n" + svc.screenMap().take(1800)
            }
            "enter" -> { val svc = a11y() ?: return NEED_A11Y; val ok = svc.pressEnter(); delay(700); (if (ok) "Подтвердил" else "Не нашёл кнопку подтверждения") + "\n" + svc.screenMap().take(1500) }
            "wait" -> { delay(((i("seconds") ?: 1).coerceIn(1, 10) * 1000).toLong()); "Подождал" }
            "remind" -> remind(ctx, s("text"), i("minutes"), s("at"))
            "calendar_list" -> calendarList(ctx, i("days") ?: 2)
            "calendar_add" -> calendarAdd(ctx, s("title"), s("at"), i("minutes") ?: 60, s("location"))
            "notifications" -> notifications(ctx, s("app"), i("minutes") ?: 180)
            "location" -> location(ctx)
            "http_get" -> httpGet(s("url"), s("method").ifBlank { "GET" }, a["headers"] as? JsonObject, s("body"))
            "site_probe" -> siteProbe(s("url"))
            "web_capture" -> webCapture(ctx, s("url"), (i("seconds") ?: 10).coerceIn(4, 25), b("hook") != false, s("js"))
            "contacts" -> contacts(ctx, s("query"))
            "call" -> call(ctx, s("to"))
            "sms" -> sms(ctx, s("to"), s("text"))
            "message" -> message(ctx, s("app"), s("to"), s("text"))
            "watch_screen" -> {
                val svc = a11y() ?: return NEED_A11Y
                val words = s("until").lowercase().split(',', ';').map { it.trim() }.filter { it.isNotEmpty() }
                val deadline = System.currentTimeMillis() + (i("seconds") ?: 30).coerceIn(5, 45) * 1000L
                var map = svc.screenMap(); var hit: String? = null
                while (System.currentTimeMillis() < deadline) {
                    val low = map.lowercase(); hit = words.firstOrNull { low.contains(it) }
                    if (hit != null) break
                    delay(3000); map = svc.screenMap()
                }
                (if (hit != null) "Появилось: «$hit»" else "Пока не появилось (${words.joinToString()})") + "\nЭкран:\n" + map.take(2200)
            }
            "media" -> media(ctx, s("op"))
            "music_play" -> musicPlay(ctx, s("query"), s("app"))
            else -> "Неизвестная команда: ${s("action")}"
        } }.getOrElse { "Ошибка: ${it.message}" }
    }

    private const val MOBILE_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
    private val netClient by lazy { okhttp3.OkHttpClient.Builder().dns(object : okhttp3.Dns { override fun lookup(hostname: String) = okhttp3.Dns.SYSTEM.lookup(hostname).sortedBy { it is java.net.Inet6Address } }).connectTimeout(12, java.util.concurrent.TimeUnit.SECONDS).readTimeout(20, java.util.concurrent.TimeUnit.SECONDS).followRedirects(true).build() }

    /** Запрос с самого телефона (его IP и регион): для сайтов, закрытых для сервера. Ответ целиком уходит на сервер, там он сохраняется/сокращается. */
    private suspend fun httpGet(url: String, method: String, headers: JsonObject?, body: String): String = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
        if (!url.startsWith("http")) return@withContext "Нужен url (https://…)"
        val rb = if (method.equals("GET", true) || method.equals("HEAD", true)) null else body.toRequestBody("application/json".toMediaTypeOrNull())
        val req = okhttp3.Request.Builder().url(url).method(method.uppercase(), rb).header("User-Agent", MOBILE_UA).header("Accept", "application/json, text/plain, */*").apply { headers?.forEach { (k, v) -> header(k, v.jsonPrimitive.content) } }.build()
        fun run(rq: okhttp3.Request) = netClient.newCall(rq).execute().use { r -> "httpresp:${r.code}\n" + (r.body?.string().orEmpty().take(900_000)) }
        runCatching { run(req) }.recoverCatching { e ->
            // сайт мог не поддерживать выбранную схему (https у сайта, который работает только по http, даёт «connection refused») — пробуем вторую
            val alt = altScheme(url) ?: throw e
            run(req.newBuilder().url(alt).build())
        }.getOrElse { "Ошибка запроса: ${it.javaClass.simpleName}: ${it.message}${it.cause?.let { c -> " ← ${c.javaClass.simpleName}: ${c.message}" } ?: ""}" }
    }

    // Перехват запросов страницы. WebSocket оборачиваем через Proxy: статические поля (OPEN, CLOSED…) и прототип остаются родными — иначе библиотеки сайта (SockJS, socket.io) падают с JS-ошибкой.
    /** https↔http: многие городские сервисы работают только по http. */
    private fun altScheme(u: String): String? = when { u.startsWith("https://") -> "http://" + u.removePrefix("https://"); u.startsWith("http://") -> "https://" + u.removePrefix("http://"); else -> null }
    private fun abs(base: String, u: String): String = runCatching { java.net.URI(base).resolve(u).toString() }.getOrDefault(u)
    /** Без браузера и JS: берёт HTML, находит скрипты сайта, читает их и вытаскивает адреса API/WebSocket — работает, даже когда скрытый браузер не может открыть страницу. */
    private suspend fun siteProbe(url: String): String = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
        if (!url.startsWith("http")) return@withContext "Нужен url (https://…)"
        fun get(u: String, max: Int): Pair<Int, String> = netClient.newCall(okhttp3.Request.Builder().url(u).header("User-Agent", MOBILE_UA).header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8").header("Accept-Language", "ru-RU,ru;q=0.9,en;q=0.8").build()).execute().use { r -> r.code to (r.body?.string().orEmpty().take(max)) }
        var base = url
        val (code, html) = runCatching { get(url, 400_000) }.recoverCatching { e -> val alt = altScheme(url) ?: throw e; base = alt; get(alt, 400_000) }.getOrElse { return@withContext "Не удалось открыть $url: ${it.javaClass.simpleName}: ${it.message}${it.cause?.let { c -> " ← ${c.message}" } ?: ""}" }
        val scripts = Regex("<script[^>]+src=[\"']([^\"']+)[\"']", RegexOption.IGNORE_CASE).findAll(html).map { abs(base, it.groupValues[1]) }.distinct().toList()
        val inline = Regex("<script(?![^>]*src)[^>]*>([\\s\\S]*?)</script>", RegexOption.IGNORE_CASE).findAll(html).joinToString("\n") { it.groupValues[1] }.take(200_000)
        val found = LinkedHashSet<String>(); val errs = ArrayList<String>()
        val rxPath = Regex("[\"'`]((?:https?:)?//[A-Za-z0-9._:\\-]+)?(/(?:api|rest|ajax|json|data|track|tracking|geo|ws|socket|signalr|v[0-9])[A-Za-z0-9_/.\\-?=&{}$:]*)[\"'`]")
        val rxUrl = Regex("(?:https?|wss?)://[A-Za-z0-9._:\\-]+(?:/[A-Za-z0-9_/.\\-?=&%{}$:]*)?")
        fun scan(t: String) { rxPath.findAll(t).forEach { found.add((it.groupValues[1] + it.groupValues[2]).take(160)) }; rxUrl.findAll(t).forEach { u -> if (Regex("api|ws|socket|track|bus|stop|route|vehicle|transport|go2|pvl|arriv|position|json", RegexOption.IGNORE_CASE).containsMatchIn(u.value)) found.add(u.value.take(160)) } }
        scan(inline); scan(html)
        scripts.filter { !it.contains("google") && !it.contains("yandex") && !it.contains("gstatic") }.take(8).forEach { s -> runCatching { scan(get(s, 900_000).second) }.onFailure { errs.add("${s.take(80)}: ${it.message}") } }
        val title = Regex("<title>([\\s\\S]*?)</title>", RegexOption.IGNORE_CASE).find(html)?.groupValues?.get(1)?.trim().orEmpty()
        "HTTP $code · $title · ${html.length / 1024} КБ\nСкрипты: ${scripts.take(10).joinToString(" ") { it.substringAfterLast('/').take(40) }}\nКандидаты API/WebSocket (${found.size}):\n" + found.take(60).joinToString("\n").ifBlank { "(не найдено — возможно, адреса собираются в коде динамически; используйте web_capture)" } + (if (errs.isNotEmpty()) "\nОшибки чтения скриптов: " + errs.joinToString("; ") else "")
    }

    private const val HOOK = "(function(){if(window.__oa)return;window.__oa=1;var L=function(t,u,s,b){try{OA.log(t+' '+u+' '+(s||'')+' '+String(b||'').slice(0,500));}catch(e){}};window.addEventListener('error',function(e){L('jserror',e.filename+':'+e.lineno,'',e.message);});window.addEventListener('unhandledrejection',function(e){L('jsreject','','',String(e.reason&&e.reason.message||e.reason));});try{var of=window.fetch;if(of)window.fetch=function(){var a=arguments;var u=(a[0]&&a[0].url)||a[0];var p=of.apply(this,a);try{p.then(function(r){try{r.clone().text().then(function(t){L('fetch',u,r.status,t);}).catch(function(){});}catch(e){}}).catch(function(){});}catch(e){}return p;};}catch(e){}try{var ox=XMLHttpRequest.prototype.open,os=XMLHttpRequest.prototype.send;XMLHttpRequest.prototype.open=function(m,u){this.__u=u;this.__m=m;return ox.apply(this,arguments);};XMLHttpRequest.prototype.send=function(){var x=this;try{x.addEventListener('load',function(){try{L('xhr '+x.__m,x.__u,x.status,(x.responseType===''||x.responseType==='text')?x.responseText:'['+x.responseType+']');}catch(e){}});}catch(e){}return os.apply(this,arguments);};}catch(e){}try{var OW=window.WebSocket;if(OW&&window.Proxy){window.WebSocket=new Proxy(OW,{construct:function(t,a,nt){var w=Reflect.construct(t,a,nt);L('ws',a[0],'open','');var n=0;try{w.addEventListener('message',function(e){if(n++<3)L('ws-msg',a[0],'',typeof e.data==='string'?e.data:'[binary]');});}catch(e){}return w;}});}}catch(e){}})();"
    private const val GLOBALS_JS = "(function(){try{var f=document.createElement('iframe');f.style.display='none';document.body.appendChild(f);var s=new Set(Object.getOwnPropertyNames(f.contentWindow));var r=Object.getOwnPropertyNames(window).filter(function(k){return !s.has(k)&&k!=='OA'&&k!=='__oa'});document.body.removeChild(f);return r.slice(0,70).join(',');}catch(e){return 'err '+e;}})()"

    private class Cap(val reqs: List<String>, val log: List<String>, val errs: List<String>, val text: String, val globals: String, val jsOut: String)

    @android.annotation.SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
    private suspend fun captureOnce(ctx: Context, url: String, seconds: Int, hook: Boolean, js: String): Cap {
        val log = java.util.Collections.synchronizedList(ArrayList<String>()); val reqs = java.util.Collections.synchronizedSet(LinkedHashSet<String>()); val errs = java.util.Collections.synchronizedList(ArrayList<String>())
        var text = ""; var globals = ""; var jsOut = ""
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
            val wv = android.webkit.WebView(ctx.applicationContext)
            wv.settings.userAgentString = wv.settings.userAgentString.replace("; wv", "").replace(Regex("Version/[\\d.]+ "), "")      // как у обычного Chrome: часть сайтов/WAF отбрасывает «WebView»
            wv.settings.apply { javaScriptEnabled = true; domStorageEnabled = true; databaseEnabled = true; setGeolocationEnabled(true); mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_ALWAYS_ALLOW; javaScriptCanOpenWindowsAutomatically = false; loadWithOverviewMode = true; useWideViewPort = true; mediaPlaybackRequiresUserGesture = true }
            android.webkit.CookieManager.getInstance().apply { setAcceptCookie(true); setAcceptThirdPartyCookies(wv, true) }
            wv.addJavascriptInterface(object { @android.webkit.JavascriptInterface fun log(s: String) { if (log.size < 90) log.add(s) } }, "OA")
            wv.webChromeClient = object : android.webkit.WebChromeClient() {
                override fun onGeolocationPermissionsShowPrompt(origin: String?, cb: android.webkit.GeolocationPermissions.Callback?) { cb?.invoke(origin, true, false) }
                override fun onConsoleMessage(m: android.webkit.ConsoleMessage): Boolean { if (m.messageLevel() == android.webkit.ConsoleMessage.MessageLevel.ERROR && errs.size < 25) errs.add("console: ${m.message().take(200)} (${m.sourceId().substringAfterLast('/')}:${m.lineNumber()})"); return true }
            }
            wv.webViewClient = object : android.webkit.WebViewClient() {
                override fun onPageStarted(v: android.webkit.WebView, u: String?, f: android.graphics.Bitmap?) { if (hook) v.evaluateJavascript(HOOK, null) }
                override fun onPageFinished(v: android.webkit.WebView, u: String?) { if (hook) v.evaluateJavascript(HOOK, null) }
                override fun onReceivedError(v: android.webkit.WebView, r: android.webkit.WebResourceRequest, e: android.webkit.WebResourceError) { if (errs.size < 25) errs.add("сеть: ${e.description} ← ${r.url.toString().take(120)}") }
                override fun onReceivedHttpError(v: android.webkit.WebView, r: android.webkit.WebResourceRequest, e: android.webkit.WebResourceResponse) { if (e.statusCode >= 400 && errs.size < 25) errs.add("HTTP ${e.statusCode} ← ${r.url.toString().take(120)}") }
                override fun onReceivedSslError(v: android.webkit.WebView, h: android.webkit.SslErrorHandler, e: android.net.http.SslError) { if (errs.size < 25) errs.add("SSL: ${e.primaryError} ← ${e.url.take(100)} (разрешено для чтения публичных данных)"); h.proceed() }
                override fun shouldInterceptRequest(v: android.webkit.WebView?, r: android.webkit.WebResourceRequest?): android.webkit.WebResourceResponse? {
                    val u = r?.url?.toString().orEmpty()
                    if (u.startsWith("http") && !Regex("\\.(js|css|png|jpe?g|gif|svg|webp|woff2?|ttf|ico|map)(\\?|$)", RegexOption.IGNORE_CASE).containsMatchIn(u) && reqs.size < 70) reqs.add("${r?.method} $u")
                    return null
                }
            }
            wv.loadUrl(url)
            delay(seconds * 1000L)
            suspend fun eval(code: String): String = kotlinx.coroutines.suspendCancellableCoroutine { c -> wv.evaluateJavascript(code) { c.resume(it ?: "") {} } }
            text = eval("(document.title+' | '+(document.body&&document.body.innerText||'')).slice(0,1200)")
            globals = eval(GLOBALS_JS)
            if (js.isNotBlank()) { jsOut = eval(js); if (jsOut.length > 2500) jsOut = jsOut.take(2500) + "…" }
            runCatching { wv.stopLoading(); wv.destroy() }
        }
        return Cap(reqs.toList(), synchronized(log) { log.toList() }, errs.toList(), text, globals, jsOut)
    }

    /** Открывает страницу в скрытом WebView и записывает, какие API/WebSocket она вызывает, какие JS-ошибки и что в ответах — так находим «скрытые» API сайтов без документации. */
    private suspend fun webCapture(ctx: Context, url: String, seconds: Int, hook: Boolean, js: String): String {
        if (!url.startsWith("http")) return "Нужен url (https://…)"
        var c = captureOnce(ctx, url, seconds, hook, js); var note = ""
        if (c.text.length < 5 && c.errs.any { it.startsWith("сеть") && (it.contains("REFUSED") || it.contains("CLEARTEXT") || it.contains("SSL") || it.contains("CONNECTION")) }) altScheme(url)?.let { alt -> val c2 = captureOnce(ctx, alt, seconds, hook, js); if (c2.text.length >= 5 || c2.reqs.size > c.reqs.size) { c = c2; note = "(https не открылся — открыл по $alt)\n" } }
        // страница ругается JS-ошибками и при этом перехват ничего не поймал — возможно, мешает наш перехват: повторяем без него
        if (hook && c.errs.any { it.startsWith("console") } && c.log.none { !it.startsWith("js") }) { val c2 = captureOnce(ctx, url, seconds, false, js); if (c2.errs.size < c.errs.size || c2.text.length > c.text.length) { c = c2; note = "(повтор без перехвата — со встроенным перехватом страница падала)\n" } }
        val sb = StringBuilder(note).append("Запросы страницы (без картинок/скриптов):\n").append(c.reqs.joinToString("\n").ifBlank { "(нет)" })
        sb.append("\n\nОтветы API / WebSocket:\n").append(c.log.joinToString("\n") { it.take(560) }.ifBlank { "(нет; адреса запросов выше можно вызвать через http_get)" })
        if (c.errs.isNotEmpty()) sb.append("\n\nОшибки загрузки/JS:\n").append(c.errs.joinToString("\n"))
        if (c.globals.isNotBlank() && c.globals != "\"\"") sb.append("\n\nГлобальные объекты страницы (возможное состояние приложения; читать через js): ").append(c.globals.trim('"'))
        if (c.jsOut.isNotBlank()) sb.append("\n\nРезультат js: ").append(c.jsOut)
        sb.append("\n\nТекст страницы: ").append(c.text.trim('"').take(1200))
        return sb.toString().take(10000)
    }

    private fun granted(ctx: Context, p: String) = androidx.core.content.ContextCompat.checkSelfPermission(ctx, p) == PackageManager.PERMISSION_GRANTED
    private const val NEED_PERM = "Нет разрешения. Откройте OpenAgent → Настройки → «Данные и подключения» → «Разрешения для звонков и сообщений»."

    private fun contacts(ctx: Context, q: String): String {
        if (!granted(ctx, android.Manifest.permission.READ_CONTACTS)) return NEED_PERM
        val res = ArrayList<String>()
        ctx.contentResolver.query(android.provider.ContactsContract.CommonDataKinds.Phone.CONTENT_URI, arrayOf(android.provider.ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME, android.provider.ContactsContract.CommonDataKinds.Phone.NUMBER),
            if (q.isBlank()) null else "${android.provider.ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} LIKE ?", if (q.isBlank()) null else arrayOf("%$q%"), "${android.provider.ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} ASC")?.use { c ->
            while (c.moveToNext() && res.size < 10) res.add("${c.getString(0)}: ${c.getString(1)}")
        }
        return if (res.isEmpty()) "Контакт «$q» не найден" else res.distinct().joinToString("\n")
    }
    /** Имя из контактов или номер → номер в формате цифр (с плюсом, если был). */
    private fun resolveNumber(ctx: Context, to: String): String? {
        val raw = to.trim()
        if (raw.count { it.isDigit() } >= 5 && raw.all { it.isDigit() || it in "+ ()-" }) return raw.filter { it.isDigit() || it == '+' }
        if (!granted(ctx, android.Manifest.permission.READ_CONTACTS)) return null
        var found: String? = null
        ctx.contentResolver.query(android.provider.ContactsContract.CommonDataKinds.Phone.CONTENT_URI, arrayOf(android.provider.ContactsContract.CommonDataKinds.Phone.NUMBER),
            "${android.provider.ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} LIKE ?", arrayOf("%$raw%"), null)?.use { c -> if (c.moveToFirst()) found = c.getString(0)?.filter { it.isDigit() || it == '+' } }
        return found
    }
    private fun call(ctx: Context, to: String): String {
        if (to.isBlank()) return "Кому звонить?"
        val num = resolveNumber(ctx, to) ?: return "Не нашёл номер для «$to». ${if (!granted(ctx, android.Manifest.permission.READ_CONTACTS)) NEED_PERM else "Назовите номер или точное имя."}"
        val uri = Uri.parse("tel:" + Uri.encode(num))
        return if (granted(ctx, android.Manifest.permission.CALL_PHONE) && start(ctx, Intent(Intent.ACTION_CALL, uri))) "Звоню: $to ($num)"
        else if (start(ctx, Intent(Intent.ACTION_DIAL, uri))) "Открыл набор номера $num — нажмите «позвонить» (нет разрешения на прямой звонок)" else "Не удалось начать звонок"
    }
    private suspend fun sms(ctx: Context, to: String, text: String): String {
        if (text.isBlank()) return "Нет текста сообщения"
        val num = resolveNumber(ctx, to) ?: return "Не нашёл номер для «$to». ${if (!granted(ctx, android.Manifest.permission.READ_CONTACTS)) NEED_PERM else "Назовите номер или точное имя."}"
        if (granted(ctx, android.Manifest.permission.SEND_SMS)) {
            return runCatching {
                @Suppress("DEPRECATION") val sm = if (android.os.Build.VERSION.SDK_INT >= 31) ctx.getSystemService(android.telephony.SmsManager::class.java) else android.telephony.SmsManager.getDefault()
                sm.sendMultipartTextMessage(num, null, sm.divideMessage(text), null, null); "SMS отправлено: $to ($num)"
            }.getOrElse { "Не удалось отправить SMS: ${it.message}" }
        }
        if (!start(ctx, Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:$num")).putExtra("sms_body", text))) return "Не удалось открыть сообщения"
        delay(1800)
        val svc = a11y()
        val send = svc?.find(listOf("отправить", "send"))
        return if (send != null && svc.clickNode(send)) "SMS отправлено: $to" else "Открыл SMS с текстом — нажмите «отправить» (нет разрешения SEND_SMS или службы доступности)"
    }
    private suspend fun message(ctx: Context, app: String, to: String, text: String): String {
        if (text.isBlank()) return "Нет текста сообщения"
        val which = when { app.lowercase().let { "whats" in it || "ват" in it || "вот" in it } -> "wa"; app.lowercase().let { "tele" in it || "теле" in it || it == "tg" } -> "tg"; else -> return "Поддерживаются whatsapp и telegram (app)" }
        val svc = a11y() ?: return NEED_A11Y
        val t = to.trim()
        if (which == "wa") {
            val num = resolveNumber(ctx, t)?.filter { it.isDigit() } ?: return "Не нашёл номер для «$to». Назовите номер в международном формате или выдайте доступ к контактам."
            val i = Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/$num?text=" + Uri.encode(text)))
            val pk = listOf("com.whatsapp", "com.whatsapp.w4b").firstOrNull { runCatching { ctx.packageManager.getPackageInfo(it, 0) }.isSuccess }
            if (pk != null) i.setPackage(pk)
            if (!start(ctx, i)) return "Не удалось открыть WhatsApp"
            delay(3000)
            val b = svc.find(listOf("отправить", "send")) ?: return "Открыл чат с текстом, но не нашёл кнопку отправки. Экран:\n" + svc.screenMap().take(1200)
            svc.clickNode(b); delay(700); return "WhatsApp: отправлено → $to"
        }
        val uri = if (t.startsWith("@")) "tg://resolve?domain=${t.drop(1)}" else {
            val num = resolveNumber(ctx, t)?.filter { it.isDigit() } ?: return "Не нашёл номер для «$to». Укажите @username, номер или выдайте доступ к контактам."
            "tg://resolve?phone=$num"
        }
        val i = Intent(Intent.ACTION_VIEW, Uri.parse(uri)).apply { runCatching { ctx.packageManager.getPackageInfo("org.telegram.messenger", 0) }.onSuccess { setPackage("org.telegram.messenger") } }
        if (!start(ctx, i)) return "Не удалось открыть Telegram"
        delay(3000)
        if (!svc.typeText(text, "", false)) return "Открыл чат, но не нашёл поле ввода. Экран:\n" + svc.screenMap().take(1200)
        delay(500)
        val b = svc.find(listOf("отправить", "send")) ?: return "Текст введён, но не нашёл кнопку отправки. Экран:\n" + svc.screenMap().take(1200)
        svc.clickNode(b); delay(700); return "Telegram: отправлено → $to"
    }

    private fun parseLocal(at: String): Long? = listOf("yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd HH:mm", "yyyy-MM-dd'T'HH:mm:ss").firstNotNullOfOrNull { f -> runCatching { java.text.SimpleDateFormat(f, java.util.Locale.US).parse(at.trim())?.time }.getOrNull() }

    private fun remind(ctx: Context, text: String, minutes: Int?, at: String): String {
        if (text.isBlank()) return "О чём напомнить?"
        val trigger = minutes?.let { System.currentTimeMillis() + it * 60_000L } ?: parseLocal(at) ?: return "Нужно minutes или at (например 2026-11-20T18:30)"
        if (trigger <= System.currentTimeMillis()) return "Это время уже прошло"
        val am = ctx.getSystemService(Context.ALARM_SERVICE) as android.app.AlarmManager
        val code = (trigger / 1000).toInt()
        val fire = android.app.PendingIntent.getBroadcast(ctx, code, Intent(ctx, ReminderReceiver::class.java).putExtra("text", text), android.app.PendingIntent.FLAG_IMMUTABLE or android.app.PendingIntent.FLAG_UPDATE_CURRENT)
        val show = android.app.PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java), android.app.PendingIntent.FLAG_IMMUTABLE)
        am.setAlarmClock(android.app.AlarmManager.AlarmClockInfo(trigger, show), fire)     // точное срабатывание без спец. разрешений
        return "Напомню в " + java.text.SimpleDateFormat("d MMM HH:mm", java.util.Locale("ru")).format(java.util.Date(trigger)) + ": $text"
    }

    private fun calendarList(ctx: Context, days: Int): String {
        if (!granted(ctx, android.Manifest.permission.READ_CALENDAR)) return NEED_PERM
        val from = System.currentTimeMillis(); val to = from + days.coerceIn(1, 30) * 86_400_000L
        val b = android.provider.CalendarContract.Instances.CONTENT_URI.buildUpon().also { android.content.ContentUris.appendId(it, from); android.content.ContentUris.appendId(it, to) }.build()
        val f = java.text.SimpleDateFormat("d MMM HH:mm", java.util.Locale("ru"))
        val out = ArrayList<String>()
        ctx.contentResolver.query(b, arrayOf(android.provider.CalendarContract.Instances.TITLE, android.provider.CalendarContract.Instances.BEGIN, android.provider.CalendarContract.Instances.END, android.provider.CalendarContract.Instances.EVENT_LOCATION, android.provider.CalendarContract.Instances.ALL_DAY), null, null, "${android.provider.CalendarContract.Instances.BEGIN} ASC")?.use { c ->
            while (c.moveToNext() && out.size < 25) out.add((if (c.getInt(4) == 1) "весь день" else f.format(java.util.Date(c.getLong(1)))) + " — " + (c.getString(0) ?: "(без названия)") + (c.getString(3)?.takeIf { it.isNotBlank() }?.let { " · $it" } ?: ""))
        }
        return if (out.isEmpty()) "Событий на ближайшие $days дн. нет" else out.joinToString("\n")
    }

    private fun calendarAdd(ctx: Context, title: String, at: String, minutes: Int, location: String): String {
        if (!granted(ctx, android.Manifest.permission.WRITE_CALENDAR)) return NEED_PERM
        val start = parseLocal(at) ?: return "Нужно at в формате 2026-11-20T18:30"
        if (title.isBlank()) return "Нужен title"
        var calId = -1L
        ctx.contentResolver.query(android.provider.CalendarContract.Calendars.CONTENT_URI, arrayOf(android.provider.CalendarContract.Calendars._ID), "${android.provider.CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL}>=500 AND ${android.provider.CalendarContract.Calendars.VISIBLE}=1", null, "${android.provider.CalendarContract.Calendars.IS_PRIMARY} DESC")?.use { if (it.moveToFirst()) calId = it.getLong(0) }
        if (calId < 0) return "Не нашёл календарь с правом записи (войдите в Google-аккаунт в календаре)"
        val v = android.content.ContentValues().apply {
            put(android.provider.CalendarContract.Events.CALENDAR_ID, calId); put(android.provider.CalendarContract.Events.TITLE, title)
            put(android.provider.CalendarContract.Events.DTSTART, start); put(android.provider.CalendarContract.Events.DTEND, start + minutes.coerceAtLeast(5) * 60_000L)
            put(android.provider.CalendarContract.Events.EVENT_TIMEZONE, java.util.TimeZone.getDefault().id); if (location.isNotBlank()) put(android.provider.CalendarContract.Events.EVENT_LOCATION, location)
        }
        return if (ctx.contentResolver.insert(android.provider.CalendarContract.Events.CONTENT_URI, v) != null) "Добавил в календарь: $title, ${java.text.SimpleDateFormat("d MMM HH:mm", java.util.Locale("ru")).format(java.util.Date(start))}" else "Не удалось добавить событие"
    }

    private fun notifications(ctx: Context, app: String, minutes: Int): String {
        if (!OaNotifService.enabled(ctx)) { runCatching { start(ctx, Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }; return "Нужен доступ к уведомлениям: включите OpenAgent в открывшемся списке (или Настройки OpenAgent → «Доступ к уведомлениям»)." }
        val since = System.currentTimeMillis() - minutes.coerceIn(5, 1440) * 60_000L
        val f = java.text.SimpleDateFormat("HH:mm", java.util.Locale("ru"))
        val items = OaNotifService.recent().filter { it.time >= since && (app.isBlank() || it.app.lowercase().contains(app.lowercase())) }.takeLast(40)
        return if (items.isEmpty()) "Новых уведомлений за $minutes мин. нет" else items.joinToString("\n") { "${f.format(java.util.Date(it.time))} [${it.app}] ${it.title}: ${it.text}".take(220) }
    }

    @android.annotation.SuppressLint("MissingPermission")
    private fun location(ctx: Context): String {
        if (!granted(ctx, android.Manifest.permission.ACCESS_FINE_LOCATION) && !granted(ctx, android.Manifest.permission.ACCESS_COARSE_LOCATION)) return NEED_PERM
        val lm = ctx.getSystemService(Context.LOCATION_SERVICE) as android.location.LocationManager
        val best = lm.getProviders(true).mapNotNull { runCatching { lm.getLastKnownLocation(it) }.getOrNull() }.maxByOrNull { it.time } ?: return "Местоположение сейчас недоступно (включите геолокацию и откройте Карты на секунду)"
        val age = (System.currentTimeMillis() - best.time) / 60000
        return "%.5f,%.5f (точность ~%d м, %d мин назад)".format(java.util.Locale.US, best.latitude, best.longitude, best.accuracy.toInt(), age)
    }

    private fun media(ctx: Context, op: String): String {
        val am = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        fun key(code: Int) { am.dispatchMediaKeyEvent(android.view.KeyEvent(android.view.KeyEvent.ACTION_DOWN, code)); am.dispatchMediaKeyEvent(android.view.KeyEvent(android.view.KeyEvent.ACTION_UP, code)) }
        return when (op) {
            "play" -> { key(android.view.KeyEvent.KEYCODE_MEDIA_PLAY); "Воспроизведение" }
            "pause" -> { key(android.view.KeyEvent.KEYCODE_MEDIA_PAUSE); "Пауза" }
            "toggle" -> { key(android.view.KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE); "Play/Pause" }
            "next" -> { key(android.view.KeyEvent.KEYCODE_MEDIA_NEXT); "Следующий трек" }
            "prev", "previous" -> { key(android.view.KeyEvent.KEYCODE_MEDIA_PREVIOUS); "Предыдущий трек" }
            "stop" -> { key(android.view.KeyEvent.KEYCODE_MEDIA_STOP); "Остановил" }
            "forward" -> { key(android.view.KeyEvent.KEYCODE_MEDIA_FAST_FORWARD); "Перемотка вперёд" }
            "rewind" -> { key(android.view.KeyEvent.KEYCODE_MEDIA_REWIND); "Перемотка назад" }
            "volume_up" -> { am.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_RAISE, AudioManager.FLAG_SHOW_UI); "Громче" }
            "volume_down" -> { am.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_LOWER, AudioManager.FLAG_SHOW_UI); "Тише" }
            "status" -> if (am.isMusicActive) "Сейчас что-то играет" else "Ничего не играет"
            else -> "Неизвестная операция: $op (play|pause|toggle|next|prev|stop|forward|rewind|volume_up|volume_down|status)"
        }
    }

    private suspend fun musicPlay(ctx: Context, query: String, app: String): String {
        if (query.isBlank()) return "Не указано, что включить"
        val pkg = app.takeIf { it.isNotBlank() }?.let { findApp(ctx, it)?.pkg }
        val i = Intent(android.provider.MediaStore.INTENT_ACTION_MEDIA_PLAY_FROM_SEARCH).putExtra(android.app.SearchManager.QUERY, query)
            .putExtra(android.provider.MediaStore.EXTRA_MEDIA_FOCUS, "vnd.android.cursor.item/*").apply { pkg?.let { setPackage(it) } }
        val ok = start(ctx, i)
        if (!ok) return "Не нашёл музыкальное приложение, которое умеет искать и играть. Укажите app (например Spotify, YouTube Music) или откройте приложение и используйте tap/type."
        delay(2500)
        val svc = a11y()
        // многие плееры открывают поиск, но не жмут «играть» — пробуем нажать «Воспроизвести/Play/Перемешать»
        val btn = svc?.find(listOf("воспроизвести", "слушать", "play", "перемешать", "shuffle"))
        if (btn != null && svc.clickNode(btn)) return "Включаю «$query»"
        return "Запустил поиск «$query»" + (svc?.let { "\nЭкран:\n" + it.screenMap().take(1500) } ?: " (для автоматического запуска включите службу доступности)")
    }

    private fun system(ctx: Context, op: String): String {
        val svc = a11y()
        return when (op) {
            "home" -> { if (svc != null) svc.global(AccessibilityService.GLOBAL_ACTION_HOME) else start(ctx, Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME)); "Рабочий стол" }
            "back" -> svc?.let { it.global(AccessibilityService.GLOBAL_ACTION_BACK); "Назад" } ?: NEED_A11Y
            "recents" -> svc?.let { it.global(AccessibilityService.GLOBAL_ACTION_RECENTS); "Недавние приложения" } ?: NEED_A11Y
            "notifications" -> svc?.let { it.global(AccessibilityService.GLOBAL_ACTION_NOTIFICATIONS); "Шторка уведомлений" } ?: NEED_A11Y
            "quick_settings" -> svc?.let { it.global(AccessibilityService.GLOBAL_ACTION_QUICK_SETTINGS); "Быстрые настройки" } ?: NEED_A11Y
            "lock" -> svc?.let { it.global(AccessibilityService.GLOBAL_ACTION_LOCK_SCREEN); "Экран заблокирован" } ?: NEED_A11Y
            else -> "Неизвестная системная команда: $op"
        }
    }

    private val TILES = mapOf(
        "wifi" to listOf("wi-fi", "wifi", "вай-фай", "интернет", "internet"), "bluetooth" to listOf("bluetooth", "блютуз"),
        "airplane" to listOf("авиарежим", "режим полёта", "режим полета", "airplane", "flight"), "dnd" to listOf("не беспокоить", "do not disturb"),
        "autorotate" to listOf("автоповорот", "auto-rotate", "auto rotate", "поворот"), "nfc" to listOf("nfc"), "hotspot" to listOf("точка доступа", "hotspot", "модем"),
        "location" to listOf("геолокация", "местоположение", "location", "gps"), "battery_saver" to listOf("экономия заряда", "энергосбережение", "battery saver"))
    private val PANELS = mapOf("wifi" to Settings.Panel.ACTION_WIFI, "bluetooth" to Settings.ACTION_BLUETOOTH_SETTINGS, "airplane" to Settings.ACTION_AIRPLANE_MODE_SETTINGS,
        "nfc" to Settings.ACTION_NFC_SETTINGS, "location" to Settings.ACTION_LOCATION_SOURCE_SETTINGS, "hotspot" to Settings.ACTION_WIRELESS_SETTINGS, "battery_saver" to Settings.ACTION_BATTERY_SAVER_SETTINGS,
        "dnd" to Settings.ACTION_ZEN_MODE_PRIORITY_SETTINGS, "autorotate" to Settings.ACTION_DISPLAY_SETTINGS)

    private fun stateOf(n: AccessibilityNodeInfo): Boolean? {
        if (n.isCheckable) return n.isChecked
        val t = ((n.text?.toString() ?: "") + " " + (n.contentDescription?.toString() ?: "") + " " + (n.stateDescription?.toString() ?: "")).lowercase()
        return when { Regex("выкл|\\boff\\b").containsMatchIn(t) -> false; Regex("вкл|\\bon\\b").containsMatchIn(t) -> true; else -> null }
    }

    private suspend fun toggle(ctx: Context, target: String, on: Boolean?): String {
        val words = TILES[target] ?: return "Неизвестная настройка: $target"
        val svc = a11y()
        if (svc == null) {
            PANELS[target]?.let { start(ctx, Intent(it)) }
            return "Открыл настройки «$target» — включить/выключить там нужно вручную. Чтобы я делал это сам: $NEED_A11Y"
        }
        svc.global(AccessibilityService.GLOBAL_ACTION_QUICK_SETTINGS)
        var tile: AccessibilityNodeInfo? = null
        repeat(8) { if (tile == null) { delay(250); tile = svc.find(words) } }
        val n = tile ?: run { svc.global(AccessibilityService.GLOBAL_ACTION_HOME); return "Не нашёл переключатель «$target» в быстрых настройках" }
        val before = stateOf(n)
        if (on != null && before == on) { svc.global(AccessibilityService.GLOBAL_ACTION_HOME); return "«$target» уже ${if (on) "включён" else "выключен"}" }
        val ok = svc.clickNode(n)
        delay(450)
        val after = svc.find(words)?.let { stateOf(it) }
        svc.global(AccessibilityService.GLOBAL_ACTION_HOME)
        return if (!ok) "Не удалось нажать на «$target»" else "«$target» " + when (after) { true -> "включён"; false -> "выключен"; null -> "переключён" }
    }

    private fun stopwatch(ctx: Context, op: String): String {
        val p = ctx.getSharedPreferences("oa", Context.MODE_PRIVATE)
        val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val started = p.getLong("sw", 0L)
        fun fmt(ms: Long) = "%d:%02d.%d".format(ms / 60000, ms / 1000 % 60, ms / 100 % 10)
        return when (op) {
            "stop" -> if (started == 0L) "Секундомер не запущен" else { p.edit().remove("sw").apply(); nm.cancel(77); "Секундомер остановлен: ${fmt(System.currentTimeMillis() - started)}" }
            "status" -> if (started == 0L) "Секундомер не запущен" else "Идёт: ${fmt(System.currentTimeMillis() - started)}"
            else -> {
                Notifier.ensureChannels(ctx)
                val t = System.currentTimeMillis(); p.edit().putLong("sw", t).apply()
                val open = android.app.PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java), android.app.PendingIntent.FLAG_IMMUTABLE)
                val n = NotificationCompat.Builder(ctx, Notifier.RUN).setSmallIcon(R.drawable.ic_stat).setContentTitle("Секундомер").setUsesChronometer(true).setWhen(t).setOngoing(true).setContentIntent(open).build()
                nm.notify(77, n); "Секундомер запущен (виден в шторке уведомлений)"
            }
        }
    }
}
