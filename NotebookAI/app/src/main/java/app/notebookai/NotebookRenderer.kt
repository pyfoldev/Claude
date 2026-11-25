package app.notebookai

import android.content.Context
import android.graphics.*
import kotlin.math.max
import kotlin.random.Random

data class RenderOptions(
    val font: String = "MarckScript",   // имя файла в assets/fonts без .ttf
    val cell: Int = 48,                 // размер клетки в px (ширина страницы 1280)
    val messiness: Float = 1f,          // 0..2 «небрежность» почерка
    val ink: Int = 0xFF3B2FA0.toInt(),  // фиолетово-синяя паста
    val background: Bitmap? = null,     // фото пустой страницы; null = рисуем клетку
)

object NotebookRenderer {
    private const val W = 1280

    /** Линии страницы: y линии k на левом (xL) и правом (xR) краях текста. Между ними — линейно (наклон фото). */
    private class Ruling(val yL: FloatArray, val yR: FloatArray, val xL: Float, val xR: Float) {
        val size get() = yL.size
        fun y(k: Int, x: Float) = yL[k] + (yR[k] - yL[k]) * ((x - xL) / (xR - xL))
        fun mid(k: Int) = (yL[k] + yR[k]) / 2f
        fun gap(k: Int): Float = if (size < 2) 48f else if (k <= 0) mid(1) - mid(0) else mid(k) - mid(k - 1)
        fun slopeDeg(k: Int) = Math.toDegrees(Math.atan(((yR[k] - yL[k]) / (xR - xL)).toDouble())).toFloat()
    }

    private class Row(val text: String, val indent: Boolean, val page: Int, val k: Int, val size: Float)

    fun render(ctx: Context, text: String, o: RenderOptions, seed: Long = System.nanoTime()): List<Bitmap> {
        val rnd = Random(seed)
        val tf = Typeface.createFromAsset(ctx.assets, "fonts/${o.font}.ttf")
        val m = o.messiness
        val bg = o.background
        val pageH = bg?.let { (W.toFloat() / it.width * it.height).toInt() } ?: (o.cell * 36)
        val redLeft = bg?.let { findRedMarginX(it, left = true) }
        val redX = bg?.let { findRedMarginX(it) }
        val left = if (redLeft != null) redLeft + o.cell * 0.7f else o.cell * 3f
        val right = if (redX != null && redX > W * 0.5f) redX - o.cell * 0.7f else W - o.cell * 1.2f

        val ruling: Ruling = (bg?.let { detectRuling(it, pageH, left, right) }) ?: run {
            val n = (pageH / o.cell) + 1
            val ys = FloatArray(n) { it * o.cell.toFloat() }
            Ruling(ys, ys, left, right)
        }
        val detected = bg != null && ruling.size > 0 && (ruling.yL.size != (pageH / o.cell) + 1)
        val top = if (detected) pageH * 0.06f else o.cell * 2.5f
        var k0 = 0
        while (k0 < ruling.size && ruling.mid(k0) < top) k0++
        var kEnd = ruling.size - 1
        while (kEnd > k0 && ruling.mid(kEnd) > pageH - ruling.gap(kEnd) * 0.6f) kEnd--
        val perPage = max(1, kEnd - k0 + 1)

        val pen = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            typeface = tf
            textSkewX = -0.22f            // наклон вперёд, как на образце
            style = Paint.Style.FILL_AND_STROKE; strokeWidth = 0.9f
        }

        // раскладка по строкам. Размер букв каждой строки зависит от реального шага линий в этом месте.
        val safety = 1.10f
        val rows = ArrayList<Row>()
        fun sizeFor(k: Int) = ruling.gap(k.coerceIn(0, ruling.size - 1)) * 0.9f
        fun nextRowIdx() = rows.size
        val paras = text.split("\n").map { it.trim() }.filter { it.isNotEmpty() }
        paras.forEachIndexed { pi, para ->
            var first = true
            var cur = ""
            fun k() = k0 + nextRowIdx() % perPage
            fun limit(): Float {
                pen.textSize = sizeFor(k())
                return right - left - (if (first && pi > 0) pen.textSize * 1.8f else 0f)
            }
            fun flush(ind: Boolean) { rows.add(Row(cur, ind, rows.size / perPage, k(), sizeFor(k()))) }
            for (w in para.split(" ").filter { it.isNotEmpty() }) {
                val t = if (cur.isEmpty()) w else "$cur $w"
                val lim = limit()
                if (pen.measureText(t) * safety > lim && cur.isNotEmpty()) {
                    flush(first && pi > 0); first = false; cur = w
                } else cur = t
            }
            flush(first && pi > 0)
        }

        val pages = ArrayList<Bitmap>()
        val pageCount = (rows.lastOrNull()?.page ?: -1) + 1
        for (pg in 0 until pageCount) {
            val bmp = newPage(o, pageH, ruling.size)
            val c = Canvas(bmp)
            for (row in rows.filter { it.page == pg }) {
                pen.textSize = row.size
                val cs = row.size / 0.9f
                var x = left + (if (row.indent) row.size * 1.8f else 0f) + rnd.nextFloat() * cs * 0.25f * m
                var drift = 0f
                val tilt = ruling.slopeDeg(row.k)
                for (ch in row.text) {
                    val s = ch.toString()
                    val wch = pen.measureText(s)
                    drift = drift * 0.85f + (rnd.nextFloat() - 0.5f) * cs * 0.05f * m
                    val baseY = ruling.y(row.k, x) - cs * 0.07f
                    val dy = drift + (rnd.nextFloat() - 0.5f) * cs * 0.06f * m
                    val rot = tilt + (rnd.nextFloat() - 0.5f) * 8f * m
                    val sc = 1f + (rnd.nextFloat() - 0.5f) * 0.18f * m
                    pen.color = o.ink
                    pen.alpha = (215 + rnd.nextInt(40))
                    c.save()
                    c.translate(x + wch / 2, baseY + dy)
                    c.rotate(rot)
                    c.scale(sc, sc * (1f + (rnd.nextFloat() - 0.5f) * 0.15f * m))
                    c.drawText(s, -wch / 2, 0f, pen)
                    c.restore()
                    if (ch != ' ' && rnd.nextInt(500) == 0 && m > 0.3f) blot(c, x + wch / 2, baseY + dy - row.size * 0.3f, o.ink, rnd)
                    x += wch * (0.95f + rnd.nextFloat() * 0.12f * m) + (if (ch == ' ') cs * 0.1f * rnd.nextFloat() * m else 0f)
                }
            }
            pages.add(photoEffect(bmp, rnd))
        }
        return pages
    }

    /** Линии на фото: ищем отдельно у левого и правого края текста (учёт наклона), шаг может меняться (перспектива). */
    private fun detectRuling(bg: Bitmap, pageH: Int, xl: Float, xr: Float): Ruling? {
        val span = xr - xl
        if (span < 200f) return null
        val l = stripLines(bg, pageH, xl, xl + span * 0.2f) ?: return null
        val r = stripLines(bg, pageH, xr - span * 0.2f, xr) ?: return null
        // сопоставляем линии: для каждой левой берём ближайшую правую (наклон меньше полушага)
        val yl = ArrayList<Float>(); val yr = ArrayList<Float>()
        for (a in l) {
            val b = r.minByOrNull { Math.abs(it - a) } ?: continue
            val gap = if (l.size > 1) (l.last() - l.first()) / (l.size - 1) else 50f
            if (Math.abs(b - a) < gap * 0.5f && (yr.isEmpty() || b > yr.last())) { yl.add(a); yr.add(b) }
        }
        if (yl.size < 6) return null
        return Ruling(yl.toFloatArray(), yr.toFloatArray(), (xl + span * 0.1f), (xr - span * 0.1f))
    }

    /** y (в координатах страницы) всех линий в вертикальной полосе [xa, xb]; пропущенные линии достраиваются. */
    private fun stripLines(bg: Bitmap, pageH: Int, xa: Float, xb: Float): List<Float>? {
        val bw = bg.width; val bh = bg.height
        val from = (xa / W * bw).toInt().coerceIn(0, bw - 1)
        val to = (xb / W * bw).toInt().coerceIn(from + 1, bw)
        if (to - from < 10 || bh < 60) return null
        val lum = FloatArray(bh)
        val row = IntArray(bw)
        for (r in 0 until bh) {
            bg.getPixels(row, 0, bw, 0, r, bw, 1)
            var sum = 0f; var n = 0
            var x = from
            while (x < to) { val c = row[x]; sum += 0.3f * Color.red(c) + 0.59f * Color.green(c) + 0.11f * Color.blue(c); n++; x += 2 }
            lum[r] = sum / n
        }
        val rad = max(4, bh / 80)
        val dip = FloatArray(bh)
        for (r in 0 until bh) {
            var s = 0f; var n = 0
            for (q in max(0, r - rad)..minOf(bh - 1, r + rad)) { s += lum[q]; n++ }
            dip[r] = s / n - lum[r]
        }
        val sorted = dip.sortedArray()
        val thr = max(1.5f, sorted[(bh * 0.97f).toInt().coerceIn(0, bh - 1)] * 0.4f)
        val md = max(4, bh / 100)
        val peaks = ArrayList<Int>()
        for (r in 0 until bh) {
            if (dip[r] < thr) continue
            var isMax = true
            for (q in max(0, r - md)..minOf(bh - 1, r + md)) if (dip[q] > dip[r]) { isMax = false; break }
            if (isMax && (peaks.isEmpty() || r - peaks.last() > md)) peaks.add(r)
        }
        if (peaks.size < 6) return null
        val firstGaps = (1..minOf(3, peaks.size - 1)).map { peaks[it] - peaks[it - 1] }.sorted()
        var prevGap = firstGaps[firstGaps.size / 2].toFloat()
        if (prevGap < 8f) return null
        val out = ArrayList<Float>()
        var last = peaks[0].toFloat()
        out.add(last)
        for (i in 1 until peaks.size) {
            val gap = peaks[i] - last
            val n = Math.round(gap / prevGap)
            if (n < 1 || Math.abs(gap - n * prevGap) > 0.3f * n * prevGap) continue
            for (j in 1 until n) out.add(last + gap * j / n)   // достраиваем пропущенную линию
            out.add(peaks[i].toFloat())
            prevGap = gap / n; last = peaks[i].toFloat()
        }
        if (out.size < 6) return null
        val sy = pageH.toFloat() / bh
        return out.map { it * sy }
    }

    private fun blot(c: Canvas, x: Float, y: Float, ink: Int, rnd: Random) {
        val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = ink; alpha = 200; style = Paint.Style.STROKE; strokeWidth = 3f }
        val path = Path().apply { moveTo(x, y); repeat(12) { lineTo(x + rnd.nextInt(-14, 14), y + rnd.nextInt(-12, 12)) } }
        c.drawPath(path, p)
    }

    private fun newPage(o: RenderOptions, h: Int, @Suppress("UNUSED_PARAMETER") lines: Int): Bitmap {
        val bmp = Bitmap.createBitmap(W, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp)
        val bg = o.background
        if (bg != null) {
            c.drawBitmap(bg, null, Rect(0, 0, W, h), Paint(Paint.FILTER_BITMAP_FLAG))
            return bmp
        }
        c.drawColor(0xFFF7F6F0.toInt())
        val grid = Paint().apply { color = 0xFF9DB8D9.toInt(); strokeWidth = 1.6f; alpha = 190 }
        var x = 0f; while (x <= W) { c.drawLine(x, 0f, x, h.toFloat(), grid); x += o.cell }
        var y = 0f; while (y <= h) { c.drawLine(0f, y, W.toFloat(), y, grid); y += o.cell }
        val field = Paint().apply { color = 0xFFD9534F.toInt(); strokeWidth = 3f; alpha = 200 }
        c.drawLine(o.cell * 2f, 0f, o.cell * 2f, h.toFloat(), field)
        return bmp
    }

    /** лёгкая «фото с телефона»: виньетка, шум, небольшой поворот на столе */
    private fun photoEffect(src: Bitmap, rnd: Random): Bitmap {
        val w = src.width; val h = src.height
        val out = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(out)
        c.drawColor(0xFF3A3A3A.toInt())
        c.save()
        c.rotate((rnd.nextFloat() - 0.5f) * 2.4f, w / 2f, h / 2f)
        c.scale(1.04f, 1.04f, w / 2f, h / 2f)
        c.drawBitmap(src, 0f, 0f, null)
        c.restore()
        val vig = Paint().apply {
            shader = RadialGradient(w * (0.4f + rnd.nextFloat() * 0.2f), h * 0.45f, h * 0.85f,
                intArrayOf(0x00000000, 0x00000000, 0x66000000), floatArrayOf(0f, 0.55f, 1f), Shader.TileMode.CLAMP)
        }
        c.drawRect(0f, 0f, w.toFloat(), h.toFloat(), vig)
        val n = Paint().apply { color = Color.BLACK; alpha = 14 }
        repeat(14000) { c.drawPoint(rnd.nextInt(w).toFloat(), rnd.nextInt(h).toFloat(), n) }
        return out
    }

    /** x (в координатах страницы шириной W) красной линии поля на фото; null если не найдена */
    private fun findRedMarginX(bg: Bitmap, left: Boolean = false): Float? {
        val bw = bg.width; val bh = bg.height
        val from = if (left) 0 else (bw * 0.5f).toInt()
        val to = if (left) (bw * 0.5f).toInt() else bw
        val score = FloatArray(to - from)
        val rows = 60
        val row = IntArray(bw)
        for (r in 0 until rows) {
            bg.getPixels(row, 0, bw, 0, (bh * (0.1f + 0.8f * r / rows)).toInt().coerceIn(0, bh - 1), bw, 1)
            for (x in from until to) {
                val c = row[x]
                score[x - from] += (Color.red(c) - (Color.green(c) + Color.blue(c)) / 2f).coerceAtLeast(0f)
            }
        }
        var bi = 0
        for (i in score.indices) if (score[i] > score[bi]) bi = i
        val avg = score[bi] / rows
        return if (avg > 18f) (from + bi).toFloat() / bw * W else null
    }
}
