package com.antispam.blocker.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Analytics
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.antispam.blocker.SpamBlockerApp
import com.antispam.blocker.data.db.entity.DecisionRecord
import com.antispam.blocker.domain.tracking.DecisionTracker
import com.antispam.blocker.domain.tracking.TrackingStats
import com.antispam.blocker.ui.components.GlassCard
import com.antispam.blocker.ui.components.MonoLabelText
import com.antispam.blocker.ui.components.SectionHeader
import com.antispam.blocker.ui.theme.*
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import org.json.JSONArray
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ModelDebugScreen() {
    val app = SpamBlockerApp.instance
    val tracker = remember {
        DecisionTracker(app.database.decisionRecordDao()) { app.modelVersion }
    }
    val scope = rememberCoroutineScope()
    val modelCard = app.modelCard
    var records by remember { mutableStateOf<List<DecisionRecord>>(emptyList()) }
    var stats by remember { mutableStateOf<TrackingStats?>(null) }

    LaunchedEffect(Unit) {
        tracker.observeRecent(50).collectLatest {
            records = it
            stats = tracker.stats()
        }
    }

    Scaffold(
        containerColor = Ink,
        contentWindowInsets = WindowInsets(0)
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                SectionHeader(
                    eyebrow = "// AI OBSERVABILITY",
                    title = "ИИ и отслеживание"
                )
                Spacer(Modifier.height(4.dp))
            }

            item {
                GlassCard(modifier = Modifier.fillMaxWidth(), accentBorder = true) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Icon(Icons.Rounded.AutoAwesome, contentDescription = null, tint = Amber)
                            Text("Model Card", style = MaterialTheme.typography.titleMedium, color = TextPrimary)
                        }
                        if (modelCard == null) {
                            Text(
                                "TFLite model card не найден. Сейчас приложение использует rule fallback или старую модель, если она совместима.",
                                style = MaterialTheme.typography.bodySmall,
                                color = WarnAmber
                            )
                        } else {
                            MetricGrid(
                                items = listOf(
                                    "VERSION" to modelCard.version,
                                    "FEATURES" to modelCard.featureCount.toString(),
                                    "ROWS" to modelCard.rows.toString(),
                                    "BLOCK PREC" to "${(modelCard.blockPrecision * 100).toInt()}%",
                                    "BLOCK REC" to "${(modelCard.blockRecall * 100).toInt()}%",
                                    "ROC-AUC" to (modelCard.rocAuc?.let { "%.3f".format(it) } ?: "n/a")
                                )
                            )
                        }
                    }
                }
            }

            item {
                val s = stats
                GlassCard(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Icon(Icons.Rounded.Analytics, contentDescription = null, tint = Amber)
                            Text("Production telemetry", style = MaterialTheme.typography.titleMedium, color = TextPrimary)
                        }
                        MetricGrid(
                            items = listOf(
                                "TOTAL" to (s?.total ?: 0).toString(),
                                "BLOCK" to (s?.blockCount ?: 0).toString(),
                                "WARN" to (s?.warnCount ?: 0).toString(),
                                "ALLOW" to (s?.allowCount ?: 0).toString(),
                                "MODEL" to (s?.modelDecisions ?: 0).toString(),
                                "RULE" to (s?.ruleDecisions ?: 0).toString(),
                                "FEEDBACK" to (s?.feedbackCount ?: 0).toString(),
                                "AGREE" to (s?.agreementRate?.let { "${(it * 100).toInt()}%" } ?: "n/a")
                            )
                        )

                        if (records.isNotEmpty()) {
                            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                MonoLabelText(text = "VERDICT TREND", color = TextTertiary)
                                VerdictSparkline(
                                    records = records,
                                    modifier = Modifier.fillMaxWidth().height(48.dp)
                                )
                                Row(
                                    horizontalArrangement = Arrangement.spacedBy(16.dp),
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    SparklineLegend("BLOCK", BlockRed)
                                    SparklineLegend("WARN", WarnAmber)
                                    SparklineLegend("ALLOW", AllowGreen)
                                }
                            }
                        }
                        OutlinedButton(
                            onClick = {
                                scope.launch {
                                    tracker.clear()
                                    stats = tracker.stats()
                                }
                            },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp),
                            border = androidx.compose.foundation.BorderStroke(1.dp, InkBorder),
                            colors = ButtonDefaults.outlinedButtonColors(contentColor = TextPrimary)
                        ) {
                            Text("Очистить telemetry")
                        }
                    }
                }
            }

            item {
                MonoLabelText(text = "LAST 50 DECISIONS", color = TextTertiary)
            }

            if (records.isEmpty()) {
                item {
                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        Text(
                            "Пока нет записанных решений. После входящего звонка здесь появятся фичи, вероятности и причины.",
                            modifier = Modifier.padding(16.dp),
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextSecondary
                        )
                    }
                }
            } else {
                items(records, key = { it.id }) { record ->
                    DecisionCard(record)
                }
            }
        }
    }
}

@Composable
private fun MetricGrid(items: List<Pair<String, String>>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items.chunked(2).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                row.forEach { (label, value) ->
                    MetricChip(label = label, value = value, modifier = Modifier.weight(1f))
                }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun MetricChip(label: String, value: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .background(InkSurface, RoundedCornerShape(12.dp))
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        MonoLabelText(text = label, color = TextTertiary)
        Text(value, style = MaterialTheme.typography.titleMedium, color = TextPrimary, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun DecisionCard(record: DecisionRecord) {
    val verdictColor = when (record.verdict) {
        "BLOCK" -> BlockRed
        "WARN" -> WarnAmber
        else -> AllowGreen
    }
    val icon = when (record.verdict) {
        "BLOCK", "WARN" -> Icons.Rounded.Warning
        else -> Icons.Rounded.CheckCircle
    }
    GlassCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Icon(icon, contentDescription = null, tint = verdictColor, modifier = Modifier.size(18.dp))
                    Text(record.verdict, color = verdictColor, style = MaterialTheme.typography.titleMedium)
                }
                MonoLabelText(text = formatTime(record.timestamp), color = TextTertiary)
            }

            Text(
                text = record.rawNumber ?: record.normalizedNumber ?: "Скрытый номер",
                style = MaterialTheme.typography.titleLarge,
                color = TextPrimary
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                MetricChip("SCORE", record.score.toString(), Modifier.weight(1f))
                MetricChip("RULE", record.ruleScore.toString(), Modifier.weight(1f))
                MetricChip("SOURCE", record.source, Modifier.weight(1f))
            }

            ProbabilityBars(record)

            val reasons = parseJsonArray(record.reasonsJson)
            if (reasons.isNotEmpty()) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    MonoLabelText(text = "REASONS", color = TextTertiary)
                    reasons.take(4).forEach { reason ->
                        Text("• $reason", style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                    }
                }
            }

            val factors = parseJsonArray(record.activeFactorsJson)
            if (factors.isNotEmpty()) {
                Text(
                    text = "Factors: ${factors.joinToString(", ")}",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextTertiary
                )
            }
        }
    }
}

@Composable
private fun ProbabilityBars(record: DecisionRecord) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        ProbBar("ALLOW", record.modelAllowProb, AllowGreen)
        ProbBar("WARN", record.modelWarnProb, WarnAmber)
        ProbBar("BLOCK", record.modelBlockProb, BlockRed)
    }
}

@Composable
private fun ProbBar(label: String, value: Float, color: Color) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        MonoLabelText(text = label, color = TextTertiary, modifier = Modifier.width(48.dp))
        LinearProgressIndicator(
            progress = value.coerceIn(0f, 1f),
            modifier = Modifier
                .weight(1f)
                .height(8.dp),
            color = color,
            trackColor = InkBorder
        )
        Text("${(value * 100).toInt()}%", color = TextSecondary, style = MaterialTheme.typography.bodySmall)
    }
}

private fun parseJsonArray(json: String): List<String> {
    return runCatching {
        val arr = JSONArray(json)
        List(arr.length()) { idx -> arr.optString(idx) }
    }.getOrDefault(emptyList())
}

private fun formatTime(ts: Long): String {
    return SimpleDateFormat("HH:mm:ss dd.MM", Locale.getDefault()).format(Date(ts))
}

@Composable
private fun VerdictSparkline(records: List<DecisionRecord>, modifier: Modifier = Modifier) {
    val blockProbs = records.map { it.modelBlockProb }
    val warnProbs = records.map { it.modelWarnProb }
    val allowProbs = records.map { it.modelAllowProb }

    Canvas(modifier = modifier) {
        val w = size.width
        val h = size.height
        if (blockProbs.size < 2) return@Canvas

        val drawSparkline: (List<Float>, Color) -> Unit = { data, color ->
            val step = w / (data.size - 1).coerceAtLeast(1)
            for (i in 0 until data.size - 1) {
                val x1 = i * step
                val x2 = (i + 1) * step
                val y1 = h - data[i].coerceIn(0f, 1f) * h
                val y2 = h - data[i + 1].coerceIn(0f, 1f) * h
                drawLine(
                    color = color,
                    start = Offset(x1, y1),
                    end = Offset(x2, y2),
                    strokeWidth = 2.dp.toPx(),
                    cap = StrokeCap.Round
                )
            }
        }

        drawSparkline(allowProbs, AllowGreen.copy(alpha = 0.5f))
        drawSparkline(warnProbs, WarnAmber.copy(alpha = 0.7f))
        drawSparkline(blockProbs, BlockRed.copy(alpha = 0.9f))
    }
}

@Composable
private fun SparklineLegend(label: String, color: Color) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Canvas(modifier = Modifier.size(8.dp)) {
            drawCircle(color = color)
        }
        MonoLabelText(text = label, color = TextSecondary)
    }
}
