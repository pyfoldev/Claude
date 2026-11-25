package app.staika

import androidx.annotation.DrawableRes
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

enum class Status(val label: String) { Idle("Свободен"), Working("Работает"), Waiting("Ждёт вас") }

fun statusOf(s: String?) = when (s) { "Working" -> Status.Working; "Waiting" -> Status.Waiting; else -> Status.Idle }

/** Персонажи. Имя элемента хранится на сервере как внешность агента. */
enum class Pal(@DrawableRes val img: Int, val title: String) {
    Cloud(R.drawable.ch_cloud, "Облачко"),
    Black(R.drawable.ch_black, "Уголёк"),
    Blue(R.drawable.ch_blue, "Капля"),
    Green(R.drawable.ch_green, "Мятка"),
    Yellow(R.drawable.ch_yellow, "Цветок"),
    Pink(R.drawable.ch_pink, "Пион"),
    Purple(R.drawable.ch_purple, "Шарик"),
    Orange(R.drawable.ch_orange, "Огонёк"),
    Cyan(R.drawable.ch_cyan, "Ромб"),
    Lilac(R.drawable.ch_lilac, "Облако");

    companion object { fun of(s: String?) = entries.firstOrNull { it.name == s } ?: Cloud }
}

data class Perms(val server: Boolean = false, val browser: Boolean = false, val mail: Boolean = false)

data class Agent(
    val id: String, val name: String, val role: String, val pal: Pal, val status: Status,
    val last: String, val lastAt: Long, val chief: Boolean = false, val parentId: String? = null,
    val model: String = "", val perms: Perms = Perms(),
) { val time: String get() = timeLabel(lastAt) }

enum class Decision { Pending, Allowed, Denied }

sealed interface Msg {
    val id: String
    val at: Long
    data class Text(override val id: String, override val at: Long, val text: String, val mine: Boolean) : Msg
    data class System(override val id: String, override val at: Long, val text: String) : Msg
    data class Doc(override val id: String, override val at: Long, val title: String, val host: String) : Msg
    data class Approval(
        override val id: String, override val at: Long, val approvalId: String, val title: String, val detail: String,
        val risk: String, val decision: Decision,
    ) : Msg
    data class Task(override val id: String, override val at: Long, val title: String, val progress: Float, val status: String) : Msg
    data class Day(override val id: String, override val at: Long, val label: String) : Msg
    data object Typing : Msg { override val id = "typing"; override val at = Long.MAX_VALUE }
}

data class TaskItem(val id: String, val title: String, val agentId: String, val status: String, val progress: Float, val at: Long)
data class AuditItem(val agentId: String?, val action: String, val details: String, val at: Long)
data class UsageItem(val agentId: String, val tokensIn: Long, val tokensOut: Long, val cost: Double)
data class ModelOpt(val id: String, val label: String, val provider: String)
data class Me(val id: String, val email: String, val name: String, val role: String, val verified: Boolean) {
    val roleLabel get() = when (role) { "owner" -> "Владелец"; "family" -> "Семья"; else -> "Участник" }
}
data class UserRow(val id: String, val email: String, val name: String, val role: String)

fun timeLabel(ms: Long): String {
    if (ms <= 0) return ""
    val now = Calendar.getInstance(); val t = Calendar.getInstance().apply { timeInMillis = ms }
    val days = ((startOfDay(now) - startOfDay(t)) / 86_400_000L).toInt()
    return when {
        days <= 0 -> SimpleDateFormat("HH:mm", Locale("ru")).format(Date(ms))
        days == 1 -> "Вчера"
        days < 7 -> SimpleDateFormat("EE", Locale("ru")).format(Date(ms)).replaceFirstChar { it.uppercase() }
        else -> SimpleDateFormat("d.MM", Locale("ru")).format(Date(ms))
    }
}

fun dayLabel(ms: Long): String {
    val now = Calendar.getInstance(); val t = Calendar.getInstance().apply { timeInMillis = ms }
    val days = ((startOfDay(now) - startOfDay(t)) / 86_400_000L).toInt()
    return when (days) {
        0 -> "Сегодня"; 1 -> "Вчера"
        else -> SimpleDateFormat("d MMMM", Locale("ru")).format(Date(ms))
    }
}

private fun startOfDay(c: Calendar): Long = Calendar.getInstance().apply {
    timeInMillis = c.timeInMillis; set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
}.timeInMillis

/** Что умеют агенты сейчас (встроенные инструменты) и что появится позже. */
data class ToolInfo(val name: String, val desc: String, val glyph: String, val color: Long, val ready: Boolean, val group: String)

val toolCatalog = listOf(
    ToolInfo("Файлы", "Читать и писать файлы в своей папке на сервере", "▤", 0xFF22B573, true, "Встроено"),
    ToolInfo("Память", "Запоминать факты и вспоминать их позже", "◐", 0xFF7B5CF0, true, "Встроено"),
    ToolInfo("Веб", "Открывать страницы и API (только чтение)", "◎", 0xFF0B0B10, true, "Встроено"),
    ToolInfo("Команда", "Поручать задачи другим агентам и получать отчёты", "⇄", 0xFF2F7BFF, true, "Встроено"),
    ToolInfo("Расписание", "Запускать агента по расписанию, без телефона", "◷", 0xFFFF9500, true, "Встроено"),
    ToolInfo("Gmail", "Искать, читать, писать и разбирать почту", "M", 0xFFEA4335, false, "Скоро"),
    ToolInfo("Google Календарь", "События и назначение встреч", "31", 0xFF4285F4, false, "Скоро"),
    ToolInfo("Google Диск", "Искать, читать, создавать и делиться файлами", "▲", 0xFF34A853, false, "Скоро"),
    ToolInfo("Telegram", "Писать агенту и получать итоги в Telegram", "✈", 0xFF229ED9, false, "Скоро"),
    ToolInfo("Почта агента", "Свой адрес на вашем домене", "@", 0xFF7B5CF0, false, "Скоро"),
    ToolInfo("Браузер", "Chromium с живым просмотром и перехватом", "◎", 0xFF0B0B10, false, "Скоро"),
)
