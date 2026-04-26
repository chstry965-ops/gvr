package com.antispam.blocker.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AddCircle
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.antispam.blocker.SpamBlockerApp
import com.antispam.blocker.data.db.entity.CallRecord
import com.antispam.blocker.data.repository.BlockListRepository
import com.antispam.blocker.domain.detector.Verdict
import com.antispam.blocker.ui.components.GlassCard
import com.antispam.blocker.ui.components.MonoLabelText
import com.antispam.blocker.ui.components.SectionHeader
import com.antispam.blocker.ui.components.StatusPill
import com.antispam.blocker.ui.theme.*
import com.antispam.blocker.util.PhoneNormalizer
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CallLogScreen() {
    val app = SpamBlockerApp.instance
    val callLogRepo = remember { com.antispam.blocker.data.repository.CallLogRepository(app.database.callRecordDao()) }
    val blockListRepo = remember {
        BlockListRepository(app.database.blockedNumberDao(), app.database.allowedNumberDao(), PhoneNormalizer)
    }
    val scope = rememberCoroutineScope()

    val records by callLogRepo.allRecords.collectAsState(initial = emptyList())

    Scaffold(
        containerColor = Ink,
        contentWindowInsets = WindowInsets(0)
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            item {
                SectionHeader(
                    eyebrow = "// EVENT STREAM",
                    title = "Журнал"
                )
                Spacer(Modifier.height(4.dp))
                MonoLabelText(
                    text = "${records.size} events logged",
                    color = TextTertiary
                )
                Spacer(Modifier.height(16.dp))
            }

            if (records.isEmpty()) {
                item {
                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(32.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(
                                    text = "Пока нет записей",
                                    style = MaterialTheme.typography.titleMedium,
                                    color = TextPrimary
                                )
                                Spacer(Modifier.height(4.dp))
                                Text(
                                    text = "Как только поступит звонок, он появится здесь",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = TextSecondary
                                )
                            }
                        }
                    }
                }
            } else {
                items(records, key = { it.id }) { record ->
                    CallRecordItem(
                        record = record,
                        onBlock = {
                            val num = record.originalNumber ?: return@CallRecordItem
                            scope.launch { blockListRepo.addToBlockList(num) }
                        },
                        onAllow = {
                            val num = record.originalNumber ?: return@CallRecordItem
                            scope.launch { blockListRepo.addToAllowList(num) }
                        }
                    )
                }
            }
        }
    }
}

@Composable
private fun CallRecordItem(
    record: CallRecord,
    onBlock: () -> Unit,
    onAllow: () -> Unit
) {
    val (color, label) = when (record.verdict) {
        Verdict.BLOCK -> BlockRed to "заблокирован"
        Verdict.WARN -> WarnAmber to "подозрительный"
        Verdict.ALLOW -> AllowGreen to "разрешён"
    }

    val dateFormat = remember { SimpleDateFormat("dd.MM HH:mm", Locale.getDefault()) }

    GlassCard(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Text(
                    text = record.originalNumber ?: "Скрытый номер",
                    style = MaterialTheme.typography.titleMedium,
                    color = TextPrimary
                )
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    StatusPill(text = label, color = color)
                    if (record.ruleName != null) {
                        MonoLabelText(
                            text = "· ${record.ruleName}",
                            color = TextTertiary
                        )
                    }
                }
                MonoLabelText(
                    text = dateFormat.format(Date(record.timestamp)),
                    color = TextTertiary
                )
            }

            if (record.verdict != Verdict.BLOCK) {
                IconButton(onClick = onBlock) {
                    Icon(
                        Icons.Rounded.AddCircle,
                        contentDescription = "В чёрный список",
                        tint = BlockRed
                    )
                }
            }
            if (record.verdict != Verdict.ALLOW) {
                IconButton(onClick = onAllow) {
                    Icon(
                        Icons.Rounded.CheckCircle,
                        contentDescription = "В белый список",
                        tint = AllowGreen
                    )
                }
            }
        }
    }
}
