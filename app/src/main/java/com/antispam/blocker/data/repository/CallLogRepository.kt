package com.antispam.blocker.data.repository

import com.antispam.blocker.data.db.dao.CallRecordDao
import com.antispam.blocker.data.db.entity.CallRecord
import com.antispam.blocker.domain.detector.Verdict
import kotlinx.coroutines.flow.Flow

class CallLogRepository(private val dao: CallRecordDao) {

    val allRecords: Flow<List<CallRecord>> = dao.getAll()

    fun recordsSince(from: Long): Flow<List<CallRecord>> = dao.getSince(from)

    fun blockedCountSince(from: Long): Flow<Int> = dao.countBlockedSince(from)

    fun warnedCountSince(from: Long): Flow<Int> = dao.countWarnedSince(from)

    suspend fun record(
        normalizedNumber: String?,
        originalNumber: String?,
        verdict: Verdict,
        ruleName: String? = null
    ) {
        dao.insert(
            CallRecord(
                normalizedNumber = normalizedNumber,
                originalNumber = originalNumber,
                verdict = verdict,
                ruleName = ruleName
            )
        )
    }

    suspend fun deleteOlderThan(before: Long) {
        dao.deleteOlderThan(before)
    }
}
