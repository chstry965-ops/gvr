package com.antispam.blocker.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.antispam.blocker.SpamBlockerApp
import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.domain.detector.Verdict
import com.antispam.blocker.ui.components.GlassCard
import com.antispam.blocker.ui.components.MonoLabelText
import com.antispam.blocker.ui.components.SectionHeader
import com.antispam.blocker.ui.theme.*
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RulesScreen() {
    val app = SpamBlockerApp.instance
    val settings = app.settingsStore
    val scope = rememberCoroutineScope()

    val contactsAllowEnabled by settings.contactsAllowEnabled.collectAsState(initial = true)
    val blockHiddenNumbers by settings.blockHiddenNumbers.collectAsState(initial = true)
    val hiddenNumberAction by settings.hiddenNumberAction.collectAsState(initial = Verdict.WARN)
    val blockStirFailed by settings.blockStirFailed.collectAsState(initial = true)
    val stirFailedAction by settings.stirFailedAction.collectAsState(initial = Verdict.BLOCK)
    val blockPrefixes by settings.blockPrefixes.collectAsState(initial = true)
    val prefixAction by settings.prefixAction.collectAsState(initial = Verdict.WARN)
    val prefixList by settings.prefixList.collectAsState(initial = SettingsStore.DEFAULT_PREFIXES)
    val rateLimitEnabled by settings.rateLimitEnabled.collectAsState(initial = true)
    val rateLimitCount by settings.rateLimitCount.collectAsState(initial = 3)
    val rateLimitMinutes by settings.rateLimitMinutes.collectAsState(initial = 5)
    val rateLimitAction by settings.rateLimitAction.collectAsState(initial = Verdict.WARN)
    val blockShortNumbers by settings.blockShortNumbers.collectAsState(initial = true)
    val shortNumberAction by settings.shortNumberAction.collectAsState(initial = Verdict.WARN)
    val blockLongNumbers by settings.blockLongNumbers.collectAsState(initial = true)
    val longNumberAction by settings.longNumberAction.collectAsState(initial = Verdict.WARN)

    Scaffold(
        containerColor = Ink,
        contentWindowInsets = WindowInsets(0)
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 24.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            item {
                SectionHeader(
                    eyebrow = "// DETECTION PIPELINE",
                    title = "Правила"
                )
                Spacer(Modifier.height(4.dp))
                MonoLabelText(
                    text = "9 rules • executed in order",
                    color = TextTertiary
                )
                Spacer(Modifier.height(12.dp))
            }

            item {
                RuleCard(
                    index = 1,
                    title = "Контакты",
                    description = "Номера из контактов всегда разрешены",
                    checked = contactsAllowEnabled,
                    onCheckedChange = { scope.launch { settings.set("contacts_allow_enabled", it) } },
                    showAction = false,
                    alwaysAllow = true
                )
            }
            item {
                RuleCard(
                    index = 2,
                    title = "Скрытые номера",
                    description = "Номера без определителя",
                    checked = blockHiddenNumbers,
                    onCheckedChange = { scope.launch { settings.set("block_hidden_numbers", it) } },
                    action = hiddenNumberAction,
                    onActionChange = { scope.launch { settings.set("hidden_number_action", it) } }
                )
            }
            item {
                RuleCard(
                    index = 3,
                    title = "STIR/SHAKEN",
                    description = "Блокировать номера с проваленной криптографической проверкой (спуфинг)",
                    checked = blockStirFailed,
                    onCheckedChange = { scope.launch { settings.set("block_stir_failed", it) } },
                    action = stirFailedAction,
                    onActionChange = { scope.launch { settings.set("stir_failed_action", it) } }
                )
            }
            item {
                RuleCard(
                    index = 4,
                    title = "Подозрительные префиксы",
                    description = "Номера, начинающиеся с: ${prefixList.joinToString(", ")}",
                    checked = blockPrefixes,
                    onCheckedChange = { scope.launch { settings.set("block_prefixes", it) } },
                    action = prefixAction,
                    onActionChange = { scope.launch { settings.set("prefix_action", it) } }
                )
            }
            item {
                RuleCard(
                    index = 5,
                    title = "Повторные звонки",
                    description = "≥$rateLimitCount звонков за $rateLimitMinutes мин от одного номера",
                    checked = rateLimitEnabled,
                    onCheckedChange = { scope.launch { settings.set("rate_limit_enabled", it) } },
                    action = rateLimitAction,
                    onActionChange = { scope.launch { settings.set("rate_limit_action", it) } }
                )
            }
            item {
                RuleCard(
                    index = 6,
                    title = "Короткие номера (1–6 цифр)",
                    description = "Слишком короткие номера, обычно мошеннические",
                    checked = blockShortNumbers,
                    onCheckedChange = { scope.launch { settings.set("block_short_numbers", it) } },
                    action = shortNumberAction,
                    onActionChange = { scope.launch { settings.set("short_number_action", it) } }
                )
            }
            item {
                RuleCard(
                    index = 7,
                    title = "Длинные номера (>15 цифр)",
                    description = "Нестандартно длинные номера",
                    checked = blockLongNumbers,
                    onCheckedChange = { scope.launch { settings.set("block_long_numbers", it) } },
                    action = longNumberAction,
                    onActionChange = { scope.launch { settings.set("long_number_action", it) } }
                )
            }
        }
    }
}

@Composable
private fun RuleCard(
    index: Int,
    title: String,
    description: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    showAction: Boolean = true,
    action: Verdict = Verdict.WARN,
    onActionChange: (Verdict) -> Unit = {},
    alwaysAllow: Boolean = false
) {
    GlassCard(
        modifier = Modifier.fillMaxWidth(),
        accentBorder = checked
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    MonoLabelText(
                        text = "RULE ${index.toString().padStart(2, '0')}",
                        color = if (checked) Amber else TextTertiary
                    )
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
                }
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

            if (alwaysAllow && checked) {
                VerdictTag(label = "Разрешать", color = AllowGreen)
            } else if (showAction && checked) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    VerdictChip(
                        label = "Блокировать",
                        value = Verdict.BLOCK,
                        selected = action,
                        color = BlockRed,
                        onSelect = onActionChange,
                        modifier = Modifier.weight(1f)
                    )
                    VerdictChip(
                        label = "Предупредить",
                        value = Verdict.WARN,
                        selected = action,
                        color = WarnAmber,
                        onSelect = onActionChange,
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }
    }
}

@Composable
private fun VerdictChip(
    label: String,
    value: Verdict,
    selected: Verdict,
    color: androidx.compose.ui.graphics.Color,
    onSelect: (Verdict) -> Unit,
    modifier: Modifier = Modifier
) {
    val isSelected = selected == value
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(10.dp),
        color = if (isSelected) color.copy(alpha = 0.14f) else androidx.compose.ui.graphics.Color.Transparent,
        border = BorderStroke(
            1.dp,
            if (isSelected) color.copy(alpha = 0.5f) else InkBorder
        ),
        onClick = { onSelect(value) }
    ) {
        Box(
            modifier = Modifier.padding(vertical = 10.dp),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.labelLarge,
                color = if (isSelected) color else TextSecondary
            )
        }
    }
}

@Composable
private fun VerdictTag(label: String, color: androidx.compose.ui.graphics.Color) {
    Surface(
        shape = RoundedCornerShape(10.dp),
        color = color.copy(alpha = 0.14f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.5f))
    ) {
        Text(
            text = label,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
            style = MaterialTheme.typography.labelLarge,
            color = color
        )
    }
}
