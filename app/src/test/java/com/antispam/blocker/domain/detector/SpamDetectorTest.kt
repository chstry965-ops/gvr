package com.antispam.blocker.domain.detector

import com.antispam.blocker.data.prefs.SettingsStore
import com.antispam.blocker.domain.detector.rules.*
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.mockito.kotlin.*

class SpamDetectorTest {

    private lateinit var settings: SettingsStore
    private lateinit var whitelistRule: WhitelistRule
    private lateinit var blacklistRule: BlacklistRule
    private lateinit var hiddenNumberRule: HiddenNumberRule
    private lateinit var prefixRule: PrefixRule
    private lateinit var lengthRule: LengthRule
    private lateinit var blockListRepo: com.antispam.blocker.data.repository.BlockListRepository

    private fun makeDetector(vararg rules: Rule): SpamDetector {
        return SpamDetector(rules.toList(), settings)
    }

    @Before
    fun setup() {
        settings = mock()
        blockListRepo = mock()

        whenever(settings.protectionEnabled).thenReturn(flowOf(true))
        whenever(settings.contactsAllowEnabled).thenReturn(flowOf(true))
        whenever(settings.blockHiddenNumbers).thenReturn(flowOf(true))
        whenever(settings.hiddenNumberAction).thenReturn(flowOf(Verdict.WARN))
        whenever(settings.blockPrefixes).thenReturn(flowOf(true))
        whenever(settings.prefixList).thenReturn(flowOf(listOf("8800", "+7495")))
        whenever(settings.prefixAction).thenReturn(flowOf(Verdict.WARN))
        whenever(settings.blockShortNumbers).thenReturn(flowOf(true))
        whenever(settings.shortNumberAction).thenReturn(flowOf(Verdict.WARN))
        whenever(settings.blockLongNumbers).thenReturn(flowOf(true))
        whenever(settings.longNumberAction).thenReturn(flowOf(Verdict.WARN))

        whitelistRule = WhitelistRule(blockListRepo)
        blacklistRule = BlacklistRule(blockListRepo)
        hiddenNumberRule = HiddenNumberRule(settings)
        prefixRule = PrefixRule(settings)
        lengthRule = LengthRule(settings)
    }

    @Test
    fun `protection disabled returns ALLOW`() = runTest {
        whenever(settings.protectionEnabled).thenReturn(flowOf(false))
        val detector = makeDetector(blacklistRule)
        val result = detector.detect("+79001234567", false)
        assertEquals(Verdict.ALLOW, result.verdict)
        assertNull(result.ruleName)
    }

    @Test
    fun `number in blacklist returns BLOCK`() = runTest {
        whenever(blockListRepo.isBlocked("+79001234567")).thenReturn(true)
        whenever(blockListRepo.isAllowed("+79001234567")).thenReturn(false)
        val detector = makeDetector(whitelistRule, blacklistRule)
        val result = detector.detect("+79001234567", false)
        assertEquals(Verdict.BLOCK, result.verdict)
        assertEquals("blacklist", result.ruleName)
    }

    @Test
    fun `number in whitelist overrides blacklist`() = runTest {
        whenever(blockListRepo.isAllowed("+79001234567")).thenReturn(true)
        whenever(blockListRepo.isBlocked("+79001234567")).thenReturn(true)
        val detector = makeDetector(whitelistRule, blacklistRule)
        val result = detector.detect("+79001234567", false)
        assertEquals(Verdict.ALLOW, result.verdict)
        assertEquals("whitelist", result.ruleName)
    }

    @Test
    fun `hidden number returns WARN by default`() = runTest {
        val detector = makeDetector(hiddenNumberRule)
        val result = detector.detect(null, true)
        assertEquals(Verdict.WARN, result.verdict)
        assertEquals("hidden_number", result.ruleName)
    }

    @Test
    fun `hidden number returns BLOCK when configured`() = runTest {
        whenever(settings.hiddenNumberAction).thenReturn(flowOf(Verdict.BLOCK))
        val detector = makeDetector(hiddenNumberRule)
        val result = detector.detect(null, true)
        assertEquals(Verdict.BLOCK, result.verdict)
    }

    @Test
    fun `prefix match returns WARN`() = runTest {
        val detector = makeDetector(prefixRule)
        val result = detector.detect("88001234567", false)
        assertEquals(Verdict.WARN, result.verdict)
        assertEquals("prefix", result.ruleName)
    }

    @Test
    fun `no prefix match falls through`() = runTest {
        val detector = makeDetector(prefixRule)
        val result = detector.detect("+79161234567", false)
        assertEquals(Verdict.ALLOW, result.verdict)
    }

    @Test
    fun `short number returns WARN`() = runTest {
        val detector = makeDetector(lengthRule)
        val result = detector.detect("1234", false)
        assertEquals(Verdict.WARN, result.verdict)
        assertEquals("length", result.ruleName)
    }

    @Test
    fun `normal length number is ALLOW`() = runTest {
        val detector = makeDetector(lengthRule)
        val result = detector.detect("+79001234567", false)
        assertEquals(Verdict.ALLOW, result.verdict)
    }

    @Test
    fun `priority order - whitelist before blacklist`() = runTest {
        whenever(blockListRepo.isAllowed("+79001234567")).thenReturn(true)
        whenever(blockListRepo.isBlocked("+79001234567")).thenReturn(true)
        val detector = makeDetector(whitelistRule, blacklistRule)
        val result = detector.detect("+79001234567", false)
        assertEquals(Verdict.ALLOW, result.verdict)
    }

    @Test
    fun `null number with no hidden flag is ALLOW`() = runTest {
        val detector = makeDetector(hiddenNumberRule)
        val result = detector.detect(null, false)
        assertEquals(Verdict.ALLOW, result.verdict)
    }
}
