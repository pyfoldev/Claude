package app.staika

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Visibility
import androidx.compose.material.icons.outlined.VisibilityOff
import androidx.compose.animation.AnimatedVisibility
import kotlinx.coroutines.launch
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.graphicsLayer
import kotlinx.coroutines.delay
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
private fun Floaty(pal: Pal, size: Int, x: Float, y: Float, phase: Int, rot: Float, delayMs: Int) {
    val t = rememberInfiniteTransition(label = "f")
    val dy by t.animateFloat(
        -9f, 9f, infiniteRepeatable(tween(2600 + phase * 350, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "dy",
    )
    var shown by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { delay(delayMs.toLong()); shown = true }
    val sc by animateFloatAsState(if (shown) 1f else 0f, spring(0.5f, 260f), label = "in")
    BoxWithConstraints(Modifier.fillMaxSize()) {
        Avatar(
            pal, size.dp,
            Modifier.offset(x = maxWidth * x - (size / 2).dp, y = maxHeight * y - (size / 2).dp + dy.dp).rotate(rot).scale(sc),
        )
    }
}

@Composable
fun WelcomeScreen(onLogin: () -> Unit, onSignUp: () -> Unit) {
    var up by remember { mutableStateOf(false) }
    var dialog by remember { mutableStateOf(false) }
    var pending by remember { mutableStateOf<(() -> Unit)?>(null) }
    var server by remember { mutableStateOf(Prefs.server) }
    LaunchedEffect(Unit) { delay(120); up = true }
    val a by animateFloatAsState(if (up) 1f else 0f, tween(600, easing = EaseOutCubic), label = "welcome")
    fun go(action: () -> Unit) { if (server.isBlank()) { pending = action; dialog = true } else action() }

    Box(Modifier.fillMaxSize().background(Color.White)) {
        Floaty(Pal.Green, 96, 0.22f, 0.15f, 0, -5f, 100)
        Floaty(Pal.Yellow, 84, 0.80f, 0.27f, 1, 7f, 220)
        Floaty(Pal.Pink, 84, 0.04f, 0.60f, 2, -9f, 340)
        Floaty(Pal.Blue, 104, 0.92f, 0.62f, 3, 5f, 460)
        Floaty(Pal.Orange, 88, 0.50f, 0.74f, 4, -4f, 580)
        Column(
            Modifier.fillMaxSize().padding(horizontal = 24.dp).graphicsLayer { alpha = a; translationY = (1f - a) * 30f },
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.weight(1.25f))
            Text("Стайка", style = MaterialTheme.typography.headlineLarge, fontSize = 44.sp)
            Spacer(Modifier.height(10.dp))
            Text("Ваша команда агентов,\nкоторые доводят дело до конца.", color = C.Muted, textAlign = TextAlign.Center, fontSize = 19.sp, lineHeight = 26.sp)
            Spacer(Modifier.weight(1.1f))
            BlackButton("Войти", { go(onLogin) })
            Spacer(Modifier.height(10.dp))
            GrayButton("Регистрация", { go(onSignUp) })
            Text(
                if (server.isBlank()) "Указать сервер" else server.removePrefix("https://").removePrefix("http://"),
                color = C.Muted, fontSize = 14.sp,
                modifier = Modifier.clip(CircleShape).bounceClick { dialog = true }.padding(horizontal = 14.dp, vertical = 10.dp),
            )
            Spacer(Modifier.navigationBarsPadding())
        }
    }
    if (dialog) ServerDialog(server, { dialog = false; pending = null }) { url ->
        server = url; dialog = false; pending?.invoke(); pending = null
    }
}

/** Ввод адреса сервера с проверкой доступности. */
@Composable
fun ServerDialog(current: String, onDismiss: () -> Unit, onSaved: (String) -> Unit) {
    var text by remember { mutableStateOf(current) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    AlertDialog(
        onDismissRequest = onDismiss, containerColor = Color.White, shape = androidx.compose.foundation.shape.RoundedCornerShape(28.dp),
        title = { Text("Адрес сервера", fontWeight = FontWeight.SemiBold) },
        text = {
            Column {
                PillField(text, { text = it; error = null }, "agents.example.com", keyboard = KeyboardType.Uri)
                Spacer(Modifier.height(8.dp))
                val url = Api.normalizeUrl(text)
                Text(
                    error ?: if (url.startsWith("http://")) "Адрес без HTTPS: пароли и голос пойдут открытым текстом. Используйте только для проверки." else "Адрес вашего сервера Стайки",
                    color = if (error != null) C.Bad else C.Muted, fontSize = 14.sp, lineHeight = 19.sp,
                )
            }
        },
        confirmButton = {
            TextButton(enabled = !busy && text.isNotBlank(), onClick = {
                val url = Api.normalizeUrl(text); val old = Prefs.server
                busy = true; error = null
                scope.launch {
                    Prefs.server = url
                    try {
                        val cfg = Api.config()
                        Repo.googleClientId = cfg.optString("googleClientId")
                        onSaved(url)
                    } catch (e: ApiError) {
                        Prefs.server = old
                        error = if (e.code == "network") "Сервер не отвечает" else e.message
                    }
                    busy = false
                }
            }) { Text(if (busy) "Проверяю…" else "Сохранить", color = C.Ink, fontWeight = FontWeight.SemiBold) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена", color = C.Muted) } },
    )
}

private enum class AuthMode { Login, SignUp, Code, Reset }

/** Контент по центру экрана; если не помещается (клавиатура), прокручивается. */
@Composable
fun CenteredScroll(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    BoxWithConstraints(modifier) {
        val h = maxHeight
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).heightIn(min = h),
            verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally, content = content,
        )
    }
}

@Composable
private fun TextLink(text: String, bold: Boolean = false, onClick: () -> Unit) {
    Text(
        text, color = if (bold) C.Ink else C.Muted, fontSize = 16.sp, fontWeight = if (bold) FontWeight.SemiBold else FontWeight.Normal,
        modifier = Modifier.clip(CircleShape).bounceClick(onClick = onClick).padding(horizontal = 12.dp, vertical = 8.dp),
    )
}

private suspend fun googleIdToken(ctx: android.content.Context, clientId: String): String {
    val option = com.google.android.libraries.identity.googleid.GetGoogleIdOption.Builder()
        .setFilterByAuthorizedAccounts(false).setServerClientId(clientId).setAutoSelectEnabled(false).build()
    val request = androidx.credentials.GetCredentialRequest.Builder().addCredentialOption(option).build()
    val cred = androidx.credentials.CredentialManager.create(ctx).getCredential(ctx, request).credential
    if (cred is androidx.credentials.CustomCredential &&
        cred.type == com.google.android.libraries.identity.googleid.GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL)
        return com.google.android.libraries.identity.googleid.GoogleIdTokenCredential.createFrom(cred.data).idToken
    throw IllegalStateException("unsupported credential")
}

@Composable
fun AuthScreen(startSignUp: Boolean, onBack: () -> Unit, onDone: () -> Unit) {
    var mode by remember { mutableStateOf(if (startSignUp) AuthMode.SignUp else AuthMode.Login) }
    var email by remember { mutableStateOf("") }
    var pass by remember { mutableStateOf("") }
    var show by remember { mutableStateOf(false) }
    var codeSent by remember { mutableStateOf(false) }
    var code by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var serverDialog by remember { mutableStateOf(false) }
    val main = mode == AuthMode.Login || mode == AuthMode.SignUp
    val scope = rememberCoroutineScope()
    val ctx = androidx.compose.ui.platform.LocalContext.current

    fun toMode(m: AuthMode) { mode = m; codeSent = false; code = ""; error = null }

    fun run(block: suspend () -> Unit) {
        if (busy) return
        busy = true; error = null
        scope.launch {
            try { block() } catch (e: ApiError) { error = if (e.code == "network") "Нет связи с сервером" else e.message }
            busy = false
        }
    }
    fun finish(me: Me) { Repo.onLoggedIn(me); onDone() }
    fun emailOk() = email.contains('@') && email.contains('.')

    fun submit() {
        if (!emailOk()) { error = "Введите почту"; return }
        when (mode) {
            AuthMode.Login -> run { finish(Api.login(email, pass)) }
            AuthMode.SignUp -> { if (pass.length < 8) { error = "Пароль не короче 8 символов"; return }; run { finish(Api.register(email, pass)) } }
            AuthMode.Code -> if (!codeSent) run { Api.requestCode(email); codeSent = true } else run { finish(Api.codeLogin(email, code)) }
            AuthMode.Reset -> if (!codeSent) run { Api.forgot(email); codeSent = true } else {
                if (pass.length < 8) { error = "Пароль не короче 8 символов"; return }
                run { Api.resetPassword(email, code, pass); toMode(AuthMode.Login); Repo.say("Пароль изменён, войдите") }
            }
        }
    }

    fun google() {
        if (Repo.googleClientId.isBlank()) { error = "Вход через Google не настроен на сервере"; return }
        run {
            val token = try { googleIdToken(ctx, Repo.googleClientId) } catch (e: Exception) { error = "Вход через Google отменён или недоступен"; return@run }
            finish(Api.google(token))
        }
    }

    Column(Modifier.fillMaxSize().background(Color.White).imePadding()) {
        Row(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 16.dp, vertical = 8.dp)) {
            BackPill { if (main) onBack() else toMode(AuthMode.Login) }
        }
        CenteredScroll(Modifier.weight(1f).padding(horizontal = 24.dp)) {
            Text(
                when (mode) { AuthMode.Login -> "Вход"; AuthMode.SignUp -> "Регистрация"; AuthMode.Code -> "Вход по коду"; AuthMode.Reset -> "Сброс пароля" },
                style = MaterialTheme.typography.headlineMedium, textAlign = TextAlign.Center,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                when (mode) {
                    AuthMode.Login -> "С возвращением"
                    AuthMode.SignUp -> "Пара минут, и первый агент готов"
                    AuthMode.Code -> if (codeSent) "Код отправлен на $email" else "Пришлём одноразовый код на почту"
                    AuthMode.Reset -> if (codeSent) "Введите код из письма и новый пароль" else "Пришлём код для нового пароля"
                },
                color = C.Muted, fontSize = 17.sp, textAlign = TextAlign.Center,
            )
            Spacer(Modifier.height(28.dp))

            if (!codeSent) PillField(email, { email = it; error = null }, "Почта", keyboard = KeyboardType.Email)
            if (main || (mode == AuthMode.Reset && codeSent)) {
                if (mode == AuthMode.Reset) PillField(code, { if (it.length <= 6 && it.all(Char::isDigit)) code = it }, "6-значный код", keyboard = KeyboardType.NumberPassword)
                Spacer(Modifier.height(10.dp))
                PillField(
                    pass, { pass = it; error = null }, if (mode == AuthMode.Reset) "Новый пароль" else "Пароль", password = !show, keyboard = KeyboardType.Password,
                    trailing = { IconButton({ show = !show }) { Icon(if (show) Icons.Outlined.VisibilityOff else Icons.Outlined.Visibility, null, tint = C.Muted) } },
                )
            }
            if (mode == AuthMode.Code && codeSent) PillField(code, { if (it.length <= 6 && it.all(Char::isDigit)) code = it }, "6-значный код", keyboard = KeyboardType.NumberPassword)

            AnimatedVisibility(error != null) {
                Text(error.orEmpty(), color = C.Bad, fontSize = 15.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 12.dp))
            }
            Spacer(Modifier.height(18.dp))
            BlackButton(
                if (busy) "Подождите…" else when (mode) {
                    AuthMode.Login -> "Войти"; AuthMode.SignUp -> "Создать аккаунт"
                    AuthMode.Code -> if (codeSent) "Подтвердить" else "Отправить код"
                    AuthMode.Reset -> if (codeSent) "Сменить пароль" else "Отправить код"
                },
                { submit() }, enabled = !busy,
            )
            if (main) {
                Spacer(Modifier.height(10.dp))
                GrayButton("Продолжить с Google", { google() }, leading = { Text("G", color = C.Blue, fontWeight = FontWeight.Bold, fontSize = 20.sp) })
                Spacer(Modifier.height(14.dp))
                Row(horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                    if (mode == AuthMode.Login) TextLink("Забыли пароль?") { toMode(AuthMode.Reset) }
                    TextLink("По коду из письма") { toMode(AuthMode.Code) }
                }
                TextLink(if (mode == AuthMode.Login) "Нет аккаунта? Регистрация" else "Уже есть аккаунт? Войти", bold = true) {
                    toMode(if (mode == AuthMode.Login) AuthMode.SignUp else AuthMode.Login)
                }
                TextLink("Сервер: " + Prefs.server.removePrefix("https://").removePrefix("http://")) { serverDialog = true }
            }
        }
    }
    if (serverDialog) ServerDialog(Prefs.server, { serverDialog = false }) { serverDialog = false }
}
