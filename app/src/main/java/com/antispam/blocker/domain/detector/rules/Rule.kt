package com.antispam.blocker.domain.detector.rules

import android.telecom.Call
import com.antispam.blocker.domain.detector.Verdict

data class RuleResult(
    val verdict: Verdict,
    val ruleName: String
)

interface Rule {
    val name: String
    suspend fun check(number: String?, isHidden: Boolean, callDetails: Call.Details? = null): RuleResult?
}
