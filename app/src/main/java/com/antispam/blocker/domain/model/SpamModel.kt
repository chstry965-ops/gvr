package com.antispam.blocker.domain.model

import android.content.Context
import com.antispam.blocker.domain.detector.Verdict
import com.antispam.blocker.domain.scoring.CallFeatures
import com.antispam.blocker.domain.scoring.RiskLevel
import com.antispam.blocker.domain.scoring.RiskScore
import org.tensorflow.lite.Interpreter
import java.io.FileInputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.channels.FileChannel

class SpamModel(private val context: Context) {

    private var interpreter: Interpreter? = null
    private var isModelLoaded = false
    private var thresholds: ModelCard.Thresholds? = null

    fun loadModel(): Boolean {
        return try {
            val modelBuffer = loadModelFile()
            val options = Interpreter.Options().apply {
                setNumThreads(2)
            }
            interpreter = Interpreter(modelBuffer, options)
            // Load thresholds from model_card.json (if present); falls back to argmax otherwise.
            thresholds = ModelCard.load(context)?.thresholds
            isModelLoaded = true
            true
        } catch (e: Exception) {
            android.util.Log.e("SpamModel", "Failed to load TFLite model", e)
            isModelLoaded = false
            false
        }
    }

    fun predict(features: CallFeatures): RiskScore? {
        val interp = interpreter ?: return null
        if (!isModelLoaded) return null

        return try {
            val input = features.toFloatArray()
            val expectedInputSize = interp.getInputTensor(0).shape().lastOrNull() ?: input.size
            if (expectedInputSize != input.size) {
                android.util.Log.w("SpamModel", "Model input size mismatch: model=$expectedInputSize features=${input.size}")
                return null
            }
            val inputBuffer = ByteBuffer.allocateDirect(input.size * 4).order(ByteOrder.nativeOrder())
            input.forEach { inputBuffer.putFloat(it) }
            inputBuffer.rewind()

            val outputBuffer = ByteBuffer.allocateDirect(3 * 4).order(ByteOrder.nativeOrder())

            interp.run(inputBuffer, outputBuffer)
            outputBuffer.rewind()

            val allow = outputBuffer.getFloat()
            val warn = outputBuffer.getFloat()
            val block = outputBuffer.getFloat()

            val probs = listOf(allow, warn, block)
            val maxIdx = probs.indices.maxByOrNull { probs[it] } ?: 0

            // Apply per-class thresholds from model_card.json (when available);
            // otherwise fall back to plain argmax.
            val thr = thresholds
            val verdict = if (thr != null) {
                when {
                    block >= thr.blockThreshold -> Verdict.BLOCK
                    warn >= thr.warnThreshold -> Verdict.WARN
                    else -> Verdict.ALLOW
                }
            } else {
                when (maxIdx) {
                    0 -> Verdict.ALLOW
                    1 -> Verdict.WARN
                    2 -> Verdict.BLOCK
                    else -> Verdict.ALLOW
                }
            }
            // Confidence still tracks argmax probability so UI gauges keep meaning.
            val confidence = probs[maxIdx]

            val score = (block * 100).toInt().coerceIn(0, 100)
            val level = when {
                score >= 70 -> RiskLevel.DANGEROUS
                score >= 35 -> RiskLevel.SUSPICIOUS
                else -> RiskLevel.SAFE
            }

            RiskScore(
                score = score,
                level = level,
                verdict = verdict,
                reasons = emptyList(),
                confidence = when {
                    confidence > 0.8f -> RiskScore.Confidence.HIGH
                    confidence > 0.5f -> RiskScore.Confidence.MEDIUM
                    else -> RiskScore.Confidence.LOW
                },
                source = "tflite_model",
                modelProbabilities = floatArrayOf(allow, warn, block),
                ruleScore = score,
                activeFactorIds = emptyList(),
                modelInputSize = expectedInputSize
            )
        } catch (e: Exception) {
            android.util.Log.e("SpamModel", "Prediction failed", e)
            null
        }
    }

    fun close() {
        interpreter?.close()
        interpreter = null
        isModelLoaded = false
    }

    private fun loadModelFile(): ByteBuffer {
        val file = java.io.File(context.filesDir, MODEL_FILENAME)
        if (!file.exists()) {
            // Try loading from assets as fallback
            val assetFd = context.assets.openFd(MODEL_FILENAME)
            val inputStream = FileInputStream(assetFd.fileDescriptor)
            val buffer = inputStream.channel.map(
                FileChannel.MapMode.READ_ONLY,
                assetFd.startOffset,
                assetFd.declaredLength
            )
            return buffer
        }
        val inputStream = FileInputStream(file)
        val buffer = inputStream.channel.map(
            FileChannel.MapMode.READ_ONLY,
            0,
            file.length()
        )
        return buffer
    }

    companion object {
        const val MODEL_FILENAME = "spam_model.tflite"
        const val INPUT_SIZE = CallFeatures.FEATURE_COUNT
    }
}
