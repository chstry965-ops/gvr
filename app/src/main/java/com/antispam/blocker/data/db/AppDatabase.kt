package com.antispam.blocker.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.antispam.blocker.data.db.dao.AllowedNumberDao
import com.antispam.blocker.data.db.dao.BlockedNumberDao
import com.antispam.blocker.data.db.dao.CallRecordDao
import com.antispam.blocker.data.db.dao.DecisionRecordDao
import com.antispam.blocker.data.db.dao.TrainingDataDao
import com.antispam.blocker.data.db.entity.AllowedNumber
import com.antispam.blocker.data.db.entity.BlockedNumber
import com.antispam.blocker.data.db.entity.CallRecord
import com.antispam.blocker.data.db.entity.DecisionRecord
import com.antispam.blocker.data.db.entity.TrainingData
import com.antispam.blocker.data.db.util.VerdictConverter

@Database(
    entities = [BlockedNumber::class, AllowedNumber::class, CallRecord::class, TrainingData::class, DecisionRecord::class],
    version = 4,
    exportSchema = true
)
@TypeConverters(VerdictConverter::class)
abstract class AppDatabase : RoomDatabase() {

    abstract fun blockedNumberDao(): BlockedNumberDao
    abstract fun allowedNumberDao(): AllowedNumberDao
    abstract fun callRecordDao(): CallRecordDao
    abstract fun trainingDataDao(): TrainingDataDao
    abstract fun decisionRecordDao(): DecisionRecordDao

    companion object {
        @Volatile
        private var INSTANCE: AppDatabase? = null

        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE blocked_numbers ADD COLUMN pattern TEXT DEFAULT NULL")
            }
        }

        private val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("""
                    CREATE TABLE IF NOT EXISTS training_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                        normalizedNumber TEXT NOT NULL,
                        featuresJson TEXT NOT NULL,
                        label TEXT NOT NULL,
                        weight REAL NOT NULL DEFAULT 1.0,
                        userAction TEXT,
                        timestamp INTEGER NOT NULL
                    )
                """.trimIndent())
                db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS index_training_data_normalizedNumber_timestamp ON training_data(normalizedNumber, timestamp)")
            }
        }

        private val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("""
                    CREATE TABLE IF NOT EXISTS decision_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                        timestamp INTEGER NOT NULL,
                        rawNumber TEXT,
                        normalizedNumber TEXT,
                        verdict TEXT NOT NULL,
                        score INTEGER NOT NULL,
                        source TEXT NOT NULL,
                        confidence TEXT NOT NULL,
                        modelAllowProb REAL NOT NULL,
                        modelWarnProb REAL NOT NULL,
                        modelBlockProb REAL NOT NULL,
                        modelInputSize INTEGER NOT NULL,
                        featuresJson TEXT NOT NULL,
                        reasonsJson TEXT NOT NULL,
                        activeFactorsJson TEXT NOT NULL,
                        ruleScore INTEGER NOT NULL,
                        warnThreshold INTEGER NOT NULL,
                        blockThreshold INTEGER NOT NULL,
                        userAction TEXT,
                        userActionTimestamp INTEGER,
                        modelVersion TEXT
                    )
                """.trimIndent())
                db.execSQL("CREATE INDEX IF NOT EXISTS index_decision_records_timestamp ON decision_records(timestamp)")
                db.execSQL("CREATE INDEX IF NOT EXISTS index_decision_records_normalizedNumber ON decision_records(normalizedNumber)")
            }
        }

        fun getInstance(context: Context): AppDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "spam_blocker_db"
                )
                    .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)
                    .fallbackToDestructiveMigration()
                    .build()
                INSTANCE = instance
                instance
            }
        }
    }
}
