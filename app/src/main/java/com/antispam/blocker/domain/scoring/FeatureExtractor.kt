package com.antispam.blocker.domain.scoring

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.telecom.Call
import android.telecom.Connection
import com.antispam.blocker.data.db.dao.CallRecordDao
import com.antispam.blocker.data.repository.BlockListRepository
import com.antispam.blocker.util.PhoneNormalizer
import kotlin.math.ln
import java.util.Calendar

class FeatureExtractor(
    private val context: Context,
    private val callRecordDao: CallRecordDao,
    private val blockListRepo: BlockListRepository? = null
) {
    private val recentContextProvider = RecentUserContextProvider(context)

    suspend fun extract(
        number: String?,
        isHidden: Boolean,
        callDetails: Call.Details?,
        profileVector: UserProfileVector
    ): CallFeatures {
        val normalized = number?.let { PhoneNormalizer.normalize(it) }
        val hasContactsPermission = context.checkSelfPermission(Manifest.permission.READ_CONTACTS) == PackageManager.PERMISSION_GRANTED
        val hasCallLogPermission = context.checkSelfPermission(Manifest.permission.READ_CALL_LOG) == PackageManager.PERMISSION_GRANTED

        val isContact = if (hasContactsPermission && normalized != null) {
            checkIsContact(normalized)
        } else false

        val isRussian = normalized != null && normalized.startsWith("+7")
        val isForeign = normalized != null && !normalized.startsWith("+7") && !normalized.startsWith("8")
        val rawDigits = number?.filter { it.isDigit() }.orEmpty()
        val normalizedDigits = normalized?.filter { it.isDigit() }.orEmpty()
        val isShort = rawDigits.length in 2..6 || normalizedDigits.length in 2..6
        val isStandardLen = normalizedDigits.length == 11 && normalizedDigits.startsWith("7")
        val isTollFree8800 = normalized?.startsWith("+7800") == true || rawDigits.startsWith("8800")
        val defCode = getRuDefCode(normalized)
        val isMobileRu = defCode in 900..999
        val isGeographical = defCode in 300..499
        val isValidRuRange = isShort || isTollFree8800 || isMobileRu || isGeographical
        val spoofingPrefixFlag = isSpoofingPrefix(number, normalized)
        val digitEntropy = calculateDigitEntropy(normalizedDigits.ifBlank { rawDigits })
        val repeatDigitRatio = calculateRepeatDigitRatio(normalizedDigits.ifBlank { rawDigits })
        val maxSameDigitRun = calculateMaxSameDigitRun(normalizedDigits.ifBlank { rawDigits })
        val beautifulNumberFlag = isBeautifulNumber(normalizedDigits.ifBlank { rawDigits })

        val prefixRisk = if (normalized != null) calculatePrefixRisk(normalized) else 0f

        val callFrequency = if (hasCallLogPermission && normalized != null) {
            calculateCallFrequency(normalized)
        } else 0.5f

        val isNight = isNightTime()

        val previouslyRejected = if (hasCallLogPermission && normalized != null) {
            callRecordDao.countByNumberSince(normalized, System.currentTimeMillis() - 24 * 60 * 60_000L) > 0
        } else false

        val callerVerifyFailed = callDetails?.callerNumberVerificationStatus == Connection.VERIFICATION_STATUS_FAILED

        // Recent user context from UsageStats (requires Usage Access permission)
        val recentContext = recentContextProvider.getRecentContext()

        val (vulnerability, business) = profileVector.toFeatureValues()

        val inBlacklist = if (blockListRepo != null && normalized != null) {
            blockListRepo.isBlocked(normalized)
        } else false

        val inAllowlist = if (blockListRepo != null && normalized != null) {
            blockListRepo.isAllowed(normalized)
        } else false
        val reputationScore = calculateLocalReputation(prefixRisk, inBlacklist, inAllowlist, spoofingPrefixFlag, beautifulNumberFlag)
        val sourceConfidence = when {
            inBlacklist || inAllowlist -> 1f
            spoofingPrefixFlag -> 0.85f
            prefixRisk > 0.5f -> 0.65f
            else -> 0.35f
        }

        return CallFeatures(
            isContact = isContact,
            isRussianNumber = isRussian,
            isForeignNumber = isForeign,
            isShortCode = isShort,
            isStandardLen = isStandardLen,
            isTollFree8800 = isTollFree8800,
            isGeographical = isGeographical,
            isMobileRu = isMobileRu,
            isValidRuRange = isValidRuRange,
            spoofingPrefixFlag = spoofingPrefixFlag,
            digitEntropy = digitEntropy,
            repeatDigitRatio = repeatDigitRatio,
            maxSameDigitRun = maxSameDigitRun,
            beautifulNumberFlag = beautifulNumberFlag,
            prefixRisk = prefixRisk,
            callFrequency = callFrequency,
            isNightTime = isNight,
            recentBankApp = recentContext.recentBankApp,
            recentGovApp = recentContext.recentGovApp,
            recentMarketplaceApp = recentContext.recentMarketplaceApp,
            recentMessengerApp = recentContext.recentMessengerApp,
            previouslyRejected = previouslyRejected,
            inBlacklist = inBlacklist,
            inAllowlist = inAllowlist,
            hiddenNumber = isHidden,
            callerVerifyFailed = callerVerifyFailed,
            userVulnerability = vulnerability,
            userBusinessActivity = business,
            contactsAvailable = hasContactsPermission,
            usageAccessAvailable = recentContextProvider.isUsageAccessGranted(),
            reputationScore = reputationScore,
            sourceConfidence = sourceConfidence
        )
    }

    private fun checkIsContact(normalizedNumber: String): Boolean {
        val uri = android.provider.ContactsContract.CommonDataKinds.Phone.CONTENT_URI
        val projection = arrayOf(android.provider.ContactsContract.CommonDataKinds.Phone.NORMALIZED_NUMBER)
        val selection = "${android.provider.ContactsContract.CommonDataKinds.Phone.NORMALIZED_NUMBER} = ?"
        context.contentResolver.query(uri, projection, selection, arrayOf(normalizedNumber), null)?.use { cursor ->
            return cursor.moveToFirst()
        }
        return false
    }

    private fun calculatePrefixRisk(normalized: String): Float {
        val prefix = normalized.take(6)
        return when {
            normalized.startsWith("+84") -> 0.8f
            prefix.startsWith("+7800") -> 0.25f
            prefix.startsWith("+7495") -> 0.4f
            prefix.startsWith("+7499") -> 0.4f
            prefix.startsWith("+7844") -> 0.3f
            prefix.startsWith("+7900") -> 0.65f
            prefix.startsWith("+7958") -> 0.65f
            prefix.startsWith("+7966") -> 0.65f
            prefix.startsWith("+7969") -> 0.65f
            else -> 0.1f
        }
    }

    private suspend fun calculateCallFrequency(normalized: String): Float {
        val since = System.currentTimeMillis() - 5 * 60_000L
        val count = callRecordDao.countByNumberSince(normalized, since)
        return (count / 5f).coerceIn(0f, 1f)
    }

    private fun isNightTime(): Boolean {
        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
        return hour >= 22 || hour < 8
    }

    private fun getRuDefCode(normalized: String?): Int {
        if (normalized == null || !normalized.startsWith("+7")) return -1
        val digits = normalized.filter { it.isDigit() }
        if (digits.length < 4) return -1
        return digits.substring(1, 4).toIntOrNull() ?: -1
    }

    private fun isSpoofingPrefix(raw: String?, normalized: String?): Boolean {
        val cleanedRaw = raw.orEmpty().replace(Regex("[\\s\\-().]"), "")
        val rawDigits = cleanedRaw.filter { it.isDigit() }
        val normalizedDigits = normalized.orEmpty().filter { it.isDigit() }
        return (cleanedRaw.startsWith("+84") && rawDigits.startsWith("8495")) ||
                (rawDigits.startsWith("008495")) ||
                (normalized.orEmpty().startsWith("+84") && normalizedDigits.startsWith("8495"))
    }

    private fun calculateDigitEntropy(digits: String): Float {
        if (digits.isBlank()) return 0f
        val counts = digits.groupingBy { it }.eachCount()
        val entropy = counts.values.sumOf { count ->
            val p = count.toDouble() / digits.length
            -p * (ln(p) / ln(2.0))
        }
        return (entropy / (ln(10.0) / ln(2.0))).toFloat().coerceIn(0f, 1f)
    }

    private fun calculateRepeatDigitRatio(digits: String): Float {
        if (digits.length <= 1) return 0f
        val repeats = (1 until digits.length).count { digits[it] == digits[it - 1] }
        return (repeats.toFloat() / (digits.length - 1)).coerceIn(0f, 1f)
    }

    private fun calculateMaxSameDigitRun(digits: String): Float {
        if (digits.isBlank()) return 0f
        var best = 1
        var current = 1
        for (i in 1 until digits.length) {
            if (digits[i] == digits[i - 1]) {
                current++
                if (current > best) best = current
            } else {
                current = 1
            }
        }
        return (best.toFloat() / digits.length).coerceIn(0f, 1f)
    }

    private fun isBeautifulNumber(digits: String): Boolean {
        if (digits.isBlank()) return false
        val tail = digits.takeLast(7)
        val hasPairPattern = Regex("(\\d{2,3})\\1+").containsMatchIn(tail)
        val hasLongRun = calculateMaxSameDigitRun(tail) >= (4f / tail.length.coerceAtLeast(1))
        val hasManyRepeats = calculateRepeatDigitRatio(tail) >= 0.45f
        return hasPairPattern || hasLongRun || hasManyRepeats
    }

    private fun calculateLocalReputation(
        prefixRisk: Float,
        inBlacklist: Boolean,
        inAllowlist: Boolean,
        spoofingPrefixFlag: Boolean,
        beautifulNumberFlag: Boolean
    ): Float {
        if (inAllowlist) return 0f
        if (inBlacklist) return 1f
        var score = prefixRisk * 0.55f
        if (spoofingPrefixFlag) score += 0.35f
        if (beautifulNumberFlag) score += 0.1f
        return score.coerceIn(0f, 1f)
    }
}
