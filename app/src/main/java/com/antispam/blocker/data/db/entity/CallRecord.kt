package com.antispam.blocker.data.db.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.antispam.blocker.domain.detector.Verdict

@Entity(tableName = "call_records")
data class CallRecord(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val normalizedNumber: String?,
    val originalNumber: String?,
    val verdict: Verdict,
    val timestamp: Long = System.currentTimeMillis(),
    val ruleName: String? = null
)
