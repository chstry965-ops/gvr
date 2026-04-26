package com.antispam.blocker.notification

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.antispam.blocker.SpamBlockerApp
import com.antispam.blocker.data.db.entity.BlockedNumber
import com.antispam.blocker.util.PhoneNormalizer
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class SpamActionReceiver : BroadcastReceiver() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onReceive(context: Context, intent: Intent) {
        val number = intent.getStringExtra(SpamWarningNotifier.EXTRA_NUMBER) ?: return
        val notifId = intent.getIntExtra(SpamWarningNotifier.EXTRA_NOTIF_ID, -1)

        val app = SpamBlockerApp.instance
        val repo = com.antispam.blocker.data.repository.BlockListRepository(
            app.database.blockedNumberDao(),
            app.database.allowedNumberDao(),
            PhoneNormalizer
        )

        when (intent.action) {
            SpamWarningNotifier.ACTION_BLOCK -> {
                scope.launch { repo.addToBlockList(number, source = BlockedNumber.Source.REPORT) }
            }
            SpamWarningNotifier.ACTION_ALLOW -> {
                scope.launch {
                    // удалить из чёрного списка (если был) и добавить в белый
                    val normalized = PhoneNormalizer.normalize(number)
                    if (normalized != null) repo.removeFromBlockList(normalized)
                    repo.addToAllowList(number)
                }
            }
        }

        if (notifId > 0) {
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
            nm.cancel(notifId)
        }
    }
}
