package openagent.app.com

import kotlinx.serialization.json.*

/** Порт server/src/slotCheck.js + validateAction: числа и привязка действий малой модели к фразе проверяются обычным алгоритмом. */
object SlotCheck {
    private val W = mapOf("ноль" to 0, "один" to 1, "одна" to 1, "одну" to 1, "одно" to 1, "два" to 2, "две" to 2, "три" to 3, "четыре" to 4, "пять" to 5, "шесть" to 6, "семь" to 7, "восемь" to 8, "девять" to 9, "десять" to 10, "одиннадцать" to 11, "двенадцать" to 12, "тринадцать" to 13, "четырнадцать" to 14, "пятнадцать" to 15, "шестнадцать" to 16, "семнадцать" to 17, "восемнадцать" to 18, "девятнадцать" to 19, "двадцать" to 20, "тридцать" to 30, "сорок" to 40, "пятьдесят" to 50, "шестьдесят" to 60, "семьдесят" to 70, "восемьдесят" to 80, "девяносто" to 90, "сто" to 100)
    private val ORD = mapOf("первого" to 1, "второго" to 2, "третьего" to 3, "четвертого" to 4, "пятого" to 5, "шестого" to 6, "седьмого" to 7, "восьмого" to 8, "девятого" to 9, "десятого" to 10, "одиннадцатого" to 11, "двенадцатого" to 12)
    private fun norm(t: String) = t.lowercase().replace('ё', 'е').replace(Regex("[,!?;]+"), " ").replace(Regex("\\s+"), " ").trim()

    private class Num(val v: Int, val i: Int, val j: Int)
    private fun numbers(toks: List<String>): List<Num> {
        val out = ArrayList<Num>(); var i = 0
        while (i < toks.size) {
            val t = toks[i]
            if (t.matches(Regex("\\d+"))) { out.add(Num(t.toInt(), i, i + 1)); i++; continue }
            if (t in W) {
                var v = W[t]!!; var j = i + 1
                if (v in 20..99 && v % 10 == 0 && j < toks.size && (W[toks[j]] ?: 0) in 1..9) { v += W[toks[j]]!!; j++ }
                out.add(Num(v, i, j)); i = j; continue
            }
            i++
        }
        return out
    }
    private fun unit(t: String) = when {
        Regex("^час(а|ов|у)?$").matches(t) -> 3600
        Regex("^минут.*").matches(t) || t == "мин" || t == "м" -> 60
        Regex("^секунд.*").matches(t) || t == "сек" -> 1
        else -> 0
    }

    fun parseDuration(text: String): Int? {
        val s = norm(text)
        val special = listOf("(?:^| )(полчаса|пол часа|половину часа)(?= |$)" to 1800, "(?:^| )полтора часа(?= |$)" to 5400, "(?:^| )(полторы минуты)(?= |$)" to 90, "(?:^| )(полминуты|пол минуты)(?= |$)" to 30,
            "(?:^| )три четверти часа(?= |$)" to 2700, "(?:^| )четверть часа(?= |$)" to 900, "(?:^| )два с половиной часа(?= |$)" to 9000)
        for ((re, v) in special) if (Regex(re).containsMatchIn(s)) return v
        Regex("(\\d+)\\.5 час").find(s)?.let { return it.groupValues[1].toInt() * 3600 + 1800 }
        Regex("(\\d+)\\.5 мин").find(s)?.let { return it.groupValues[1].toInt() * 60 + 30 }
        val toks = s.split(' '); val nums = numbers(toks)
        var total = 0; var found = false; val used = HashSet<Int>()
        for (k in toks.indices) {
            val u = unit(toks[k]); if (u == 0) continue
            val prev = nums.firstOrNull { it.j == k && it.i !in used }
            if (prev != null) { total += prev.v * u; used.add(prev.i) } else if (toks[k] == "час" || toks[k] == "минуту" || toks[k] == "секунду") total += u else continue
            found = true
        }
        if (!found) Regex("(?:^|\\D)(\\d+) ?м(?: |$)").find(s)?.let { return it.groupValues[1].toInt() * 60 }
        return if (found && total > 0) total else null
    }

    private val PERIOD = mapOf("утра" to "am", "дня" to "day", "вечера" to "pm", "ночи" to "night")
    private fun applyPeriod(h: Int, p: String?): Int = when (p) { null -> h; "am" -> if (h == 12) 0 else h; "day" -> if (h == 12) 12 else if (h < 12) h + 12 else h; "pm" -> if (h < 12) h + 12 else h; else -> if (h == 12) 0 else if (h in 6..11) h + 12 else h }
    private fun hh(o: Int) = if (o - 1 == 0) 12 else o - 1
    data class Clock(val hour: Int, val minute: Int)
    fun parseClock(text: String): Clock? {
        val s = norm(text)
        if (Regex("(?:^| )полночь(?= |$)").containsMatchIn(s)) return Clock(0, 0)
        if (Regex("(?:^| )полдень(?= |$)").containsMatchIn(s)) return Clock(12, 0)
        val toks = s.split(' ')
        val per = toks.firstNotNullOfOrNull { PERIOD[it] }
        Regex("(?:^|\\D)(\\d{1,2})[:.](\\d{2})(?!\\d)").find(s)?.let { m -> val h = m.groupValues[1].toInt(); val mi = m.groupValues[2].toInt(); if (h <= 23 && mi <= 59) return Clock(if (h > 12) h else applyPeriod(h, per), mi) }
        fun ordAfter(k: Int): Int? { for (i in k until minOf(toks.size, k + 2)) ORD[toks[i]]?.let { return it }; return null }
        val nums = numbers(toks)
        fun at(k: Int) = nums.firstOrNull { it.i == k }
        for (k in toks.indices) {
            if (Regex("^(половину|половине|пол)$").matches(toks[k])) ordAfter(k + 1)?.let { return Clock(applyPeriod(hh(it), per) % 24, 30) }
            if (toks[k] == "четверть" && toks.getOrNull(k - 1) != "без") ordAfter(k + 1)?.let { return Clock(applyPeriod(hh(it), per) % 24, 15) }
            if (toks[k] == "без") {
                val mm = mapOf("четверти" to 45, "пятнадцати" to 45, "десяти" to 50, "пяти" to 55, "двадцати" to 40)[toks.getOrNull(k + 1)]
                val n = at(k + 2) ?: at(k + 3)
                if (mm != null && n != null) return Clock(applyPeriod(hh(n.v), per) % 24, mm)
            }
        }
        for (n in nums) { val nx = toks.getOrNull(n.j); if (nx != null && nx.startsWith("мин") && ordAfter(n.j + 1) != null) return Clock(applyPeriod(hh(ordAfter(n.j + 1)!!), per) % 24, n.v) }
        val hrs = nums.filter { n -> !(toks.getOrNull(n.j)?.let { Regex("^(мин|сек)").containsMatchIn(it) } ?: false) }
        if (hrs.size >= 2 && hrs[1].i == hrs[0].j) { val h = hrs[0].v; val mi = hrs[1].v; if (mi <= 59 && h <= 23) return Clock(if (h > 12) h else applyPeriod(h, per), mi) }
        if (hrs.size >= 3 && hrs[0].v == 0) return null
        if (hrs.size >= 3 && hrs[1].i == hrs[0].j && hrs[2].i == hrs[1].j && hrs[1].v == 0 && hrs[2].v < 10) return Clock(applyPeriod(hrs[0].v, per), hrs[2].v)
        if (hrs.isNotEmpty()) { val h = hrs[0].v; if (h in 0..23 && (per != null || h in 4..12 || h > 12)) return Clock(if (h > 12) h else applyPeriod(h, per), 0) }
        return null
    }

    fun parseLevel(text: String): Int? {
        val s = norm(text)
        Regex("(\\d{1,3})(?:%| процент|(?= |$))").find(s)?.let { return it.groupValues[1].toInt() }
        for ((re, v) in listOf("(?:^| )(максимум|максимальную|полную|сто процентов|на сто)(?= |$)" to 100, "(?:^| )(минимум|ноль|ноль процентов)(?= |$)" to 0, "(?:^| )(половину|середину)(?= |$)" to 50, "(?:^| )четверть(?= |$)" to 25)) if (Regex(re).containsMatchIn(s)) return v
        return numbers(s.split(' ')).lastOrNull()?.v
    }

    private fun str(a: JsonObject, k: String) = a[k]?.jsonPrimitive?.contentOrNull
    private fun int(a: JsonObject, k: String) = a[k]?.jsonPrimitive?.intOrNull

    fun slotsOk(actions: List<JsonObject>, text: String): Boolean {
        val numeric = actions.filter { str(it, "action") in setOf("alarm", "timer", "remind", "volume", "brightness") }
        if (numeric.isEmpty()) return true
        if (actions.size > 1) return false
        val a = numeric[0]
        return when (str(a, "action")) {
            "timer" -> parseDuration(text) == int(a, "seconds")
            "remind" -> { val d = parseDuration(text.replace(Regex("^.*?через "), "")); d != null && d / 60 == int(a, "minutes") && d % 60 == 0 }
            "alarm" -> { if (norm(text).contains("через")) false else { val c = parseClock(text); c != null && c.hour == int(a, "hour") && c.minute == (int(a, "minute") ?: 0) } }
            else -> { val lv = parseLevel(text); lv != null && lv == int(a, "level") }
        }
    }

    private val OFF_RE = Regex("выключ|отключ|выруб|погас|деактив|отруб|закрой|убери")
    private val ON_RE = Regex("включ|вруб|актив|запуст|зажг|засвет|посвет|раздай|открой|подключ")
    private fun stem(w: String) = w.take(maxOf(3, minOf(5, w.length - 2)))
    private fun hasWord(text: String, word: String): Boolean { val t = norm(text); val tt = t.split(' '); return word.lowercase().split(Regex("\\s+")).filter { it.isNotEmpty() }.all { w -> if (w.matches(Regex("\\d+"))) t.contains(w) else tt.any { it.startsWith(stem(w)) } } }
    private val KNOWN_APPS = setOf("2гис", "alice", "avito", "calculator", "calendar", "camera", "chrome", "clock", "contacts", "discord", "duolingo", "facebook", "files", "gallery", "gmail", "google", "instagram", "mail", "maps", "music", "netflix", "notes", "ozon", "phone", "pinterest", "play market", "settings", "skype", "sms", "spotify", "telegram", "tiktok", "twitch", "twitter", "viber", "vk", "whatsapp", "wildberries", "youtube", "zoom", "госуслуги", "дзен", "кинопоиск", "магнит", "пятёрочка", "сбербанк", "тинькофф", "шазам", "яндекс карты", "яндекс музыка", "яндекс такси")
    private val TARGET_RE = mapOf("wifi" to "вай|wi-?fi", "bluetooth" to "блют|bluetooth", "airplane" to "авиа|полет|самолет", "dnd" to "беспокоить|dnd", "autorotate" to "поворот", "nfc" to "nfc|нфс|нфц", "hotspot" to "точк|раздач|раздай|модем|хотспот|hotspot", "location" to "геолокац|gps|местоположен|геопозиц", "battery_saver" to "экономи|энергосбереж").mapValues { Regex(it.value) }
    private val MUSIC_FILLER = setOf("включи", "поставь", "песню", "песня", "трек", "музыку", "хочу", "послушать", "сыграй", "запусти", "давай", "послушаем", "найди", "и", "в", "через", "мне", "пожалуйста", "плиз", "быстро", "сейчас", "слушай", "ну", "эй", "алиса", "окей", "спасибо", "ладно", "будь", "добр", "спотифай", "spotify", "спотифае", "яндекс", "музыке", "ютуб", "youtube", "music", "можешь", "а", "ка", "так", "короче", "срочно", "прямо")

    fun groundedOk(actions: List<JsonObject>, text: String): Boolean {
        val t = norm(text)
        if (actions.size > 1 && !Regex("( и |,|потом|затем|еще|заодно)").containsMatchIn(text.lowercase().replace('ё', 'е'))) return false
        for (a in actions) {
            val act = str(a, "action")
            if (act == "call" && !hasWord(t, str(a, "to").orEmpty())) return false
            if (act == "message" && (!hasWord(t, str(a, "to").orEmpty()) || !hasWord(t, str(a, "text").orEmpty().split(' ')[0]))) return false
            if (act == "music_play") {
                val qs = str(a, "query").orEmpty(); if (!hasWord(t, qs)) return false
                val q = norm(qs).split(' ').map { stem(it) }.toSet()
                for (w in t.split(' ')) if (w !in MUSIC_FILLER && stem(w) !in q) return false
            }
            if (act == "toggle") TARGET_RE[str(a, "target")]?.let { if (!it.containsMatchIn(t)) return false }
            if ((act == "open_app" || act == "close_app") && str(a, "app").orEmpty().lowercase() !in KNOWN_APPS) return false
            if (act == "volume" && !Regex("громк|звук|тише|громче").containsMatchIn(t)) return false
            if (act == "brightness" && !Regex("яркост|ярче|темнее").containsMatchIn(t)) return false
            if ((act == "toggle" || act == "flashlight") && "on" in a) {
                val off = OFF_RE.containsMatchIn(t); val on = ON_RE.containsMatchIn(t) || Regex("(^| )(вкл)( |$)").containsMatchIn(t)
                val v = a["on"]?.jsonPrimitive?.booleanOrNull
                if (off && !on && v != false) return false
                if (on && !off && v != true) return false
            }
        }
        return true
    }

    // ---- схема действий (зеркало phone-model/sim.py) ----
    private val SCHEMA = mapOf("open_app" to mapOf("app" to "s!"), "close_app" to mapOf("app" to "s!"), "alarm" to mapOf("hour" to "i!", "minute" to "i", "label" to "s"), "timer" to mapOf("seconds" to "i!", "label" to "s"), "stopwatch" to mapOf("op" to "s"), "flashlight" to mapOf("on" to "b"),
        "toggle" to mapOf("target" to "s!", "on" to "b"), "volume" to mapOf("level" to "i!", "target" to "s"), "brightness" to mapOf("level" to "i!"), "system" to mapOf("op" to "s!"), "media" to mapOf("op" to "s!"), "music_play" to mapOf("query" to "s!", "app" to "s"),
        "call" to mapOf("to" to "s!"), "message" to mapOf("app" to "s!", "to" to "s!", "text" to "s!"), "remind" to mapOf("text" to "s!", "minutes" to "i!"))
    private val ENUM = mapOf("toggle.target" to listOf("wifi", "bluetooth", "airplane", "dnd", "autorotate", "nfc", "hotspot", "location", "battery_saver"), "system.op" to listOf("home", "back", "recents", "notifications", "quick_settings", "lock"),
        "media.op" to listOf("play", "pause", "toggle", "next", "prev", "stop", "forward", "rewind", "volume_up", "volume_down"), "stopwatch.op" to listOf("start", "stop", "status"), "volume.target" to listOf("media", "ring", "alarm"), "message.app" to listOf("whatsapp", "telegram"))
    /** null — действие корректно, иначе причина. */
    fun validate(a: JsonObject): String? {
        val act = str(a, "action"); val spec = SCHEMA[act] ?: return "неизвестное действие"
        for ((k, v) in a) {
            if (k == "action") continue
            val t = spec[k] ?: return "лишнее поле $k"; val p = v as? JsonPrimitive ?: return "$k: не примитив"
            when (t[0]) { 'i' -> if (p.isString || p.intOrNull == null) return "$k: нужен int"; 'b' -> if (p.isString || p.booleanOrNull == null) return "$k: нужен bool"; 's' -> if (!p.isString || p.content.isBlank()) return "$k: нужна строка" }
            ENUM["$act.$k"]?.let { if (p.content !in it) return "$k: недопустимое значение" }
        }
        for ((k, t) in spec) if (t.endsWith("!") && k !in a) return "нет поля $k"
        if (act == "alarm" && !(int(a, "hour")!! in 0..23 && (int(a, "minute") ?: 0) in 0..59)) return "время вне диапазона"
        if (act == "timer" && int(a, "seconds")!! !in 1..86400) return "длительность вне диапазона"
        if ((act == "volume" || act == "brightness") && int(a, "level")!! !in 0..100) return "уровень вне 0..100"
        if (act == "remind" && int(a, "minutes")!! !in 1..43200) return "minutes вне диапазона"
        return null
    }
}
