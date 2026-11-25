package openagent.app.com

import android.app.Application
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.math.PI
import kotlin.math.sin

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class StartupTest {
    /** Запуск MainActivity с включёнными «всеми фичами» (хлопок, жест, оффлайн, автоответчик) — как у пользователя. */
    @Test fun launchWithAllFeaturesOn() {
        val app = ApplicationProvider.getApplicationContext<Application>()
        val st = Store(app)
        st.token = "t"; st.clapWake = true; st.gestureWake = true; st.offlineMode = true; st.callScreen = true; st.gateSessions = true; st.onboarded = true
        val a = Robolectric.buildActivity(MainActivity::class.java).create().start().resume().visible().get()
        assertTrue(a != null)
    }
    @Test fun launchDefault() {
        val a = Robolectric.buildActivity(MainActivity::class.java).create().start().resume().visible().get()
        assertTrue(a != null)
    }

    private fun tone(n: Int, hz: Double, amp: Double) = ShortArray(n) { (amp * sin(2 * PI * hz * it / 16000) * 32767).toInt().toShort() }
    private fun noise(n: Int, amp: Double, seed: Long) = java.util.Random(seed).let { r -> ShortArray(n) { ((r.nextGaussian() * amp) * 32767).toInt().coerceIn(-32768, 32767).toShort() } }
    private fun clap(): ShortArray { val r = java.util.Random(5); return ShortArray(1200) { i -> ((r.nextGaussian() * 0.5 * Math.exp(-i / 160.0)) * 32767).toInt().coerceIn(-32768, 32767).toShort() } }   // ~75 мс затухающий щелчок

    @Test fun clapDetectorFindsDoubleClapAndNoException() {
        val d = ClapDetector(); var found = 0
        fun feed(x: ShortArray) { var i = 0; while (i < x.size) { val n = minOf(1600, x.size - i); if (d.feed(x.copyOfRange(i, i + n), n) != null) found++; i += n } }
        feed(noise(16000 * 2, 0.002, 1))                                   // тихая комната 2 с
        feed(clap()); feed(noise(16000 * 3 / 10, 0.002, 2)); feed(clap())  // два хлопка с паузой 0,3 с
        feed(noise(16000 * 2, 0.002, 3))                                   // тишина после
        assertTrue("двойной хлопок не найден, found=$found", found == 1)
    }
    @Test fun clapDetectorIgnoresSingleClapAndSpeechLikeTone() {
        val d = ClapDetector(); var found = 0
        fun feed(x: ShortArray) { var i = 0; while (i < x.size) { val n = minOf(1600, x.size - i); if (d.feed(x.copyOfRange(i, i + n), n) != null) found++; i += n } }
        feed(noise(16000 * 2, 0.002, 1)); feed(clap()); feed(noise(16000 * 3, 0.002, 2))
        feed(tone(16000 * 2, 220.0, 0.3)); feed(noise(16000 * 2, 0.002, 4))
        assertTrue("ложное срабатывание, found=$found", found == 0)
    }
}
