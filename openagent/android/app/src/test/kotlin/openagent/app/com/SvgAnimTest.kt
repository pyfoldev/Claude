package openagent.app.com

import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File

@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34])
class SvgAnimTest {
    private val out = File(System.getProperty("shots") ?: "/tmp/svgframes").also { it.mkdirs() }
    private fun render(name: String, svg: String, times: List<Long>): List<String> {
        val p = SvgAnim.prepare(svg); assertTrue("prepare failed for $name", p != null); assertTrue("not animated: $name", p!!.animated)
        val frames = times.map { SvgAnim.frame(p, it) }
        frames.forEachIndexed { i, f ->
            val pic = com.caverock.androidsvg.SVG.getFromString(f).renderToPicture(300, 225)
            val bmp = android.graphics.Bitmap.createBitmap(300, 225, android.graphics.Bitmap.Config.ARGB_8888)
            android.graphics.Canvas(bmp).also { it.drawColor(android.graphics.Color.WHITE) }.drawPicture(pic)
            File(out, "${name}_$i.png").outputStream().use { bmp.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
        }
        return frames
    }
    @Test fun smil() {
        val f = render("smil", SVG_SELFTEST, listOf(0, 400, 800, 1200))
        assertTrue(f.toSet().size == 4)
    }
    @Test fun css() {
        val svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><style>
            .wing{transform-origin:200px 150px;animation:flap 1s ease-in-out infinite alternate}
            @keyframes flap{from{transform:rotate(-30deg)}to{transform:rotate(30deg)}}
            .body{transform-box:fill-box;transform-origin:center;animation:bob 2s infinite}
            @keyframes bob{0%{transform:translateY(0)}50%{transform:translateY(-20px)}100%{transform:translateY(0)}}
            .eye{animation:blink 1.5s infinite}@keyframes blink{0%,90%{opacity:1}95%{opacity:0}100%{opacity:1}}
          </style><rect width="400" height="300" fill="#102030"/>
          <ellipse class="body" cx="200" cy="170" rx="80" ry="45" fill="#f5f5f5"/>
          <path class="wing" d="M200 150 L320 110 L330 150 Z" fill="#cde"/><circle class="eye" cx="290" cy="120" r="6" fill="#000"/></svg>"""
        val f = render("css", svg, listOf(0, 250, 500, 750))
        assertTrue(f.toSet().size >= 3)
    }
    @Test fun motion() {
        val svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><rect width="400" height="300" fill="#123"/>
          <path id="p" d="M20 200 C120 50 280 50 380 200" fill="none" stroke="#456"/>
          <g><circle r="14" fill="#fc3"/><animateMotion dur="2s" repeatCount="indefinite"><mpath href="#p"/></animateMotion></g></svg>"""
        val f = render("motion", svg, listOf(0, 500, 1000, 1500)); assertTrue(f.toSet().size == 4)
    }
}
