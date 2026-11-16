package com.pia.mobile

import android.content.Context

class PiaPushTokenStore(context: Context) {
    private val preferences = context.getSharedPreferences("pia.push", Context.MODE_PRIVATE)

    fun load(): String? = preferences.getString(KEY_TOKEN, null)

    fun save(token: String) {
        preferences.edit().putString(KEY_TOKEN, token).apply()
    }

    fun clear() {
        preferences.edit().remove(KEY_TOKEN).apply()
    }

    companion object {
        private const val KEY_TOKEN = "fcm_device_token"
    }
}
