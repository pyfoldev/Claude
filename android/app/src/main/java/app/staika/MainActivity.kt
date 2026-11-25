package app.staika

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.*
import androidx.compose.animation.core.EaseOutCubic
import androidx.compose.animation.core.tween
import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { StaikaTheme { App() } }
    }
}

@Composable
fun App() {
    val nav = rememberNavController()
    val back: () -> Unit = { nav.popBackStack() }
    fun NavHostController.toHome() = navigate("home") { popUpTo(0) { inclusive = true } }

    NavHost(
        nav, startDestination = "welcome",
        enterTransition = { slideInHorizontally(tween(380, easing = EaseOutCubic)) { it / 3 } + fadeIn(tween(300)) },
        exitTransition = { slideOutHorizontally(tween(380, easing = EaseOutCubic)) { -it / 6 } + fadeOut(tween(260)) },
        popEnterTransition = { slideInHorizontally(tween(380, easing = EaseOutCubic)) { -it / 6 } + fadeIn(tween(300)) },
        popExitTransition = { slideOutHorizontally(tween(380, easing = EaseOutCubic)) { it / 3 } + fadeOut(tween(260)) },
    ) {
        composable("welcome") { WelcomeScreen({ nav.navigate("auth/false") }, { nav.navigate("auth/true") }) }
        composable("auth/{signup}") { e -> AuthScreen(e.arguments?.getString("signup") == "true", back) { nav.toHome() } }
        composable("home") {
            HomeScreen(
                onChat = { nav.navigate("chat/$it") }, onProfile = { nav.navigate("profile") },
                onCreate = { nav.navigate("create") }, onPlugins = { nav.navigate("plugins") },
            )
        }
        composable("chat/{id}") { e ->
            val id = e.arguments?.getString("id") ?: "chief"
            ChatScreen(id, back, { nav.navigate("call/$id") }, { nav.navigate("computer") })
        }
        composable("call/{id}") { e -> CallScreen(e.arguments?.getString("id") ?: "chief", back) }
        composable("create") { CreateAgentScreen(back) }
        composable("plugins") { PluginsScreen(back) }
        composable("profile") { ProfileScreen(back) { nav.navigate(it) } }
        composable("team") { TeamScreen(back, { nav.navigate("chat/$it") }, { nav.navigate("create") }) }
        composable("tasks") { TasksScreen(back) { nav.navigate("chat/$it") } }
        composable("computer") { ComputerScreen(back) }
        composable("stats") { StatsScreen(back) }
        composable("activity") { ActivityScreen(back) }
        composable("settings") { SettingsScreen(back) { nav.navigate("welcome") { popUpTo(0) { inclusive = true } } } }
    }
}
