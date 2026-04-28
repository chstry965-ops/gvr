package com.antispam.blocker.data.prefs

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

class FeedbackLearningStore(private val context: Context) {

    private val Context.feedbackDataStore by preferencesDataStore("feedback_learning")

    // Factor weights (key = factor_id, default = 1.0)
    fun weight(factorId: String): Flow<Float> =
        context.feedbackDataStore.data.map { it[floatPreferencesKey("w_$factorId")] ?: 1.0f }

    suspend fun setWeight(factorId: String, weight: Float) {
        context.feedbackDataStore.edit { it[floatPreferencesKey("w_$factorId")] = weight.coerceIn(0.1f, 3.0f) }
    }

    suspend fun getAllWeights(): Map<String, Float> {
        val prefs = context.feedbackDataStore.data.first().asMap()
        return prefs.filterKeys { it.name.startsWith("w_") }
            .mapKeys { it.key.name.removePrefix("w_") }
            .mapValues { (it.value as? Number)?.toFloat() ?: 1.0f }
    }

    // Adaptive thresholds
    val warnThreshold: Flow<Float> = context.feedbackDataStore.data.map {
        it[floatPreferencesKey("warn_threshold")] ?: 0.35f
    }
    val blockThreshold: Flow<Float> = context.feedbackDataStore.data.map {
        it[floatPreferencesKey("block_threshold")] ?: 0.70f
    }

    suspend fun setWarnThreshold(value: Float) {
        context.feedbackDataStore.edit { it[floatPreferencesKey("warn_threshold")] = value.coerceIn(0.15f, 0.50f) }
    }

    suspend fun setBlockThreshold(value: Float) {
        context.feedbackDataStore.edit { it[floatPreferencesKey("block_threshold")] = value.coerceIn(0.50f, 0.85f) }
    }

    // Feedback count for threshold adaptation
    val feedbackCount: Flow<Int> = context.feedbackDataStore.data.map {
        (it[floatPreferencesKey("feedback_count")]?.toInt()) ?: 0
    }

    suspend fun incrementFeedbackCount() {
        context.feedbackDataStore.edit { prefs ->
            val current = (prefs[floatPreferencesKey("feedback_count")]?.toInt()) ?: 0
            prefs[floatPreferencesKey("feedback_count")] = (current + 1).toFloat()
        }
    }

    suspend fun resetAll() {
        context.feedbackDataStore.edit { it.clear() }
    }

    companion object {
        const val ALPHA = 0.05f // EMA smoothing factor
        const val MIN_FEEDBACK_FOR_THRESHOLD = 5
    }
}
