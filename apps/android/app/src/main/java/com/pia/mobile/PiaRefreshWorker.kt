package com.pia.mobile

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

class PiaRefreshWorker(
    appContext: Context,
    workerParams: WorkerParameters,
) : CoroutineWorker(appContext, workerParams) {
    override suspend fun doWork(): Result {
        val token = SecureTokenStore(applicationContext).load()
            ?: return Result.failure()
        val baseUrl = inputData.getString(KEY_BASE_URL)
            ?: return Result.failure()
        val client = PiaApiClient(baseUrl, token)
        return runCatching {
            client.health()
            val preferences = applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            val cursor = preferences.getLong(KEY_SYNC_CURSOR, 0L)
            val sync = client.sync(cursor = cursor)
            preferences.edit()
                .putLong(KEY_SYNC_CURSOR, sync.optLong("next_cursor", cursor))
                .apply()
            client.notifications(unreadOnly = true)
            Result.success()
        }.getOrElse {
            Result.retry()
        }
    }

    companion object {
        private const val WORK_NAME = "pia-background-refresh"
        private const val PREFERENCES = "pia_sync_state"
        private const val KEY_SYNC_CURSOR = "cursor"
        const val KEY_BASE_URL = "base_url"

        fun schedule(context: Context, baseUrl: String) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = PeriodicWorkRequestBuilder<PiaRefreshWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .setInputData(androidx.work.workDataOf(KEY_BASE_URL to baseUrl))
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.UPDATE,
                request,
            )
        }
    }
}
