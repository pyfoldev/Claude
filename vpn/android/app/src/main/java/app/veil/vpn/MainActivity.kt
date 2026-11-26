package app.veil.vpn

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.wireguard.android.backend.GoBackend
import com.wireguard.android.backend.Tunnel

private val Bg = Color(0xFF0B0F1A)
private val Surface = Color(0xFF131A2B)
private val Accent = Color(0xFF3DDC97)
private val Blue = Color(0xFF4C7DFF)
private val Muted = Color(0xFF7C88A6)
private val Danger = Color(0xFFFF5C6C)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Vpn.init(this)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = Accent, background = Bg, surface = Surface)) {
                Home()
            }
        }
    }
}

private fun fmtBytes(b: Long): String = when {
    b < 1024 -> "$b Б"
    b < 1024 * 1024 -> "%.1f КБ".format(b / 1024.0)
    b < 1024L * 1024 * 1024 -> "%.1f МБ".format(b / 1048576.0)
    else -> "%.2f ГБ".format(b / 1073741824.0)
}

private fun fmtTime(ms: Long): String {
    val s = ms / 1000
    return "%02d:%02d:%02d".format(s / 3600, s % 3600 / 60, s % 60)
}

@Composable
fun Home() {
    val ctx = LocalContext.current
    val state by Vpn.state.collectAsState()
    val busy by Vpn.busy.collectAsState()
    val error by Vpn.error.collectAsState()
    val rx by Vpn.rx.collectAsState()
    val tx by Vpn.tx.collectAsState()
    val since by Vpn.since.collectAsState()
    val endpoint by Vpn.endpoint.collectAsState()
    var showImport by remember { mutableStateOf(false) }
    val up = state == Tunnel.State.UP

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

    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(up) { while (up) { now = System.currentTimeMillis(); kotlinx.coroutines.delay(1000) } }

    Box(
        Modifier.fillMaxSize()
            .background(Brush.verticalGradient(listOf(Bg, Color(0xFF101830))))
            .systemBarsPadding().padding(horizontal = 24.dp)
    ) {
        Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally) {
            Row(Modifier.fillMaxWidth().padding(top = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Veil", color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                    Text("WireGuard · без логов", color = Muted, fontSize = 13.sp)
                }
                TextButton(onClick = { showImport = true }) { Text("Сервер", color = Accent) }
            }

            Spacer(Modifier.weight(1f))
            PowerButton(up = up, busy = busy, onClick = { if (!busy) toggle() })
            Spacer(Modifier.height(28.dp))
            Text(
                when { busy -> "Подождите…"; up -> "Защищено"; else -> "Не защищено" },
                color = if (up) Accent else Color.White, fontSize = 28.sp, fontWeight = FontWeight.SemiBold
            )
            Spacer(Modifier.height(6.dp))
            Text(
                error ?: if (endpoint == null) "Добавьте сервер, чтобы начать" else if (up) "Весь трафик идёт через ваш сервер" else "Нажмите, чтобы подключиться",
                color = if (error != null) Danger else Muted, fontSize = 14.sp, textAlign = TextAlign.Center
            )
            Spacer(Modifier.weight(1f))

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Stat("Загрузка", fmtBytes(rx), Blue, Modifier.weight(1f))
                Stat("Отдача", fmtBytes(tx), Accent, Modifier.weight(1f))
                Stat("Время", if (up && since > 0) fmtTime(now - since) else "--:--:--", Color.White, Modifier.weight(1f))
            }
            Spacer(Modifier.height(12.dp))
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Surface)
                    .clickable { showImport = true }.padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(Modifier.size(10.dp).clip(CircleShape).background(if (up) Accent else Muted))
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("Сервер", color = Muted, fontSize = 12.sp)
                    Text(endpoint ?: "не настроен", color = Color.White, fontSize = 16.sp)
                }
                Text("Изменить", color = Accent, fontSize = 14.sp)
            }
            TextButton(
                onClick = { ctx.startActivity(Intent(Settings.ACTION_VPN_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) },
                modifier = Modifier.padding(bottom = 8.dp)
            ) { Text("Kill switch: «Блокировать соединения без VPN»", color = Muted, fontSize = 12.sp) }
        }
    }

    if (showImport) ImportDialog(onDismiss = { showImport = false })
}

@Composable
private fun PowerButton(up: Boolean, busy: Boolean, onClick: () -> Unit) {
    val t = rememberInfiniteTransition(label = "pulse")
    val pulse by t.animateFloat(1f, 1.18f, infiniteRepeatable(tween(1600, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "p")
    val spin by t.animateFloat(0f, 360f, infiniteRepeatable(tween(1100, easing = LinearEasing)), label = "s")
    val color by animateColorAsState(if (up) Accent else Color(0xFF2A3350), label = "c")
    Box(Modifier.size(260.dp), contentAlignment = Alignment.Center) {
        Box(
            Modifier.size(220.dp).scale(if (up) pulse else 1f).alpha(if (up) 0.18f else 0.08f)
                .clip(CircleShape).background(color)
        )
        Box(
            Modifier.size(180.dp).clip(CircleShape)
                .background(Brush.linearGradient(if (up) listOf(Accent, Color(0xFF1FA67A)) else listOf(Color(0xFF232C47), Color(0xFF181F36))))
                .clickable(onClick = onClick),
            contentAlignment = Alignment.Center
        ) {
            androidx.compose.foundation.Canvas(Modifier.size(72.dp)) {
                val c = if (up) Bg else Color.White
                val w = 9.dp.toPx()
                drawArc(c, -60f, 300f, false, Offset(w, w), Size(size.width - 2 * w, size.height - 2 * w), style = Stroke(w, cap = StrokeCap.Round))
                drawLine(c, Offset(size.width / 2, 0f), Offset(size.width / 2, size.height * 0.5f), w, StrokeCap.Round)
            }
        }
        if (busy) androidx.compose.foundation.Canvas(Modifier.size(204.dp)) {
            drawArc(Accent, spin, 90f, false, style = Stroke(6.dp.toPx(), cap = StrokeCap.Round))
        }
    }
}

@Composable
private fun Stat(label: String, value: String, color: Color, modifier: Modifier) {
    Column(modifier.clip(RoundedCornerShape(18.dp)).background(Surface).padding(14.dp)) {
        Text(label, color = Muted, fontSize = 12.sp)
        Spacer(Modifier.height(4.dp))
        Text(value, color = color, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
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
        containerColor = Surface,
        title = { Text("Добавить сервер", color = Color.White) },
        text = {
            Column {
                Text("Вставьте ссылку vpn://… или содержимое .conf, которое выдал сервер (vpnctl add).", color = Muted, fontSize = 13.sp)
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = text, onValueChange = { text = it; err = null },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 120.dp, max = 220.dp),
                    isError = err != null, placeholder = { Text("vpn://…") }
                )
                err?.let { Text(it, color = Danger, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp)) }
                Row(Modifier.padding(top = 8.dp)) {
                    TextButton(onClick = { clip.getText()?.text?.let { text = it; err = null } }) { Text("Вставить") }
                    TextButton(onClick = { picker.launch(arrayOf("*/*")) }) { Text("Из файла") }
                }
            }
        },
        confirmButton = {
            Button(onClick = {
                runCatching { Vpn.save(text) }
                    .onSuccess { onDismiss() }
                    .onFailure { err = "Неверная конфигурация: ${it.message}" }
            }, colors = ButtonDefaults.buttonColors(containerColor = Accent, contentColor = Bg)) { Text("Сохранить") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена", color = Muted) } }
    )
}
