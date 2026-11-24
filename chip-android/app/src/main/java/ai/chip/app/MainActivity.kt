package ai.chip.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.lifecycle.viewmodel.compose.viewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
        )
        setContent {
            ChipTheme {
                val vm: ChatViewModel = viewModel()
                ChatScreen(vm)
            }
        }
    }
}

object ChipColors {
    val Ink = Color(0xFF0D0D0D)
    val Gray = Color(0xFFF4F4F4)
    val Line = Color(0xFFE5E5E5)
    val Muted = Color(0xFF6E6E80)
}

/** Light only: white background like ChatGPT / Claude. */
@Composable
fun ChipTheme(content: @Composable () -> Unit) {
    val scheme = lightColorScheme(
        primary = ChipColors.Ink, onPrimary = Color.White,
        background = Color.White, onBackground = ChipColors.Ink,
        surface = Color.White, onSurface = ChipColors.Ink,
        surfaceVariant = ChipColors.Gray, onSurfaceVariant = ChipColors.Muted,
        outline = ChipColors.Line,
    )
    MaterialTheme(colorScheme = scheme, content = content)
}
