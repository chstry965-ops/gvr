package com.antispam.blocker.data.prefs

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.antispam.blocker.domain.scoring.QuestionnaireAnswers
import com.antispam.blocker.domain.scoring.UserProfileVector
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

class ProfileVectorStore(private val context: Context) {

    private val Context.profileDataStore by preferencesDataStore("profile_vector")

    private fun floatPref(key: String, default: Float): Flow<Float> =
        context.profileDataStore.data.map { it[floatPreferencesKey(key)] ?: default }

    private fun boolPref(key: String, default: Boolean): Flow<Boolean> =
        context.profileDataStore.data.map { it[booleanPreferencesKey(key)] ?: default }

    val vulnerabilityScore: Flow<Float> = floatPref("vulnerability_score", 50f)
    val businessActivity: Flow<Float> = floatPref("business_activity", 50f)
    val digitalActivity: Flow<Float> = floatPref("digital_activity", 50f)
    val adsActivity: Flow<Float> = floatPref("ads_activity", 50f)
    val spamTolerance: Flow<Float> = floatPref("spam_tolerance", 50f)
    val falseAlarmFear: Flow<Float> = floatPref("false_alarm_fear", 50f)
    val awarenessLevel: Flow<Float> = floatPref("awareness_level", 50f)
    val hasForeignContacts: Flow<Boolean> = boolPref("has_foreign_contacts", false)
    val hasHomePhone: Flow<Boolean> = boolPref("has_home_phone", false)
    val isOnboardingComplete: Flow<Boolean> = boolPref("onboarding_complete", false)

    suspend fun getVector(): UserProfileVector {
        return UserProfileVector(
            vulnerabilityScore = vulnerabilityScore.first(),
            businessActivity = businessActivity.first(),
            digitalActivity = digitalActivity.first(),
            adsActivity = adsActivity.first(),
            spamTolerance = spamTolerance.first(),
            falseAlarmFear = falseAlarmFear.first(),
            awarenessLevel = awarenessLevel.first(),
            hasForeignContacts = hasForeignContacts.first(),
            hasHomePhone = hasHomePhone.first()
        )
    }

    suspend fun saveVector(vector: UserProfileVector) {
        context.profileDataStore.edit { prefs ->
            prefs[floatPreferencesKey("vulnerability_score")] = vector.vulnerabilityScore
            prefs[floatPreferencesKey("business_activity")] = vector.businessActivity
            prefs[floatPreferencesKey("digital_activity")] = vector.digitalActivity
            prefs[floatPreferencesKey("ads_activity")] = vector.adsActivity
            prefs[floatPreferencesKey("spam_tolerance")] = vector.spamTolerance
            prefs[floatPreferencesKey("false_alarm_fear")] = vector.falseAlarmFear
            prefs[floatPreferencesKey("awareness_level")] = vector.awarenessLevel
            prefs[booleanPreferencesKey("has_foreign_contacts")] = vector.hasForeignContacts
            prefs[booleanPreferencesKey("has_home_phone")] = vector.hasHomePhone
        }
    }

    suspend fun saveFromQuestionnaire(answers: QuestionnaireAnswers) {
        val vector = UserProfileVector.fromQuestionnaire(answers)
        saveVector(vector)
        setOnboardingComplete(true)
    }

    suspend fun setOnboardingComplete(complete: Boolean) {
        context.profileDataStore.edit { prefs ->
            prefs[booleanPreferencesKey("onboarding_complete")] = complete
        }
    }
}
