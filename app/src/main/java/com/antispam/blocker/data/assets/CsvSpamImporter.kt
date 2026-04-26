package com.antispam.blocker.data.assets

import android.content.Context
import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.data.repository.BlockListRepository
import com.antispam.blocker.data.db.entity.BlockedNumber
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.InputStreamReader

class CsvSpamImporter(
    private val context: Context,
    private val repository: BlockListRepository,
    private val settings: SettingsStore
) {

    companion object {
        // Поднимай версию, когда меняешь spam_numbers.csv — база
        // автоматически переимпортируется при следующем запуске приложения.
        const val BUNDLED_DB_VERSION = 4
        private const val PREFS = "spam_import"
        private const val KEY_VERSION = "bundled_version"
    }

    suspend fun importIfFirstRun() = importInternal(force = false)

    suspend fun reimport() = importInternal(force = true)

    /** Сбросить метку импорта (например, после очистки всей базы). */
    fun resetImportFlag() {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().remove(KEY_VERSION).apply()
    }

    private suspend fun importInternal(force: Boolean) {
        withContext(Dispatchers.IO) {
            val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            val installedVersion = prefs.getInt(KEY_VERSION, 0)
            if (!force && installedVersion >= BUNDLED_DB_VERSION) return@withContext

            // Чистим старые PREBUILT-записи — это и удалит возможный мусор
            // от предыдущих версий / битых URL-импортов.
            if (installedVersion > 0 || force) {
                repository.clearPrebuilt()
            }

            val exactNumbers = mutableListOf<String>()
            val regexEntries = mutableListOf<Pair<String, String>>()
            val prefixes = mutableListOf<String>()

            try {
                val inputStream = context.assets.open("spam_numbers.csv")
                BufferedReader(InputStreamReader(inputStream)).use { reader ->
                    var line = reader.readLine()
                    while (line != null) {
                        val trimmed = line.trim()
                        if (trimmed.isNotBlank() && !trimmed.startsWith("#")) {
                            when {
                                trimmed.startsWith("prefix:") -> prefixes.add(trimmed.removePrefix("prefix:"))
                                trimmed.startsWith("regex:") -> {
                                    val pattern = trimmed.removePrefix("regex:")
                                    regexEntries.add(pattern to pattern)
                                }
                                else -> exactNumbers.add(trimmed)
                            }
                        }
                        line = reader.readLine()
                    }
                }
            } catch (_: Exception) {
                return@withContext
            }

            if (exactNumbers.isNotEmpty()) {
                repository.importPrebuilt(exactNumbers)
            }

            for ((raw, pattern) in regexEntries) {
                repository.addToBlockList(raw, source = BlockedNumber.Source.PREBUILT, pattern = pattern)
            }

            if (prefixes.isNotEmpty()) {
                val existing = settings.prefixList.first()
                val merged = (existing + prefixes).distinct()
                settings.setPrefixList(merged)
            }

            prefs.edit().putInt(KEY_VERSION, BUNDLED_DB_VERSION).apply()
        }
    }
}
