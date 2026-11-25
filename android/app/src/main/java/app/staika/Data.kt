package app.staika

import androidx.annotation.DrawableRes
import androidx.compose.runtime.mutableStateListOf

enum class Status(val label: String) { Idle("Свободен"), Working("Работает"), Waiting("Ждёт вас") }

/** Персонажи пользователя (вырезаны из присланного набора). */
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
    Lilac(R.drawable.ch_lilac, "Облако"),
}

data class Agent(
    val id: String,
    val name: String,
    val role: String,
    val pal: Pal,
    val status: Status,
    val last: String,
    val time: String,
    val chief: Boolean = false,
    val pinned: Boolean = false,
    val parentId: String? = null,
    val model: String = "Claude Sonnet 5.5",
)

sealed interface Msg {
    data class Text(val text: String, val mine: Boolean) : Msg
    data class Doc(val title: String, val host: String) : Msg
    data class Approval(
        val id: Int, val title: String, val detail: String, val risk: String,
        val decision: Decision = Decision.Pending,
    ) : Msg
    data class Task(val title: String, val progress: Float, val status: String) : Msg
    data class Day(val label: String) : Msg
    data object Typing : Msg
}

enum class Decision { Pending, Allowed, Denied }

data class Plugin(val name: String, val desc: String, val glyph: String, val color: Long, val added: Boolean, val group: String)

data class TaskItem(val title: String, val agentId: String, val status: String, val progress: Float, val due: String)

object Store {
    val agents = mutableStateListOf(
        Agent("chief", "Главный", "Руководитель команды, распределяет задачи", Pal.Black, Status.Idle,
            "Утро: 41 письмо, 6 требуют вас.", "8:00", chief = true, pinned = true, model = "Claude Sonnet 5.5"),
        Agent("ea", "Секретарь", "Календарь, встречи, напоминания", Pal.Blue, Status.Working,
            "Перенёс созвон на четверг.", "8:41", pinned = true, parentId = "chief", model = "Claude Haiku 4.5"),
        Agent("mail", "Почтальон", "Разбирает входящие, готовит ответы", Pal.Green, Status.Waiting,
            "3 черновика ждут вашего одобрения.", "8:22", pinned = true, parentId = "chief", model = "DeepSeek V4.1 Flash"),
        Agent("dev", "Разработчик", "Деплой и правки кода на сервере", Pal.Orange, Status.Working,
            "Собираю релиз 0.4.2…", "8:05", parentId = "chief", model = "Claude Sonnet 5.5"),
        Agent("ops", "Сервер", "Мониторинг, логи, резервные копии", Pal.Cyan, Status.Idle,
            "Бэкап завершён, 2.1 ГБ.", "Вчера", parentId = "chief", model = "GLM-5.3 Flash"),
        Agent("res", "Исследователь", "Поиск и сводки по темам", Pal.Lilac, Status.Idle,
            "Собрал 6 источников по рынку.", "Вчера", model = "Kimi K3"),
        Agent("smm", "Автор", "Тексты и посты для соцсетей", Pal.Pink, Status.Idle,
            "Три варианта заголовка готовы.", "Вт", model = "GPT-5.5"),
        Agent("sup", "Поддержка", "Отвечает клиентам по почте", Pal.Cloud, Status.Idle,
            "12 обращений решено, 2 у вас.", "Вт", parentId = "mail", model = "Claude Haiku 4.5"),
        Agent("fin", "Аналитик", "Расходы, счета, отчёты", Pal.Yellow, Status.Idle,
            "Счета разнесены, один спорный.", "Пн", model = "Gemini 3.5 Flash"),
        Agent("voice", "Голос", "Принимает звонки и отвечает голосом", Pal.Purple, Status.Idle,
            "Звонок 4:12, итог в чате.", "Пн", model = "Claude Haiku 4.5"),
    )

    val plugins = listOf(
        Plugin("Gmail", "Искать, читать, писать и разбирать почту", "M", 0xFFEA4335, true, "Избранное"),
        Plugin("Google Календарь", "События и назначение встреч", "31", 0xFF4285F4, true, "Избранное"),
        Plugin("Google Диск", "Искать, читать, создавать и делиться файлами", "▲", 0xFF34A853, true, "Избранное"),
        Plugin("Telegram", "Писать агенту и получать итоги в Telegram", "✈", 0xFF229ED9, false, "Избранное"),
        Plugin("Почта агента", "Свой адрес на вашем домене", "@", 0xFF7B5CF0, true, "Свои"),
        Plugin("Браузер", "Chromium с живым просмотром и перехватом", "◎", 0xFF0B0B10, true, "Свои"),
        Plugin("Сервер", "Файлы, команды и деплой в песочнице", "›_", 0xFF22B573, true, "Свои"),
        Plugin("Notion", "Заметки, базы и страницы", "N", 0xFF0B0B10, false, "Работа"),
        Plugin("GitHub", "Репозитории, issues и pull request", "GH", 0xFF24292F, false, "Работа"),
        Plugin("Slack", "Каналы и личные сообщения", "#", 0xFF611F69, false, "Работа"),
        Plugin("Linear", "Задачи и проекты", "L", 0xFF5E6AD2, false, "Работа"),
        Plugin("Stripe", "Платежи и счета", "S", 0xFF635BFF, false, "Финансы"),
        Plugin("Google Таблицы", "Читать и заполнять таблицы", "▦", 0xFF0F9D58, false, "Финансы"),
        Plugin("Яндекс Диск", "Файлы в облаке Яндекса", "Я", 0xFFFC3F1D, false, "Файлы"),
    )

    val tasks = listOf(
        TaskItem("Подготовить отчёт для совета", "chief", "В работе", 0.7f, "Сегодня 14:00"),
        TaskItem("Разобрать письма за ночь", "mail", "Ждёт вас", 0.9f, "Сегодня"),
        TaskItem("Выкатить релиз 0.4.2", "dev", "В работе", 0.45f, "Сегодня 18:00"),
        TaskItem("Согласовать встречу с командой", "ea", "В работе", 0.6f, "Завтра"),
        TaskItem("Ежедневный бэкап", "ops", "Готово", 1f, "Каждый день 03:00"),
        TaskItem("Сводка по конкурентам", "res", "Готово", 1f, "Вчера"),
    )

    fun agent(id: String?) = agents.firstOrNull { it.id == id } ?: agents.first()
}
