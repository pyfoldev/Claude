package ai.chip.app

import androidx.annotation.RawRes

/** One pre-rendered video circle. Chip never generates video: the AI only picks one of these. */
data class Emotion(
    val id: String,
    val ru: String,
    @RawRes val clip: Int,
    val emojis: String,
    val keywords: List<String>,
)

object Emotions {
    val all = listOf(
        Emotion("joy", "радость", R.raw.clip_joy, "🎉✨", listOf("ура", "круто получилось", "сдал", "выиграл", "рад", "счастлив", "отлично", "класс", "супер", "победил", "получилось", "happy", "yay", "great", "won")),
        Emotion("love", "любовь", R.raw.clip_love, "😍💕", listOf("люблю", "влюб", "обожаю", "любимый", "любимая", "скучаю", "сердечко", "love", "miss you", "crush")),
        Emotion("laugh", "смех", R.raw.clip_laugh, "😂🤣", listOf("ахах", "хаха", "лол", "смешно", "ржу", "анекдот", "шутк", "lol", "haha", "funny")),
        Emotion("sad", "грусть", R.raw.clip_sad, "😢💧", listOf("грустно", "плохо", "плач", "одинок", "тоскливо", "умер", "расстал", "обидно", "тяжело", "sad", "cry", "lonely", "depress")),
        Emotion("angry", "злость", R.raw.clip_angry, "😤💢", listOf("бесит", "злой", "злюсь", "ненавижу", "достал", "раздража", "ярость", "angry", "hate", "mad", "annoy")),
        Emotion("surprised", "удивление", R.raw.clip_surprised, "😲❗", listOf("ничего себе", "серьёзно", "серьезно", "не может быть", "вау", "офигеть", "неожиданно", "wow", "omg", "really")),
        Emotion("scared", "страх", R.raw.clip_scared, "😨💦", listOf("страшно", "боюсь", "испуг", "жутко", "кошмар", "пугает", "scared", "afraid", "fear", "terrified")),
        Emotion("sleepy", "сон", R.raw.clip_sleepy, "😴💤", listOf("спать", "сонн", "устал", "спокойной ночи", "зеваю", "засыпаю", "sleep", "tired", "good night")),
        Emotion("think", "размышление", R.raw.clip_think, "🤔❓", listOf("как думаешь", "почему", "зачем", "интересно", "не знаю", "что делать", "помоги выбрать", "why", "how come", "i wonder", "?")),
        Emotion("blush", "смущение", R.raw.clip_blush, "😳🙈", listOf("смущ", "стесня", "неловко", "комплимент", "красив", "милый", "милая", "shy", "embarrass", "blush")),
        Emotion("cool", "круто", R.raw.clip_cool, "😎🔥", listOf("я крут", "как босс", "легко", "изи", "по-крутому", "стиль", "boss", "easy", "cool", "awesome")),
        Emotion("hello", "привет", R.raw.clip_hello, "👋☁️", listOf("привет", "здравств", "добрый день", "доброе утро", "добрый вечер", "хай", "пока", "hello", "hi ", "hey", "bye")),
    )

    private val byId = all.associateBy { it.id }
    fun byId(id: String?): Emotion = byId[id?.trim()?.lowercase()] ?: byId.getValue("hello")
    fun find(id: String?): Emotion? = byId[id?.trim()?.lowercase()]
    val idList: String get() = all.joinToString(", ") { it.id }

    /** Offline fallback: pick an emotion from keywords. */
    fun guess(text: String): Emotion {
        val t = " " + text.lowercase() + " "
        var best: Emotion? = null
        var bestScore = 0
        for (e in all) {
            val score = e.keywords.count { t.contains(it) }
            if (score > bestScore) { best = e; bestScore = score }
        }
        return best ?: byId.getValue(if (text.trim().endsWith("?")) "think" else "hello")
    }
}
