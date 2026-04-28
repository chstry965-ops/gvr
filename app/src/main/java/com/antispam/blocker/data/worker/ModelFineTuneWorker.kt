package com.antispam.blocker.data.worker

import android.content.Context
import android.util.Log
import androidx.work.*
import com.antispam.blocker.SpamBlockerApp
import com.antispam.blocker.domain.model.SpamModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

class ModelFineTuneWorker(
    context: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(context, workerParams) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        try {
            val app = SpamBlockerApp.instance
            val trainingDao = app.database.trainingDataDao()

            // Get recent training data with user feedback
            val recentData = trainingDao.getLatest(100)
            if (recentData.size < 5) {
                Log.d("ModelFineTune", "Not enough training data (${recentData.size} samples), skipping")
                return@withContext Result.success()
            }

            // For now: reload model from assets (actual on-device training requires TFLite Task Library)
            // Future: implement on-device transfer learning with user feedback data
            val model = SpamModel(applicationContext)
            val loaded = model.loadModel()
            if (loaded) {
                Log.d("ModelFineTune", "Model reloaded successfully with ${recentData.size} samples available")
            } else {
                Log.w("ModelFineTune", "Model reload failed, will use rule engine fallback")
            }
            model.close()

            Result.success()
        } catch (e: Exception) {
            Log.e("ModelFineTune", "Fine-tune failed", e)
            Result.retry()
        }
    }

    companion object {
        const val WORK_NAME = "model_fine_tune"

        fun schedule(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiresBatteryNotLow(true)
                .setRequiresCharging(true)
                .setRequiresDeviceIdle(true)
                .build()

            val request = PeriodicWorkRequestBuilder<ModelFineTuneWorker>(
                24, TimeUnit.HOURS
            )
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.LINEAR, 30, TimeUnit.MINUTES)
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request
            )
            Log.d("ModelFineTune", "Scheduled nightly fine-tune on charge")
        }
    }
}
