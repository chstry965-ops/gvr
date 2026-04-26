package com.antispam.blocker

import android.app.Application
import com.antispam.blocker.data.assets.CsvSpamImporter
import com.antispam.blocker.data.db.AppDatabase
import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.data.repository.BlockListRepository
import com.antispam.blocker.util.PhoneNormalizer
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class SpamBlockerApp : Application() {

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    val database: AppDatabase by lazy { AppDatabase.getInstance(this) }
    val settingsStore: SettingsStore by lazy { SettingsStore(this) }

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
        }
    }

    companion object {
        lateinit var instance: SpamBlockerApp
            private set
    }
}
