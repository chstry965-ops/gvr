package com.antispam.blocker.domain.model

import android.content.Context
import org.json.JSONObject

/**
 * Структурированная карточка модели: версия, дата, метрики, размер вектора.
 *
 * Загружается из `assets/model_card.json` или из `filesDir/model_card.json`,
 * если worker дообучения положит туда новую версию.
 */
data class ModelCard(
    val version: String,
    val createdAt: String,
    val featureCount: Int,
    val rows: Int,
    val classCounts: Map<String, Int>,
    val blockPrecision: Float,
    val blockRecall: Float,
    val rocAuc: Float?,
    val datasetHash: String?,
    val notes: String? = null
) {
    companion object {
        private const val ASSET_NAME = "model_card.json"

        fun load(context: Context): ModelCard? {
            return loadFromFiles(context) ?: loadFromAssets(context)
        }

        private fun loadFromFiles(context: Context): ModelCard? {
            val file = java.io.File(context.filesDir, ASSET_NAME)
            if (!file.exists()) return null
            return runCatching { parse(file.readText(Charsets.UTF_8)) }.getOrNull()
        }

        private fun loadFromAssets(context: Context): ModelCard? {
            return runCatching {
                context.assets.open(ASSET_NAME).bufferedReader(Charsets.UTF_8).use { it.readText() }
            }.getOrNull()?.let { runCatching { parse(it) }.getOrNull() }
        }

        fun parse(json: String): ModelCard? {
            return runCatching {
                val obj = JSONObject(json)
                val classObj = obj.optJSONObject("class_counts")
                val classCounts = mutableMapOf<String, Int>()
                if (classObj != null) {
                    val keys = classObj.keys()
                    while (keys.hasNext()) {
                        val k = keys.next()
                        classCounts[k] = classObj.optInt(k, 0)
                    }
                }
                ModelCard(
                    version = obj.optString("version", "unknown"),
                    createdAt = obj.optString("created_at", ""),
                    featureCount = obj.optInt("feature_count", 0),
                    rows = obj.optInt("rows", 0),
                    classCounts = classCounts,
                    blockPrecision = obj.optDouble("block_precision", 0.0).toFloat(),
                    blockRecall = obj.optDouble("block_recall", 0.0).toFloat(),
                    rocAuc = obj.optDouble("roc_auc_ovr", Double.NaN).takeUnless { it.isNaN() }?.toFloat(),
                    datasetHash = obj.optString("dataset_hash", "").ifBlank { null },
                    notes = obj.optString("notes", "").ifBlank { null }
                )
            }.getOrNull()
        }
    }
}
