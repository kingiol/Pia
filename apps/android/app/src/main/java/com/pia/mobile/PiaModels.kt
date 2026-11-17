package com.pia.mobile

import org.json.JSONObject

data class PiaHealth(
    val status: String,
    val runtime: String,
    val model: String,
    val credentialsConfigured: Boolean,
)

data class PiaTask(
    val id: String,
    val triggerType: String,
    val status: String,
    val asOf: String,
    val createdAt: String,
    val symbol: String?,
)

data class PiaTaskEvent(
    val eventType: String,
    val payload: JSONObject,
    val createdAt: String?,
)

data class PiaNotification(
    val id: String,
    val title: String,
    val body: String,
    val eventType: String,
    val taskId: String?,
    val createdAt: String,
    val readAt: String?,
)

class PiaApiException(message: String) : Exception(message)
