package ai.chip.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.lifecycle.viewmodel.compose.viewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            ChipTheme {
                val vm: ChatViewModel = viewModel()
                ChatScreen(vm)
            }
        }
    }
}

object ChipColors {
    val Sky = Color(0xFF5DB9F6)
    val SkyDark = Color(0xFF2E8FD6)
}

@Composable
fun ChipTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val scheme = if (dark) darkColorScheme(
        primary = ChipColors.Sky, onPrimary = Color(0xFF06223A),
        background = Color(0xFF0F1A2B), surface = Color(0xFF182638), onSurface = Color(0xFFE8F2FF),
        surfaceVariant = Color(0xFF22344B), onSurfaceVariant = Color(0xFFA9C0DA),
    ) else lightColorScheme(
        primary = ChipColors.SkyDark, onPrimary = Color.White,
        background = Color(0xFFEFF7FF), surface = Color.White, onSurface = Color(0xFF1B2540),
        surfaceVariant = Color(0xFFDDEBFA), onSurfaceVariant = Color(0xFF5B6B85),
    )
    MaterialTheme(colorScheme = scheme, content = content)
}
