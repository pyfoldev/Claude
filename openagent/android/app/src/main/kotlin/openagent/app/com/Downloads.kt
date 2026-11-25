package openagent.app.com

import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import java.io.File

/** Сохранение файлов в системную папку «Загрузки» (видна в «Файлах» и в галерее загрузок). Android 10+ — через MediaStore без разрешений. */
object Dl {
    private fun safe(n: String) = n.replace(Regex("[/\\\\:*?\"<>|]"), "_").trim().ifBlank { "file" }

    /** Копирует src в «Загрузки». Возвращает итоговое имя (при совпадении система добавит « (1)») или null, если не вышло. */
    fun save(ctx: Context, src: File, name: String, mime: String = ""): String? = runCatching {
        val n = safe(name)
        val type = mime.ifBlank { android.webkit.MimeTypeMap.getSingleton().getMimeTypeFromExtension(n.substringAfterLast('.', "").lowercase()) ?: "application/octet-stream" }
        if (Build.VERSION.SDK_INT >= 29) {
            val cv = ContentValues().apply { put(MediaStore.Downloads.DISPLAY_NAME, n); put(MediaStore.Downloads.MIME_TYPE, type); put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS); put(MediaStore.Downloads.IS_PENDING, 1) }
            val uri = ctx.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv) ?: return@runCatching null
            ctx.contentResolver.openOutputStream(uri)!!.use { o -> src.inputStream().use { it.copyTo(o) } }
            ctx.contentResolver.update(uri, ContentValues().apply { put(MediaStore.Downloads.IS_PENDING, 0) }, null, null)
            ctx.contentResolver.query(uri, arrayOf(MediaStore.Downloads.DISPLAY_NAME), null, null, null)?.use { c -> if (c.moveToFirst()) c.getString(0) else n } ?: n
        } else {
            val dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).also { it.mkdirs() }
            var out = File(dir, n); var i = 1
            while (out.exists()) { out = File(dir, n.substringBeforeLast('.', n) + " ($i)" + (if (n.contains('.')) "." + n.substringAfterLast('.') else "")); i++ }
            src.copyTo(out); android.media.MediaScannerConnection.scanFile(ctx, arrayOf(out.absolutePath), arrayOf(type), null)
            out.name
        }
    }.getOrNull()

    fun saveText(ctx: Context, text: String, name: String, mime: String): String? {
        val tmp = File(File(ctx.cacheDir, "dl").also { it.mkdirs() }, safe(name)).also { it.writeText(text) }
        return save(ctx, tmp, name, mime)
    }
}
