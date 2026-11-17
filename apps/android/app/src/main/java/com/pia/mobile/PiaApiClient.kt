package com.pia.mobile

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class PiaApiClient(
    baseUrl: String,
    token: String? = null,
) {
    private val baseUrl = baseUrl.trimEnd('/')
    private var token: String? = token?.trim()?.takeIf { it.isNotEmpty() }

    fun setToken(value: String?) {
        token = value?.trim()?.takeIf { it.isNotEmpty() }
    }

    fun getToken(): String? = token

    suspend fun health(): PiaHealth = withContext(Dispatchers.IO) {
        val payload = request("/health")
        val llm = payload.optJSONObject("llm")
        PiaHealth(
            status = payload.optString("status", "unknown"),
            runtime = payload.optString("runtime", "local"),
            model = llm?.optString("model", "deepseek-flash") ?: "deepseek-flash",
            credentialsConfigured = llm?.optBoolean("credentials_configured", false) ?: false,
        )
    }

    suspend fun tasks(): List<PiaTask> = withContext(Dispatchers.IO) {
        val tasks = request("/tasks").optJSONArray("tasks") ?: JSONArray()
        (0 until tasks.length()).map { index -> tasks.getJSONObject(index).toTask() }
    }

    suspend fun notifications(unreadOnly: Boolean = false): List<PiaNotification> = withContext(Dispatchers.IO) {
        val suffix = if (unreadOnly) "?unread=1" else "?unread=0"
        val items = request("/notifications$suffix").optJSONArray("notifications") ?: JSONArray()
        (0 until items.length()).map { index -> items.getJSONObject(index).toNotification() }
    }

    suspend fun markNotificationRead(id: String) = withContext(Dispatchers.IO) {
        request("/notifications/${encodePath(id)}/read", "POST")
    }

    suspend fun registerDevice(
        deviceId: String,
        platform: String = "android",
        deviceName: String? = null,
        pushToken: String? = null,
    ): JSONObject = withContext(Dispatchers.IO) {
        request(
            "/devices",
            "POST",
            JSONObject()
                .put("device_id", deviceId)
                .put("platform", platform)
                .putOpt("device_name", deviceName)
                .putOpt("push_token", pushToken),
        )
    }

    suspend fun unregisterDevice(deviceId: String): JSONObject = withContext(Dispatchers.IO) {
        request("/devices/${encodePath(deviceId)}", "DELETE")
    }

    suspend fun sync(cursor: Long = 0, limit: Int = 100): JSONObject = withContext(Dispatchers.IO) {
        request("/sync?cursor=${cursor.coerceAtLeast(0)}&limit=${limit.coerceIn(1, 500)}")
    }

    suspend fun task(taskId: String): JSONObject = withContext(Dispatchers.IO) {
        request("/tasks/${encodePath(taskId)}")
    }

    suspend fun approve(taskId: String, action: String, notes: String? = null): JSONObject =
        withContext(Dispatchers.IO) {
            request(
                "/tasks/${encodePath(taskId)}/approve",
                "POST",
                JSONObject().put("action", action).putOpt("notes", notes),
            )
        }

    suspend fun pause(taskId: String): JSONObject = withContext(Dispatchers.IO) {
        request("/tasks/${encodePath(taskId)}/pause", "POST")
    }

    suspend fun resume(taskId: String): JSONObject = withContext(Dispatchers.IO) {
        request("/tasks/${encodePath(taskId)}/resume", "POST")
    }

    suspend fun retry(taskId: String): JSONObject = withContext(Dispatchers.IO) {
        request("/tasks/${encodePath(taskId)}/retry", "POST")
    }

    suspend fun cancel(taskId: String, reason: String? = null): JSONObject = withContext(Dispatchers.IO) {
        request(
            "/tasks/${encodePath(taskId)}/cancel",
            "POST",
            JSONObject().putOpt("reason", reason),
        )
    }

    suspend fun takeover(taskId: String, notes: String? = null): JSONObject = withContext(Dispatchers.IO) {
        request(
            "/tasks/${encodePath(taskId)}/takeover",
            "POST",
            JSONObject().putOpt("notes", notes),
        )
    }

    suspend fun taskContext(taskId: String): JSONObject = withContext(Dispatchers.IO) {
        request("/tasks/${encodePath(taskId)}/context")
    }

    suspend fun createMarketCloseTask(asOf: String): PiaTask = withContext(Dispatchers.IO) {
        val payload = JSONObject()
            .put("trigger_type", "MarketClose")
            .put("target", JSONObject().put("as_of", asOf))
        request("/tasks", "POST", payload).getJSONObject("task").toTask()
    }

    fun taskEventsUrl(taskId: String): String =
        "$baseUrl/tasks/${encodePath(taskId)}/events"

    fun taskEvents(taskId: String): Flow<PiaTaskEvent> = flow {
        val connection = (URL(taskEventsUrl(taskId)).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 5_000
            readTimeout = 0
            setRequestProperty("Accept", "text/event-stream")
            token?.let { setRequestProperty("Authorization", "Bearer $it") }
        }
        try {
            val status = connection.responseCode
            if (status !in 200..299) {
                val body = connection.errorStream?.bufferedReader()?.use { it.readText() }.orEmpty()
                throw PiaApiException(body.ifBlank { "HTTP $status" })
            }
            connection.inputStream.bufferedReader().use { reader ->
                var eventType = "message"
                val dataLines = mutableListOf<String>()
                while (currentCoroutineContext().isActive) {
                    val line = reader.readLine() ?: break
                    if (line.isEmpty()) {
                        parseTaskEvent(eventType, dataLines.joinToString("\n"))?.let { emit(it) }
                        eventType = "message"
                        dataLines.clear()
                    } else if (line.startsWith("event:")) {
                        eventType = line.removePrefix("event:").trim()
                    } else if (line.startsWith("data:")) {
                        dataLines += line.removePrefix("data:").trim()
                    }
                }
                parseTaskEvent(eventType, dataLines.joinToString("\n"))?.let { emit(it) }
            }
        } finally {
            connection.disconnect()
        }
    }.flowOn(Dispatchers.IO)

    private fun parseTaskEvent(eventType: String, data: String): PiaTaskEvent? {
        if (data.isBlank()) return null
        val event = runCatching { JSONObject(data) }.getOrNull() ?: return null
        val payload = event.optJSONObject("payload") ?: event
        return PiaTaskEvent(
            eventType = event.optString("event_type", eventType),
            payload = payload,
            createdAt = event.optString("created_at").takeIf { it.isNotBlank() },
        )
    }

    private fun request(path: String, method: String = "GET", body: JSONObject? = null): JSONObject {
        val connection = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 5_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/json")
            token?.let { setRequestProperty("Authorization", "Bearer $it") }
        }
        try {
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use { it.write(body.toString().toByteArray()) }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (status !in 200..299) throw PiaApiException(text.ifBlank { "HTTP $status" })
            return if (text.isBlank()) JSONObject() else JSONObject(text)
        } finally {
            connection.disconnect()
        }
    }

    private fun JSONObject.toTask() = PiaTask(
        id = optString("id"),
        triggerType = optString("trigger_type"),
        status = optString("status"),
        asOf = optJSONObject("target")?.text("as_of") ?: "—",
        createdAt = text("created_at").orEmpty(),
        symbol = optJSONObject("target")?.symbol(),
    )

    private fun JSONObject.toNotification() = PiaNotification(
        id = optString("id"),
        title = optString("title"),
        body = optString("body"),
        eventType = optString("event_type"),
        taskId = optString("task_id").takeIf { it.isNotBlank() && it != "null" },
        createdAt = optString("created_at"),
        readAt = optString("read_at").takeIf { it.isNotBlank() && it != "null" },
    )

    private fun encodePath(value: String): String =
        URLEncoder.encode(value, Charsets.UTF_8.name()).replace("+", "%20")
}
