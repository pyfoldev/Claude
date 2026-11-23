package openagent.app.com

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

// ====================== Монитор сервера ======================
private fun levelColor(p: Int) = when { p >= 90 -> C.danger; p >= 70 -> Color(0xFFB8B8C0); else -> C.ok }
private fun fmtBytes(b: Long) = when { b >= 1L shl 30 -> "%.1f ГБ".format(b / 1073741824.0); b >= 1L shl 20 -> "%d МБ".format(b shr 20); else -> "%d КБ".format(b shr 10) }
private fun fmtUptime(s: Double): String { val d = (s / 86400).toInt(); val h = ((s % 86400) / 3600).toInt(); val m = ((s % 3600) / 60).toInt(); return if (d > 0) "$d д $h ч" else if (h > 0) "$h ч $m мин" else "$m мин" }

@Composable
fun RingGauge(percent: Int, title: String, caption: String, modifier: Modifier = Modifier) {
    val p by animateFloatAsState(percent.coerceIn(0, 100) / 100f, tween(700, easing = FastOutSlowInEasing), label = "g")
    val col by animateColorAsState(levelColor(percent), tween(400), label = "gc")
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Box(Modifier.size(96.dp), contentAlignment = Alignment.Center) {
            val track = C.surface3
            androidx.compose.foundation.Canvas(Modifier.fillMaxSize()) {
                val w = 11.dp.toPx(); val s = Size(size.width - w, size.height - w); val tl = Offset(w / 2, w / 2)
                drawArc(track, 135f, 270f, false, tl, s, style = Stroke(w, cap = StrokeCap.Round))
                drawArc(col, 135f, 270f * p, false, tl, s, style = Stroke(w, cap = StrokeCap.Round))
            }
            Text("$percent%", color = C.text, fontSize = 20.sp, fontWeight = FontWeight.Bold)
        }
        Text(title, color = C.text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 4.dp))
        Text(caption, color = C.dim, fontSize = 11.sp, textAlign = TextAlign.Center, maxLines = 1)
    }
}

@Composable
fun Sparkline(values: List<Int>, modifier: Modifier = Modifier) {
    val col = C.accent
    androidx.compose.foundation.Canvas(modifier) {
        if (values.size < 2) return@Canvas
        val step = size.width / (values.size - 1)
        val path = Path(); val fill = Path()
        values.forEachIndexed { i, v ->
            val x = i * step; val y = size.height - (v.coerceIn(0, 100) / 100f) * size.height
            if (i == 0) { path.moveTo(x, y); fill.moveTo(x, size.height); fill.lineTo(x, y) } else { path.lineTo(x, y); fill.lineTo(x, y) }
        }
        fill.lineTo(size.width, size.height); fill.close()
        drawPath(fill, Brush.verticalGradient(listOf(col.copy(alpha = 0.35f), Color.Transparent)))
        drawPath(path, col, style = Stroke(3.dp.toPx(), cap = StrokeCap.Round, join = androidx.compose.ui.graphics.StrokeJoin.Round))
    }
}

@Composable
fun ServerScreen(vm: AppVM) {
    LaunchedEffect(Unit) { while (true) { vm.loadSystem(); delay(4000) } }
    val s = vm.sys
    PageScaffold("Сервер", { vm.screen = Screen.Chat }) {
        if (s == null) Box(Modifier.fillMaxWidth().padding(48.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = C.accent) }
        else LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 28.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            item {
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(C.surface2).padding(18.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(44.dp).clip(CircleShape).background(C.container), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.Dns, null, tint = C.onContainer) }
                        Spacer(Modifier.width(14.dp))
                        Column(Modifier.weight(1f)) { Text(s.host.ifBlank { "Сервер" }, color = C.text, fontSize = 18.sp, fontWeight = FontWeight.Bold); Text("Работает ${fmtUptime(s.uptime)} · ${s.cores} яд.", color = C.dim, fontSize = 13.sp) }
                        Box(Modifier.size(10.dp).clip(CircleShape).background(C.ok))
                    }
                    Spacer(Modifier.height(14.dp))
                    Text("Нагрузка CPU", color = C.dim, fontSize = 12.sp)
                    Sparkline(vm.cpuHistory, Modifier.fillMaxWidth().height(56.dp).padding(top = 6.dp))
                    Text("load: " + s.load.joinToString(" · ") { "%.2f".format(it) }, color = C.dim, fontSize = 11.sp, modifier = Modifier.padding(top = 6.dp))
                }
            }
            item {
                val cpu = s.cpu ?: ((s.load.firstOrNull() ?: 0.0) / s.cores * 100).toInt().coerceIn(0, 100)
                val ramP = if (s.mem.total > 0) (s.mem.used * 100 / s.mem.total).toInt() else 0
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(C.surface2).padding(vertical = 18.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
                    RingGauge(cpu, "CPU", "${s.cores} ядер")
                    RingGauge(ramP, "Память", "${fmtBytes(s.mem.used)} / ${fmtBytes(s.mem.total)}")
                    RingGauge(s.disk?.percent ?: 0, "Диск", s.disk?.let { "${fmtBytes(it.used)} / ${fmtBytes(it.total)}" } ?: "—")
                }
            }
            if (s.services.isNotEmpty()) item {
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(C.surface2).padding(18.dp)) {
                    Text("Службы", color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    Row(Modifier.padding(top = 10.dp).horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        s.services.forEach { sv ->
                            val ok = sv.active == "active"
                            Row(Modifier.height(36.dp).clip(RoundedCornerShape(18.dp)).background(C.surface3).padding(horizontal = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                                Box(Modifier.size(8.dp).clip(CircleShape).background(if (ok) C.ok else C.danger)); Spacer(Modifier.width(8.dp)); Text(sv.name, color = C.text, fontSize = 13.sp)
                            }
                        }
                    }
                }
            }
            if (s.procs.isNotEmpty()) item {
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(C.surface2).padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Процессы", color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    s.procs.forEach { p ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(p.name, color = C.text, fontSize = 14.sp, modifier = Modifier.width(110.dp), maxLines = 1, overflow = TextOverflow.Ellipsis)
                            val w by animateFloatAsState((p.cpu.toFloat() / 100f).coerceIn(0.02f, 1f), tween(600), label = "pb")
                            Box(Modifier.weight(1f).height(8.dp).clip(CircleShape).background(C.surface3)) { Box(Modifier.fillMaxWidth(w).fillMaxHeight().clip(CircleShape).background(levelColor(p.cpu.toInt()))) }
                            Text("%.1f%%".format(p.cpu), color = C.dim, fontSize = 12.sp, textAlign = TextAlign.End, modifier = Modifier.width(54.dp))
                        }
                    }
                }
            }
            if (s.ports.isNotEmpty()) item {
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(C.surface2).padding(18.dp)) {
                    Text("Открытые порты", color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    Row(Modifier.padding(top = 10.dp).horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        s.ports.forEach { Text(it, color = C.accent, style = Mono, fontSize = 13.sp, modifier = Modifier.clip(RoundedCornerShape(14.dp)).background(C.surface3).padding(horizontal = 12.dp, vertical = 7.dp)) }
                    }
                }
            }
        }
    }
}

// ====================== Git ======================
private fun gitColor(code: String) = when (code.firstOrNull()) { 'M' -> Color(0xFFB8B8C0); 'A' -> C.ok; 'D' -> C.danger; 'R' -> C.accent; else -> C.dim }

@Composable
fun GitScreen(vm: AppVM) {
    var commitOpen by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { vm.loadGitRepos() }
    val info = vm.gitInfo
    PageScaffold("Git", { if (info != null) vm.gitInfo = null else vm.screen = Screen.Chat }) {
        if (info == null || !info.repo) LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 24.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { Text("Репозитории в рабочих папках агента. Выберите, чтобы увидеть изменения, историю и сделать commit / pull / push.", color = C.dim, fontSize = 14.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)) }
            if (vm.gitRepos.isEmpty()) item { EmptyHint(Icons.Outlined.AccountTree, "Репозиториев не найдено.\nПопросите агента: «склонируй репозиторий …»") }
            items(vm.gitRepos, key = { it.path }) { r ->
                Row(Modifier.fillMaxWidth().animateItem().bounceClick { vm.openGit(r.path) }.clip(RoundedCornerShape(24.dp)).background(C.surface2).padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(44.dp).clip(CircleShape).background(C.container), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.AccountTree, null, tint = C.onContainer) }
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) { Text(r.name, color = C.text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold); Text(r.path, color = C.dim, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis) }
                    Icon(Icons.Outlined.ChevronRight, null, tint = C.dim)
                }
            }
            if (info != null && !info.repo) item { Text("Это не git-репозиторий", color = C.danger, modifier = Modifier.padding(8.dp)) }
        } else LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(C.surface2).padding(18.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.AltRoute, null, tint = C.accent); Spacer(Modifier.width(10.dp))
                        Text(info.branch, color = C.text, fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                        if (info.ahead > 0) Text("↑${info.ahead}", color = C.ok, fontWeight = FontWeight.Bold, modifier = Modifier.padding(end = 8.dp))
                        if (info.behind > 0) Text("↓${info.behind}", color = Color(0xFFB8B8C0), fontWeight = FontWeight.Bold)
                    }
                    if (info.remote.isNotBlank()) Text(info.remote, color = C.dim, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (info.diffstat.isNotBlank()) Text(info.diffstat, color = C.dim, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
                    Row(Modifier.padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        PillButton("Commit", { commitOpen = true }, enabled = info.status.isNotEmpty() && !vm.gitBusy, icon = Icons.Outlined.Check, height = 48.dp)
                        SoftChip(Icons.Outlined.ArrowDownward, "Pull", false) { if (!vm.gitBusy) vm.gitDo("pull") }
                        SoftChip(Icons.Outlined.ArrowUpward, "Push", info.ahead > 0) { if (!vm.gitBusy) vm.gitDo("push") }
                        if (vm.gitBusy) CircularProgressIndicator(Modifier.size(24.dp), color = C.accent, strokeWidth = 2.5.dp)
                    }
                }
            }
            item { Text(if (info.status.isEmpty()) "Изменений нет" else "Изменения (${info.status.size})", color = C.dim, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp)) }
            items(info.status, key = { "s" + it.file }) { f ->
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(C.surface2).padding(horizontal = 14.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(f.code, color = gitColor(f.code), style = Mono, fontWeight = FontWeight.Bold, modifier = Modifier.width(26.dp))
                    Text(f.file, color = C.text, fontSize = 13.sp, style = Mono, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
            item { Text("История", color = C.dim, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp, top = 6.dp)) }
            items(info.log, key = { "c" + it.hash }) { c ->
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(C.surface2).padding(14.dp)) {
                    Text(c.subject, color = C.text, fontSize = 14.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text("${c.hash} · ${c.author} · ${c.ago}", color = C.dim, fontSize = 11.sp, modifier = Modifier.padding(top = 3.dp))
                }
            }
        }
    }
    if (commitOpen) {
        var msg by remember { mutableStateOf("") }
        AppDialog("Commit", { commitOpen = false }, "Закоммитить", msg.isNotBlank(), { vm.gitDo("commit", msg.trim()); commitOpen = false }) {
            Text("Все изменения будут добавлены (git add -A).", color = C.dim, fontSize = 13.sp)
            Field(msg, { msg = it }, "Сообщение коммита", singleLine = false, minLines = 2)
        }
    }
}
