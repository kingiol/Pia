package com.pia.mobile

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONObject

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun ResearchDetailScreen(
    client: PiaApiClient,
    task: PiaTask,
    onBack: () -> Unit,
    onTaskChanged: suspend () -> Unit,
) {
    var detail by remember { mutableStateOf<JSONObject?>(null) }
    var loading by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var actionsVerified by remember { mutableStateOf(false) }
    var evidenceExpanded by rememberSaveable { mutableStateOf(false) }
    var traceExpanded by rememberSaveable { mutableStateOf(false) }
    var reviewExpanded by rememberSaveable { mutableStateOf(false) }
    var rulesExpanded by rememberSaveable { mutableStateOf(task.status == "BLOCKED") }
    val mutex = remember { Mutex() }
    val scope = rememberCoroutineScope()
    val currentTask = detail?.optJSONObject("task")
    val status = currentTask?.text("status") ?: task.status
    val target = currentTask?.optJSONObject("target")
    val dataDate = target?.text("as_of") ?: task.asOf
    val eligible = detail?.optJSONObject("result_metadata")?.opt("action_eligible") == true
    val hasSymbol = target?.symbol() != null
    val decision = detail?.optJSONObject("decision")
    val rules = remember(decision) { researchRules(decision) }
    val evidence = detail?.optJSONArray("evidence")
    val trace = detail?.optJSONArray("trace")

    suspend fun load() {
        mutex.withLock {
            detail = client.task(task.id)
            actionsVerified = true
            if (detail?.optJSONObject("task")?.text("status") == "BLOCKED") rulesExpanded = true
        }
    }

    fun refresh() {
        if (loading || busy) return
        loading = true
        error = null
        scope.launch {
            try {
                load()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (failure: Exception) {
                actionsVerified = false
                error = failure.message ?: "读取研究失败，请刷新重试"
            } finally {
                loading = false
            }
        }
    }

    fun act(action: String) {
        if (busy || loading || !actionsVerified) return
        val latestStatus = detail?.optJSONObject("task")?.text("status") ?: return
        if (taskActions(latestStatus, eligible, hasSymbol).none { it.second == action }) return
        busy = true
        error = null
        scope.launch {
            try {
                mutex.withLock {
                    when (action) {
                        "APPROVE", "REJECT", "NO_ACTION", "REQUEST_MORE_RESEARCH", "MARK_AS_WATCH" ->
                            client.approve(task.id, action, "Reviewed in Android")
                        "PAUSE" -> client.pause(task.id)
                        "RESUME" -> client.resume(task.id)
                        "CANCEL" -> client.cancel(task.id, "Cancelled from Android")
                        "TAKEOVER" -> client.takeover(task.id, "Taken over from Android")
                        "RETRY" -> client.retry(task.id)
                        else -> throw IllegalArgumentException("Unsupported task action: $action")
                    }
                    actionsVerified = false
                    detail = client.task(task.id)
                    actionsVerified = true
                }
                onTaskChanged()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (failure: Exception) {
                // Require a fresh status before retrying an action whose outcome is uncertain.
                actionsVerified = false
                error = failure.message ?: "提交失败，请刷新后重试"
            } finally {
                busy = false
            }
        }
    }

    BackHandler(onBack = onBack)
    LaunchedEffect(task.id) {
        try {
            load()
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (failure: Exception) {
            error = failure.message ?: "读取研究失败，请刷新重试"
        } finally {
            loading = false
        }
        try {
            client.taskEvents(task.id).collect { load() }
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            // The refresh control remains available if the event stream disconnects.
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(task.title) },
                navigationIcon = {
                    IconButton(onClick = onBack) { PiaIcon(R.drawable.ic_phosphor_arrow_left, "返回") }
                },
                actions = {
                    IconButton(onClick = { refresh() }, enabled = !loading && !busy) {
                        PiaIcon(R.drawable.ic_phosphor_arrow_clockwise, "刷新")
                    }
                },
            )
        },
    ) { insets ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(insets),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            if (loading || busy) {
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        LinearProgressIndicator(Modifier.fillMaxWidth())
                        Text(if (busy) "正在提交" else "正在读取研究", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            error?.let { message ->
                item {
                    ErrorNotice(message)
                    TextButton(onClick = { refresh() }, enabled = !loading && !busy) { Text("重新加载") }
                }
            }
            if (decision != null) {
                item {
                    DetailSection("研究结论") {
                        decision.text("status")?.let { Text(statusText(it), style = MaterialTheme.typography.titleMedium) }
                        rules.firstOrNull { it.isBlocking }?.let {
                            Text(it.title, style = MaterialTheme.typography.titleMedium)
                            Text(it.comparison)
                        }
                        decision.text("next_action")?.let { Text(researchNextAction(it)) }
                        DetailValue("数据日期", dataDate)
                        decision.text("risk_level")?.let { DetailValue("风险", researchLevel(it)) }
                        decision.text("confidence")?.let { DetailValue("置信度", researchLevel(it)) }
                    }
                }
            } else {
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        TaskStatusLabel(status)
                        DetailValue("数据日期", dataDate)
                    }
                }
            }
            if (actionsVerified && status == "WAITING_APPROVAL") {
                item {
                    DisclosureHeading(if (eligible) "查看确认选项" else "查看处理选项", reviewExpanded) {
                        reviewExpanded = !reviewExpanded
                    }
                    if (reviewExpanded) {
                        DetailSection(if (eligible) "可确认建议" else "待处理 · 仅供研究") {
                            DetailValue("风险", researchLevel(decision?.text("risk_level") ?: "—"))
                            DetailValue("规则版本", currentTask?.text("rule_snapshot_id") ?: "—")
                            DetailValue("数据日期", dataDate)
                            TaskActionButtons(taskActions(status, eligible, hasSymbol), !busy && !loading, ::act)
                        }
                    }
                }
            }
            if (decision != null) {
                item {
                    DisclosureHeading("规则与风险 · ${rules.size}", rulesExpanded) { rulesExpanded = !rulesExpanded }
                    if (rulesExpanded) {
                        if (rules.isEmpty()) Text("暂无规则触发记录")
                        rules.forEach { DetailValue(it.title, it.comparison) }
                    }
                }
            }
            item {
                DisclosureHeading("依据 · ${evidence?.length() ?: 0}", evidenceExpanded) {
                    evidenceExpanded = !evidenceExpanded
                }
                if (evidenceExpanded && (evidence == null || evidence.length() == 0)) {
                    Text(if (loading) "正在读取依据" else "暂无可引用的依据")
                }
            }
            if (evidenceExpanded && evidence != null) {
                items(evidence.length()) { index ->
                    val item = evidence.optJSONObject(index)
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(item?.text("title") ?: "研究依据", style = MaterialTheme.typography.titleMedium)
                        Text(item?.text("excerpt") ?: "暂无摘要")
                        item?.text("source")?.let { DetailValue("来源", it) }
                        item?.text("provider_id")?.let { DetailValue("数据源", it) }
                        item?.text("as_of")?.let { DetailValue("数据日期", it) }
                        item?.let { DetailValue("质量", evidenceQuality(it)) }
                        val usedBy = item?.optJSONArray("used_by")
                        if (usedBy != null && usedBy.length() > 0) {
                            DetailValue("被使用于", (0 until usedBy.length()).map { usedBy.optString(it) }.joinToString(" · "))
                        }
                        HorizontalDivider()
                    }
                }
            }
            item {
                DisclosureHeading("分析过程 · ${trace?.length() ?: 0}", traceExpanded) {
                    traceExpanded = !traceExpanded
                }
                if (traceExpanded && (trace == null || trace.length() == 0)) Text("分析还没有开始")
            }
            if (traceExpanded && trace != null) {
                items(trace.length()) { index ->
                    val run = trace.optJSONObject(index)
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(run?.text("agent_name") ?: "分析步骤", style = MaterialTheme.typography.titleMedium)
                        run?.text("status")?.let { Text(statusText(it), style = MaterialTheme.typography.bodySmall) }
                        HorizontalDivider()
                    }
                }
            }
            if (actionsVerified && status != "WAITING_APPROVAL") {
                val actions = taskActions(status)
                if (actions.isNotEmpty()) {
                    item {
                        DetailSection("任务控制") {
                            TaskActionButtons(actions, !busy && !loading, ::act)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TaskActionButtons(
    actions: List<Pair<String, String>>,
    enabled: Boolean,
    onAction: (String) -> Unit,
) {
    actions.forEach { (label, action) ->
        if (action in setOf("APPROVE", "RESUME", "RETRY")) {
            Button(onClick = { onAction(action) }, enabled = enabled, modifier = Modifier.fillMaxWidth()) {
                Text(label)
            }
        } else {
            OutlinedButton(onClick = { onAction(action) }, enabled = enabled, modifier = Modifier.fillMaxWidth()) {
                Text(label, color = if (enabled && action in setOf("REJECT", "CANCEL")) {
                    MaterialTheme.colorScheme.error
                } else {
                    LocalContentColor.current
                })
            }
        }
    }
}

@Composable
private fun DetailSection(title: String, content: @Composable () -> Unit) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        HorizontalDivider()
        Text(title, style = MaterialTheme.typography.titleMedium)
        content()
    }
}

@Composable
private fun DetailValue(label: String, value: String) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun DisclosureHeading(title: String, expanded: Boolean, onClick: () -> Unit) {
    Column {
        HorizontalDivider()
        TextButton(onClick = onClick, modifier = Modifier.fillMaxWidth(), contentPadding = PaddingValues(vertical = 12.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    title,
                    Modifier.weight(1f),
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                androidx.compose.material3.Icon(
                    painter = androidx.compose.ui.res.painterResource(R.drawable.ic_phosphor_caret_down),
                    contentDescription = if (expanded) "收起" else "展开",
                    modifier = Modifier.rotate(if (expanded) 180f else 0f),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}
