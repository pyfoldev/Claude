package ai.chip.app

import android.content.Context
import android.graphics.Outline
import android.graphics.SurfaceTexture
import android.media.MediaPlayer
import android.view.Surface
import android.view.TextureView
import android.view.View
import android.view.ViewOutlineProvider
import androidx.annotation.RawRes
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.viewinterop.AndroidView

/** Looping, muted, circle-cropped video note (TextureView so the oval outline really clips it). */
@Composable
fun VideoCircle(@RawRes clip: Int, size: Dp, modifier: Modifier = Modifier) {
    AndroidView(
        factory = { CircleVideoView(it).also { v -> v.setClip(clip) } },
        update = { it.setClip(clip) },
        modifier = modifier.size(size),
    )
}

class CircleVideoView(context: Context) : TextureView(context), TextureView.SurfaceTextureListener {
    private var player: MediaPlayer? = null
    private var surface: Surface? = null
    private var clip = 0

    init {
        surfaceTextureListener = this
        isOpaque = false
        clipToOutline = true
        outlineProvider = object : ViewOutlineProvider() {
            override fun getOutline(view: View, outline: Outline) { outline.setOval(0, 0, view.width, view.height) }
        }
    }

    fun setClip(@RawRes res: Int) {
        if (res == clip) return
        clip = res
        restart()
    }

    private fun restart() {
        release()
        val s = surface ?: return
        if (clip == 0) return
        try {
            val afd = resources.openRawResourceFd(clip)
            player = MediaPlayer().apply {
                setDataSource(afd.fileDescriptor, afd.startOffset, afd.length)
                afd.close()
                setSurface(s)
                isLooping = true
                setVolume(0f, 0f)
                setOnPreparedListener { it.start() }
                prepareAsync()
            }
        } catch (_: Exception) { release() }
    }

    private fun release() {
        player?.let { try { it.release() } catch (_: Exception) {} }
        player = null
    }

    override fun onSurfaceTextureAvailable(st: SurfaceTexture, w: Int, h: Int) { surface = Surface(st); restart() }
    override fun onSurfaceTextureSizeChanged(st: SurfaceTexture, w: Int, h: Int) {}
    override fun onSurfaceTextureUpdated(st: SurfaceTexture) {}
    override fun onSurfaceTextureDestroyed(st: SurfaceTexture): Boolean {
        release(); surface?.release(); surface = null
        return true
    }
}
