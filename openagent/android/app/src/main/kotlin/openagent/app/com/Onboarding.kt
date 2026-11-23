package openagent.app.com

import android.Manifest
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val INTERESTS = listOf("Технологии и ИИ", "Бизнес", "Программирование", "Финансы", "Спорт", "Путешествия", "Кино и сериалы", "Музыка", "Игры", "Авто", "Здоровье", "Кулинария", "Наука", "Книги", "Мода", "Дом и ремонт")

/** Мастер первоначальной настройки: кто вы, где живёте, чем занимаетесь, как общаться, какие доступы выдать. */
@Composable
fun OnboardingScreen(vm: AppVM) {
    val ctx = LocalContext.current
    var step by remember { mutableIntStateOf(0) }
    val total = 7
    var name by remember { mutableStateOf(vm.user?.name.orEmpty()) }
    var address by remember { mutableStateOf("ty") }
    var city by remember { mutableStateOf("") }; var home by remember { mutableStateOf("") }
    var job by remember { mutableStateOf("") }; var picked by remember { mutableStateOf(setOf<String>()) }; var other by remember { mutableStateOf("") }
    var style by remember { mutableStateOf("short") }; var humor by remember { mutableStateOf("joke") }
    var about by remember { mutableStateOf("") }
    LaunchedEffect(Unit) { vm.loadProfile { p -> if (name.isBlank()) name = p.name; city = p.city; home = p.home; job = p.job; about = p.about; if (p.address.isNotBlank()) address = p.address; if (p.style.isNotBlank()) style = p.style; if (p.humor.isNotBlank()) humor = p.humor } }
    BackHandler { if (step > 0) step-- else vm.finishOnboarding(null) }
    val permLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { vm.toast = "Готово" }

    fun finish() {
        val interests = (picked.toList() + other.split(',').map { it.trim() }.filter { it.isNotEmpty() }).joinToString(", ")
        vm.finishOnboarding(Profile(name.trim(), city.trim(), home.trim(), job.trim(), interests, about.trim(), style, address, humor))
    }

    Column(Modifier.fillMaxSize().systemBarsPadding().imePadding().padding(horizontal = 22.dp)) {
        Row(Modifier.fillMaxWidth().padding(top = 16.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            SaturnMark(34.dp); Spacer(Modifier.width(10.dp))
            Text("Знакомство", color = C.text, fontSize = 22.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            TextButton({ vm.finishOnboarding(null) }) { Text("Пропустить", color = C.dim) }
        }
        LinearProgressIndicator(progress = { (step + 1f) / total }, modifier = Modifier.fillMaxWidth().height(4.dp).clip(RoundedCornerShape(2.dp)), color = C.accent, trackColor = C.surface3)
        AnimatedContent(step, modifier = Modifier.weight(1f), transitionSpec = {
            if (targetState > initialState) (slideInHorizontally(tween(260)) { it / 4 } + fadeIn(tween(260))) togetherWith (slideOutHorizontally(tween(200)) { -it / 4 } + fadeOut(tween(160)))
            else (slideInHorizontally(tween(260)) { -it / 4 } + fadeIn(tween(260))) togetherWith (slideOutHorizontally(tween(200)) { it / 4 } + fadeOut(tween(160)))
        }, label = "onb") { s ->
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(top = 22.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                when (s) {
                    0 -> { H("Привет! Как вас зовут?", "Я буду вашим личным агентом. Расскажите о себе — отвечать я стану точнее, а вопросов задавать меньше."); Field(name, { name = it }, "Имя"); Text("Обращение", color = C.dim, fontSize = 13.sp); Segmented(listOf("ty" to "На «ты»", "vy" to "На «вы»"), address, { address = it }) }
                    1 -> { H("Где вы живёте?", "Город нужен для погоды, транспорта, такси и «что рядом»."); Field(city, { city = it }, "Город"); Field(home, { home = it }, "Район или адрес дома (по желанию — для такси и маршрутов)") }
                    2 -> { H("Чем занимаетесь?", "Работа, учёба, бизнес — как есть."); Field(job, { job = it }, "Занятие", singleLine = false, minLines = 2) }
                    3 -> {
                        H("Что вам интересно?", "Выберите несколько — по ним я буду подбирать новости, советы и находки.")
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            INTERESTS.chunked(2).forEach { row -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { row.forEach { t ->
                                val on = t in picked
                                Box(Modifier.weight(1f).clip(RoundedCornerShape(20.dp)).background(if (on) C.container else C.surface2).clickableNoRipple { Haptics.tick(); picked = if (on) picked - t else picked + t }.padding(vertical = 13.dp, horizontal = 12.dp), contentAlignment = Alignment.Center) { Text(t, color = if (on) C.onContainer else C.text, fontSize = 14.sp, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal) }
                            } } }
                        }
                        Field(other, { other = it }, "Что-то ещё (через запятую)")
                    }
                    4 -> {
                        H("Как со мной общаться?", "Это можно поменять в любой момент.")
                        Text("Длина ответов", color = C.dim, fontSize = 13.sp); Segmented(listOf("short" to "Кратко", "detailed" to "Подробно"), style, { style = it })
                        Text("Тон", color = C.dim, fontSize = 13.sp); Segmented(listOf("joke" to "С юмором", "serious" to "Серьёзно"), humor, { humor = it })
                        Field(about, { about = it }, "Ещё о вас: семья, привычки, любимые места, что не любите…", singleLine = false, minLines = 4)
                    }
                    5 -> {
                        H("Защита", "По желанию: запишите голос и лицо — и приложение, и голосовые сеансы смогут открываться только вам. Всё хранится на телефоне; можно пропустить и сделать позже в настройках.")
                        BioEnrollRows(vm)
                    }
                    else -> {
                        H("Доступы", "Чтобы я мог звонить, писать, ставить встречи и находить рядом — разрешите нужное. Всё можно выдать позже в настройках.")
                        PermRow(Icons.Outlined.Call, "Контакты, звонки, SMS, календарь, геолокация") { permLauncher.launch(arrayOf(Manifest.permission.READ_CONTACTS, Manifest.permission.CALL_PHONE, Manifest.permission.SEND_SMS, Manifest.permission.READ_CALENDAR, Manifest.permission.WRITE_CALENDAR, Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.POST_NOTIFICATIONS)) }
                        PermRow(Icons.Outlined.PhoneAndroid, "Управление телефоном (служба доступности)") { runCatching { ctx.startActivity(android.content.Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)) } }
                        PermRow(Icons.Outlined.Notifications, "Доступ к уведомлениям (сводка «что пропустил»)") { runCatching { ctx.startActivity(android.content.Intent(android.provider.Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)) } }
                        PermRow(Icons.Outlined.Mic, "Микрофон для голоса") { permLauncher.launch(arrayOf(Manifest.permission.RECORD_AUDIO)) }
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(vertical = 14.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (step > 0) OutlinedButton({ step-- }, shape = RoundedCornerShape(26.dp), modifier = Modifier.height(54.dp)) { Text("Назад", color = C.text) }
            PillButton(if (step == total - 1) "Готово" else "Далее", { if (step == total - 1) finish() else step++ }, Modifier.weight(1f), height = 54.dp)
        }
    }
}

@Composable private fun H(title: String, sub: String) { Text(title, color = C.text, fontSize = 28.sp, fontWeight = FontWeight.SemiBold, lineHeight = 34.sp); Text(sub, color = C.dim, fontSize = 15.sp, lineHeight = 21.sp) }

@Composable
private fun PermRow(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(C.surface2).clickableNoRipple { Haptics.click(); onClick() }.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(40.dp).clip(CircleShape).background(C.surface3), contentAlignment = Alignment.Center) { Icon(icon, null, tint = C.text, modifier = Modifier.size(20.dp)) }
        Spacer(Modifier.width(14.dp)); Text(label, color = C.text, fontSize = 15.sp, modifier = Modifier.weight(1f)); Icon(Icons.Outlined.ChevronRight, null, tint = C.dim)
    }
}

private fun Modifier.clickableNoRipple(onClick: () -> Unit): Modifier = this.then(Modifier.clickable(interactionSource = null, indication = null, onClick = onClick))
