package com.antispam.blocker.notification

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import com.antispam.blocker.MainActivity
import com.antispam.blocker.R

/**
 * Показывает уведомления о входящих подозрительных/заблокированных звонках.
 *
 * Для того чтобы уведомление реально появилось ПОВЕРХ системного incoming call UI,
 * используется:
 *  - отдельный канал с IMPORTANCE_HIGH
 *  - CATEGORY_CALL + PRIORITY_MAX
 *  - setFullScreenIntent(...) — единственный способ показать нотификацию поверх
 *    активного звонка на современных Android (требует USE_FULL_SCREEN_INTENT).
 *  - уникальный notificationId для каждого звонка — чтобы подряд идущие
 *    уведомления не перетирали друг друга.
 */
class SpamWarningNotifier(private val context: Context) {

    companion object {
        const val CHANNEL_WARN = "spam_warning_channel"
        const val CHANNEL_BLOCK = "spam_blocked_channel"

        const val ACTION_BLOCK = "com.antispam.blocker.ACTION_BLOCK"
        const val ACTION_ALLOW = "com.antispam.blocker.ACTION_ALLOW"
        const val EXTRA_NUMBER = "extra_number"
        const val EXTRA_NOTIF_ID = "extra_notif_id"
    }

    private val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

    init {
        createChannels()
    }

    private fun createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return

        val warnChannel = NotificationChannel(
            CHANNEL_WARN,
            "Подозрительные звонки",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Предупреждения о подозрительных входящих звонках"
            enableVibration(true)
            enableLights(true)
            lightColor = Color.rgb(0xFF, 0x6B, 0x1A)
            setBypassDnd(true)
            lockscreenVisibility = NotificationCompat.VISIBILITY_PUBLIC
        }

        val blockChannel = NotificationChannel(
            CHANNEL_BLOCK,
            "Заблокированные звонки",
            NotificationManager.IMPORTANCE_DEFAULT
        ).apply {
            description = "Информация о заблокированных звонках"
            enableVibration(false)
            lockscreenVisibility = NotificationCompat.VISIBILITY_PUBLIC
        }

        nm.createNotificationChannel(warnChannel)
        nm.createNotificationChannel(blockChannel)
    }

    /**
     * Уведомление о подозрительном звонке. Показывается как heads-up поверх
     * incoming call UI через FullScreenIntent.
     */
    fun showWarning(number: String, ruleName: String? = null) {
        val notifId = generateId(number)

        val blockPending = buildActionIntent(ACTION_BLOCK, number, notifId, requestCode = notifId * 10)
        val allowPending = buildActionIntent(ACTION_ALLOW, number, notifId, requestCode = notifId * 10 + 1)
        val contentPending = buildContentIntent(notifId * 10 + 2)

        val subtitle = ruleName?.let { "• $it" } ?: "Проверено по правилам"

        val notification = NotificationCompat.Builder(context, CHANNEL_WARN)
            .setSmallIcon(R.drawable.ic_warning)
            .setContentTitle("Подозрение на спам")
            .setContentText("Звонок от $number  $subtitle")
            .setStyle(
                NotificationCompat.BigTextStyle()
                    .bigText("Звонок от $number\n$subtitle\n\nЕсли это важный звонок — нажмите «Это не спам».")
            )
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setColor(Color.rgb(0xFF, 0x6B, 0x1A))
            .setColorized(true)
            .setAutoCancel(true)
            .setOngoing(false)
            .setFullScreenIntent(contentPending, true)
            .setContentIntent(contentPending)
            .addAction(0, "В чёрный список", blockPending)
            .addAction(0, "Это не спам", allowPending)
            .setVibrate(longArrayOf(0, 300, 200, 300))
            .build()

        nm.notify(notifId, notification)
    }

    /**
     * Уведомление о заблокированном звонке (после того как звонок уже отклонён).
     * Показывается в обычном режиме + даёт возможность вернуть номер в белый список.
     */
    fun showBlocked(number: String, ruleName: String? = null) {
        val notifId = generateId(number) + 1_000_000 // отдельный диапазон для blocked

        val allowPending = buildActionIntent(ACTION_ALLOW, number, notifId, requestCode = notifId * 10 + 3)
        val contentPending = buildContentIntent(notifId * 10 + 4)

        val subtitle = ruleName?.let { "• $it" } ?: ""

        val notification = NotificationCompat.Builder(context, CHANNEL_BLOCK)
            .setSmallIcon(R.drawable.ic_warning)
            .setContentTitle("Звонок заблокирован")
            .setContentText("$number  $subtitle")
            .setStyle(
                NotificationCompat.BigTextStyle()
                    .bigText("Заблокирован звонок от $number\n$subtitle\n\nЕсли это ошибка — добавьте номер в белый список.")
            )
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setColor(Color.rgb(0xFF, 0x4D, 0x6D))
            .setAutoCancel(true)
            .setContentIntent(contentPending)
            .addAction(0, "Это не спам", allowPending)
            .build()

        nm.notify(notifId, notification)
    }

    private fun buildActionIntent(
        action: String,
        number: String,
        notifId: Int,
        requestCode: Int
    ): PendingIntent {
        val intent = Intent(context, SpamActionReceiver::class.java).apply {
            this.action = action
            // Уникальный data URI — иначе PendingIntent переиспользует старый intent с чужим номером
            data = Uri.parse("antispam://call/$notifId")
            putExtra(EXTRA_NUMBER, number)
            putExtra(EXTRA_NOTIF_ID, notifId)
        }
        return PendingIntent.getBroadcast(
            context, requestCode, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    private fun buildContentIntent(requestCode: Int): PendingIntent {
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        return PendingIntent.getActivity(
            context, requestCode, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    /** Стабильный id на основе номера и времени, в диапазоне int. */
    private fun generateId(number: String): Int {
        val base = (System.currentTimeMillis() / 1000).toInt() and 0x0000FFFF
        val hash = number.hashCode() and 0x0000FFFF
        return (base xor hash) and 0x0FFFFFFF
    }
}
