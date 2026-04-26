package com.antispam.blocker.data.prefs

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import com.antispam.blocker.domain.detector.Verdict
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "settings")

class SettingsStore(private val context: Context) {

    private val store get() = context.dataStore

    val protectionEnabled: Flow<Boolean> = boolPref("protection_enabled", true)

    val blockHiddenNumbers: Flow<Boolean> = boolPref("block_hidden_numbers", true)
    val hiddenNumberAction: Flow<Verdict> = verdictPref("hidden_number_action", Verdict.WARN)

    val blockNonContacts: Flow<Boolean> = boolPref("block_non_contacts", false)
    val nonContactsAction: Flow<Verdict> = verdictPref("non_contacts_action", Verdict.WARN)

    val blockPrefixes: Flow<Boolean> = boolPref("block_prefixes", true)
    val prefixList: Flow<List<String>> = stringListPref("prefix_list", DEFAULT_PREFIXES)
    val prefixAction: Flow<Verdict> = verdictPref("prefix_action", Verdict.WARN)

    val blockShortNumbers: Flow<Boolean> = boolPref("block_short_numbers", true)
    val shortNumberAction: Flow<Verdict> = verdictPref("short_number_action", Verdict.WARN)

    val blockLongNumbers: Flow<Boolean> = boolPref("block_long_numbers", true)
    val longNumberAction: Flow<Verdict> = verdictPref("long_number_action", Verdict.WARN)

    val blockStirFailed: Flow<Boolean> = boolPref("block_stir_failed", true)
    val stirFailedAction: Flow<Verdict> = verdictPref("stir_failed_action", Verdict.BLOCK)

    val rateLimitEnabled: Flow<Boolean> = boolPref("rate_limit_enabled", true)
    val rateLimitCount: Flow<Int> = intPref("rate_limit_count", 3)
    val rateLimitMinutes: Flow<Int> = intPref("rate_limit_minutes", 5)
    val rateLimitAction: Flow<Verdict> = verdictPref("rate_limit_action", Verdict.WARN)

    val skipCallLogForBlocked: Flow<Boolean> = boolPref("skip_call_log_for_blocked", false)

    val contactsAllowEnabled: Flow<Boolean> = boolPref("contacts_allow_enabled", true)

    val dbUpdateEnabled: Flow<Boolean> = boolPref("db_update_enabled", false)
    val dbUpdateUrl: Flow<String> = stringPref("db_update_url", "")

    suspend fun set(key: String, value: Boolean) {
        store.edit { it[booleanPreferencesKey(key)] = value }
    }

    suspend fun set(key: String, value: String) {
        store.edit { it[stringPreferencesKey(key)] = value }
    }

    suspend fun set(key: String, value: Verdict) {
        store.edit { it[stringPreferencesKey(key)] = value.name }
    }

    suspend fun set(key: String, value: Int) {
        store.edit { it[intPreferencesKey(key)] = value }
    }

    suspend fun setPrefixList(values: List<String>) {
        store.edit { it[stringPreferencesKey("prefix_list")] = values.joinToString(",") }
    }

    // --- helpers ---

    private fun boolPref(key: String, default: Boolean): Flow<Boolean> =
        store.data.map { it[booleanPreferencesKey(key)] ?: default }

    private fun stringPref(key: String, default: String): Flow<String> =
        store.data.map { it[stringPreferencesKey(key)] ?: default }

    private fun intPref(key: String, default: Int): Flow<Int> =
        store.data.map { it[intPreferencesKey(key)] ?: default }

    private fun verdictPref(key: String, default: Verdict): Flow<Verdict> =
        store.data.map { Verdict.valueOf(it[stringPreferencesKey(key)] ?: default.name) }

    private fun stringListPref(key: String, default: List<String>): Flow<List<String>> =
        store.data.map {
            val raw = it[stringPreferencesKey(key)]
            if (raw.isNullOrBlank()) default else raw.split(",").map { s -> s.trim() }
        }

    companion object {
        val DEFAULT_PREFIXES = listOf("8800", "8449", "+7495", "+7499", "+7800")
    }
}
