package app.staika

import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Visibility
import androidx.compose.material.icons.rounded.VisibilityOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
private fun Floaty(pal: Pal, size: Int, x: Float, y: Float, phase: Int, rot: Float) {
    val t = rememberInfiniteTransition(label = "f")
    val dy by t.animateFloat(
        -10f, 10f, infiniteRepeatable(tween(2400 + phase * 300, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "dy",
    )
    BoxWithConstraints(Modifier.fillMaxSize()) {
        Avatar(
            pal, size.dp,
            Modifier.offset(x = maxWidth * x - (size / 2).dp, y = maxHeight * y + dy.dp).rotate(rot),
            shape = androidx.compose.foundation.shape.RoundedCornerShape(size.dp * 0.32f),
        )
    }
}

@Composable
fun WelcomeScreen(onLogin: () -> Unit, onSignUp: () -> Unit) {
    Box(Modifier.fillMaxSize().background(Color.White)) {
        Floaty(Pal.Cloud, 84, 0.22f, 0.10f, 0, -6f)
        Floaty(Pal.Star, 76, 0.78f, 0.20f, 1, 8f)
        Floaty(Pal.Fire, 70, 0.10f, 0.52f, 2, -10f)
        Floaty(Pal.Jelly, 88, 0.86f, 0.55f, 3, 6f)
        Floaty(Pal.Bunny, 74, 0.52f, 0.69f, 4, -4f)
        Column(
            Modifier.fillMaxSize().padding(horizontal = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.weight(1.1f))
            Text("Стайка", style = MaterialTheme.typography.headlineLarge, fontSize = 40.sp)
            Spacer(Modifier.height(8.dp))
            Text(
                "Ваша команда ИИ-агентов,\nкоторые доводят дела до конца.",
                color = C.Muted, textAlign = TextAlign.Center, style = MaterialTheme.typography.bodyLarge,
            )
            Spacer(Modifier.weight(1.4f))
            BlackButton("Войти", onLogin)
            Spacer(Modifier.height(12.dp))
            GrayButton("Регистрация", onSignUp)
            Spacer(Modifier.height(28.dp).navigationBarsPadding())
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
                            Icon(if (show) Icons.Rounded.VisibilityOff else Icons.Rounded.Visibility, null, tint = C.Muted)
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
