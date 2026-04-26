package com.antispam.blocker.domain.detector

import android.telecom.Call
import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.domain.detector.rules.*
import kotlinx.coroutines.flow.first

data class DetectionResult(
    val verdict: Verdict,
    val ruleName: String?
)

class SpamDetector(
    private val rules: List<Rule>,
    private val settings: SettingsStore
) {

    suspend fun detect(number: String?, isHidden: Boolean, callDetails: Call.Details? = null): DetectionResult {
        if (!settings.protectionEnabled.first()) {
            return DetectionResult(Verdict.ALLOW, null)
        }

        for (rule in rules) {
            val result = rule.check(number, isHidden, callDetails)
            if (result != null) {
                return DetectionResult(result.verdict, result.ruleName)
            }
        }

        return DetectionResult(Verdict.ALLOW, null)
    }
}
