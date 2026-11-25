package app.staika

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Visibility
import androidx.compose.material.icons.outlined.VisibilityOff
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
    LaunchedEffect(Unit) { delay(120); up = true }
    val a by animateFloatAsState(if (up) 1f else 0f, tween(600, easing = EaseOutCubic), label = "welcome")
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
            Text(
                "Ваша команда агентов,\nкоторые доводят дело до конца.",
                color = C.Muted, textAlign = TextAlign.Center, fontSize = 19.sp, lineHeight = 26.sp,
            )
            Spacer(Modifier.weight(1.1f))
            BlackButton("Войти", onLogin)
            Spacer(Modifier.height(10.dp))
            GrayButton("Регистрация", onSignUp)
            Spacer(Modifier.height(14.dp))
            Spacer(Modifier.navigationBarsPadding())
        }
    }
}

private enum class AuthMode { Login, SignUp, Code, Reset }

@Composable
fun AuthScreen(startSignUp: Boolean, onBack: () -> Unit, onDone: () -> Unit) {
    var mode by remember { mutableStateOf(if (startSignUp) AuthMode.SignUp else AuthMode.Login) }
    var email by remember { mutableStateOf("") }
    var pass by remember { mutableStateOf("") }
    var show by remember { mutableStateOf(false) }
    var codeSent by remember { mutableStateOf(false) }
    var code by remember { mutableStateOf("") }
    var resetSent by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().background(Color.White).imePadding()) {
        ScreenTop("", if (mode == AuthMode.Login || mode == AuthMode.SignUp) onBack else {{ mode = AuthMode.Login; codeSent = false; resetSent = false }})
        Column(
            Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 24.dp),
        ) {
            Text(
                when (mode) {
                    AuthMode.Login -> "С возвращением"; AuthMode.SignUp -> "Создайте аккаунт"
                    AuthMode.Code -> "Вход по коду"; AuthMode.Reset -> "Сброс пароля"
                },
                style = MaterialTheme.typography.headlineMedium,
            )
            Spacer(Modifier.height(6.dp))
            Text(
                when (mode) {
                    AuthMode.Login -> "Войдите, чтобы вернуться к команде."
                    AuthMode.SignUp -> "Пара минут, и первый агент готов."
                    AuthMode.Code -> if (codeSent) "Мы отправили 6-значный код на $email" else "Пришлём одноразовый код на почту."
                    AuthMode.Reset -> if (resetSent) "Письмо со ссылкой отправлено на $email" else "Введите почту, пришлём ссылку для нового пароля."
                },
                color = C.Muted, style = MaterialTheme.typography.bodyLarge,
            )
            Spacer(Modifier.height(24.dp))

            if (mode == AuthMode.Login || mode == AuthMode.SignUp) {
                GrayButton("Продолжить с Google", onDone, leading = {
                    Text("G", color = C.Blue, fontWeight = FontWeight.Bold, fontSize = 20.sp)
                })
                Spacer(Modifier.height(18.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    HorizontalDivider(Modifier.weight(1f), color = C.Line)
                    Text("  или по почте  ", color = C.Muted, fontSize = 13.sp)
                    HorizontalDivider(Modifier.weight(1f), color = C.Line)
                }
                Spacer(Modifier.height(18.dp))
            }

            if (!(mode == AuthMode.Code && codeSent) && !(mode == AuthMode.Reset && resetSent)) {
                PillField(email, { email = it }, "Почта", keyboard = KeyboardType.Email)
            }
            if (mode == AuthMode.Login || mode == AuthMode.SignUp) {
                Spacer(Modifier.height(12.dp))
                PillField(
                    pass, { pass = it }, "Пароль", password = !show, keyboard = KeyboardType.Password,
                    trailing = {
                        IconButton({ show = !show }) {
                            Icon(if (show) Icons.Outlined.VisibilityOff else Icons.Outlined.Visibility, null, tint = C.Muted)
                        }
                    },
                )
            }
            if (mode == AuthMode.Code && codeSent) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    repeat(6) { i ->
                        Box(
                            Modifier.weight(1f).height(56.dp).clip(androidx.compose.foundation.shape.RoundedCornerShape(16.dp))
                                .background(C.Bubble), Alignment.Center,
                        ) { Text(code.getOrNull(i)?.toString() ?: "", fontSize = 22.sp, fontWeight = FontWeight.SemiBold) }
                    }
                }
                Spacer(Modifier.height(12.dp))
                PillField(code, { if (it.length <= 6 && it.all(Char::isDigit)) code = it }, "Введите код", keyboard = KeyboardType.NumberPassword)
                Spacer(Modifier.height(8.dp))
                Text("Отправить код ещё раз", color = C.Muted, modifier = Modifier.clickable { }.padding(8.dp))
            }
            if (mode == AuthMode.Login) {
                Spacer(Modifier.height(8.dp))
                Text("Забыли пароль?", color = C.Muted, modifier = Modifier.clickable { mode = AuthMode.Reset }.padding(8.dp))
            }

            Spacer(Modifier.height(20.dp))
            val label = when (mode) {
                AuthMode.Login -> "Войти"; AuthMode.SignUp -> "Создать аккаунт"
                AuthMode.Code -> if (codeSent) "Подтвердить" else "Отправить код"
                AuthMode.Reset -> if (resetSent) "Вернуться ко входу" else "Отправить ссылку"
            }
            BlackButton(label, {
                when (mode) {
                    AuthMode.Login, AuthMode.SignUp -> onDone()
                    AuthMode.Code -> if (!codeSent) codeSent = true else onDone()
                    AuthMode.Reset -> if (!resetSent) resetSent = true else { mode = AuthMode.Login; resetSent = false }
                }
            })
            Spacer(Modifier.height(12.dp))
            if (mode == AuthMode.Login || mode == AuthMode.SignUp) {
                GrayButton("Войти по коду из письма", { mode = AuthMode.Code; codeSent = false })
                Spacer(Modifier.height(18.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                    Text(if (mode == AuthMode.Login) "Нет аккаунта? " else "Уже есть аккаунт? ", color = C.Muted)
                    Text(
                        if (mode == AuthMode.Login) "Регистрация" else "Войти", fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.clickable { mode = if (mode == AuthMode.Login) AuthMode.SignUp else AuthMode.Login },
                    )
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}
