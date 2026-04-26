package com.antispam.blocker.domain.detector.rules

import com.antispam.blocker.data.repository.BlockListRepository
import com.antispam.blocker.domain.detector.Verdict

class BlacklistRule(private val repo: BlockListRepository) : Rule {

    override val name = "blacklist"

    override suspend fun check(number: String?, isHidden: Boolean, callDetails: android.telecom.Call.Details?): RuleResult? {
        if (number == null) return null
        return if (repo.isBlocked(number)) {
            RuleResult(Verdict.BLOCK, name)
        } else null
    }
}
