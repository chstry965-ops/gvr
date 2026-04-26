package com.antispam.blocker.domain.detector.rules

import android.content.Context
import android.provider.ContactsContract
import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.domain.detector.Verdict
import com.antispam.blocker.util.PhoneNormalizer
import kotlinx.coroutines.flow.first

class ContactsRule(
    private val context: Context,
    private val settings: SettingsStore,
    private val phoneNormalizer: PhoneNormalizer
) : Rule {

    override val name = "contacts"

    override suspend fun check(number: String?, isHidden: Boolean, callDetails: android.telecom.Call.Details?): RuleResult? {
        if (!settings.contactsAllowEnabled.first()) return null
        if (number == null) return null

        val normalized = phoneNormalizer.normalize(number) ?: return null
        return if (isInContacts(normalized)) {
            RuleResult(Verdict.ALLOW, name)
        } else null
    }

    private fun isInContacts(normalizedNumber: String): Boolean {
        val uri = ContactsContract.CommonDataKinds.Phone.CONTENT_URI
        val projection = arrayOf(ContactsContract.CommonDataKinds.Phone.NORMALIZED_NUMBER)
        val selection = "${ContactsContract.CommonDataKinds.Phone.NORMALIZED_NUMBER} = ?"

        context.contentResolver.query(uri, projection, selection, arrayOf(normalizedNumber), null)?.use { cursor ->
            return cursor.moveToFirst()
        }
        return false
    }
}
