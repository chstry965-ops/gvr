package com.antispam.blocker.service

import android.telecom.Call
import android.telecom.CallScreeningService
import com.antispam.blocker.SpamBlockerApp
import com.antispam.blocker.data.db.entity.TrainingData
import com.antispam.blocker.data.assets.OfficialWhitelistImporter
import com.antispam.blocker.data.prefs.FeedbackLearningStore
import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.data.repository.BlockListRepository
import com.antispam.blocker.data.repository.CallLogRepository
import com.antispam.blocker.domain.detector.Verdict
import com.antispam.blocker.domain.scoring.FeatureExtractor
import com.antispam.blocker.domain.scoring.FeedbackHandler
import com.antispam.blocker.domain.scoring.SmartSpamDetector
import com.antispam.blocker.domain.scoring.UserProfileVector
import com.antispam.blocker.domain.tracking.DecisionTracker
import com.antispam.blocker.notification.SpamWarningNotifier
import com.antispam.blocker.overlay.SpamAlertOverlayService
import com.antispam.blocker.util.PhoneNormalizer
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import org.json.JSONArray

class SpamCallScreeningService : CallScreeningService() {

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private lateinit var smartDetector: SmartSpamDetector
    private lateinit var callLogRepo: CallLogRepository
    private lateinit var blockListRepo: BlockListRepository
    private lateinit var settings: SettingsStore
    private lateinit var notifier: SpamWarningNotifier
    private lateinit var featureExtractor: FeatureExtractor
    private lateinit var profileVector: UserProfileVector
    private lateinit var feedbackHandler: FeedbackHandler
    private lateinit var feedbackStore: FeedbackLearningStore
    private lateinit var decisionTracker: DecisionTracker

    override fun onCreate() {
        super.onCreate()
        val app = SpamBlockerApp.instance
        val db = app.database
        settings = app.settingsStore
        feedbackStore = FeedbackLearningStore(this)

        blockListRepo = BlockListRepository(
            db.blockedNumberDao(),
            db.allowedNumberDao(),
            PhoneNormalizer
        )
        callLogRepo = CallLogRepository(db.callRecordDao())
        notifier = SpamWarningNotifier(this)
        featureExtractor = FeatureExtractor(this, db.callRecordDao(), blockListRepo)

        smartDetector = SmartSpamDetector(
            context = this,
            blockListRepo = blockListRepo,
            callRecordDao = db.callRecordDao(),
            settings = settings,
            featureExtractor = featureExtractor,
            feedbackStore = feedbackStore
        )

        feedbackHandler = FeedbackHandler(
            feedbackStore = feedbackStore,
            blockListRepo = blockListRepo,
            trainingDataDao = db.trainingDataDao()
        )

        decisionTracker = DecisionTracker(
            dao = db.decisionRecordDao(),
            modelVersionProvider = { app.modelVersion }
        )

        profileVector = app.profileVector

        // Импорт официального РФ whitelist (банки, операторы, экстренные службы)
        val whitelistImporter = OfficialWhitelistImporter(this, blockListRepo)
        serviceScope.launch { whitelistImporter.importIfFirstRun() }
    }

    override fun onScreenCall(callDetails: Call.Details) {
        val handle = callDetails.handle
        val number = handle?.schemeSpecificPart
        val isHidden = number.isNullOrBlank()

        android.util.Log.d("SpamBlocker", "Incoming call: $number (hidden: $isHidden)")

        serviceScope.launch {
            try {
                val normalized = PhoneNormalizer.normalize(number)
                val riskScore = smartDetector.score(number, isHidden, callDetails, profileVector)

                android.util.Log.d("SpamBlocker", "Risk score: ${riskScore.score} level=${riskScore.level} verdict=${riskScore.verdict} reasons=${riskScore.reasons}")

                callLogRepo.record(normalized, number, riskScore.verdict, riskScore.source)

                // Compute features again for tracking + training data (lightweight; FeatureExtractor is not heavy)
                val features = featureExtractor.extract(number, isHidden, callDetails, profileVector)

                try {
                    decisionTracker.record(
                        rawNumber = number,
                        normalizedNumber = normalized,
                        features = features,
                        risk = riskScore
                    )
                } catch (e: Exception) {
                    android.util.Log.w("SpamBlocker", "Failed to record decision", e)
                }

                if (normalized != null) {
                    saveTrainingData(normalized, features, riskScore.verdict)
                }

                val displayNumber = number ?: "Скрытый номер"

                when (riskScore.verdict) {
                    Verdict.BLOCK -> {
                        val skipLog = settings.skipCallLogForBlocked.first()
                        respondToCall(callDetails, buildBlockResponse(skipLog))
                        notifier.showBlocked(displayNumber, riskScore.reasons.firstOrNull())
                    }
                    Verdict.WARN -> {
                        respondToCall(callDetails, buildWarnResponse())
                        notifier.showWarning(displayNumber, riskScore.reasons.firstOrNull())
                        SpamAlertOverlayService.show(
                            this@SpamCallScreeningService,
                            displayNumber,
                            riskScore.reasons.firstOrNull()
                        )
                    }
                    Verdict.ALLOW -> respondToCall(callDetails, buildAllowResponse())
                }
            } catch (e: Exception) {
                android.util.Log.e("SpamBlocker", "Error in onScreenCall", e)
                respondToCall(callDetails, buildAllowResponse())
            }
        }
    }

    private suspend fun saveTrainingData(
        normalizedNumber: String,
        features: com.antispam.blocker.domain.scoring.CallFeatures,
        verdict: Verdict
    ) {
        val featuresArray = JSONArray()
        features.toFloatArray().forEach { featuresArray.put(it) }

        val app = SpamBlockerApp.instance
        app.database.trainingDataDao().insert(
            TrainingData(
                normalizedNumber = normalizedNumber,
                featuresJson = featuresArray.toString(),
                label = verdict.name.lowercase(),
                weight = 1.0f,
                userAction = null,
                timestamp = System.currentTimeMillis()
            )
        )
    }

    private fun buildBlockResponse(skipCallLog: Boolean): CallResponse {
        return CallResponse.Builder()
            .setDisallowCall(true)
            .setRejectCall(true)
            .setSkipCallLog(skipCallLog)
            .setSkipNotification(true)
            .build()
    }

    private fun buildWarnResponse(): CallResponse {
        return CallResponse.Builder()
            .setSilenceCall(true)
            .setSkipNotification(true)
            .build()
    }

    private fun buildAllowResponse(): CallResponse {
        return CallResponse.Builder().build()
    }
}
