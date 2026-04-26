package com.antispam.blocker.data.repository

import com.antispam.blocker.data.db.dao.AllowedNumberDao
import com.antispam.blocker.data.db.dao.BlockedNumberDao
import com.antispam.blocker.data.db.entity.AllowedNumber
import com.antispam.blocker.data.db.entity.BlockedNumber
import com.antispam.blocker.util.PhoneNormalizer
import kotlinx.coroutines.flow.Flow

class BlockListRepository(
    private val blockedDao: BlockedNumberDao,
    private val allowedDao: AllowedNumberDao,
    private val phoneNormalizer: PhoneNormalizer
) {

    val allBlocked: Flow<List<BlockedNumber>> = blockedDao.getAll()
    val allAllowed: Flow<List<AllowedNumber>> = allowedDao.getAll()
    val totalCount: Flow<Int> = blockedDao.countAll()
    val prebuiltCount: Flow<Int> = blockedDao.countPrebuilt()

    private var cachedPatterns: List<Regex>? = null

    suspend fun isBlocked(rawNumber: String): Boolean {
        val normalized = phoneNormalizer.normalize(rawNumber) ?: return false
        if (blockedDao.contains(normalized)) return true

        val patterns = cachedPatterns ?: blockedDao.getAllPatterns()
            .mapNotNull { entry ->
                try { Regex(entry.pattern!!) } catch (_: Exception) { null }
            }.also { cachedPatterns = it }

        return patterns.any { it.containsMatchIn(normalized) }
    }

    suspend fun isAllowed(rawNumber: String): Boolean {
        val normalized = phoneNormalizer.normalize(rawNumber) ?: return false
        return allowedDao.contains(normalized)
    }

    suspend fun addToBlockList(rawNumber: String, source: BlockedNumber.Source = BlockedNumber.Source.MANUAL, pattern: String? = null) {
        val rawTrimmed = rawNumber.trim()
        if (rawTrimmed.isBlank()) return

        if (pattern != null) {
            // Маска: не требуем валидного телефонного формата.
            // Проверяем что regex сам компилируется, иначе запись бесполезна.
            try {
                Regex(pattern)
            } catch (_: Exception) {
                return
            }
            blockedDao.insert(
                BlockedNumber(
                    normalizedNumber = rawTrimmed, // для маски храним как есть (юзер увидит в списке)
                    originalNumber = rawTrimmed,
                    source = source,
                    pattern = pattern
                )
            )
            cachedPatterns = null
            return
        }

        // Обычный номер — строгая нормализация
        val normalized = phoneNormalizer.normalize(rawTrimmed) ?: return
        blockedDao.insert(
            BlockedNumber(
                normalizedNumber = normalized,
                originalNumber = rawTrimmed,
                source = source,
                pattern = null
            )
        )
    }

    suspend fun addToAllowList(rawNumber: String) {
        val normalized = phoneNormalizer.normalize(rawNumber) ?: return
        allowedDao.insert(
            AllowedNumber(
                normalizedNumber = normalized,
                originalNumber = rawNumber
            )
        )
    }

    suspend fun removeFromBlockList(normalizedNumber: String) {
        blockedDao.deleteByNumber(normalizedNumber)
        cachedPatterns = null
    }

    suspend fun removeFromAllowList(normalizedNumber: String) {
        allowedDao.deleteByNumber(normalizedNumber)
    }

    /** Полная очистка всех заблокированных номеров (включая встроенную базу). */
    suspend fun clearAllBlocked() {
        blockedDao.deleteAll()
        cachedPatterns = null
    }

    /** Удалить только PREBUILT-записи (оставить ручные и по сообщениям). */
    suspend fun clearPrebuilt() {
        blockedDao.deletePrebuilt()
        cachedPatterns = null
    }

    suspend fun importPrebuilt(numbers: List<String>) {
        for (num in numbers) {
            val normalized = phoneNormalizer.normalize(num) ?: continue
            blockedDao.insert(
                BlockedNumber(
                    normalizedNumber = normalized,
                    originalNumber = num,
                    source = BlockedNumber.Source.PREBUILT
                )
            )
        }
    }
}
