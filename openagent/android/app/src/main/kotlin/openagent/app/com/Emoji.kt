package openagent.app.com

import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily

/** Монохромный шрифт эмодзи (Noto Emoji): смайлы рисуются линиями и цветом текста — чёрно-белые, как и всё приложение. */
val EmojiFont = FontFamily(Font(R.font.noto_emoji))

private fun isEmojiCp(cp: Int) = cp in 0x1F000..0x1FAFF || cp in 0x2600..0x27BF || cp in 0x2B00..0x2BFF || cp in 0x2300..0x23FF ||
    cp == 0x200D || cp == 0xFE0F || cp == 0x20E3 || cp == 0x203C || cp == 0x2049 || cp == 0x2122 || cp == 0x2139 || cp == 0x24C2 ||
    cp == 0x00A9 || cp == 0x00AE || cp == 0x3030 || cp == 0x303D || cp == 0x3297 || cp == 0x3299 || cp in 0x25AA..0x25FE || cp in 0x2190..0x21AA

fun AnnotatedString.monoEmoji(): AnnotatedString {
    val s = text
    var any = false
    var k = 0
    while (k < s.length) { val cp = s.codePointAt(k); if (cp > 0x2000 && isEmojiCp(cp)) { any = true; break }; k += Character.charCount(cp) }
    if (!any) return this
    return buildAnnotatedString {
        append(this@monoEmoji)
        var i = 0
        while (i < s.length) {
            val cp = s.codePointAt(i); val n = Character.charCount(cp)
            if (cp > 0x2000 && isEmojiCp(cp)) {
                var j = i + n
                while (j < s.length) { val c2 = s.codePointAt(j); if (isEmojiCp(c2) && c2 > 0x2000) j += Character.charCount(c2) else break }
                addStyle(SpanStyle(fontFamily = EmojiFont), i, j); i = j
            } else i += n
        }
    }
}
/** U+FE0F (цветное представление) → U+FE0E (текстовое): эмодзи рисуются монохромно. */
fun String.monoEmoji(): AnnotatedString = AnnotatedString(replace('\uFE0F', '\uFE0E')).monoEmoji()
