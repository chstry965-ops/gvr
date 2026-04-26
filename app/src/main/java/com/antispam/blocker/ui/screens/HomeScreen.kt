package com.antispam.blocker.ui.screens

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.antispam.blocker.SpamBlockerApp
import com.antispam.blocker.ui.components.GlassCard
import com.antispam.blocker.ui.components.HeroBackground
import com.antispam.blocker.ui.components.MetricCounter
import com.antispam.blocker.ui.components.MonoLabelText
import com.antispam.blocker.ui.components.StatusPill
import com.antispam.blocker.ui.theme.*
import com.antispam.blocker.util.RoleManagerHelper
import kotlinx.coroutines.launch
import java.util.Calendar

@Preview(showBackground = true, backgroundColor = 0xFF0A0A0B)
@Composable
fun HomeScreenPreview() {
    SpamBlockerTheme {
        HomeScreen(
            protectionEnabled = true,
            isRoleHeld = true,
            canDrawOverlay = true,
            blockedToday = 12,
            warnedToday = 5,
            onProtectionChanged = {},
            onRequestOverlay = {}
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    protectionEnabled: Boolean,
    isRoleHeld: Boolean,
    canDrawOverlay: Boolean,
    blockedToday: Int,
    warnedToday: Int,
    onProtectionChanged: (Boolean) -> Unit,
    onRequestOverlay: () -> Unit
) {
    val isActive = protectionEnabled && isRoleHeld

    val statusColor by animateColorAsState(
        targetValue = when {
            isActive -> Amber
            !isRoleHeld -> BlockRed
            else -> TextTertiary
        },
        animationSpec = tween(500),
        label = "status_color"
    )

    val infinite = rememberInfiniteTransition(label = "hero_pulse")
    val pulse by infinite.animateFloat(
        initialValue = 1f,
        targetValue = if (isActive) 1.08f else 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(2200, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "pulse"
    )

    Scaffold(
        containerColor = Ink,
        contentWindowInsets = WindowInsets(0)
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 24.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp)
        ) {
            // --- Top brand row ---
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    MonoLabelText(text = "SENTINEL • v2.0", color = TextTertiary)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = "Antispam",
                        style = MaterialTheme.typography.headlineLarge,
                        color = TextPrimary
                    )
                }
                StatusPill(
                    text = when {
                        isActive -> "active"
                        !isRoleHeld -> "unassigned"
                        else -> "paused"
                    },
                    color = statusColor
                )
            }

            // --- Hero status card ---
            HeroBackground(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 320.dp)
            ) {
                if (isActive) {
                    Box(
                        modifier = Modifier
                            .align(Alignment.Center)
                            .size(260.dp)
                            .scale(pulse)
                            .background(
                                Brush.radialGradient(
                                    0f to AmberGlow,
                                    1f to Color.Transparent
                                ),
                                shape = CircleShape
                            )
                    )
                }

                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(24.dp),
                    verticalArrangement = Arrangement.SpaceBetween
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        MonoLabelText(text = "// CALL SCREENING", color = TextTertiary)
                        Switch(
                            checked = protectionEnabled,
                            onCheckedChange = onProtectionChanged,
                            colors = SwitchDefaults.colors(
                                checkedThumbColor = TextOnAccent,
                                checkedTrackColor = Amber,
                                uncheckedThumbColor = TextSecondary,
                                uncheckedTrackColor = InkSurface,
                                uncheckedBorderColor = InkBorder
                            )
                        )
                    }

                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 12.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Box(
                            modifier = Modifier
                                .size(104.dp)
                                .clip(CircleShape)
                                .background(statusColor.copy(alpha = 0.12f))
                                .border(1.dp, statusColor.copy(alpha = 0.4f), CircleShape),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = Icons.Default.Shield,
                                contentDescription = null,
                                tint = statusColor,
                                modifier = Modifier.size(48.dp)
                            )
                        }
                    }

                    Column {
                        Text(
                            text = when {
                                isActive -> "Защита активна"
                                !isRoleHeld -> "Не назначен фильтром"
                                else -> "Защита приостановлена"
                            },
                            style = MaterialTheme.typography.headlineMedium,
                            color = TextPrimary
                        )
                        Spacer(Modifier.height(6.dp))
                        Text(
                            text = when {
                                isActive -> "Входящие звонки проверяются по 9 правилам в реальном времени."
                                !isRoleHeld -> "Назначьте приложение фильтром в системных настройках Android."
                                else -> "Включите защиту, чтобы начать блокировать спам-звонки."
                            },
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextSecondary
                        )
                    }
                }
            }

            // --- Stats grid ---
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                MetricCounter(
                    value = blockedToday,
                    label = "ЗАБЛОКИРОВАНО / 24Ч",
                    color = BlockRed,
                    modifier = Modifier.weight(1f)
                )
                MetricCounter(
                    value = warnedToday,
                    label = "ПОДОЗРИТЕЛЬНЫХ / 24Ч",
                    color = WarnAmber,
                    modifier = Modifier.weight(1f)
                )
            }

            // --- Warning card if role is not held ---
            if (!isRoleHeld) {
                GlassCard(
                    modifier = Modifier.fillMaxWidth(),
                    accentBorder = true
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Warning,
                            contentDescription = null,
                            tint = Amber,
                            modifier = Modifier.size(22.dp)
                        )
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(
                                text = "Требуется действие",
                                style = MaterialTheme.typography.titleSmall,
                                color = TextPrimary
                            )
                            Text(
                                text = "Настройки Android → Приложения → По умолчанию → Фильтр и идентификация звонков",
                                style = MaterialTheme.typography.bodySmall,
                                color = TextSecondary
                            )
                        }
                    }
                }
            }

            // --- Warning card if overlay permission is missing ---
            if (!canDrawOverlay) {
                GlassCard(
                    modifier = Modifier.fillMaxWidth(),
                    accentBorder = true
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Icon(
                                imageVector = Icons.Default.Warning,
                                contentDescription = null,
                                tint = WarnAmber,
                                modifier = Modifier.size(22.dp)
                            )
                            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text(
                                    text = "Включите плашку поверх звонка",
                                    style = MaterialTheme.typography.titleSmall,
                                    color = TextPrimary
                                )
                                Text(
                                    text = "Без этого разрешения предупреждение о подозрительном звонке не появится поверх экрана входящего вызова.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = TextSecondary
                                )
                            }
                        }
                        Button(
                            onClick = onRequestOverlay,
                            modifier = Modifier.fillMaxWidth(),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Amber,
                                contentColor = TextOnAccent
                            ),
                            shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)
                        ) {
                            Text("Открыть настройки")
                        }
                    }
                }
            }

            // --- Footer tagline ---
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center
            ) {
                MonoLabelText(
                    text = "OFFLINE FIRST  •  NO TELEMETRY  •  RU",
                    color = TextTertiary
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen() {
    val context = LocalContext.current
    val app = SpamBlockerApp.instance
    val settings = app.settingsStore
    val callLogRepo = remember {
        com.antispam.blocker.data.repository.CallLogRepository(app.database.callRecordDao())
    }

    val protectionEnabled by settings.protectionEnabled.collectAsState(initial = true)
    val isRoleHeld = remember { RoleManagerHelper.isCallScreeningRoleHeld(context) }

    // Проверка overlay-разрешения обновляется при возврате из настроек.
    // Перечитываем при каждом resume активити.
    var canDrawOverlay by remember {
        mutableStateOf(android.provider.Settings.canDrawOverlays(context))
    }
    androidx.compose.runtime.DisposableEffect(Unit) {
        val activity = context as? android.app.Activity
        val lifecycle = (activity as? androidx.lifecycle.LifecycleOwner)?.lifecycle
        val observer = androidx.lifecycle.LifecycleEventObserver { _, event ->
            if (event == androidx.lifecycle.Lifecycle.Event.ON_RESUME) {
                canDrawOverlay = android.provider.Settings.canDrawOverlays(context)
            }
        }
        lifecycle?.addObserver(observer)
        onDispose { lifecycle?.removeObserver(observer) }
    }

    val startOfDay = remember {
        val cal = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, 0)
            set(Calendar.MINUTE, 0)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        cal.timeInMillis
    }

    val blockedToday by callLogRepo.blockedCountSince(startOfDay).collectAsState(initial = 0)
    val warnedToday by callLogRepo.warnedCountSince(startOfDay).collectAsState(initial = 0)

    val scope = rememberCoroutineScope()

    HomeScreen(
        protectionEnabled = protectionEnabled,
        isRoleHeld = isRoleHeld,
        canDrawOverlay = canDrawOverlay,
        blockedToday = blockedToday,
        warnedToday = warnedToday,
        onProtectionChanged = { enabled ->
            scope.launch { settings.set("protection_enabled", enabled) }
        },
        onRequestOverlay = {
            val intent = android.content.Intent(
                android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                android.net.Uri.parse("package:${context.packageName}")
            ).apply {
                addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            try {
                context.startActivity(intent)
            } catch (_: Exception) {
                // fallback — общие настройки оверлея
                context.startActivity(
                    android.content.Intent(android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION)
                        .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                )
            }
        }
    )
}

