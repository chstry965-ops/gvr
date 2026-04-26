package com.antispam.blocker.data.db.dao

import androidx.room.*
import com.antispam.blocker.data.db.entity.CallRecord
import kotlinx.coroutines.flow.Flow

@Dao
interface CallRecordDao {

    @Query("SELECT * FROM call_records ORDER BY timestamp DESC")
    fun getAll(): Flow<List<CallRecord>>

    @Query("SELECT * FROM call_records WHERE timestamp >= :from ORDER BY timestamp DESC")
    fun getSince(from: Long): Flow<List<CallRecord>>

    @Query("SELECT COUNT(*) FROM call_records WHERE verdict = 'BLOCK' AND timestamp >= :from")
    fun countBlockedSince(from: Long): Flow<Int>

    @Query("SELECT COUNT(*) FROM call_records WHERE verdict = 'WARN' AND timestamp >= :from")
    fun countWarnedSince(from: Long): Flow<Int>

    @Query("SELECT COUNT(*) FROM call_records WHERE normalizedNumber = :number AND timestamp >= :since")
    suspend fun countByNumberSince(number: String, since: Long): Int

    @Insert
    suspend fun insert(record: CallRecord): Long

    @Query("DELETE FROM call_records WHERE timestamp < :before")
    suspend fun deleteOlderThan(before: Long)
}
