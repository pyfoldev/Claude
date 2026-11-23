package openagent.app.com

import org.w3c.dom.Document
import org.w3c.dom.Element
import org.w3c.dom.Node
import java.io.StringReader
import kotlin.math.abs
import kotlin.math.pow

/**
 * Анимация SVG без браузера: разбираем SMIL (animate / animateTransform / animateMotion / set) и простые CSS-анимации (@keyframes),
 * на каждый кадр подставляем значения в DOM и отдаём готовый статичный SVG — его рисует AndroidSVG. Работает на любом телефоне,
 * не зависит от WebView.
 */
object SvgAnim {
    private val NUM = Regex("[-+]?(?:\\d+\\.?\\d*|\\.\\d+)(?:[eE][-+]?\\d+)?")

    internal class A(
        val el: Element, val attr: String, val kind: String /* attr | transform | set | motion */, val tType: String, val values: List<String>, val keyTimes: List<Float>?,
        val dur: Long, val begin: Long, val repeat: Double, val freeze: Boolean, val additive: Boolean, val motionPath: String? = null,
    )
    internal class Kf(val name: String, val frames: List<Pair<Float, Map<String, String>>>)
    internal class Css(val el: Element, val kf: Kf, val dur: Long, val delay: Long, val iter: Double, val alt: Boolean, val rev: Boolean, val ease: String, val origin: String?, val box: String?)

    class Prepared internal constructor(internal val doc: Document, internal val smil: List<A>, internal val css: List<Css>, internal val orig: Map<Element, Map<String, String?>>) {
        val animated get() = smil.isNotEmpty() || css.isNotEmpty()
    }

    fun prepare(svgText: String): Prepared? = runCatching {
        val clean = svgText.replace(Regex("&(?!amp;|lt;|gt;|quot;|apos;|#\\d+;|#x[0-9a-fA-F]+;)"), "&amp;")
        val f = javax.xml.parsers.DocumentBuilderFactory.newInstance().apply { isNamespaceAware = false; isValidating = false }
        val doc = f.newDocumentBuilder().parse(org.xml.sax.InputSource(StringReader(clean)))
        val smil = ArrayList<A>(); val css = ArrayList<Css>()
        collectSmil(doc.documentElement, doc, smil)
        collectCss(doc, css)
        val orig = HashMap<Element, MutableMap<String, String?>>()
        fun keep(e: Element, attr: String) { val m = orig.getOrPut(e) { HashMap() }; if (!m.containsKey(attr)) m[attr] = if (e.hasAttribute(attr)) e.getAttribute(attr) else null }
        smil.forEach { keep(it.el, if (it.kind == "transform" || it.kind == "motion") "transform" else it.attr) }
        css.forEach { c -> keep(c.el, "transform"); c.kf.frames.flatMap { it.second.keys }.distinct().forEach { k -> if (k != "transform") keep(c.el, "style") } }
        Prepared(doc, smil, css, orig)
    }.getOrNull()

    /** Готовый SVG-текст для момента t (мс от начала). */
    fun frame(p: Prepared, tMs: Long): String {
        for ((e, m) in p.orig) for ((k, v) in m) if (v == null) e.removeAttribute(k) else e.setAttribute(k, v)
        // SMIL: атрибуты и transform
        val tr = LinkedHashMap<Element, MutableList<A>>()
        for (a in p.smil) {
            when (a.kind) {
                "attr", "set" -> valueAt(a, tMs)?.let { a.el.setAttribute(a.attr, it) }
                "transform", "motion" -> tr.getOrPut(a.el) { ArrayList() }.add(a)
            }
        }
        for ((e, list) in tr) {
            val parts = ArrayList<String>(); var base = false
            for (a in list) {
                val v = valueAt(a, tMs) ?: continue
                if (a.kind == "motion") { parts.add(v); base = true } else { parts.add("${a.tType}($v)"); if (a.additive) base = true }
            }
            if (parts.isNotEmpty()) { val b = if (base) e.getAttribute("transform") else ""; e.setAttribute("transform", (b + " " + parts.joinToString(" ")).trim()) }
        }
        // CSS-анимации
        for (c in p.css) applyCss(c, tMs)
        val sb = StringBuilder(4096); ser(p.doc.documentElement, sb); return sb.toString()
    }

    // ---------------- SMIL ----------------
    private fun collectSmil(e: Element, doc: Document, out: MutableList<A>) {
        val tag = e.tagName.substringAfter(':')
        if (tag == "animate" || tag == "animateTransform" || tag == "set" || tag == "animateMotion") parseAnim(e, tag, doc)?.let { out.add(it) }
        var c = e.firstChild
        while (c != null) { if (c.nodeType == Node.ELEMENT_NODE) collectSmil(c as Element, doc, out); c = c.nextSibling }
    }
    private fun time(s: String?): Long? {
        val v = s?.trim() ?: return null
        return when { v.endsWith("ms") -> v.dropLast(2).toDoubleOrNull()?.toLong(); v.endsWith("s") -> v.dropLast(1).toDoubleOrNull()?.times(1000)?.toLong(); v.endsWith("min") -> v.dropLast(3).toDoubleOrNull()?.times(60000)?.toLong(); else -> v.toDoubleOrNull()?.times(1000)?.toLong() }
    }
    private fun parseAnim(e: Element, tag: String, doc: Document): A? {
        val href = (e.getAttribute("href").ifEmpty { e.getAttribute("xlink:href") }).removePrefix("#")
        val target = (if (href.isNotEmpty()) byId(doc.documentElement, href) else e.parentNode as? Element) ?: return null
        val dur = if (tag == "set") (time(e.getAttribute("dur")) ?: 0L) else (time(e.getAttribute("dur")) ?: return null)
        val begin = e.getAttribute("begin").split(';').firstNotNullOfOrNull { time(it) } ?: 0L
        val rc = e.getAttribute("repeatCount"); val repeat = when { rc == "indefinite" -> Double.POSITIVE_INFINITY; rc.isNotEmpty() -> rc.toDoubleOrNull() ?: 1.0; e.getAttribute("repeatDur") == "indefinite" -> Double.POSITIVE_INFINITY; else -> 1.0 }
        val freeze = e.getAttribute("fill") == "freeze"
        val kt = e.getAttribute("keyTimes").takeIf { it.isNotBlank() }?.split(';')?.mapNotNull { it.trim().toFloatOrNull() }
        var values = e.getAttribute("values").split(';').map { it.trim() }.filter { it.isNotEmpty() }
        if (values.isEmpty()) {
            val from = e.getAttribute("from"); val to = e.getAttribute("to")
            if (to.isNotEmpty()) values = listOf(from.ifEmpty { target.getAttribute(e.getAttribute("attributeName")) }, to)
        }
        return when (tag) {
            "animateMotion" -> {
                var path = e.getAttribute("path")
                if (path.isEmpty()) { var c = e.firstChild; while (c != null) { if (c is Element && c.tagName.endsWith("mpath")) { val r = (c.getAttribute("href").ifEmpty { c.getAttribute("xlink:href") }).removePrefix("#"); byId(doc.documentElement, r)?.getAttribute("d")?.let { path = it } }; c = c.nextSibling } }
                if (path.isEmpty()) null else A(target, "transform", "motion", "", emptyList(), null, dur, begin, repeat, freeze, true, path)
            }
            "animateTransform" -> if (values.size < 1) null else A(target, "transform", "transform", e.getAttribute("type").ifEmpty { "translate" }, values, kt, dur, begin, repeat, freeze, e.getAttribute("additive") == "sum")
            else -> { val attr = e.getAttribute("attributeName"); if (attr.isEmpty() || values.isEmpty() || attr == "transform") null else A(target, attr, if (tag == "set") "set" else "attr", "", values, kt, dur, begin, repeat, freeze, false) }
        }
    }
    private fun byId(e: Element, id: String): Element? {
        if (e.getAttribute("id") == id) return e
        var c = e.firstChild
        while (c != null) { if (c is Element) byId(c, id)?.let { return it }; c = c.nextSibling }
        return null
    }

    private fun progress(a: A, t: Long): Double? {
        val local = t - a.begin; if (local < 0) return null
        if (a.kind == "set") return if (a.dur <= 0 || local < a.dur * a.repeat || a.freeze) 1.0 else null
        if (a.dur <= 0) return null
        val total = if (a.repeat.isInfinite()) Double.POSITIVE_INFINITY else a.dur * a.repeat
        return if (local >= total) (if (a.freeze) 1.0 else null) else (local % a.dur).toDouble() / a.dur
    }
    private fun valueAt(a: A, t: Long): String? {
        val p = progress(a, t) ?: return null
        if (a.kind == "set") return a.values[0]
        if (a.kind == "motion") return motionAt(a, p)
        return interp(a.values, a.keyTimes, p)
    }
    private fun motionAt(a: A, p: Double): String? {
        val path = runCatching { androidx.core.graphics.PathParser.createPathFromPathData(a.motionPath!!) }.getOrNull() ?: return null
        val pm = android.graphics.PathMeasure(path, false); val len = pm.length; if (len <= 0f) return null
        val pos = FloatArray(2); pm.getPosTan((len * p).toFloat().coerceIn(0f, len), pos, null)
        return "translate(${fmt(pos[0].toDouble())} ${fmt(pos[1].toDouble())})"
    }
    private fun interp(values: List<String>, keyTimes: List<Float>?, p: Double): String {
        val n = values.size; if (n == 1 || p >= 1.0) return values.last()
        val kt = keyTimes?.takeIf { it.size == n } ?: List(n) { it / (n - 1f) }
        var i = 0; while (i < n - 2 && p >= kt[i + 1]) i++
        val span = (kt[i + 1] - kt[i]).toDouble(); val f = if (span <= 0) 0.0 else ((p - kt[i]) / span).coerceIn(0.0, 1.0)
        return lerp(values[i], values[i + 1], f)
    }

    // ---------------- интерполяция значений ----------------
    private fun fmt(d: Double): String = if (abs(d - d.toLong()) < 1e-6) d.toLong().toString() else "%.4f".format(java.util.Locale.US, d).trimEnd('0').trimEnd('.')
    private fun color(s: String): IntArray? {
        val v = s.trim()
        if (Regex("#[0-9a-fA-F]{6}").matches(v)) return intArrayOf(v.substring(1, 3).toInt(16), v.substring(3, 5).toInt(16), v.substring(5, 7).toInt(16))
        if (Regex("#[0-9a-fA-F]{3}").matches(v)) return intArrayOf(v[1].digitToInt(16) * 17, v[2].digitToInt(16) * 17, v[3].digitToInt(16) * 17)
        return null
    }
    private val UNIT = Regex("(?<=\\d)(?:px|deg|rad|turn|%|em|s|ms)")
    private fun lerp(a0: String, b0: String, f: Double): String {
        // единицы (px, deg, %) для интерполяции не важны: «translateY(0)» ↔ «translateY(-20px)»
        val a = if (NUM.replace(a0, "#") == NUM.replace(b0, "#")) a0 else UNIT.replace(a0, "")
        val b = if (NUM.replace(a0, "#") == NUM.replace(b0, "#")) b0 else UNIT.replace(b0, "")
        val ca = color(a); val cb = color(b)
        if (ca != null && cb != null) return "#" + (0..2).joinToString("") { "%02x".format((ca[it] + (cb[it] - ca[it]) * f).toInt().coerceIn(0, 255)) }
        val na = NUM.findAll(a).map { it.value.toDouble() }.toList(); val nb = NUM.findAll(b).map { it.value.toDouble() }.toList()
        if (na.size == nb.size && na.isNotEmpty() && NUM.replace(a, "#") == NUM.replace(b, "#")) {
            var i = 0; return NUM.replace(a) { val v = na[i] + (nb[i] - na[i]) * f; i++; fmt(v) }
        }
        return if (f < 1.0) a else b
    }

    // ---------------- CSS ----------------
    private fun styleText(doc: Document): String {
        val sb = StringBuilder(); val ls = doc.getElementsByTagName("style")
        for (i in 0 until ls.length) sb.append(ls.item(i).textContent).append('\n')
        return sb.toString().replace(Regex("/\\*[\\s\\S]*?\\*/"), "")
    }
    private fun decls(s: String): Map<String, String> = s.split(';').mapNotNull { d -> val i = d.indexOf(':'); if (i < 0) null else d.substring(0, i).trim().lowercase() to d.substring(i + 1).trim() }.toMap()
    private fun collectCss(doc: Document, out: MutableList<Css>) {
        val css = styleText(doc); if (!css.contains("@keyframes")) return
        val kfs = HashMap<String, Kf>()
        val kfRx = Regex("@(?:-webkit-)?keyframes\\s+([\\w-]+)\\s*\\{((?:[^{}]*\\{[^{}]*\\})*[^{}]*)\\}")
        for (m in kfRx.findAll(css)) {
            val frames = ArrayList<Pair<Float, Map<String, String>>>()
            for (b in Regex("([^{}]+)\\{([^{}]*)\\}").findAll(m.groupValues[2])) {
                val d = decls(b.groupValues[2])
                for (sel in b.groupValues[1].split(',')) { val s = sel.trim().lowercase(); val off = when { s == "from" -> 0f; s == "to" -> 1f; s.endsWith("%") -> (s.dropLast(1).toFloatOrNull() ?: continue) / 100f; else -> continue }; frames.add(off to d) }
            }
            kfs[m.groupValues[1]] = Kf(m.groupValues[1], frames.sortedBy { it.first })
        }
        if (kfs.isEmpty()) return
        val rules = Regex("([^{}@]+)\\{([^{}]*)\\}").findAll(kfRx.replace(css, "")).map { it.groupValues[1].split(',').map { s -> s.trim() } to decls(it.groupValues[2]) }.toList()
        fun walk(e: Element) {
            val merged = HashMap<String, String>()
            for ((sels, d) in rules) if (sels.any { matches(e, it) }) merged.putAll(d)
            merged.putAll(decls(e.getAttribute("style")))
            val an = merged["animation"]; val name = merged["animation-name"] ?: an?.split(Regex("\\s+"))?.firstOrNull { kfs.containsKey(it) }
            if (name != null && kfs[name] != null) {
                val toks = (an ?: "").split(Regex("\\s+(?![^(]*\\))")).filter { it.isNotEmpty() }
                val times = toks.mapNotNull { Regex("^[\\d.]+m?s$").find(it)?.value }
                val dur = time(merged["animation-duration"] ?: times.getOrNull(0)) ?: 1000L
                val delay = time(merged["animation-delay"] ?: times.getOrNull(1)) ?: 0L
                val itS = merged["animation-iteration-count"] ?: toks.firstOrNull { it == "infinite" || Regex("^\\d+(\\.\\d+)?$").matches(it) }
                val iter = when { itS == "infinite" -> Double.POSITIVE_INFINITY; itS != null -> itS.toDoubleOrNull() ?: 1.0; else -> 1.0 }
                val dir = merged["animation-direction"] ?: toks.firstOrNull { it in setOf("alternate", "reverse", "alternate-reverse", "normal") } ?: "normal"
                val ease = merged["animation-timing-function"] ?: toks.firstOrNull { it.startsWith("ease") || it == "linear" || it.startsWith("cubic-bezier") } ?: "ease"
                out.add(Css(e, kfs[name]!!, dur.coerceAtLeast(1), delay, iter, dir.contains("alternate"), dir.contains("reverse"), ease, merged["transform-origin"], merged["transform-box"]))
            }
            var c = e.firstChild; while (c != null) { if (c is Element) walk(c); c = c.nextSibling }
        }
        walk(doc.documentElement)
    }
    private fun matches(e: Element, sel: String): Boolean {
        val last = sel.trim().split(Regex("[\\s>+~]+")).lastOrNull { it.isNotEmpty() } ?: return false
        val cls = e.getAttribute("class").split(Regex("\\s+")).filter { it.isNotEmpty() }
        val m = Regex("^([a-zA-Z][\\w-]*)?((?:[.#][\\w-]+)*)$").find(last) ?: return false
        val tag = m.groupValues[1]; if (tag.isNotEmpty() && tag != "*" && e.tagName.substringAfter(':') != tag) return false
        for (q in Regex("([.#])([\\w-]+)").findAll(m.groupValues[2])) { if (q.groupValues[1] == "." && q.groupValues[2] !in cls) return false; if (q.groupValues[1] == "#" && e.getAttribute("id") != q.groupValues[2]) return false }
        return tag.isNotEmpty() && tag != "*" || m.groupValues[2].isNotEmpty()
    }
    private fun bez(x1: Double, y1: Double, x2: Double, y2: Double, x: Double): Double {
        var t = x; repeat(8) { val cx = 3 * x1 * t * (1 - t).pow(2) + 3 * x2 * t * t * (1 - t) + t.pow(3); val d = 3 * x1 * (1 - t).pow(2) + 6 * (x2 - x1) * t * (1 - t) + 3 * (1 - x2) * t * t; if (abs(d) > 1e-6) t -= (cx - x) / d; t = t.coerceIn(0.0, 1.0) }
        return 3 * y1 * t * (1 - t).pow(2) + 3 * y2 * t * t * (1 - t) + t.pow(3)
    }
    private fun easeFn(name: String, x: Double): Double = when {
        name == "linear" -> x; name == "ease-in" -> bez(.42, 0.0, 1.0, 1.0, x); name == "ease-out" -> bez(0.0, 0.0, .58, 1.0, x); name == "ease-in-out" -> bez(.42, 0.0, .58, 1.0, x)
        name.startsWith("cubic-bezier") -> NUM.findAll(name).map { it.value.toDouble() }.toList().let { if (it.size == 4) bez(it[0], it[1], it[2], it[3], x) else x }
        else -> bez(.25, .1, .25, 1.0, x)
    }
    private fun applyCss(c: Css, t: Long) {
        val local = t - c.delay; if (local < 0) return
        val total = if (c.iter.isInfinite()) Double.POSITIVE_INFINITY else c.dur * c.iter
        if (local >= total) return
        val k = (local / c.dur).toInt(); var p = (local % c.dur).toDouble() / c.dur
        val backwards = (c.rev xor (c.alt && k % 2 == 1)); if (backwards) p = 1.0 - p
        val fr = c.kf.frames; if (fr.size < 2) return
        var i = 0; while (i < fr.size - 2 && p >= fr[i + 1].first) i++
        val a = fr[i]; val b = fr[i + 1]; val span = (b.first - a.first).toDouble()
        val f = easeFn(c.ease, if (span <= 0) 1.0 else ((p - a.first) / span).coerceIn(0.0, 1.0))
        val props = (a.second.keys + b.second.keys)
        val style = StringBuilder(c.el.getAttribute("style"))
        for (pr in props) {
            val va = a.second[pr] ?: b.second[pr] ?: continue; val vb = b.second[pr] ?: va
            val v = lerp(va, vb, f)
            if (pr == "transform") c.el.setAttribute("transform", cssTransform(v, c))
            else { if (style.isNotEmpty() && !style.endsWith(";")) style.append(';'); style.append(pr).append(':').append(v).append(';') }
        }
        if (style.isNotEmpty()) c.el.setAttribute("style", style.toString())
    }
    private fun cssTransform(v: String, c: Css): String {
        val parts = Regex("(\\w+)\\(([^)]*)\\)").findAll(v).map { m ->
            val args = NUM.findAll(m.groupValues[2]).map { it.value }.toList()
            when (m.groupValues[1]) {
                "translate" -> "translate(${args.getOrElse(0) { "0" }} ${args.getOrElse(1) { "0" }})"; "translateX" -> "translate(${args.getOrElse(0) { "0" }} 0)"; "translateY" -> "translate(0 ${args.getOrElse(0) { "0" }})"
                "rotate" -> "rotate(${args.getOrElse(0) { "0" }})"; "scale" -> "scale(${args.getOrElse(0) { "1" }} ${args.getOrElse(1) { args.getOrElse(0) { "1" } }})"
                "scaleX" -> "scale(${args.getOrElse(0) { "1" }} 1)"; "scaleY" -> "scale(1 ${args.getOrElse(0) { "1" }})"; "skewX" -> "skewX(${args.getOrElse(0) { "0" }})"; "skewY" -> "skewY(${args.getOrElse(0) { "0" }})"
                "matrix" -> "matrix(${args.joinToString(" ")})"; else -> ""
            }
        }.joinToString(" ")
        val o = originOf(c) ?: return parts
        return "translate(${fmt(o.first)} ${fmt(o.second)}) $parts translate(${fmt(-o.first)} ${fmt(-o.second)})"
    }
    private fun originOf(c: Css): Pair<Double, Double>? {
        val s = c.origin ?: return null
        val tok = s.trim().split(Regex("\\s+"))
        val fill = c.box == "fill-box"
        val bb = if (fill) bbox(c.el) else null
        fun res(t: String, axis: Int): Double {
            val lo = if (bb != null) bb[axis].toDouble() else 0.0; val size = if (bb != null) (bb[axis + 2] - bb[axis]).toDouble() else viewSize(c.el)[axis]
            return when { t == "center" -> lo + size / 2; t == "left" || t == "top" -> lo; t == "right" || t == "bottom" -> lo + size; t.endsWith("%") -> lo + size * (t.dropLast(1).toDoubleOrNull() ?: 50.0) / 100; else -> lo + (NUM.find(t)?.value?.toDoubleOrNull() ?: 0.0) }
        }
        val x = tok.getOrElse(0) { "50%" }; val y = tok.getOrElse(1) { if (x == "top" || x == "bottom") "50%" else "50%" }
        val (xx, yy) = if (x == "top" || x == "bottom") y to x else x to y
        return res(xx, 0) to res(yy, 1)
    }
    private fun viewSize(e: Element): DoubleArray {
        val root = e.ownerDocument.documentElement; val vb = NUM.findAll(root.getAttribute("viewBox")).map { it.value.toDouble() }.toList()
        return if (vb.size == 4) doubleArrayOf(vb[2], vb[3]) else doubleArrayOf(NUM.find(root.getAttribute("width"))?.value?.toDoubleOrNull() ?: 100.0, NUM.find(root.getAttribute("height"))?.value?.toDoubleOrNull() ?: 100.0)
    }
    /** Ограничивающий прямоугольник элемента (left, top, right, bottom) в его системе координат; группы — объединение детей. */
    private fun bbox(e: Element): FloatArray? {
        fun n(a: String) = e.getAttribute(a).toFloatOrNull() ?: 0f
        val tag = e.tagName.substringAfter(':')
        return when (tag) {
            "rect", "image", "use" -> floatArrayOf(n("x"), n("y"), n("x") + n("width"), n("y") + n("height"))
            "circle" -> floatArrayOf(n("cx") - n("r"), n("cy") - n("r"), n("cx") + n("r"), n("cy") + n("r"))
            "ellipse" -> floatArrayOf(n("cx") - n("rx"), n("cy") - n("ry"), n("cx") + n("rx"), n("cy") + n("ry"))
            "line" -> floatArrayOf(minOf(n("x1"), n("x2")), minOf(n("y1"), n("y2")), maxOf(n("x1"), n("x2")), maxOf(n("y1"), n("y2")))
            "polygon", "polyline" -> NUM.findAll(e.getAttribute("points")).map { it.value.toFloat() }.toList().chunked(2).filter { it.size == 2 }.let { pts -> if (pts.isEmpty()) null else floatArrayOf(pts.minOf { it[0] }, pts.minOf { it[1] }, pts.maxOf { it[0] }, pts.maxOf { it[1] }) }
            "path" -> runCatching { val r = android.graphics.RectF(); androidx.core.graphics.PathParser.createPathFromPathData(e.getAttribute("d")).computeBounds(r, true); floatArrayOf(r.left, r.top, r.right, r.bottom) }.getOrNull()
            "text" -> floatArrayOf(n("x"), n("y") - 16f, n("x") + 80f, n("y"))
            else -> {
                var out: FloatArray? = null; var c = e.firstChild
                while (c != null) { if (c is Element) bbox(c)?.let { b -> out = if (out == null) b else floatArrayOf(minOf(out!![0], b[0]), minOf(out!![1], b[1]), maxOf(out!![2], b[2]), maxOf(out!![3], b[3])) }; c = c.nextSibling }
                out
            }
        }
    }

    // ---------------- сериализация ----------------
    private fun esc(s: String) = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    private fun ser(e: Element, sb: StringBuilder) {
        sb.append('<').append(e.tagName)
        val at = e.attributes
        for (i in 0 until at.length) { val a = at.item(i); sb.append(' ').append(a.nodeName).append("=\"").append(esc(a.nodeValue).replace("\"", "&quot;")).append('"') }
        if (!e.hasChildNodes()) { sb.append("/>"); return }
        sb.append('>')
        var c = e.firstChild
        while (c != null) {
            when (c.nodeType) { Node.ELEMENT_NODE -> ser(c as Element, sb); Node.TEXT_NODE, Node.CDATA_SECTION_NODE -> sb.append(if (e.tagName == "style") c.nodeValue else esc(c.nodeValue)) }
            c = c.nextSibling
        }
        sb.append("</").append(e.tagName).append('>')
    }
}
