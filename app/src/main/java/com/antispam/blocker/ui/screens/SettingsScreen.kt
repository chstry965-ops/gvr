package com.antispam.blocker.ui.screens

import android.os.Build
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.work.Data
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.antispam.blocker.SpamBlockerApp
import com.antispam.blocker.data.assets.CsvSpamImporter
import com.antispam.blocker.data.repository.BlockListRepository
import com.antispam.blocker.data.worker.SpamDbUpdateWorker
import com.antispam.blocker.ui.components.GlassCard
import com.antispam.blocker.ui.components.MonoLabelText
import com.antispam.blocker.ui.components.SectionHeader
import com.antispam.blocker.ui.theme.*
import com.antispam.blocker.util.PhoneNormalizer
import kotlinx.coroutines.launch
import java.util.concurrent.TimeUnit

/** Рекомендуемые публичные источники открытой базы спам-номеров (по умолчанию пустой). */
private const val DEFAULT_DB_URL_PLACEHOLDER = "https://raw.githubusercontent.com/<user>/<repo>/main/spam_numbers.txt"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen() {
    val app = SpamBlockerApp.instance
    val settings = app.settingsStore
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    val dbUpdateEnabled by settings.dbUpdateEnabled.collectAsState(initial = false)
    val dbUpdateUrl by settings.dbUpdateUrl.collectAsState(initial = "")
    val skipCallLogForBlocked by settings.skipCallLogForBlocked.collectAsState(initial = false)

    val blockListRepo = remember {
        BlockListRepository(app.database.blockedNumberDao(), app.database.allowedNumberDao(), PhoneNormalizer)
    }
    val totalBlocked by blockListRepo.totalCount.collectAsState(initial = 0)
    val prebuiltBlocked by blockListRepo.prebuiltCount.collectAsState(initial = 0)
    var reimporting by remember { mutableStateOf(false) }
    var showClearDialog by remember { mutableStateOf(false) }

    if (showClearDialog) {
        AlertDialog(
            onDismissRequest = { showClearDialog = false },
            containerColor = InkElevated,
            title = { Text("Очистить всю базу?", color = TextPrimary) },
            text = {
                Text(
                    "Будут удалены все заблокированные номера: встроенная база, скачанные из интернета и добавленные вручную. Белый список не будет затронут.",
                    color = TextSecondary
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showClearDialog = false
                        scope.launch {
                            blockListRepo.clearAllBlocked()
                            val importer = CsvSpamImporter(context, blockListRepo, settings)
                            importer.resetImportFlag()
                            // Сразу подтягиваем встроенную базу, чтобы защита не осталась пустой
                            importer.importIfFirstRun()
                        }
                    }
                ) { Text("Очистить", color = BlockRed) }
            },
            dismissButton = {
                TextButton(onClick = { showClearDialog = false }) {
                    Text("Отмена", color = TextSecondary)
                }
            }
        )
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
                    eyebrow = "// SYSTEM",
                    title = "Настройки"
                )
                Spacer(Modifier.height(4.dp))
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                item {
                    GlassCard(
                        modifier = Modifier.fillMaxWidth(),
                        accentBorder = true
                    ) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                Icon(
                                    Icons.Rounded.Shield,
                                    contentDescription = null,
                                    tint = Amber,
                                    modifier = Modifier.size(18.dp)
                                )
                                MonoLabelText(text = "RESTRICTED SETTINGS", color = Amber)
                            }
                            Text(
                                text = "Если приложение установлено не из Google Play",
                                style = MaterialTheme.typography.titleMedium,
                                color = TextPrimary
                            )
                            Text(
                                text = "Перейдите в Настройки → Приложения → Блокировщик спама → ⋮ → Разрешить ограниченные настройки",
                                style = MaterialTheme.typography.bodySmall,
                                color = TextSecondary
                            )
                        }
                    }
                }
            }

            item {
                SettingsCard(
                    eyebrow = "CALL LOG",
                    title = "Журнал звонков",
                    description = "Не записывать заблокированные звонки в системный журнал Android"
                ) {
                    ToggleRow(
                        label = "Скрыть из журнала",
                        checked = skipCallLogForBlocked,
                        onCheckedChange = { scope.launch { settings.set("skip_call_log_for_blocked", it) } }
                    )
                }
            }

            item {
                SettingsCard(
                    eyebrow = "BUILT-IN DB",
                    title = "Встроенная база спам-номеров",
                    description = "Предзагруженный список известных спам-номеров, префиксов и масок. Работает без интернета."
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            MonoLabelText(text = "ENTRIES", color = TextTertiary)
                            Text(
                                text = totalBlocked.toString(),
                                style = MaterialTheme.typography.titleLarge,
                                color = TextPrimary
                            )
                        }
                        Column(modifier = Modifier.weight(1f)) {
                            MonoLabelText(text = "PREBUILT", color = TextTertiary)
                            Text(
                                text = prebuiltBlocked.toString(),
                                style = MaterialTheme.typography.titleLarge,
                                color = Amber
                            )
                        }
                    }
                    Spacer(Modifier.height(12.dp))
                    OutlinedButton(
                        onClick = {
                            if (!reimporting) {
                                reimporting = true
                                scope.launch {
                                    try {
                                        val repo = BlockListRepository(
                                            app.database.blockedNumberDao(),
                                            app.database.allowedNumberDao(),
                                            PhoneNormalizer
                                        )
                                        CsvSpamImporter(context, repo, settings).reimport()
                                    } finally {
                                        reimporting = false
                                    }
                                }
                            }
                        },
                        enabled = !reimporting,
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        border = androidx.compose.foundation.BorderStroke(1.dp, InkBorder),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = TextPrimary)
                    ) {
                        Text(if (reimporting) "Импорт…" else "Переимпортировать встроенную базу")
                    }
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(
                        onClick = { showClearDialog = true },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        border = androidx.compose.foundation.BorderStroke(1.dp, BlockRed.copy(alpha = 0.5f)),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = BlockRed)
                    ) {
                        Text("Очистить всю базу")
                    }
                }
            }

            item {
                SettingsCard(
                    eyebrow = "DATABASE",
                    title = "Обновление базы по ссылке",
                    description = "Опционально: укажите URL txt-файла (по одному номеру на строку) — приложение скачает и добавит номера. Подходят публичные источники на GitHub."
                ) {
                    ToggleRow(
                        label = "Автоматические обновления",
                        checked = dbUpdateEnabled,
                        onCheckedChange = { enabled ->
                            scope.launch {
                                settings.set("db_update_enabled", enabled)
                                if (enabled && dbUpdateUrl.isNotBlank()) {
                                    schedulePeriodicUpdate(context, dbUpdateUrl)
                                } else {
                                    WorkManager.getInstance(context).cancelUniqueWork("spam_db_update")
                                }
                            }
                        }
                    )
                    if (dbUpdateEnabled) {
                        Spacer(Modifier.height(12.dp))
                        OutlinedTextField(
                            value = dbUpdateUrl,
                            onValueChange = { scope.launch { settings.set("db_update_url", it) } },
                            label = { Text("URL обновления", color = TextTertiary) },
                            placeholder = {
                                Text(DEFAULT_DB_URL_PLACEHOLDER, color = TextTertiary, maxLines = 1)
                            },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                            shape = RoundedCornerShape(12.dp),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = Amber,
                                unfocusedBorderColor = InkBorder,
                                focusedTextColor = TextPrimary,
                                unfocusedTextColor = TextPrimary,
                                cursorColor = Amber
                            )
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            text = "Формат: обычный текстовый файл, по одному номеру в строке (+74951234567). Строки со знаком # игнорируются.",
                            style = MaterialTheme.typography.bodySmall,
                            color = TextTertiary
                        )
                        Spacer(Modifier.height(8.dp))
                        OutlinedButton(
                            onClick = {
                                if (dbUpdateUrl.isNotBlank()) {
                                    val data = Data.Builder()
                                        .putString("update_url", dbUpdateUrl)
                                        .build()
                                    val request = OneTimeWorkRequestBuilder<SpamDbUpdateWorker>()
                                        .setInputData(data)
                                        .build()
                                    WorkManager.getInstance(context).enqueue(request)
                                }
                            },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp),
                            border = androidx.compose.foundation.BorderStroke(1.dp, InkBorder),
                            colors = ButtonDefaults.outlinedButtonColors(
                                contentColor = TextPrimary
                            )
                        ) {
                            Text("Обновить сейчас")
                        }
                    }
                }
            }

            item {
                SettingsCard(
                    eyebrow = "ABOUT",
                    title = "Antispam Sentinel v2.0",
                    description = "Приложение фильтрует входящие звонки, блокируя известные мошеннические номера и предупреждая о подозрительных. Работает полностью без интернета."
                )
            }

            item {
                Spacer(Modifier.height(12.dp))
                MonoLabelText(
                    text = "BUILT WITH KOTLIN  •  JETPACK COMPOSE  •  ROOM",
                    color = TextTertiary,
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }
    }
}

@Composable
private fun SettingsCard(
    eyebrow: String,
    title: String,
    description: String,
    content: (@Composable ColumnScope.() -> Unit)? = null
) {
    GlassCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            MonoLabelText(text = eyebrow, color = TextTertiary)
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                color = TextPrimary
            )
            Text(
                text = description,
                style = MaterialTheme.typography.bodySmall,
                color = TextSecondary
            )
            if (content != null) {
                Spacer(Modifier.height(4.dp))
                content()
            }
        }
    }
}

@Composable
private fun ToggleRow(
    label: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyMedium,
            color = TextPrimary
        )
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            colors = SwitchDefaults.colors(
                checkedThumbColor = TextOnAccent,
                checkedTrackColor = Amber,
                uncheckedThumbColor = TextSecondary,
                uncheckedTrackColor = InkSurface,
                uncheckedBorderColor = InkBorder
            )
        )
    }
}

private fun schedulePeriodicUpdate(context: android.content.Context, url: String) {
    val data = Data.Builder()
        .putString("update_url", url)
        .build()
    val request = PeriodicWorkRequestBuilder<SpamDbUpdateWorker>(24, TimeUnit.HOURS)
        .setInputData(data)
        .build()
    WorkManager.getInstance(context).enqueueUniquePeriodicWork(
        "spam_db_update",
        androidx.work.ExistingPeriodicWorkPolicy.KEEP,
        request
    )
}
