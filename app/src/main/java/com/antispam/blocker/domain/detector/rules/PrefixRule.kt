package com.antispam.blocker.domain.detector.rules

import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.domain.detector.Verdict
import kotlinx.coroutines.flow.first

class PrefixRule(private val settings: SettingsStore) : Rule {

    override val name = "prefix"

    override suspend fun check(number: String?, isHidden: Boolean, callDetails: android.telecom.Call.Details?): RuleResult? {
        if (!settings.blockPrefixes.first()) return null
        if (number == null) return null

        val prefixes = settings.prefixList.first()
        val action = settings.prefixAction.first()

        for (prefix in prefixes) {
            if (number.startsWith(prefix)) {
                return RuleResult(action, name)
            }
        }
        return null
    }
}
