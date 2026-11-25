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

    fun render(ctx: Context, text: String, o: RenderOptions, seed: Long = System.nanoTime()): List<Bitmap> {
        val rnd = Random(seed)
        val tf = Typeface.createFromAsset(ctx.assets, "fonts/${o.font}.ttf")
        val m = o.messiness
        val textSize = o.cell * 0.95f
        val pen = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            typeface = tf; this.textSize = textSize
            textSkewX = -0.22f            // наклон вперёд, как на образце
            style = Paint.Style.FILL_AND_STROKE; strokeWidth = 0.9f
        }
        val pageH = o.background?.let { (W.toFloat() / it.width * it.height).toInt() } ?: (o.cell * 36)
        val left = o.cell * 2.6f + o.cell * 0.4f
        val right = W - o.cell * 1.2f
        val top = o.cell * 2.5f
        val linesPerPage = ((pageH - top - o.cell) / o.cell).toInt()

        // раскладка по строкам
        val lines = ArrayList<String>()
        for (para in text.split("\n")) {
            if (para.isBlank()) { lines.add(""); continue }
            var cur = ""
            for (w in para.split(" ")) {
                val t = if (cur.isEmpty()) w else "$cur $w"
                if (pen.measureText(t) > right - left && cur.isNotEmpty()) { lines.add(cur); cur = w } else cur = t
            }
            lines.add(cur)
        }

        val pages = ArrayList<Bitmap>()
        for (chunk in lines.chunked(max(1, linesPerPage))) {
            val bmp = newPage(o, pageH)
            val c = Canvas(bmp)
            chunk.forEachIndexed { i, line ->
                var x = left + rnd.nextFloat() * o.cell * 0.4f * m
                val baseY = top + (i + 1) * o.cell - o.cell * 0.12f
                var drift = 0f
                val rowTilt = (rnd.nextFloat() - 0.5f) * 0.012f * m   // строка едет вверх/вниз
                for ((k, ch) in line.withIndex()) {
                    val s = ch.toString()
                    val wch = pen.measureText(s)
                    drift += (rnd.nextFloat() - 0.5f) * 0.9f * m
                    val dy = drift + (rnd.nextFloat() - 0.5f) * o.cell * 0.14f * m + (x - left) * rowTilt
                    val rot = (rnd.nextFloat() - 0.5f) * 9f * m
                    val sc = 1f + (rnd.nextFloat() - 0.5f) * 0.22f * m
                    pen.color = o.ink
                    pen.alpha = (215 + rnd.nextInt(40))
                    c.save()
                    c.translate(x + wch / 2, baseY + dy)
                    c.rotate(rot)
                    c.scale(sc, sc * (1f + (rnd.nextFloat() - 0.5f) * 0.2f * m))
                    c.drawText(s, -wch / 2, 0f, pen)
                    c.restore()
                    // редкая клякса
                    if (ch != ' ' && rnd.nextInt(500) == 0 && m > 0.3f) blot(c, x + wch / 2, baseY + dy - textSize * 0.3f, o.ink, rnd)
                    x += wch * (0.92f + rnd.nextFloat() * 0.2f * m) + (if (ch == ' ') o.cell * 0.15f * rnd.nextFloat() * m else 0f)
                    if (k < 0) break
                }
            }
            pages.add(photoEffect(bmp, rnd))
        }
        return pages
    }

    private fun blot(c: Canvas, x: Float, y: Float, ink: Int, rnd: Random) {
        val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = ink; alpha = 200; style = Paint.Style.STROKE; strokeWidth = 3f }
        val path = Path().apply { moveTo(x, y); repeat(12) { lineTo(x + rnd.nextInt(-14, 14), y + rnd.nextInt(-12, 12)) } }
        c.drawPath(path, p)
    }

    private fun newPage(o: RenderOptions, h: Int): Bitmap {
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
}
