package com.antispam.blocker

import android.app.Application
import com.antispam.blocker.data.assets.CsvSpamImporter
import com.antispam.blocker.data.worker.ModelFineTuneWorker
import com.antispam.blocker.data.db.AppDatabase
import com.antispam.blocker.data.prefs.ProfileVectorStore
import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.data.repository.BlockListRepository
import com.antispam.blocker.domain.model.ModelCard
import com.antispam.blocker.domain.scoring.InstalledAppScanner
import com.antispam.blocker.domain.scoring.UserProfileVector
import com.antispam.blocker.util.PhoneNormalizer
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class SpamBlockerApp : Application() {

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    val database: AppDatabase by lazy { AppDatabase.getInstance(this) }
    val settingsStore: SettingsStore by lazy { SettingsStore(this) }
    val profileVectorStore: ProfileVectorStore by lazy { ProfileVectorStore(this) }
    val modelCard: ModelCard? get() = ModelCard.load(this)
    val modelVersion: String get() = modelCard?.version ?: "local-rule-fallback"

    private var _profileVector: UserProfileVector = UserProfileVector()
    val profileVector: UserProfileVector get() = _profileVector

    override fun onCreate() {
        super.onCreate()
        instance = this

        appScope.launch {
            val repo = BlockListRepository(
                database.blockedNumberDao(),
                database.allowedNumberDao(),
                PhoneNormalizer
            )
            CsvSpamImporter(this@SpamBlockerApp, repo, settingsStore).importIfFirstRun()

            // Load profile vector from DataStore, enrich with installed apps
            val stored = profileVectorStore.getVector()
            val enriched = InstalledAppScanner(this@SpamBlockerApp).enrichProfile(stored)
            _profileVector = enriched

            // Schedule nightly model fine-tune on charge
            ModelFineTuneWorker.schedule(this@SpamBlockerApp)
        }
    }

    suspend fun updateProfileVector(vector: UserProfileVector) {
        _profileVector = vector
        profileVectorStore.saveVector(vector)
    }

    companion object {
        lateinit var instance: SpamBlockerApp
            private set
    }
}
