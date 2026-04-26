package com.antispam.blocker.service

import android.telecom.Call
import android.telecom.CallScreeningService
import android.telecom.TelecomManager
import com.antispam.blocker.SpamBlockerApp
import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.data.repository.BlockListRepository
import com.antispam.blocker.data.repository.CallLogRepository
import com.antispam.blocker.domain.detector.SpamDetector
import com.antispam.blocker.domain.detector.Verdict
import com.antispam.blocker.domain.detector.rules.*
import com.antispam.blocker.notification.SpamWarningNotifier
import com.antispam.blocker.overlay.SpamAlertOverlayService
import com.antispam.blocker.util.PhoneNormalizer
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class SpamCallScreeningService : CallScreeningService() {

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private lateinit var detector: SpamDetector
    private lateinit var callLogRepo: CallLogRepository
    private lateinit var blockListRepo: BlockListRepository
    private lateinit var settings: SettingsStore
    private lateinit var notifier: SpamWarningNotifier

    override fun onCreate() {
        super.onCreate()
        val app = SpamBlockerApp.instance
        val db = app.database
        settings = app.settingsStore
        val phoneNormalizer = PhoneNormalizer

        blockListRepo = BlockListRepository(
            db.blockedNumberDao(),
            db.allowedNumberDao(),
            phoneNormalizer
        )
        callLogRepo = CallLogRepository(db.callRecordDao())
        notifier = SpamWarningNotifier(this)

        val rules = listOf(
            HiddenNumberRule(settings),
            WhitelistRule(blockListRepo),
            ContactsRule(this, settings, phoneNormalizer),
            StirShakenRule(settings),
            BlacklistRule(blockListRepo),
            PrebuiltDbRule(blockListRepo),
            PrefixRule(settings),
            RateLimitRule(db.callRecordDao(), settings),
            LengthRule(settings)
        )

        detector = SpamDetector(rules, settings)
    }

    override fun onScreenCall(callDetails: Call.Details) {
        val handle = callDetails.handle
        val number = handle?.schemeSpecificPart
        val isHidden = number.isNullOrBlank()

        serviceScope.launch {
            val normalized = PhoneNormalizer.normalize(number)
            val result = detector.detect(normalized, isHidden, callDetails)

            callLogRepo.record(normalized, number, result.verdict, result.ruleName)

            val displayNumber = number ?: "Скрытый номер"

            when (result.verdict) {
                Verdict.BLOCK -> {
                    val skipLog = settings.skipCallLogForBlocked.first()
                    respondToCall(callDetails, buildBlockResponse(skipLog))
                    // Показываем уведомление о факте блокировки (post-call),
                    // чтобы пользователь понимал, почему пропущенного нет
                    notifier.showBlocked(displayNumber, result.ruleName)
                }
                Verdict.WARN -> {
                    respondToCall(callDetails, buildWarnResponse())
                    notifier.showWarning(displayNumber, result.ruleName)
                    // Плашка поверх incoming call UI — основной способ
                    // достучаться до пользователя во время звонка.
                    SpamAlertOverlayService.show(
                        this@SpamCallScreeningService,
                        displayNumber,
                        result.ruleName
                    )
                }
                Verdict.ALLOW -> respondToCall(callDetails, buildAllowResponse())
            }
        }
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
