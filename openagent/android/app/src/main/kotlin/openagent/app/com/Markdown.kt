package openagent.app.com

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import kotlinx.coroutines.withContext
import kotlinx.coroutines.isActive
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.*
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

fun copyToClipboard(ctx: Context, text: String) {
    (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("text", text))
}

private val inlineRe = Regex("(\\*\\*(.+?)\\*\\*)|(`([^`]+)`)|(\\*(.+?)\\*)|(\\[([^\\]]+)\\]\\(([^)]+)\\))")

fun inline(src: String): AnnotatedString = inlineRaw(src.replace('\uFE0F', '\uFE0E')).monoEmoji()
private fun inlineRaw(src: String): AnnotatedString = buildAnnotatedString {
    var i = 0
    for (m in inlineRe.findAll(src)) {
        append(src.substring(i, m.range.first)); i = m.range.last + 1
        when {
            m.groups[2] != null -> withStyle(SpanStyle(fontWeight = FontWeight.SemiBold)) { append(m.groups[2]!!.value) }
            m.groups[4] != null -> withStyle(SpanStyle(fontFamily = FontFamily.Monospace, background = C.surface3, fontSize = 14.sp)) { append(" ${m.groups[4]!!.value} ") }
            m.groups[6] != null -> withStyle(SpanStyle(fontStyle = FontStyle.Italic)) { append(m.groups[6]!!.value) }
            m.groups[8] != null -> withStyle(SpanStyle(color = C.accent, textDecoration = TextDecoration.Underline)) { append(m.groups[8]!!.value) }
        }
    }
    append(src.substring(i))
}

/** Блоки markdown. data class → Compose пропускает перерисовку неизменившихся блоков (важно при стриминге). */
sealed interface MdBlock
data class MdPara(val text: String) : MdBlock
data class MdHeading(val level: Int, val text: String) : MdBlock
data class MdBullet(val text: String) : MdBlock
data class MdNumber(val n: String, val text: String) : MdBlock
data class MdQuote(val text: String) : MdBlock
data class MdCode(val lang: String, val body: String, val closed: Boolean) : MdBlock
data class MdTable(val head: List<String>, val rows: List<List<String>>) : MdBlock

private val tableSep = Regex("^\\s*\\|?\\s*:?-{2,}:?\\s*(\\|\\s*:?-{2,}:?\\s*)*\\|?\\s*$")
private val numRe = Regex("^\\s*(\\d+)[.)] (.*)")

fun parseMarkdown(text: String): List<MdBlock> {
    val out = ArrayList<MdBlock>()
    val lines = text.split("\n")
    var i = 0
    while (i < lines.size) {
        val l = lines[i]
        when {
            l.trimStart().startsWith("```") -> {
                val lang = l.trim().removePrefix("```").trim()
                val code = StringBuilder(); i++
                var closed = false
                while (i < lines.size) { if (lines[i].trimStart().startsWith("```")) { closed = true; break }; code.appendLine(lines[i]); i++ }
                out.add(MdCode(lang, code.toString().trimEnd(), closed))
            }
            l.trimStart().startsWith("|") && i + 1 < lines.size && tableSep.matches(lines[i + 1]) -> {
                fun cells(s: String) = s.trim().trim('|').split("|").map { it.trim() }
                val head = cells(l); val rows = ArrayList<List<String>>(); i += 2
                while (i < lines.size && lines[i].trimStart().startsWith("|")) { rows.add(cells(lines[i])); i++ }
                i--
                out.add(MdTable(head, rows))
            }
            l.startsWith("#") -> { val lvl = l.takeWhile { it == '#' }.length; out.add(MdHeading(lvl, l.drop(lvl).trim())) }
            l.trimStart().let { it.startsWith("- ") || it.startsWith("* ") || it.startsWith("• ") } -> out.add(MdBullet(l.trimStart().drop(2)))
            numRe.matches(l) -> { val m = numRe.matchEntire(l)!!; out.add(MdNumber(m.groupValues[1], m.groupValues[2])) }
            l.startsWith(">") -> out.add(MdQuote(l.drop(1).trim()))
            l.isBlank() -> {}
            else -> out.add(MdPara(l))
        }
        i++
    }
    return out
}

@Composable
fun Markdown(text: String, modifier: Modifier = Modifier) {
    val blocks = remember(text) { parseMarkdown(text) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        blocks.forEachIndexed { i, b -> key(i) { MdBlockView(b) } }
    }
}

@Composable
private fun InlineText(src: String, color: Color = C.text, fontSize: Int = 17, lineHeight: Int = 26, modifier: Modifier = Modifier, weight: FontWeight? = null) {
    val ann = remember(src) { inline(src) }
    Text(ann, color = color, fontSize = fontSize.sp, lineHeight = lineHeight.sp, fontWeight = weight, modifier = modifier)
}

@Composable
private fun MdBlockView(b: MdBlock) {
    val ctx = LocalContext.current
    when (b) {
        is MdPara -> InlineText(b.text)
        is MdHeading -> InlineText(b.text, fontSize = (22 - b.level * 2).coerceAtLeast(16), lineHeight = 28, weight = FontWeight.SemiBold, modifier = Modifier.padding(top = 4.dp))
        is MdBullet -> Row { Text("•", color = C.dim, modifier = Modifier.padding(end = 8.dp, start = 4.dp)); InlineText(b.text, lineHeight = 25) }
        is MdNumber -> Row { Text("${b.n}.", color = C.dim, modifier = Modifier.padding(end = 8.dp, start = 4.dp)); InlineText(b.text, lineHeight = 25) }
        is MdQuote -> Row(Modifier.height(IntrinsicSize.Min)) { Box(Modifier.width(3.dp).fillMaxHeight().background(C.outline)); Spacer(Modifier.width(10.dp)); InlineText(b.text, color = C.dim, lineHeight = 25) }
        is MdCode -> if (b.closed && b.body.contains("<svg") && b.body.contains("</svg>") && b.lang.lowercase() in setOf("svg", "xml", "html", "")) SvgBlock(b.body, ctx) else CodeBlock(b.lang, b.body, ctx)
        is MdTable -> {
            val widths = remember(b) { b.head.indices.map { c -> (maxOf(b.head[c].length, b.rows.maxOfOrNull { it.getOrElse(c) { "" }.length } ?: 0) * 8.5f + 32f).coerceIn(80f, 240f).dp } }
            val total = widths.fold(0.dp) { a, w -> a + w }
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).background(C.surface2).horizontalScroll(rememberScrollState())) {
                Row(Modifier.width(total).background(C.container.copy(alpha = 0.5f))) { b.head.forEachIndexed { c, t -> Text(inline(t), color = C.onContainer, fontWeight = FontWeight.Bold, fontSize = 14.sp, modifier = Modifier.width(widths[c]).padding(horizontal = 14.dp, vertical = 10.dp)) } }
                b.rows.forEachIndexed { r, row -> Row(Modifier.width(total).background(if (r % 2 == 1) C.surface3.copy(alpha = 0.5f) else Color.Transparent)) {
                    b.head.indices.forEach { c -> Text(inline(row.getOrElse(c) { "" }), color = C.text, fontSize = 14.sp, modifier = Modifier.width(widths[c]).padding(horizontal = 14.dp, vertical = 9.dp)) } } }
            }
        }
    }
}

@Composable
fun CodeBlock(lang: String, body: String, ctx: Context) {
    val vm = LocalVM.current
    val runnable = vm != null && vm.user?.role == "owner" && lang.lowercase() in setOf("python", "py", "python3", "js", "javascript", "node", "bash", "sh", "shell")
    var out by remember(body) { mutableStateOf<String?>(null) }
    var busy by remember(body) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().background(C.surface2, RoundedCornerShape(20.dp))) {
        Row(Modifier.fillMaxWidth().padding(start = 14.dp, end = 4.dp, top = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(lang.ifEmpty { "code" }, color = C.dim, fontSize = 12.sp, modifier = Modifier.weight(1f))
            if (runnable) Text(if (busy) "Выполняю…" else "▶ Запустить", color = C.accent, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.clickable(enabled = !busy) { busy = true; out = null; vm!!.runSnippet(lang, body) { out = it; busy = false } }.padding(horizontal = 10.dp, vertical = 8.dp))
            Text("Копировать", color = C.dim, fontSize = 12.sp, modifier = Modifier.clickable { copyToClipboard(ctx, body) }.padding(8.dp))
        }
        Text(body, style = Mono, color = C.text, fontSize = 13.sp, lineHeight = 18.sp, modifier = Modifier.horizontalScroll(rememberScrollState()).padding(start = 14.dp, end = 14.dp, bottom = 12.dp))
        androidx.compose.animation.AnimatedVisibility(out != null || busy) {
            Column(Modifier.padding(start = 8.dp, end = 8.dp, bottom = 8.dp).fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(C.code).padding(12.dp)) {
                Text(if (busy) "…" else out.orEmpty(), color = C.ok, style = Mono, fontSize = 12.sp, lineHeight = 16.sp, modifier = Modifier.heightIn(max = 220.dp).verticalScroll(rememberScrollState()))
            }
        }
    }
}

fun shareText(ctx: Context, text: String) {
    val i = android.content.Intent(android.content.Intent.ACTION_SEND).setType("text/plain").putExtra(android.content.Intent.EXTRA_TEXT, text)
    runCatching { ctx.startActivity(android.content.Intent.createChooser(i, "Поделиться чатом").addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)) }
}


/**
 * SVG из ответа агента. В ленте — надёжный статический кадр (рисуется самим приложением), а если есть анимация, поверх кнопка «▶ Анимация»:
 * она открывает рисунок во весь экран в живом WebView. (Живой WebView прямо в ленте на ряде телефонов оставался белым.)
 */
@Composable
fun SvgBlock(code: String, ctx: Context) {
    val vm = LocalVM.current
    val svg = remember(code) { code.substring(code.indexOf("<svg"), code.lastIndexOf("</svg>") + 6) }
    val ratio = remember(svg) {
        val vb = Regex("viewBox\\s*=\\s*\"([^\"]+)\"").find(svg)?.groupValues?.get(1)?.trim()?.split(Regex("[ ,]+"))?.mapNotNull { it.toFloatOrNull() }
        val w = Regex("<svg[^>]*?\\swidth\\s*=\\s*\"([\\d.]+)").find(svg)?.groupValues?.get(1)?.toFloatOrNull(); val h = Regex("<svg[^>]*?\\sheight\\s*=\\s*\"([\\d.]+)").find(svg)?.groupValues?.get(1)?.toFloatOrNull()
        (if (vb != null && vb.size == 4 && vb[3] > 0f) vb[2] / vb[3] else if (w != null && h != null && h > 0f) w / h else 1.4f).coerceIn(0.45f, 3f)
    }
    val animated = remember(svg) { Regex("<animate|<set\\b|@keyframes|animation\\s*:", RegexOption.IGNORE_CASE).containsMatchIn(svg) }
    var showCode by remember(code) { mutableStateOf(false) }
    var play by remember(code) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().background(C.surface2, RoundedCornerShape(20.dp)).padding(8.dp)) {
        AnimatedSvg(svg, Modifier.fillMaxWidth().aspectRatio(ratio).heightIn(max = 480.dp).clip(RoundedCornerShape(14.dp)).background(Color.White).clickable(enabled = animated) { play = true })
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(if (animated) "SVG · анимация" else "SVG", color = C.dim, fontSize = 12.sp, modifier = Modifier.weight(1f).padding(start = 8.dp))
            Text(if (showCode) "Скрыть код" else "Код", color = C.dim, fontSize = 12.sp, modifier = Modifier.clickable { showCode = !showCode }.padding(8.dp))
            Text("Копировать", color = C.dim, fontSize = 12.sp, modifier = Modifier.clickable { copyToClipboard(ctx, svg) }.padding(8.dp))
            Text("Поделиться", color = C.accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.clickable {
                runCatching {
                    val f = java.io.File(java.io.File(ctx.cacheDir, "dl").also { it.mkdirs() }, "image.svg").also { it.writeText(svg) }
                    val uri = androidx.core.content.FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
                    ctx.startActivity(android.content.Intent.createChooser(android.content.Intent(android.content.Intent.ACTION_SEND).setType("image/svg+xml").putExtra(android.content.Intent.EXTRA_STREAM, uri).addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION), "SVG").addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
                }
            }.padding(8.dp))
        }
        if (showCode) Text(svg, style = Mono, color = C.text, fontSize = 12.sp, lineHeight = 16.sp, modifier = Modifier.heightIn(max = 260.dp).verticalScroll(rememberScrollState()).horizontalScroll(rememberScrollState()).padding(8.dp))
    }
    if (play) SvgPlayer(svg, ratio) { play = false }
}

/** Просмотр SVG крупно (нажатие по рисунку). Рисует наш собственный движок анимации — без WebView. */
@Composable
internal fun SvgPlayer(svg: String, ratio: Float, onClose: () -> Unit) {
    androidx.compose.ui.window.Dialog(onDismissRequest = onClose, properties = androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false)) {
        androidx.compose.foundation.layout.Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.88f)).clickable(indication = null, interactionSource = remember { androidx.compose.foundation.interaction.MutableInteractionSource() }) { onClose() }, contentAlignment = Alignment.Center) {
            AnimatedSvg(svg, Modifier.fillMaxWidth().padding(10.dp).aspectRatio(ratio).clip(RoundedCornerShape(14.dp)).background(Color.White))
            Text("Закрыть", color = Color.White, fontSize = 14.sp, modifier = Modifier.align(Alignment.TopEnd).padding(20.dp).clip(RoundedCornerShape(18.dp)).background(Color(0x66000000)).padding(horizontal = 16.dp, vertical = 8.dp))
        }
    }
}

/** SVG с анимацией (SMIL и CSS) рисуется кадрами нашим движком + AndroidSVG; статичный — один кадр. */
@Composable
fun AnimatedSvg(svg: String, modifier: Modifier = Modifier) {
    val prep = remember(svg) { SvgAnim.prepare(svg) }
    var size by remember { mutableStateOf(androidx.compose.ui.unit.IntSize.Zero) }
    var pic by remember { mutableStateOf<android.graphics.Picture?>(null) }
    var failed by remember(svg) { mutableStateOf(false) }
    LaunchedEffect(prep, size) {
        if (size.width <= 0 || size.height <= 0) return@LaunchedEffect
        val t0 = System.nanoTime(); val live = prep?.animated == true
        while (isActive) {
            val t = (System.nanoTime() - t0) / 1_000_000
            val next = withContext(kotlinx.coroutines.Dispatchers.Default) {
                runCatching { com.caverock.androidsvg.SVG.getFromString(if (prep != null) SvgAnim.frame(prep, t) else svg).renderToPicture(size.width, size.height) }.getOrNull()
            }
            if (next == null) { failed = true; break }
            pic = next
            if (!live) break
            kotlinx.coroutines.delay(22)
        }
    }
    androidx.compose.foundation.layout.Box(modifier.onSizeChanged { size = it }) {
        androidx.compose.foundation.Canvas(Modifier.fillMaxSize()) { pic?.let { p -> drawIntoCanvas { it.nativeCanvas.drawPicture(p) } } }
        if (failed) Text("Не удалось нарисовать SVG — смотрите «Код»", color = Color.Black, fontSize = 12.sp, modifier = Modifier.align(Alignment.Center).padding(12.dp))
    }
}

/** Эталонный анимированный SVG для проверки: если он анимируется, а рисунок агента нет — дело в самом рисунке. */
internal const val SVG_SELFTEST = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 300'><rect width='400' height='300' fill='#101014'/><circle cx='200' cy='150' r='40' fill='#ffd54a'><animate attributeName='r' values='40;70;40' dur='1.6s' repeatCount='indefinite'/></circle><circle cx='120' cy='150' r='14' fill='#fff'><animateTransform attributeName='transform' type='rotate' from='0 200 150' to='360 200 150' dur='3s' repeatCount='indefinite'/></circle><text x='200' y='270' fill='#fff' font-size='22' text-anchor='middle'>тест анимации SVG</text></svg>"
