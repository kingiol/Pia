package com.pia.mobile

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import java.time.LocalDate
import java.time.ZoneId
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

private fun shanghaiDate(): String =
    LocalDate.now(ZoneId.of("Asia/Shanghai")).toString()

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (
            android.os.Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1001)
        }
        setContent { PiaApp() }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PiaApp() {
    val context = LocalContext.current
    val baseUrl = BuildConfig.PIA_CLOUD_URL
    val secureStore = remember { SecureTokenStore(context) }
    val pushTokenStore = remember { PiaPushTokenStore(context) }
    val deviceId = remember {
        Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
            ?: "android-${android.os.Build.FINGERPRINT.hashCode()}"
    }
    val client = remember { PiaApiClient(baseUrl, secureStore.load()) }
    var token by remember { mutableStateOf("") }
    var connected by remember { mutableStateOf(false) }
    var tasks by remember { mutableStateOf<List<PiaTask>>(emptyList()) }
    var notifications by remember { mutableStateOf<List<PiaNotification>>(emptyList()) }
    var selectedTask by remember { mutableStateOf<PiaTask?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var operation by remember { mutableStateOf<String?>(null) }
    var selectedTab by rememberSaveable { mutableStateOf(0) }
    val scope = rememberCoroutineScope()
    val researchListState = rememberLazyListState()
    val orderedTasks = remember(tasks) { tasks.sortedBy { it.status != "WAITING_APPROVAL" } }

    suspend fun refresh() {
        val nextTasks = client.tasks()
        val nextNotifications = client.notifications()
        tasks = nextTasks
        notifications = nextNotifications
        val preferences = context.getSharedPreferences("pia_sync_state", 0)
        val cursor = preferences.getLong("cursor", 0L)
        val sync = client.sync(cursor)
        preferences.edit().putLong("cursor", sync.optLong("next_cursor", cursor)).apply()
    }

    fun perform(label: String, action: suspend () -> Unit) {
        if (operation != null) return
        operation = label
        error = null
        scope.launch {
            try {
                action()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (failure: Exception) {
                error = failure.message ?: "操作失败，请重试"
            } finally {
                operation = null
            }
        }
    }

    fun createReview() = perform("正在创建复盘") {
        val task = client.createMarketCloseTask(shanghaiDate())
        tasks = listOf(task) + tasks.filterNot { it.id == task.id }
        selectedTab = 1
    }

    PiaTheme {
        if (!connected) {
            Scaffold { insets ->
                Column(
                    Modifier.fillMaxSize().padding(insets).imePadding()
                        .verticalScroll(rememberScrollState()).padding(24.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    Text("Pia", style = MaterialTheme.typography.headlineMedium)
                    Text("投资研究", style = MaterialTheme.typography.titleLarge)
                    Text(
                        "查看研究结论、核对依据，由你决定下一步",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    OutlinedTextField(
                        value = token,
                        onValueChange = { token = it },
                        label = { Text("访问令牌") },
                        singleLine = true,
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                        enabled = operation == null,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Button(
                        onClick = {
                            perform("正在连接") {
                                client.setToken(token)
                                client.health()
                                secureStore.save(token)
                                // Device registration is optional; a failure must not block research.
                                runCatching {
                                    client.registerDevice(
                                        deviceId,
                                        deviceName = "Pia Android",
                                        pushToken = pushTokenStore.load(),
                                    )
                                }
                                PiaRefreshWorker.schedule(context, baseUrl)
                                connected = true
                                refresh()
                            }
                        },
                        enabled = token.isNotBlank() && operation == null,
                        shape = MaterialTheme.shapes.medium,
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text(operation ?: "连接") }
                    if (operation != null) LinearProgressIndicator(Modifier.fillMaxWidth())
                    error?.let { ErrorNotice(it) }
                }
            }
        } else {
            val task = selectedTask
            if (task != null) {
                key(task.id) {
                    ResearchDetailScreen(
                        client = client,
                        task = task,
                        onBack = {
                            selectedTask = null
                            perform("正在刷新") { refresh() }
                        },
                        onTaskChanged = { tasks = client.tasks() },
                    )
                }
            } else {
                Scaffold(
                    topBar = {
                        TopAppBar(
                            title = { Text("Pia · ${listOf("今天", "研究", "通知")[selectedTab]}") },
                            actions = {
                                IconButton(
                                    onClick = { perform("正在刷新") { refresh() } },
                                    enabled = operation == null,
                                ) { PiaIcon(R.drawable.ic_phosphor_arrow_clockwise, "刷新") }
                            },
                        )
                    },
                    bottomBar = {
                        NavigationBar {
                            listOf(
                                Triple("今天", R.drawable.ic_phosphor_sun, 0),
                                Triple("研究", R.drawable.ic_phosphor_chart_line, 1),
                                Triple("通知", R.drawable.ic_phosphor_bell, 2),
                            ).forEach { (title, icon, tab) ->
                                NavigationBarItem(
                                    selected = selectedTab == tab,
                                    onClick = { selectedTab = tab },
                                    icon = { PiaIcon(icon, null) },
                                    label = { Text(title) },
                                    colors = NavigationBarItemDefaults.colors(
                                        selectedIconColor = MaterialTheme.colorScheme.primary,
                                        selectedTextColor = MaterialTheme.colorScheme.primary,
                                        indicatorColor = MaterialTheme.colorScheme.primaryContainer,
                                    ),
                                )
                            }
                        }
                    },
                ) { insets ->
                    Column(Modifier.fillMaxSize().padding(insets)) {
                        operation?.let {
                            LinearProgressIndicator(Modifier.fillMaxWidth())
                            Text(
                                it,
                                Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                        error?.let { ErrorNotice(it) }
                        when (selectedTab) {
                            0 -> LazyColumn(
                                modifier = Modifier.fillMaxSize(),
                                contentPadding = PaddingValues(16.dp),
                                verticalArrangement = Arrangement.spacedBy(24.dp),
                            ) {
                                item {
                                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                        Text(
                                            if (tasks.isEmpty()) "开始研究" else "今日复盘",
                                            style = MaterialTheme.typography.titleLarge,
                                        )
                                        Text(
                                            if (tasks.isEmpty()) "完成一次收盘复盘，查看结论与依据"
                                            else "已有 ${tasks.size} 份研究记录",
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        )
                                        Button(
                                            onClick = { createReview() },
                                            enabled = operation == null,
                                            shape = MaterialTheme.shapes.medium,
                                            modifier = Modifier.fillMaxWidth(),
                                        ) {
                                            PiaIcon(R.drawable.ic_phosphor_plus_circle, null)
                                            Spacer(Modifier.width(8.dp))
                                            Text(if (tasks.isEmpty()) "开始第一次复盘" else "开始今日复盘")
                                        }
                                    }
                                }
                                item {
                                    HorizontalDivider()
                                    SummaryRow("研究记录", tasks.size.toString(), "所有复盘")
                                    HorizontalDivider()
                                    SummaryRow("未读通知", notifications.count { it.readAt == null }.toString(), "需要关注")
                                    HorizontalDivider()
                                }
                            }
                            1 -> LazyColumn(Modifier.fillMaxSize(), state = researchListState) {
                                item {
                                    TextButton(
                                        onClick = { createReview() },
                                        enabled = operation == null,
                                        modifier = Modifier.padding(horizontal = 8.dp),
                                    ) {
                                        PiaIcon(R.drawable.ic_phosphor_plus_circle, null)
                                        Spacer(Modifier.width(8.dp))
                                        Text("开始今日复盘")
                                    }
                                }
                                if (tasks.isEmpty() && operation == null) {
                                    item { EmptyNotice("暂无研究记录", "完成复盘后，在这里查看结论与依据") }
                                }
                                items(orderedTasks, key = { it.id }) { research ->
                                    TextButton(
                                        onClick = { selectedTask = research },
                                        modifier = Modifier.fillMaxWidth(),
                                        contentPadding = PaddingValues(16.dp),
                                    ) {
                                        Column(
                                            Modifier.fillMaxWidth(),
                                            verticalArrangement = Arrangement.spacedBy(8.dp),
                                        ) {
                                            Text(
                                                research.title,
                                                style = MaterialTheme.typography.titleMedium,
                                                color = MaterialTheme.colorScheme.onSurface,
                                            )
                                            TaskStatusLabel(research.status)
                                            Text(
                                                "数据 ${research.asOf} · 创建于 ${createdDisplay(research.createdAt)} · #${research.id.takeLast(6)}",
                                                style = MaterialTheme.typography.bodySmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            )
                                        }
                                    }
                                    HorizontalDivider()
                                }
                            }
                            else -> LazyColumn(Modifier.fillMaxSize()) {
                                if (notifications.isEmpty() && operation == null) {
                                    item { EmptyNotice("暂无通知", "当前没有需要关注的通知") }
                                }
                                items(notifications, key = { it.id }) { notification ->
                                    Column(
                                        Modifier.fillMaxWidth().padding(16.dp),
                                        verticalArrangement = Arrangement.spacedBy(8.dp),
                                    ) {
                                        Text(notification.title, style = MaterialTheme.typography.titleMedium)
                                        Text(notification.body, style = MaterialTheme.typography.bodyMedium)
                                        Text(
                                            notification.createdAt,
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        )
                                        if (notification.readAt == null) {
                                            TextButton(
                                                onClick = {
                                                    perform("正在标记已读") {
                                                        client.markNotificationRead(notification.id)
                                                        notifications = notifications.map { current ->
                                                            if (current.id == notification.id) current.copy(readAt = "read")
                                                            else current
                                                        }
                                                    }
                                                },
                                                enabled = operation == null,
                                            ) { Text("标记已读") }
                                        }
                                    }
                                    HorizontalDivider()
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

internal fun statusText(status: String): String = when (status) {
    "WAITING_APPROVAL" -> "待处理"
    "BLOCKED" -> "已被规则拦截"
    "WATCH" -> "观察"
    "DONE", "APPROVED" -> "已完成"
    "FAILED", "RETRYABLE", "TIMEOUT" -> "需要处理"
    "QUEUED" -> "排队中"
    "PLANNING", "RUNNING", "REVIEWING" -> "分析中"
    "PAUSED" -> "已暂停"
    "REJECTED" -> "已拒绝"
    "NO_ACTION" -> "暂不行动"
    "CANCELLED" -> "已取消"
    "EXPIRED" -> "已过期"
    else -> status
}

@Composable
internal fun PiaIcon(resourceId: Int, description: String?) {
    Icon(
        painter = painterResource(resourceId),
        contentDescription = description,
        modifier = Modifier.size(20.dp),
    )
}

@Composable
internal fun TaskStatusLabel(status: String) {
    val color = when (status) {
        "BLOCKED", "FAILED", "RETRYABLE", "TIMEOUT" -> MaterialTheme.colorScheme.error
        "WAITING_APPROVAL", "PLANNING", "RUNNING", "REVIEWING" -> MaterialTheme.colorScheme.primary
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Spacer(Modifier.size(8.dp).background(color, CircleShape))
        Text(statusText(status), style = MaterialTheme.typography.bodyMedium, color = color)
    }
}

@Composable
internal fun ErrorNotice(message: String) {
    Text(
        message,
        modifier = Modifier.fillMaxWidth().padding(16.dp),
        color = MaterialTheme.colorScheme.error,
        style = MaterialTheme.typography.bodyMedium,
    )
}

@Composable
private fun EmptyNotice(title: String, message: String) {
    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = MaterialTheme.typography.titleMedium)
        Text(message, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun SummaryRow(title: String, value: String, caption: String) {
    ListItem(
        headlineContent = { Text(title) },
        supportingContent = { Text(caption) },
        trailingContent = {
            Text(value, style = MaterialTheme.typography.titleLarge.copy(fontFeatureSettings = "tnum"))
        },
    )
}
