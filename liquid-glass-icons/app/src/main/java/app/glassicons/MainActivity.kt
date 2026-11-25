package app.glassicons

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringArrayResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { PackScreen() }
    }
}

@Composable
fun PackScreen() {
    val ctx = LocalContext.current
    val names = stringArrayResource(R.array.icon_names)

    Box(Modifier.fillMaxSize().background(Color(0xFF0B1020))) {
        Backdrop()
        LazyVerticalGrid(
            columns = GridCells.Adaptive(76.dp),
            modifier = Modifier.fillMaxSize().statusBarsPadding(),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item(span = { GridItemSpan(maxLineSpan) }) {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text("Жидкое стекло", color = Color.White, fontSize = 30.sp, fontWeight = FontWeight.Bold)
                    Text(
                        "Иконпак: ${names.size} иконок, более 40 приложений",
                        color = Color.White.copy(alpha = 0.7f),
                        fontSize = 14.sp,
                    )
                    HowTo()
                }
            }
            items(names) { n ->
                val id = ctx.resources.getIdentifier("glass_$n", "drawable", ctx.packageName)
                if (id != 0) {
                    Image(
                        painter = painterResource(id),
                        contentDescription = n,
                        modifier = Modifier.fillMaxWidth().aspectRatio(1f),
                    )
                }
            }
        }
    }
}

@Composable
fun HowTo() {
    val shape = RoundedCornerShape(24.dp)
    Column(
        Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(Color.White.copy(alpha = 0.10f))
            .border(1.dp, Color.White.copy(alpha = 0.28f), shape)
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text("Как применить", color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
        listOf(
            "Установите лаунчер с поддержкой иконпаков: Nova, Lawnchair, Niagara, Smart Launcher.",
            "Откройте настройки лаунчера и найдите «Тема иконок» или «Иконпак».",
            "Выберите «Жидкое стекло».",
        ).forEachIndexed { i, s ->
            Text("${i + 1}. $s", color = Color.White.copy(alpha = 0.85f), fontSize = 13.sp)
        }
        Text(
            "Приложения без готовой иконки остаются как есть.",
            color = Color.White.copy(alpha = 0.55f),
            fontSize = 12.sp,
        )
    }
}

@Composable
fun Backdrop() {
    val t = rememberInfiniteTransition(label = "blobs")
    val p by t.animateFloat(
        0f, 1f,
        infiniteRepeatable(tween(18000, easing = LinearEasing), RepeatMode.Reverse),
        label = "p",
    )
    Canvas(Modifier.fillMaxSize().blur(70.dp)) {
        val w = size.width
        val h = size.height
        drawCircle(Color(0xFF3B82F6), w * 0.45f, Offset(w * (0.2f + 0.5f * p), h * (0.15f + 0.1f * p)))
        drawCircle(Color(0xFFEC4899), w * 0.42f, Offset(w * (0.9f - 0.5f * p), h * (0.45f + 0.1f * p)))
        drawCircle(Color(0xFF22D3AA), w * 0.40f, Offset(w * (0.1f + 0.4f * p), h * (0.75f - 0.15f * p)))
    }
}
