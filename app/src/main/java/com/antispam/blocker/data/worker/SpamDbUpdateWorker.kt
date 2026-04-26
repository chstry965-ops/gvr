package com.antispam.blocker.data.worker

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.antispam.blocker.SpamBlockerApp
import com.antispam.blocker.data.assets.CsvSpamImporter
import com.antispam.blocker.data.repository.BlockListRepository
import com.antispam.blocker.util.PhoneNormalizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.URL

class SpamDbUpdateWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val urlStr = inputData.getString("update_url") ?: return@withContext Result.failure()
        if (urlStr.isBlank()) return@withContext Result.failure()

        return@withContext try {
            val connection = URL(urlStr).openConnection()
            connection.connectTimeout = 15_000
            connection.readTimeout = 30_000
            connection.setRequestProperty("Accept", "text/plain, text/csv")

            // Если сервер явно отдаёт HTML/JS — отказываемся импортировать,
            // это не база номеров, а web-страница.
            val contentType = connection.contentType?.lowercase().orEmpty()
            if (contentType.contains("text/html") ||
                contentType.contains("application/json") ||
                contentType.contains("javascript")
            ) {
                return@withContext Result.failure()
            }

            val numbers = mutableListOf<String>()
            BufferedReader(InputStreamReader(connection.getInputStream())).use { reader ->
                var line = reader.readLine()
                var lineCount = 0
                while (line != null) {
                    lineCount++
                    // защита от мусорных файлов — не читаем больше 100k строк
                    if (lineCount > 100_000) break

                    val trimmed = line.trim()
                    if (trimmed.isNotBlank() && !trimmed.startsWith("#") && isLikelyPhoneLine(trimmed)) {
                        numbers.add(trimmed)
                    }
                    line = reader.readLine()
                }
            }

            if (numbers.isNotEmpty()) {
                val app = SpamBlockerApp.instance
                val repo = BlockListRepository(
                    app.database.blockedNumberDao(),
                    app.database.allowedNumberDao(),
                    PhoneNormalizer
                )
                repo.importPrebuilt(numbers)
            }

            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }

    /**
     * Строка должна выглядеть как номер телефона: только цифры, +, пробелы,
     * дефисы и скобки, длина до 20 символов и минимум 7 цифр.
     */
    private fun isLikelyPhoneLine(s: String): Boolean {
        if (s.length > 25) return false
        if (s.any { !it.isDigit() && it != '+' && it != ' ' && it != '-' && it != '(' && it != ')' && it != '.' }) return false
        val digits = s.count { it.isDigit() }
        return digits in 7..15
    }
}
