package app.staika

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.*
import androidx.compose.animation.core.EaseOutCubic
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Prefs.init(applicationContext)
        Repo.start()
        enableEdgeToEdge()
        setContent { StaikaTheme { App() } }
    }
}

@Composable
fun App() {
    val nav = rememberNavController()
    val back: () -> Unit = { nav.popBackStack() }
    val start = remember { if (Repo.loggedIn) "home" else "welcome" }
    fun NavHostController.toHome() = navigate("home") { popUpTo(0) { inclusive = true } }
    val route by nav.currentBackStackEntryAsState()

    // сессия закрыта (выход, истёк refresh-токен): возвращаем на экран приветствия
    LaunchedEffect(Repo.loggedIn) {
        val r = route?.destination?.route
        if (!Repo.loggedIn && r != null && r != "welcome" && !r.startsWith("auth")) nav.navigate("welcome") { popUpTo(0) { inclusive = true } }
    }

    Box(Modifier.fillMaxSize()) {
        NavHost(
            nav, startDestination = start,
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
                val id = e.arguments?.getString("id") ?: ""
                ChatScreen(id, back, { nav.navigate("call/$id") }, { nav.navigate("agent/$id") })
            }
            composable("call/{id}") { e -> CallScreen(e.arguments?.getString("id") ?: "", back) }
            composable("create") { CreateAgentScreen(null, back) }
            composable("agent/{id}") { e -> CreateAgentScreen(e.arguments?.getString("id"), back) }
            composable("plugins") { PluginsScreen(back) }
            composable("profile") { ProfileScreen(back) { nav.navigate(it) } }
            composable("team") { TeamScreen(back, { nav.navigate("chat/$it") }, { nav.navigate("create") }) }
            composable("tasks") { TasksScreen(back) { nav.navigate("chat/$it") } }
            composable("stats") { StatsScreen(back) }
            composable("activity") { ActivityScreen(back) }
            composable("settings") { SettingsScreen(back) { Repo.logout() } }
        }
        ToastHost(Modifier.align(Alignment.BottomCenter))
    }
}

@Composable
fun ToastHost(modifier: Modifier = Modifier) {
    AnimatedVisibility(
        Repo.toast != null, modifier.navigationBarsPadding().padding(bottom = 86.dp, start = 24.dp, end = 24.dp),
        enter = slideInVertically(tween(260)) { it } + fadeIn(tween(200)), exit = fadeOut(tween(200)),
    ) {
        Text(
            Repo.toast.orEmpty(), color = Color.White, fontSize = 15.sp, lineHeight = 20.sp,
            modifier = Modifier.clip(androidx.compose.foundation.shape.RoundedCornerShape(20.dp)).background(Color(0xE60A0A0B)).padding(horizontal = 18.dp, vertical = 12.dp),
        )
    }
}
