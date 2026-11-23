package openagent.app.com

import android.annotation.SuppressLint
import android.app.Activity
import android.graphics.Color as AColor
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.credentials.*
import androidx.credentials.exceptions.GetCredentialCancellationException
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import kotlinx.coroutines.launch

@Composable
fun Orb(size: androidx.compose.ui.unit.Dp, level: Float = 0f, pulse: Boolean = true) = LiveOrb(size, level, OrbState.Idle)

@Composable
fun LoginScreen(vm: AppVM) {
    var email by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var captchaOpen by remember { mutableStateOf(false) }
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val needCaptcha = vm.authConfig.captchaUrl != null

    Column(Modifier.fillMaxSize().padding(horizontal = 28.dp).systemBarsPadding().imePadding(),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        var shown by remember { mutableStateOf(false) }
        LaunchedEffect(Unit) { shown = true }
        AnimatedVisibility(shown, enter = fadeIn(tween(900)) + scaleIn(tween(900), initialScale = 0.8f)) { AppLogo(124.dp) }
        Spacer(Modifier.height(28.dp))
        AnimatedVisibility(shown, enter = fadeIn(tween(900, 250)) + slideInVertically(tween(900, 250)) { it / 3 }) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text("OpenAgent", color = C.text, fontSize = 32.sp, fontWeight = FontWeight.SemiBold)
                Text("ИИ-агент на вашем сервере", color = C.dim, fontSize = 15.sp, modifier = Modifier.padding(top = 6.dp))
            }
        }
        Spacer(Modifier.height(40.dp))

        AnimatedContent(vm.codeSent, transitionSpec = { (fadeIn(tween(350)) + slideInHorizontally(tween(350)) { it / 4 }) togetherWith (fadeOut(tween(200))) }, label = "step") { sent ->
            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
                if (!sent) {
                    OutlinedTextField(email, { email = it }, singleLine = true, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(28.dp),
                        placeholder = { Text("E-mail", color = C.dim) }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email), colors = fieldColors())
                    Spacer(Modifier.height(12.dp))
                    AnimatedVisibility(captchaOpen && needCaptcha) {
                        Box(Modifier.fillMaxWidth().height(96.dp).padding(bottom = 12.dp), contentAlignment = Alignment.Center) {
                            CaptchaView(vm.authConfig.captchaUrl!!) { token -> captchaOpen = false; vm.sendCode(email, token) }
                        }
                    }
                    PrimaryButton("Продолжить", enabled = email.contains("@") && !vm.authBusy, busy = vm.authBusy) {
                        if (needCaptcha) captchaOpen = true else vm.sendCode(email, null)
                    }
                    Spacer(Modifier.height(10.dp))
                    OutlinedButton({
                        scope.launch {
                            try {
                                val opt = GetGoogleIdOption.Builder().setFilterByAuthorizedAccounts(false)
                                    .setServerClientId(vm.authConfig.googleClientId ?: BuildConfig.GOOGLE_WEB_CLIENT_ID).build()
                                val r = CredentialManager.create(ctx).getCredential(ctx as Activity, GetCredentialRequest.Builder().addCredentialOption(opt).build())
                                vm.google(GoogleIdTokenCredential.createFrom(r.credential.data).idToken)
                            } catch (e: GetCredentialCancellationException) {
                            } catch (e: Exception) { vm.authFail("Google: ${e.message}") }
                        }
                    }, Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(28.dp), border = BorderStroke(1.dp, C.outline)) {
                        GoogleG(24.dp); Spacer(Modifier.width(12.dp))
                        Text("Войти через Google", color = C.text, fontSize = 17.sp, fontWeight = FontWeight.Medium)
                    }
                } else {
                    Text("Код отправлен на $email", color = C.dim, textAlign = TextAlign.Center)
                    Spacer(Modifier.height(14.dp))
                    OutlinedTextField(code, { if (it.length <= 6) code = it.filter(Char::isDigit) }, singleLine = true, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(28.dp),
                        placeholder = { Text("000000", color = C.dim) }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword), colors = fieldColors(),
                        textStyle = androidx.compose.ui.text.TextStyle(fontSize = 24.sp, letterSpacing = 8.sp, textAlign = TextAlign.Center, color = C.text))
                    Spacer(Modifier.height(12.dp))
                    PrimaryButton("Войти", enabled = code.length == 6 && !vm.authBusy, busy = vm.authBusy) { vm.verify(email, code) }
                    TextButton({ vm.codeSent = false; code = "" }) { Text("Изменить e-mail", color = C.dim) }
                }
            }
        }
        AnimatedVisibility(vm.authError != null) {
            Text(vm.authError.orEmpty(), color = C.danger, fontSize = 14.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 14.dp))
        }
    }
}

@Composable
fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = C.accent, unfocusedBorderColor = C.outline, cursorColor = C.accent,
    focusedTextColor = C.text, unfocusedTextColor = C.text, focusedContainerColor = C.surface2, unfocusedContainerColor = C.surface2,
)

@Composable
fun PrimaryButton(text: String, enabled: Boolean = true, busy: Boolean = false, onClick: () -> Unit) {
    Button(onClick, enabled = enabled, modifier = Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(28.dp),
        colors = ButtonDefaults.buttonColors(containerColor = C.accent, contentColor = androidx.compose.ui.graphics.Color.Black, disabledContainerColor = C.surface2, disabledContentColor = C.dim)) {
        if (busy) CircularProgressIndicator(Modifier.size(20.dp), color = C.dim, strokeWidth = 2.dp) else Text(text, fontSize = 16.sp, fontWeight = FontWeight.Medium)
    }
}

@SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
@Composable
fun CaptchaView(url: String, onToken: (String) -> Unit) {
    AndroidView(factory = { c ->
        WebView(c).apply {
            setBackgroundColor(AColor.BLACK)
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            webViewClient = WebViewClient()
            addJavascriptInterface(object {
                @JavascriptInterface fun onToken(t: String) { post { onToken(t) } }
                @JavascriptInterface fun onExpired() {}
                @JavascriptInterface fun onError() {}
            }, "Android")
            loadUrl(url)
        }
    }, modifier = Modifier.fillMaxSize(), onRelease = { it.destroy() })
}
