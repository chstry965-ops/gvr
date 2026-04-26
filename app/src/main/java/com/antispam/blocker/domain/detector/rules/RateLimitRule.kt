package com.antispam.blocker.domain.detector.rules

import com.antispam.blocker.data.db.dao.CallRecordDao
import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.domain.detector.Verdict
import kotlinx.coroutines.flow.first

class RateLimitRule(
    private val callRecordDao: CallRecordDao,
    private val settings: SettingsStore
) : Rule {

    override val name = "rate_limit"

    override suspend fun check(number: String?, isHidden: Boolean, callDetails: android.telecom.Call.Details?): RuleResult? {
        if (!settings.rateLimitEnabled.first()) return null
        if (number == null) return null

        val maxCount = settings.rateLimitCount.first()
        val minutes = settings.rateLimitMinutes.first()
        val since = System.currentTimeMillis() - (minutes * 60_000L)

        val count = callRecordDao.countByNumberSince(number, since)
        return if (count >= maxCount) {
            RuleResult(settings.rateLimitAction.first(), name)
        } else null
    }
}
