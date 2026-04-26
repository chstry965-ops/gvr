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
import com.antispam.blocker.data.db.entity.AllowedNumber
import com.antispam.blocker.data.db.entity.BlockedNumber
import com.antispam.blocker.data.db.entity.CallRecord
import com.antispam.blocker.data.db.util.VerdictConverter

@Database(
    entities = [BlockedNumber::class, AllowedNumber::class, CallRecord::class],
    version = 2,
    exportSchema = true
)
@TypeConverters(VerdictConverter::class)
abstract class AppDatabase : RoomDatabase() {

    abstract fun blockedNumberDao(): BlockedNumberDao
    abstract fun allowedNumberDao(): AllowedNumberDao
    abstract fun callRecordDao(): CallRecordDao

    companion object {
        @Volatile
        private var INSTANCE: AppDatabase? = null

        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE blocked_numbers ADD COLUMN pattern TEXT DEFAULT NULL")
            }
        }

        fun getInstance(context: Context): AppDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "spam_blocker_db"
                )
                    .addMigrations(MIGRATION_1_2)
                    .build()
                INSTANCE = instance
                instance
            }
        }
    }
}
