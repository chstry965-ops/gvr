package com.antispam.blocker.domain.detector.rules

import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.domain.detector.Verdict
import kotlinx.coroutines.flow.first

class LengthRule(private val settings: SettingsStore) : Rule {

    override val name = "length"

    override suspend fun check(number: String?, isHidden: Boolean, callDetails: android.telecom.Call.Details?): RuleResult? {
        if (number == null) return null

        val digitsOnly = number.filter { it.isDigit() }
        val len = digitsOnly.length

        if (settings.blockShortNumbers.first() && len in 1..6) {
            return RuleResult(settings.shortNumberAction.first(), name)
        }

        if (settings.blockLongNumbers.first() && len > 15) {
            return RuleResult(settings.longNumberAction.first(), name)
        }

        return null
    }
}
