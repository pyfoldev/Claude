package ai.chip.app

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun ChatScreen(vm: ChatViewModel) {
    var showSettings by remember { mutableStateOf(false) }
    var confirmClear by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()

    LaunchedEffect(vm.messages.size, vm.thinking) {
        val n = vm.messages.size + if (vm.thinking) 1 else 0
        if (n > 0) listState.animateScrollToItem(n - 1)
    }

    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).imePadding()) {
        TopBar(vm.thinking, onSettings = { showSettings = true }, onClear = { confirmClear = true })
        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(vm.messages, key = { it.id }) { MessageRow(it) }
            if (vm.thinking) item(key = "thinking") { ThinkingRow() }
            if (vm.offlineHint) item(key = "hint") {
                Text(
                    "Chip сейчас работает без river.ai: проверьте ключ в настройках.",
                    fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp),
                )
            }
        }
        InputBar(enabled = !vm.thinking, onSend = vm::send)
    }

    if (showSettings) SettingsDialog(vm.settings, onDismiss = { showSettings = false }) { vm.saveSettings(it); showSettings = false }
    if (confirmClear) AlertDialog(
        onDismissRequest = { confirmClear = false },
        title = { Text("Очистить чат?") },
        text = { Text("Вся переписка с Chip будет удалена.") },
        confirmButton = { TextButton(onClick = { vm.clear(); confirmClear = false }) { Text("Очистить") } },
        dismissButton = { TextButton(onClick = { confirmClear = false }) { Text("Отмена") } },
    )
}

@Composable
private fun TopBar(thinking: Boolean, onSettings: () -> Unit, onClear: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).statusBarsPadding()
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Image(painterResource(R.drawable.chip_avatar), null, Modifier.size(42.dp).clip(CircleShape))
        Column(Modifier.weight(1f).padding(start = 12.dp)) {
            Text("Chip", fontSize = 18.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurface)
            Text(if (thinking) "думает…" else "онлайн", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        IconButton(onClick = onClear) { Icon(Icons.Filled.Delete, "Очистить чат", tint = MaterialTheme.colorScheme.onSurfaceVariant) }
        IconButton(onClick = onSettings) { Icon(Icons.Filled.Settings, "Настройки", tint = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

@Composable
private fun MessageRow(m: Message) {
    if (m.fromUser) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            Text(
                m.text, color = MaterialTheme.colorScheme.onPrimary, fontSize = 16.sp,
                modifier = Modifier.widthIn(max = 300.dp)
                    .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(20.dp, 20.dp, 6.dp, 20.dp))
                    .padding(horizontal = 14.dp, vertical = 9.dp),
            )
        }
    } else {
        val e = Emotions.byId(m.emotionId)
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.Start, verticalArrangement = Arrangement.spacedBy(6.dp)) {
            VideoCircle(e.clip, 200.dp)
            if (m.emojis.isNotBlank()) Text(
                m.emojis, fontSize = 26.sp,
                modifier = Modifier.background(MaterialTheme.colorScheme.surface, RoundedCornerShape(20.dp, 20.dp, 20.dp, 6.dp))
                    .padding(horizontal = 12.dp, vertical = 4.dp),
            )
        }
    }
}

@Composable
private fun ThinkingRow() {
    val t = rememberInfiniteTransition(label = "dots")
    Row(
        Modifier.background(MaterialTheme.colorScheme.surface, RoundedCornerShape(20.dp, 20.dp, 20.dp, 6.dp)).padding(horizontal = 16.dp, vertical = 14.dp),
        horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        repeat(3) { i ->
            val a by t.animateFloat(0.25f, 1f, infiniteRepeatable(tween(500, delayMillis = i * 160), RepeatMode.Reverse), label = "d$i")
            Box(Modifier.size(8.dp).alpha(a).background(MaterialTheme.colorScheme.onSurfaceVariant, CircleShape))
        }
    }
}

@Composable
private fun InputBar(enabled: Boolean, onSend: (String) -> Unit) {
    var text by remember { mutableStateOf("") }
    fun submit() { if (text.isNotBlank()) { onSend(text); text = "" } }
    Row(
        Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).navigationBarsPadding().padding(horizontal = 10.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        OutlinedTextField(
            value = text, onValueChange = { text = it },
            modifier = Modifier.weight(1f),
            placeholder = { Text("Напишите Chip…") },
            shape = RoundedCornerShape(24.dp), maxLines = 4,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = { submit() }),
        )
        Spacer(Modifier.size(8.dp))
        IconButton(
            onClick = { submit() }, enabled = enabled && text.isNotBlank(),
            modifier = Modifier.size(48.dp).background(
                if (enabled && text.isNotBlank()) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant, CircleShape),
        ) { Icon(Icons.AutoMirrored.Filled.Send, "Отправить", tint = MaterialTheme.colorScheme.onPrimary) }
    }
}

@Composable
private fun SettingsDialog(s: RiverSettings, onDismiss: () -> Unit, onSave: (RiverSettings) -> Unit) {
    var url by remember { mutableStateOf(s.baseUrl) }
    var key by remember { mutableStateOf(s.apiKey) }
    var model by remember { mutableStateOf(s.model) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("river.ai") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Chip отправляет в river.ai ваше сообщение и получает название эмоции. Без ключа он отвечает по словам, без интернета.", fontSize = 13.sp)
                OutlinedTextField(url, { url = it }, label = { Text("Адрес API") }, singleLine = true)
                OutlinedTextField(key, { key = it }, label = { Text("API-ключ") }, singleLine = true, visualTransformation = PasswordVisualTransformation())
                OutlinedTextField(model, { model = it }, label = { Text("Модель") }, singleLine = true)
            }
        },
        confirmButton = { TextButton(onClick = { onSave(RiverSettings(url, key, model)) }) { Text("Сохранить") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } },
    )
}
