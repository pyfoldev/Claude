package app.staika

import androidx.compose.runtime.Composable
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onRoot
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/** Рендер экранов в PNG (Robolectric Native Graphics), чтобы проверять вид без телефона. */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w411dp-h891dp-port-xxhdpi")
class ScreenshotTest {
    @get:Rule val rule = createComposeRule()

    private fun shot(name: String, content: @Composable () -> Unit) {
        rule.mainClock.autoAdvance = false
        rule.setContent { StaikaTheme { content() } }
        rule.mainClock.advanceTimeBy(2500)
        rule.onRoot().captureRoboImage("build/shots/$name.png")
    }

    @Test fun welcome() = shot("01_welcome") { WelcomeScreen({}, {}) }
    @Test fun home() = shot("02_home") { HomeScreen({}, {}, {}, {}) }
    @Test fun chatDev() = shot("03_chat_dev") { ChatScreen("dev", {}, {}, {}) }
    @Test fun chatChief() = shot("04_chat_chief") { ChatScreen("chief", {}, {}, {}) }
    @Test fun create() = shot("05_create") { CreateAgentScreen {} }
    @Test fun plugins() = shot("06_plugins") { PluginsScreen {} }
    @Test fun profile() = shot("07_profile") { ProfileScreen({}, {}) }
    @Test fun auth() = shot("08_auth") { AuthScreen(false, {}) {} }
    @Test fun call() = shot("09_call") { CallScreen("chief") {} }
    @Test fun team() = shot("10_team") { TeamScreen({}, {}, {}) }
    @Test fun tasks() = shot("11_tasks") { TasksScreen({}, {}) }
    @Test fun settings() = shot("12_settings") { SettingsScreen({}, {}) }
    @Test fun stats() = shot("13_stats") { StatsScreen({}) }
    @Test fun computer() = shot("14_computer") { ComputerScreen({}) }
}
