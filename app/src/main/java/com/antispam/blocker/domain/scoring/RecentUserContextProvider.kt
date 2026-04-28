package com.antispam.blocker.domain.scoring

import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.os.Process
import android.util.Log

class RecentUserContextProvider(private val context: Context) {

    data class RecentContext(
        val recentBankApp: Boolean = false,
        val recentGovApp: Boolean = false,
        val recentMarketplaceApp: Boolean = false,
        val recentMessengerApp: Boolean = false
    )

    fun isUsageAccessGranted(): Boolean {
        val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.checkOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            Process.myUid(),
            context.packageName
        )
        return mode == AppOpsManager.MODE_ALLOWED
    }

    fun getRecentContext(lookbackMs: Long = 30 * 60_000L): RecentContext {
        if (!isUsageAccessGranted()) {
            return RecentContext()
        }

        val usageStatsManager = context.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val endTime = System.currentTimeMillis()
        val startTime = endTime - lookbackMs

        val events = usageStatsManager.queryEvents(startTime, endTime)

        val recentPackages = mutableSetOf<String>()
        while (events.hasNextEvent()) {
            val event = UsageEvents.Event()
            events.getNextEvent(event)
            if (event.eventType == UsageEvents.Event.MOVE_TO_FOREGROUND) {
                recentPackages.add(event.packageName)
            }
        }

        return RecentContext(
            recentBankApp = BANK_PACKAGES.any { it in recentPackages },
            recentGovApp = GOV_PACKAGES.any { it in recentPackages },
            recentMarketplaceApp = MARKETPLACE_PACKAGES.any { it in recentPackages },
            recentMessengerApp = MESSENGER_PACKAGES.any { it in recentPackages }
        )
    }

    companion object {
        private val BANK_PACKAGES = setOf(
            "ru.sberbankmobile", "com.idamob.tinkoff.android", "ru.vtb.mobile",
            "ru.alfabank.mobile.android", "ru.gazprombank.mobile", "ru.rshb.v1",
            "ru.mkb.mobile", "ru.psbc.mbank", "ru.rosbank.mobile",
            "ru.otp.mobile", "ru.raiffeisen", "ru.bss.mobile"
        )

        private val GOV_PACKAGES = setOf(
            "ru.rostelecom.gosuslugi", "ru.gosuslugi", "ru.minsvyaz.gosuslugi"
        )

        private val MARKETPLACE_PACKAGES = setOf(
            "com.wildberries.ru", "com.ozon.android", "ru.beru.android",
            "com.sbermarket", "ru.megamarket"
        )

        private val MESSENGER_PACKAGES = setOf(
            "com.whatsapp", "org.telegram.messenger", "com.viber.voip",
            "vk.messenger.android"
        )
    }
}
