package openagent.app.com

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun OfflineSettings(vm: AppVM) {
    val ctx = LocalContext.current
    SwitchRow(Icons.Outlined.CloudOff, "Работать без интернета", "Чат и команды телефону считаются на устройстве", vm.offlineMode, vm::updOffline)
    Box(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) { Segmented(listOf("lfm" to "LFM (быстро)", "chat" to "Ministral (умнее)"), vm.chatModel, vm::updChatModel) }
    for (s in Offline.ALL) {
        val ready = Offline.ready(ctx, s); val pr = Offline.progress[s.id]
        val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> if (uri != null) Offline.importFile(ctx, s, uri) }
        Row3(if (s.id != "phone") Icons.Outlined.Chat else Icons.Outlined.PhoneAndroid, s.title,
            when { pr != null -> "Загрузка ${(pr * 100).toInt()}%"; ready -> "Готово · ${Offline.sizeMb(ctx, s)} МБ"; else -> "Не загружено · ~${s.size / 1_000_000} МБ" },
            trailing = {
                Row {
                    if (pr != null) TextButton({ Offline.cancel(s) }) { Text("Стоп", color = C.dim) }
                    else {
                        if (!ready) TextButton({ Offline.download(ctx, vm.store, s) }) { Text("Скачать", color = C.onContainer) }
                        else TextButton({ Offline.delete(ctx, s) }) { Text("Удалить", color = C.dim) }
                        if (s.id == "phone") TextButton({ pick.launch(arrayOf("*/*")) }) { Text("Файл…", color = C.onContainer) }
                    }
                }
            })
        if (pr != null) LinearProgressIndicator(progress = { pr }, modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 2.dp), color = C.onContainer, trackColor = C.container)
    }
    if (Offline.error.value.isNotBlank()) Text(Offline.error.value, color = C.dim, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 18.dp, vertical = 4.dp))
    Text("Модели скачиваются один раз по Wi-Fi. Чат запускается за пару секунд после первого сообщения; нужно ~3 ГБ памяти.", color = C.dim, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 18.dp, vertical = 4.dp))
}
