package com.antispam.blocker.ui.screens

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.antispam.blocker.SpamBlockerApp
import com.antispam.blocker.data.repository.BlockListRepository
import com.antispam.blocker.ui.components.GlassCard
import com.antispam.blocker.ui.components.MonoLabelText
import com.antispam.blocker.ui.components.SectionHeader
import com.antispam.blocker.ui.components.StatusPill
import com.antispam.blocker.ui.theme.*
import com.antispam.blocker.util.PhoneNormalizer
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BlacklistScreen() {
    val app = SpamBlockerApp.instance
    val repo = remember {
        BlockListRepository(app.database.blockedNumberDao(), app.database.allowedNumberDao(), PhoneNormalizer)
    }
    val scope = rememberCoroutineScope()

    var showWhitelist by remember { mutableStateOf(false) }
    var newNumber by remember { mutableStateOf("") }
    var isRegex by remember { mutableStateOf(false) }

    val blocked by repo.allBlocked.collectAsState(initial = emptyList())
    val allowed by repo.allAllowed.collectAsState(initial = emptyList())

    val list = if (showWhitelist) {
        allowed.map { Triple(it.originalNumber, it.normalizedNumber, null as String?) }
    } else {
        blocked.map { Triple(it.originalNumber, it.normalizedNumber, it.pattern) }
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
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            item {
                SectionHeader(
                    eyebrow = "// LISTS",
                    title = if (showWhitelist) "Белый список" else "Чёрный список"
                )
                Spacer(Modifier.height(16.dp))

                // Segmented toggle
                SegmentedToggle(
                    isWhitelist = showWhitelist,
                    onChange = { showWhitelist = it }
                )
                Spacer(Modifier.height(16.dp))
            }

            if (!showWhitelist) {
                item {
                    AddNumberCard(
                        value = newNumber,
                        onValueChange = { newNumber = it },
                        isRegex = isRegex,
                        onRegexChange = { isRegex = it },
                        onAdd = {
                            if (newNumber.isNotBlank()) {
                                scope.launch {
                                    val pattern = if (isRegex) {
                                        // Маска: оставляем только цифры.
                                        // Regex.containsMatchIn сам ищет подстроку,
                                        // так что "8800" совпадёт с "+78001234567".
                                        val digits = newNumber.filter { it.isDigit() }
                                        if (digits.isBlank()) null else digits
                                    } else null
                                    repo.addToBlockList(newNumber, pattern = pattern)
                                    newNumber = ""
                                }
                            }
                        }
                    )
                    Spacer(Modifier.height(16.dp))
                }
            }

            item {
                MonoLabelText(
                    text = "${list.size} entries",
                    color = TextTertiary
                )
                Spacer(Modifier.height(8.dp))
            }

            if (list.isEmpty()) {
                item {
                    GlassCard(modifier = Modifier.fillMaxWidth()) {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(32.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Text(
                                text = "Список пуст",
                                style = MaterialTheme.typography.titleMedium,
                                color = TextPrimary
                            )
                            Spacer(Modifier.height(4.dp))
                            Text(
                                text = if (showWhitelist)
                                    "Добавьте доверенные номера, которые не будут блокироваться"
                                else "Добавьте номер выше или отметьте звонок в журнале",
                                style = MaterialTheme.typography.bodySmall,
                                color = TextSecondary
                            )
                        }
                    }
                }
            } else {
                items(list, key = { it.second }) { (original, normalized, pattern) ->
                    ListRow(
                        original = original,
                        pattern = pattern,
                        accentColor = if (showWhitelist) AllowGreen else BlockRed,
                        onRemove = {
                            scope.launch {
                                if (showWhitelist) repo.removeFromAllowList(normalized)
                                else repo.removeFromBlockList(normalized)
                            }
                        }
                    )
                }
            }
        }
    }
}

@Composable
private fun SegmentedToggle(
    isWhitelist: Boolean,
    onChange: (Boolean) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(100.dp))
            .border(1.dp, InkBorder, RoundedCornerShape(100.dp))
            .padding(4.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        SegmentChip(
            label = "Чёрный",
            selected = !isWhitelist,
            onClick = { onChange(false) },
            modifier = Modifier.weight(1f)
        )
        SegmentChip(
            label = "Белый",
            selected = isWhitelist,
            onClick = { onChange(true) },
            modifier = Modifier.weight(1f)
        )
    }
}

@Composable
private fun SegmentChip(
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(100.dp),
        color = if (selected) Amber else androidx.compose.ui.graphics.Color.Transparent,
        onClick = onClick
    ) {
        Box(
            modifier = Modifier.padding(vertical = 10.dp),
            contentAlignment = Alignment.Center
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.titleSmall,
                color = if (selected) TextOnAccent else TextSecondary
            )
        }
    }
}

@Composable
private fun AddNumberCard(
    value: String,
    onValueChange: (String) -> Unit,
    isRegex: Boolean,
    onRegexChange: (Boolean) -> Unit,
    onAdd: () -> Unit
) {
    GlassCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            MonoLabelText(text = if (isRegex) "МАСКА НОМЕРА" else "НОМЕР ТЕЛЕФОНА", color = TextTertiary)
            OutlinedTextField(
                value = value,
                onValueChange = { input ->
                    // В режиме маски разрешаем ТОЛЬКО цифры, + и *
                    // В обычном режиме — цифры, +, пробелы, дефисы, скобки
                    val filtered = if (isRegex) {
                        input.filter { it.isDigit() || it == '+' || it == '*' }
                    } else {
                        input.filter { it.isDigit() || it == '+' || it == ' ' || it == '-' || it == '(' || it == ')' }
                    }
                    onValueChange(filtered)
                },
                placeholder = {
                    Text(
                        text = if (isRegex) "8800" else "+7 495 123-45-67",
                        color = TextTertiary
                    )
                },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Amber,
                    unfocusedBorderColor = InkBorder,
                    focusedTextColor = TextPrimary,
                    unfocusedTextColor = TextPrimary,
                    cursorColor = Amber
                ),
                shape = RoundedCornerShape(12.dp)
            )

            // Переключатель режима
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Switch(
                    checked = isRegex,
                    onCheckedChange = onRegexChange,
                    colors = SwitchDefaults.colors(
                        checkedThumbColor = TextOnAccent,
                        checkedTrackColor = Amber,
                        uncheckedThumbColor = TextSecondary,
                        uncheckedTrackColor = InkSurface,
                        uncheckedBorderColor = InkBorder
                    )
                )
                Spacer(Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Режим маски",
                        style = MaterialTheme.typography.titleSmall,
                        color = if (isRegex) Amber else TextPrimary
                    )
                    Text(
                        text = if (isRegex)
                            "Введите часть номера — заблокирует все номера, содержащие эти цифры. Например: 8800 заблокирует +78001234567, 78008889999 и т.п."
                        else
                            "Заблокировать один конкретный номер.",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextSecondary
                    )
                }
            }

            // Большая кнопка добавления — на всю ширину, чтобы юзеру было очевидно
            Button(
                onClick = onAdd,
                enabled = value.isNotBlank(),
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Amber,
                    contentColor = TextOnAccent,
                    disabledContainerColor = InkSurface,
                    disabledContentColor = TextTertiary
                ),
                shape = RoundedCornerShape(12.dp)
            ) {
                Icon(Icons.Rounded.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text(if (isRegex) "Добавить маску" else "Добавить номер")
            }
        }
    }
}

@Composable
private fun ListRow(
    original: String,
    pattern: String?,
    accentColor: androidx.compose.ui.graphics.Color,
    onRemove: () -> Unit
) {
    GlassCard(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                Text(
                    text = original,
                    style = MaterialTheme.typography.titleMedium,
                    color = TextPrimary
                )
                if (pattern != null) {
                    StatusPill(text = "маска", color = accentColor)
                }
            }
            IconButton(onClick = onRemove) {
                Icon(
                    Icons.Rounded.Close,
                    contentDescription = "Удалить",
                    tint = TextTertiary
                )
            }
        }
    }
}
