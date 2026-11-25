package app.staika

/** Данные только для скриншот-тестов: в приложении демо-данных нет. */
object DemoData {
    fun fill() {
        val now = System.currentTimeMillis()
        Repo.me = Me("u1", "you@example.com", "Алексей", "owner", true)
        Repo.loggedIn = true; Repo.loaded = true; Repo.connected = true
        Repo.models = listOf(ModelOpt("Claude Haiku 4.5", "Claude Haiku 4.5", "anthropic"), ModelOpt("Claude Sonnet 5.5", "Claude Sonnet 5.5", "anthropic"), ModelOpt("Kimi K3", "Kimi K3 (River)", "river"))
        Repo.agents.clear()
        Repo.agents.addAll(listOf(
            Agent("chief", "Главный", "Руководитель команды", Pal.Black, Status.Idle, "Утро: 41 письмо, 6 требуют вас.", now - 3_600_000, chief = true, model = "Claude Sonnet 5.5"),
            Agent("ea", "Секретарь", "Календарь и встречи", Pal.Blue, Status.Working, "Перенёс созвон на четверг.", now - 600_000, parentId = "chief", model = "Claude Haiku 4.5"),
            Agent("mail", "Почтальон", "Разбирает входящие", Pal.Green, Status.Waiting, "3 черновика ждут одобрения.", now - 1_800_000, parentId = "chief", model = "Kimi K3"),
            Agent("dev", "Разработчик", "Деплой и правки кода", Pal.Orange, Status.Working, "Собираю релиз 0.4.2…", now - 7_200_000, parentId = "chief", model = "Claude Sonnet 5.5"),
            Agent("res", "Исследователь", "Поиск и сводки", Pal.Lilac, Status.Idle, "Собрал 6 источников по рынку.", now - 100_000_000, model = "Kimi K3"),
            Agent("smm", "Автор", "Тексты для соцсетей", Pal.Pink, Status.Idle, "Три варианта заголовка готовы.", now - 200_000_000, model = "Claude Haiku 4.5"),
        ))
        Repo.messages.clear()
        Repo.messages["chief"] = androidx.compose.runtime.mutableStateListOf(
            Msg.Text("m1", now - 7_000_000, "Привет! Что требует моего внимания сегодня?", true),
            Msg.Text("m2", now - 6_900_000, "За ночь: 41 письмо, 6 требовали вас, остальные разобраны.", false),
            Msg.Approval("m3", now - 6_800_000, "a1", "Совет директоров в 14:00", "Календарь: создать событие «Разбор презентации», 14:00–15:00", "Внешнее действие", Decision.Pending),
            Msg.Task("m4", now - 6_700_000, "Подготовить отчёт для совета", 0.7f, "В работе"),
            Msg.System("m5", now - 6_600_000, "Достигнут лимит шагов за один запуск."),
        )
        Repo.messages["dev"] = androidx.compose.runtime.mutableStateListOf(
            Msg.Text("d1", now - 7_000_000, "Собираю релиз 0.4.2. Тесты прошли, осталась выкатка.", false),
            Msg.Approval("d2", now - 6_900_000, "a2", "Системное действие", "docker compose up -d api", "Системное действие", Decision.Pending),
        )
        Repo.tasks.clear()
        Repo.tasks.addAll(listOf(
            TaskItem("t1", "Подготовить отчёт для совета", "chief", "В работе", 0.7f, now),
            TaskItem("t2", "Согласовать встречу", "ea", "Готово", 1f, now - 90_000_000),
        ))
    }
}
