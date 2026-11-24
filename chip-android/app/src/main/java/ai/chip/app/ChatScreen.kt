package ai.chip.app

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
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
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.ui.draw.rotate
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
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
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val suggestions = listOf("Сегодня сдал экзамен!", "Мне грустно", "Расскажи шутку", "Как дела?")

@Composable
fun ChatScreen(vm: ChatViewModel) {
    var showSettings by remember { mutableStateOf(false) }
    var confirmNew by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()
    val empty = vm.messages.none { it.fromUser }

    LaunchedEffect(vm.messages.size, vm.thinking) {
        val n = vm.messages.size + if (vm.thinking) 1 else 0
        if (n > 0 && !empty) listState.animateScrollToItem(n - 1)
    }

    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).imePadding()) {
        TopBar(onNew = { if (empty) Unit else confirmNew = true }, onSettings = { showSettings = true })
        Box(Modifier.weight(1f).fillMaxWidth()) {
            if (empty) EmptyState(onPick = vm::send) else LazyColumn(
                state = listState,
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(20.dp),
            ) {
                items(vm.messages, key = { it.id }) { MessageRow(it) }
                if (vm.thinking) item(key = "thinking") { ThinkingDot() }
                if (vm.offlineHint) item(key = "hint") {
                    Text("Нет ответа от river.ai, поэтому Chip выбрал эмоцию сам. Проверьте ключ в настройках.",
                        fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
        InputBar(enabled = !vm.thinking, onSend = vm::send)
    }

    if (showSettings) SettingsDialog(vm.settings, onDismiss = { showSettings = false }) { vm.saveSettings(it); showSettings = false }
    if (confirmNew) AlertDialog(
        onDismissRequest = { confirmNew = false },
        containerColor = MaterialTheme.colorScheme.surface,
        title = { Text("Новый чат?") },
        text = { Text("Текущая переписка с Chip будет удалена.") },
        confirmButton = { TextButton(onClick = { vm.clear(); confirmNew = false }) { Text("Удалить и начать заново") } },
        dismissButton = { TextButton(onClick = { confirmNew = false }) { Text("Отмена") } },
    )
}

@Composable
private fun TopBar(onNew: () -> Unit, onSettings: () -> Unit) {
    Box(Modifier.fillMaxWidth().statusBarsPadding().height(56.dp).padding(horizontal = 4.dp)) {
        IconButton(onClick = onNew, modifier = Modifier.align(Alignment.CenterStart)) {
            Icon(Icons.Filled.Edit, "Новый чат", tint = MaterialTheme.colorScheme.onSurface)
        }
        Text("Chip", fontSize = 18.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.align(Alignment.Center))
        IconButton(onClick = onSettings, modifier = Modifier.align(Alignment.CenterEnd)) {
            Icon(Icons.Filled.Settings, "Настройки", tint = MaterialTheme.colorScheme.onSurface)
        }
    }
}

@Composable
private fun EmptyState(onPick: (String) -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(horizontal = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
    ) {
        VideoCircle(Emotions.byId("hello").clip, 150.dp)
        Spacer(Modifier.height(20.dp))
        Text("Привет, я Chip", fontSize = 26.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(6.dp))
        Text("Напишите мне, а я отвечу эмоцией", fontSize = 15.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(28.dp))
        Column(verticalArrangement = Arrangement.spacedBy(8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            suggestions.chunked(2).forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    row.forEach { s ->
                        Text(
                            s, fontSize = 14.sp,
                            modifier = Modifier.border(BorderStroke(1.dp, MaterialTheme.colorScheme.outline), RoundedCornerShape(16.dp))
                                .clickable { onPick(s) }.padding(horizontal = 14.dp, vertical = 10.dp),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun MessageRow(m: Message) {
    if (m.fromUser) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            Text(
                m.text, fontSize = 16.sp, lineHeight = 22.sp,
                modifier = Modifier.widthIn(max = 300.dp)
                    .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(22.dp))
                    .padding(horizontal = 16.dp, vertical = 10.dp),
            )
        }
    } else {
        val e = Emotions.byId(m.emotionId)
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            VideoCircle(e.clip, 200.dp)
            if (m.emojis.isNotBlank()) Text(m.emojis, fontSize = 28.sp)
        }
    }
}

@Composable
private fun ThinkingDot() {
    val t = rememberInfiniteTransition(label = "dot")
    val s by t.animateFloat(0.6f, 1f, infiniteRepeatable(tween(650), RepeatMode.Reverse), label = "s")
    Box(Modifier.padding(start = 4.dp).size((16 * s).dp).background(MaterialTheme.colorScheme.onSurface, CircleShape))
}

@Composable
private fun InputBar(enabled: Boolean, onSend: (String) -> Unit) {
    var text by remember { mutableStateOf("") }
    val canSend = enabled && text.isNotBlank()
    fun submit() { if (canSend) { onSend(text); text = "" } }
    Box(Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 12.dp, vertical = 8.dp)) {
        Row(
            Modifier.fillMaxWidth()
                .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(28.dp))
                .padding(start = 18.dp, end = 6.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.weight(1f).padding(vertical = 8.dp)) {
                if (text.isEmpty()) Text("Напишите Chip", fontSize = 16.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                BasicTextField(
                    value = text, onValueChange = { text = it }, maxLines = 5,
                    textStyle = TextStyle(fontSize = 16.sp, color = MaterialTheme.colorScheme.onSurface),
                    cursorBrush = SolidColor(MaterialTheme.colorScheme.onSurface),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(onSend = { submit() }),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Spacer(Modifier.size(8.dp))
            IconButton(
                onClick = { submit() }, enabled = canSend,
                modifier = Modifier.size(40.dp).alpha(if (canSend) 1f else 0.25f).background(MaterialTheme.colorScheme.onSurface, CircleShape),
            ) { Icon(Icons.AutoMirrored.Filled.Send, "Отправить", tint = MaterialTheme.colorScheme.background, modifier = Modifier.size(20.dp).rotate(-90f)) }
        }
    }
}

@Composable
private fun SettingsDialog(s: RiverSettings, onDismiss: () -> Unit, onSave: (RiverSettings) -> Unit) {
    var url by remember { mutableStateOf(s.baseUrl) }
    var key by remember { mutableStateOf(s.apiKey) }
    var model by remember { mutableStateOf(s.model) }
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = MaterialTheme.colorScheme.surface,
        title = { Text("river.ai") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Ключ создаётся в console.river.ai/keys. Без ключа Chip выбирает эмоцию по словам, без интернета.", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                OutlinedTextField(url, { url = it }, label = { Text("Адрес API") }, singleLine = true)
                OutlinedTextField(key, { key = it }, label = { Text("API-ключ (rv_...)") }, singleLine = true, visualTransformation = PasswordVisualTransformation())
                OutlinedTextField(model, { model = it }, label = { Text("Модель") }, singleLine = true)
            }
        },
        confirmButton = { TextButton(onClick = { onSave(RiverSettings(url, key, model)) }) { Text("Сохранить") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } },
    )
}
