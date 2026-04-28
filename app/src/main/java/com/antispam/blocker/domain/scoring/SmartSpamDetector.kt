package com.antispam.blocker.domain.scoring

import android.content.Context
import android.telecom.Call
import com.antispam.blocker.data.db.dao.CallRecordDao
import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.data.repository.BlockListRepository
import com.antispam.blocker.domain.detector.Verdict
import com.antispam.blocker.domain.model.SpamModel
import kotlinx.coroutines.flow.first

class SmartSpamDetector(
    private val context: Context,
    private val blockListRepo: BlockListRepository,
    private val callRecordDao: CallRecordDao,
    private val settings: SettingsStore,
    private val featureExtractor: FeatureExtractor,
    private val feedbackStore: com.antispam.blocker.data.prefs.FeedbackLearningStore
) {
    private val spamModel: SpamModel by lazy {
        SpamModel(context).also {
            it.loadModel()
        }
    }

    suspend fun score(
        number: String?,
        isHidden: Boolean,
        callDetails: Call.Details?,
        profileVector: UserProfileVector
    ): RiskScore {
        val warnThreshold = (feedbackStore.warnThreshold.first() * 100).toInt()
        val blockThreshold = (feedbackStore.blockThreshold.first() * 100).toInt()

        if (!settings.protectionEnabled.first()) {
            return RiskScore(
                score = 0, level = RiskLevel.SAFE, verdict = Verdict.ALLOW,
                reasons = emptyList(), confidence = RiskScore.Confidence.LOW, source = "disabled",
                warnThreshold = warnThreshold, blockThreshold = blockThreshold
            )
        }

        // Emergency whitelist: never block emergency numbers
        if (number != null && isEmergencyNumber(number)) {
            return RiskScore(
                score = 0, level = RiskLevel.SAFE, verdict = Verdict.ALLOW,
                reasons = listOf("Экстренная служба"),
                confidence = RiskScore.Confidence.HIGH, source = "emergency_whitelist",
                activeFactorIds = listOf("emergency"),
                warnThreshold = warnThreshold, blockThreshold = blockThreshold
            )
        }

        // Absolute lists checked BEFORE model
        if (number != null) {
            if (blockListRepo.isAllowed(number)) {
                return RiskScore(
                    score = 0, level = RiskLevel.SAFE, verdict = Verdict.ALLOW,
                    reasons = listOf("В белом списке"),
                    confidence = RiskScore.Confidence.HIGH, source = "allowlist",
                    activeFactorIds = listOf("allowlist"),
                    warnThreshold = warnThreshold, blockThreshold = blockThreshold
                )
            }
            if (blockListRepo.isBlocked(number)) {
                return RiskScore(
                    score = 100, level = RiskLevel.DANGEROUS, verdict = Verdict.BLOCK,
                    reasons = listOf("В чёрном списке"),
                    confidence = RiskScore.Confidence.HIGH, source = "blacklist",
                    activeFactorIds = listOf("blacklist"),
                    warnThreshold = warnThreshold, blockThreshold = blockThreshold
                )
            }
        }

        // Extract features
        val features = featureExtractor.extract(number, isHidden, callDetails, profileVector)
        val factors = evaluateFactors(features, profileVector)
        val activeFactors = factors.filter { it.isActive }
        val activeReasons = activeFactors.map { it.reason }
        val activeIds = activeFactors.map { it.id }

        val learnedWeights = feedbackStore.getAllWeights()
        val ruleTotalScore = activeFactors.sumOf { factor ->
            val learnedWeight = learnedWeights[factor.id] ?: factor.weight
            (factor.points * learnedWeight).toInt()
        }.coerceIn(0, 100)

        // Try TFLite model first
        val modelResult = spamModel.predict(features)
        if (modelResult != null) {
            return modelResult.copy(
                reasons = activeReasons.ifEmpty { modelResult.reasons },
                activeFactorIds = activeIds,
                ruleScore = ruleTotalScore,
                warnThreshold = warnThreshold,
                blockThreshold = blockThreshold
            )
        }

        // Fallback: rule-based scoring
        val level = when {
            ruleTotalScore >= 70 -> RiskLevel.DANGEROUS
            ruleTotalScore >= 35 -> RiskLevel.SUSPICIOUS
            else -> RiskLevel.SAFE
        }

        val verdict = when {
            ruleTotalScore >= blockThreshold -> Verdict.BLOCK
            ruleTotalScore >= warnThreshold -> Verdict.WARN
            else -> Verdict.ALLOW
        }

        val confidence = when {
            activeFactors.any { it.id == "blacklist" || it.id == "allowlist" } -> RiskScore.Confidence.HIGH
            activeFactors.size >= 3 -> RiskScore.Confidence.MEDIUM
            else -> RiskScore.Confidence.LOW
        }

        return RiskScore(
            score = ruleTotalScore,
            level = level,
            verdict = verdict,
            reasons = activeReasons,
            confidence = confidence,
            source = "rule_engine",
            ruleScore = ruleTotalScore,
            activeFactorIds = activeIds,
            warnThreshold = warnThreshold,
            blockThreshold = blockThreshold
        )
    }

    private fun evaluateFactors(features: CallFeatures, profile: UserProfileVector): List<RiskFactor> {
        val vulnerabilityMultiplier = 1f + (profile.vulnerabilityScore / 200f)
        val businessMultiplier = 1f - (profile.businessActivity / 300f)

        return listOf(
            RiskFactor(
                id = "hidden_number",
                displayName = "Скрытый номер",
                points = 50,
                reason = "Скрытый номер",
                weight = vulnerabilityMultiplier
            ).takeIf { features.hiddenNumber },
            RiskFactor(
                id = "not_contact",
                displayName = "Не в контактах",
                points = 20,
                reason = "Не в контактах",
                weight = if (features.contactsAvailable) 1f else 0.5f
            ).takeIf { !features.isContact && !features.hiddenNumber },
            RiskFactor(
                id = "russian_unknown",
                displayName = "Неизвестный +7",
                points = 15,
                reason = "Неизвестный российский номер",
                weight = businessMultiplier
            ).takeIf { features.isRussianNumber && !features.isContact },
            RiskFactor(
                id = "foreign_number",
                displayName = "Иностранный номер",
                points = 10,
                reason = "Иностранный номер",
                weight = if (profile.hasForeignContacts) 0.3f else 1f
            ).takeIf { features.isForeignNumber },
            RiskFactor(
                id = "short_code",
                displayName = "Короткий номер",
                points = 5,
                reason = "Короткий номер",
                weight = if (profile.hasHomePhone) 0.3f else 0.7f
            ).takeIf { features.isShortCode },
            RiskFactor(
                id = "spoofing_prefix",
                displayName = "Имитация российского префикса",
                points = 55,
                reason = "Номер похож на подмену российского кода",
                weight = vulnerabilityMultiplier
            ).takeIf { features.spoofingPrefixFlag },
            RiskFactor(
                id = "invalid_ru_range",
                displayName = "Неизвестный диапазон РФ",
                points = 15,
                reason = "Номер не похож на валидный диапазон РФ",
                weight = businessMultiplier
            ).takeIf { features.isRussianNumber && !features.isValidRuRange && !features.isShortCode },
            RiskFactor(
                id = "tollfree_8800",
                displayName = "Федеральный 8-800",
                points = 8,
                reason = "Федеральный номер 8-800",
                weight = if (features.inAllowlist) 0f else 0.7f
            ).takeIf { features.isTollFree8800 },
            RiskFactor(
                id = "beautiful_number",
                displayName = "Шаблонный номер",
                points = 10,
                reason = "Номер содержит повторяющийся цифровой паттерн",
                weight = businessMultiplier
            ).takeIf { features.beautifulNumberFlag && !features.inAllowlist },
            RiskFactor(
                id = "reputation_score",
                displayName = "Репутационный риск",
                points = (features.reputationScore * 45).toInt(),
                reason = "Репутационные признаки номера повышают риск",
                weight = 1f
            ).takeIf { features.reputationScore > 0.45f && !features.inAllowlist },
            RiskFactor(
                id = "prefix_risk",
                displayName = "Подозрительный префикс",
                points = (features.prefixRisk * 25).toInt(),
                reason = "Подозрительный префикс номера",
                weight = businessMultiplier
            ).takeIf { features.prefixRisk > 0.3f },
            RiskFactor(
                id = "night_time",
                displayName = "Ночное время",
                points = 20,
                reason = "Звонок в ночное время",
                weight = vulnerabilityMultiplier
            ).takeIf { features.isNightTime },
            RiskFactor(
                id = "recent_bank_app",
                displayName = "Недавно в банковском приложении",
                points = 25,
                reason = "Вы недавно были в банковском приложении",
                weight = (profile.digitalActivity / 100f).coerceIn(0.3f, 1.5f)
            ).takeIf { features.recentBankApp },
            RiskFactor(
                id = "recent_gov_app",
                displayName = "Недавно в Госуслугах",
                points = 15,
                reason = "Вы недавно были в Госуслугах",
                weight = (profile.digitalActivity / 100f).coerceIn(0.3f, 1.2f)
            ).takeIf { features.recentGovApp },
            RiskFactor(
                id = "recent_marketplace",
                displayName = "Недавно в маркетплейсе",
                points = 10,
                reason = "Вы недавно были в маркетплейсе",
                weight = (profile.adsActivity / 100f).coerceIn(0.2f, 1f)
            ).takeIf { features.recentMarketplaceApp },
            RiskFactor(
                id = "call_frequency",
                displayName = "Частые звонки",
                points = (features.callFrequency * 30).toInt(),
                reason = "Частые повторные звонки",
                weight = 1f
            ).takeIf { features.callFrequency > 0.5f },
            RiskFactor(
                id = "previously_rejected",
                displayName = "Ранее отклонён",
                points = 15,
                reason = "Вы ранее отклоняли этот номер",
                weight = 1f
            ).takeIf { features.previouslyRejected },
            RiskFactor(
                id = "caller_verify_failed",
                displayName = "Номер не прошёл проверку",
                points = 30,
                reason = "Номер не прошёл проверку оператора",
                weight = vulnerabilityMultiplier
            ).takeIf { features.callerVerifyFailed }
        ).filterNotNull()
    }

    private fun isEmergencyNumber(number: String): Boolean {
        val cleaned = number.replace(Regex("[^\\d]"), "")
        return cleaned in EMERGENCY_NUMBERS
    }

    companion object {
        private val EMERGENCY_NUMBERS = setOf("112", "101", "102", "103", "104")
    }
}
