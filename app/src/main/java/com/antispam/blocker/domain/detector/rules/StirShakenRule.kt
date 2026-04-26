package com.antispam.blocker.domain.detector.rules

import android.os.Build
import android.telecom.Call
import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.domain.detector.Verdict
import kotlinx.coroutines.flow.first

class StirShakenRule(private val settings: SettingsStore) : Rule {

    override val name = "stir_shaken"

    override suspend fun check(number: String?, isHidden: Boolean, callDetails: Call.Details?): RuleResult? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return null
        if (!settings.blockStirFailed.first()) return null
        if (callDetails == null) return null

        val status = callDetails.callerNumberVerificationStatus
        return if (status == 2) { // 2 is VERIFICATION_STATUS_FAILED
            val action = settings.stirFailedAction.first()
            RuleResult(action, name)
        } else null
    }
}
