package com.antispam.blocker.domain.detector.rules

import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.domain.detector.Verdict
import kotlinx.coroutines.flow.first

class HiddenNumberRule(private val settings: SettingsStore) : Rule {

    override val name = "hidden_number"

    override suspend fun check(number: String?, isHidden: Boolean, callDetails: android.telecom.Call.Details?): RuleResult? {
        if (!settings.blockHiddenNumbers.first()) return null
        if (!isHidden && number != null) return null
        val action = settings.hiddenNumberAction.first()
        return RuleResult(action, name)
    }
}
