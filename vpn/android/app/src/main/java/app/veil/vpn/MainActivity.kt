package app.veil.vpn

import android.app.Activity
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.animation.core.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.wireguard.android.backend.GoBackend
import com.wireguard.android.backend.Tunnel

private val Muted = Color(0xFF8A8A8A)
private val Danger = Color(0xFFE5656F)
private val Card = Color(0xCC0E0E0E)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = androidx.activity.SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = androidx.activity.SystemBarStyle.dark(android.graphics.Color.TRANSPARENT)
        )
        Vpn.init(this)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = Color.White, background = Color.Black, surface = Color(0xFF111111))) {
                Home()
            }
        }
    }
}

@Composable
fun Home() {
    val ctx = LocalContext.current
    val state by Vpn.state.collectAsState()
    val busy by Vpn.busy.collectAsState()
    val error by Vpn.error.collectAsState()
    val endpoint by Vpn.endpoint.collectAsState()
    var showImport by remember { mutableStateOf(false) }
    val up = state == Tunnel.State.UP

    LaunchedEffect(up) { FxLevel.level = if (up) 0.25f else 0f }

    val permLauncher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        if (it.resultCode == Activity.RESULT_OK) Vpn.connect()
    }
    val toggle = {
        if (endpoint == null) showImport = true
        else if (up) Vpn.disconnect()
        else {
            val i = GoBackend.VpnService.prepare(ctx)
            if (i != null) permLauncher.launch(i) else Vpn.connect()
        }
    }

    Box(Modifier.fillMaxSize().background(Color.Black)) {
        Backdrop()
        FlagBanner(Modifier.fillMaxWidth().height(380.dp))
        Column(Modifier.fillMaxSize().systemBarsPadding().padding(horizontal = 24.dp)) {
            Spacer(Modifier.height(28.dp))
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.clip(RoundedCornerShape(50)).border(BorderStroke(1.dp, Color(0x66FFFFFF)), RoundedCornerShape(50))
                        .padding(horizontal = 16.dp, vertical = 7.dp)
                ) { Text(if (up) "ON" else "OFF", color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.Medium) }
                Spacer(Modifier.weight(1f))
                PowerButton(up = up, busy = busy, onClick = { if (!busy) toggle() })
            }
            Spacer(Modifier.height(36.dp))
            Text("Amsterdam", color = Color.White, fontSize = 40.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(6.dp))
            Text(
                error ?: endpoint?.substringBeforeLast(":") ?: "—",
                color = if (error != null) Danger else Color(0xFFBDBDBD), fontSize = 16.sp
            )
            Spacer(Modifier.height(40.dp))
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Card)
                    .border(BorderStroke(1.dp, Color(0x22FFFFFF)), RoundedCornerShape(18.dp))
                    .clickable { showImport = true }.padding(horizontal = 16.dp, vertical = 14.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                NlFlag(Modifier.size(40.dp))
                Spacer(Modifier.width(16.dp))
                Text("Amsterdam", color = Color.White, fontSize = 20.sp, modifier = Modifier.weight(1f))
                Text("›", color = Muted, fontSize = 26.sp)
            }
        }
    }

    if (showImport) ImportDialog(onDismiss = { showImport = false })
}

/** Чёткий флаг Нидерландов (три равные полосы), приглушён и растворяется в чёрном только внизу. */
@Composable
private fun FlagBanner(modifier: Modifier) {
    Canvas(modifier) {
        val h = size.height / 3
        drawRect(Color(0xFFAE1C28).copy(alpha = 0.62f), Offset.Zero, Size(size.width, h))
        drawRect(Color.White.copy(alpha = 0.34f), Offset(0f, h), Size(size.width, h))
        drawRect(Color(0xFF21468B).copy(alpha = 0.66f), Offset(0f, 2 * h), Size(size.width, h))
        drawRect(
            Brush.verticalGradient(
                0.00f to Color(0x40000000),
                0.55f to Color(0x40000000),
                1.00f to Color.Black
            ),
            Offset.Zero, size
        )
    }
}

@Composable
private fun NlFlag(modifier: Modifier) {
    Canvas(modifier.clip(CircleShape).border(1.dp, Color(0x44FFFFFF), CircleShape)) {
        val h = size.height / 3
        drawRect(Color(0xFFAE1C28), Offset.Zero, Size(size.width, h))
        drawRect(Color.White, Offset(0f, h), Size(size.width, h))
        drawRect(Color(0xFF21468B), Offset(0f, 2 * h), Size(size.width, h))
    }
}

@Composable
private fun PowerButton(up: Boolean, busy: Boolean, onClick: () -> Unit) {
    val spin by rememberInfiniteTransition(label = "s").animateFloat(
        0f, 360f, infiniteRepeatable(tween(1000, easing = LinearEasing)), label = "r"
    )
    Box(Modifier.size(84.dp), contentAlignment = Alignment.Center) {
        Box(
            Modifier.size(68.dp).clip(CircleShape)
                .background(if (up) Color.White else Color(0xFF1A1A1A))
                .border(1.dp, Color(0x55FFFFFF), CircleShape)
                .clickable(onClick = onClick),
            contentAlignment = Alignment.Center
        ) {
            Canvas(Modifier.size(28.dp)) {
                val c = if (up) Color.Black else Color.White
                val w = 3.5.dp.toPx()
                drawArc(c, -60f, 300f, false, Offset(w, w), Size(size.width - 2 * w, size.height - 2 * w), style = Stroke(w, cap = StrokeCap.Round))
                drawLine(c, Offset(size.width / 2, 0f), Offset(size.width / 2, size.height * 0.5f), w, StrokeCap.Round)
            }
        }
        if (busy) Canvas(Modifier.size(82.dp)) {
            drawArc(Color.White, spin, 90f, false, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round))
        }
    }
}

@Composable
private fun ImportDialog(onDismiss: () -> Unit) {
    val ctx = LocalContext.current
    val clip = LocalClipboardManager.current
    var text by remember { mutableStateOf("") }
    var err by remember { mutableStateOf<String?>(null) }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) runCatching {
            text = ctx.contentResolver.openInputStream(uri)!!.bufferedReader().readText()
        }.onFailure { err = "Не удалось прочитать файл" }
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Color(0xFF111111),
        title = { Text("Сервер", color = Color.White) },
        text = {
            Column {
                OutlinedTextField(
                    value = text, onValueChange = { text = it; err = null },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 120.dp, max = 220.dp),
                    isError = err != null, placeholder = { Text("vpn://…") }
                )
                err?.let { Text(it, color = Danger, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp)) }
                Row(Modifier.padding(top = 8.dp)) {
                    TextButton(onClick = { clip.getText()?.text?.let { text = it; err = null } }) { Text("Вставить", color = Color.White) }
                    TextButton(onClick = { picker.launch(arrayOf("*/*")) }) { Text("Из файла", color = Color.White) }
                }
            }
        },
        confirmButton = {
            Button(onClick = {
                runCatching { Vpn.save(text) }
                    .onSuccess { onDismiss() }
                    .onFailure { err = "Неверная конфигурация: ${it.message}" }
            }, colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = Color.Black)) { Text("Сохранить") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена", color = Muted) } }
    )
}
