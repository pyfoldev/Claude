package app.notebookai

import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import android.provider.MediaStore
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme { Screen() } }
    }
}

private val FONTS = listOf("MarckScript" to "Marck Script", "Caveat" to "Caveat", "Pangolin" to "Pangolin")

@Composable
fun Screen() {
    val ctx = LocalContext.current
    val prefs = remember { ctx.getSharedPreferences("p", Context.MODE_PRIVATE) }
    val scope = rememberCoroutineScope()
    var key by remember { mutableStateOf(prefs.getString("key", "") ?: "") }
    var topic by remember { mutableStateOf("") }
    var font by remember { mutableStateOf(FONTS[0].first) }
    var words by remember { mutableFloatStateOf(80f) }
    var mess by remember { mutableFloatStateOf(1f) }
    var cell by remember { mutableFloatStateOf(48f) }
    var bg by remember { mutableStateOf<Bitmap?>(null) }
    var pages by remember { mutableStateOf<List<Bitmap>>(emptyList()) }
    var busy by remember { mutableStateOf(false) }

    val pick = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { u: Uri? ->
        if (u != null) scope.launch(Dispatchers.IO) {
            bg = ctx.contentResolver.openInputStream(u)?.use { BitmapFactory.decodeStream(it) }
        }
    }

    Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp).statusBarsPadding(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Тетрадь AI", style = MaterialTheme.typography.headlineSmall)
        OutlinedTextField(key, { key = it; prefs.edit().putString("key", it).apply() }, label = { Text("Anthropic API-ключ") },
            visualTransformation = PasswordVisualTransformation(), singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(topic, { topic = it }, label = { Text("Тема") }, modifier = Modifier.fillMaxWidth())
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FONTS.forEach { (id, name) -> FilterChip(font == id, { font = id }, { Text(name) }) }
        }
        Text("Длина: ${words.toInt()} слов"); Slider(words, { words = it }, valueRange = 30f..300f)
        Text("Небрежность почерка: ${"%.1f".format(mess)}"); Slider(mess, { mess = it }, valueRange = 0f..2f)
        Text("Размер клетки: ${cell.toInt()} px"); Slider(cell, { cell = it }, valueRange = 30f..80f)
        OutlinedButton({ pick.launch("image/*") }) { Text(if (bg == null) "Выбрать фото пустой тетради" else "Фон выбран ✓ (сменить)") }
        Button(enabled = !busy && key.isNotBlank() && topic.isNotBlank(), onClick = {
            busy = true
            scope.launch {
                try {
                    val text = ClaudeClient.generate(key.trim(), topic.trim(), words.toInt())
                    pages = withContext(Dispatchers.Default) {
                        NotebookRenderer.render(ctx, text, RenderOptions(font = font, cell = cell.toInt(), messiness = mess, background = bg))
                    }
                } catch (e: Exception) {
                    Toast.makeText(ctx, e.message ?: "Ошибка", Toast.LENGTH_LONG).show()
                } finally { busy = false }
            }
        }, modifier = Modifier.fillMaxWidth()) { Text(if (busy) "Пишу…" else "Написать в тетради") }

        pages.forEachIndexed { i, p ->
            Image(p.asImageBitmap(), null, Modifier.fillMaxWidth())
            OutlinedButton({ save(ctx, p, i) }) { Text("Сохранить в галерею") }
        }
    }
}

private fun save(ctx: Context, bmp: Bitmap, i: Int) {
    val v = ContentValues().apply {
        put(MediaStore.Images.Media.DISPLAY_NAME, "notebook_${System.currentTimeMillis()}_$i.jpg")
        put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
        put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/NotebookAI")
    }
    val uri = ctx.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, v) ?: return
    ctx.contentResolver.openOutputStream(uri)?.use { bmp.compress(Bitmap.CompressFormat.JPEG, 92, it) }
    Toast.makeText(ctx, "Сохранено", Toast.LENGTH_SHORT).show()
}
