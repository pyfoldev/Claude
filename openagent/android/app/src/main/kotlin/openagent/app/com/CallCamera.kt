package openagent.app.com

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.exifinterface.media.ExifInterface
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.coroutines.resume

/** Камера в голосовом звонке: превью на экране и кадр «по запросу» агента (функция look → camera). Кадры уходят на сервер только когда агент их просит. */
object CallCamera {
    @Volatile var capture: ImageCapture? = null

    /** Снимает кадр, поворачивает по EXIF, уменьшает до 1280 px → JPEG-файл или null, если камера не готова. */
    suspend fun takeFrame(ctx: Context): File? {
        val cap = capture ?: return null
        val raw = File(File(ctx.cacheDir, "cam").also { it.mkdirs() }, "cam_${System.currentTimeMillis()}.jpg")
        val ok = suspendCancellableCoroutine<Boolean> { c ->
            cap.takePicture(ImageCapture.OutputFileOptions.Builder(raw).build(), ContextCompat.getMainExecutor(ctx), object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(r: ImageCapture.OutputFileResults) { if (c.isActive) c.resume(true) }
                override fun onError(e: ImageCaptureException) { if (c.isActive) c.resume(false) }
            })
        }
        if (!ok) return null
        return withContext(Dispatchers.IO) {
            runCatching {
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }.also { BitmapFactory.decodeFile(raw.path, it) }
                val sample = maxOf(1, maxOf(bounds.outWidth, bounds.outHeight) / 1280)
                var bmp = BitmapFactory.decodeFile(raw.path, BitmapFactory.Options().apply { inSampleSize = sample }) ?: return@runCatching raw
                val deg = when (ExifInterface(raw.path).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
                    ExifInterface.ORIENTATION_ROTATE_90 -> 90f; ExifInterface.ORIENTATION_ROTATE_180 -> 180f; ExifInterface.ORIENTATION_ROTATE_270 -> 270f; else -> 0f
                }
                if (deg != 0f) bmp = Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, Matrix().apply { postRotate(deg) }, true)
                val out = File(raw.parentFile, "cam_${System.currentTimeMillis()}_s.jpg")
                out.outputStream().use { bmp.compress(Bitmap.CompressFormat.JPEG, 82, it) }
                raw.delete(); out
            }.getOrDefault(raw)
        }
    }
}

@Composable
fun CameraPreviewBox(front: Boolean, modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val view = androidx.compose.runtime.remember { PreviewView(ctx).apply { scaleType = PreviewView.ScaleType.FILL_CENTER } }
    DisposableEffect(front) {
        val fut = ProcessCameraProvider.getInstance(ctx)
        val run = Runnable {
            runCatching {
                val provider = fut.get()
                provider.unbindAll()
                val preview = Preview.Builder().build().also { it.setSurfaceProvider(view.surfaceProvider) }
                val cap = ImageCapture.Builder().setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY).build()
                provider.bindToLifecycle(owner, if (front) CameraSelector.DEFAULT_FRONT_CAMERA else CameraSelector.DEFAULT_BACK_CAMERA, preview, cap)
                CallCamera.capture = cap
            }
        }
        fut.addListener(run, ContextCompat.getMainExecutor(ctx))
        onDispose { CallCamera.capture = null; runCatching { fut.get().unbindAll() } }
    }
    AndroidView(factory = { view }, modifier = modifier)
}
