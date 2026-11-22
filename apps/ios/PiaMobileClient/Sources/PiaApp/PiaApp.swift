import Foundation
import PiaMobileClient
import SwiftUI

#if os(iOS)
import UIKit
import UserNotifications

final class PiaAppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    let pushTokenStore = PiaPushTokenStore()

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        pushTokenStore.save(deviceToken.map { String(format: "%02x", $0) }.joined())
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        pushTokenStore.clear()
    }
}
#endif

private enum PiaCloudConfiguration {
    static var baseURL: URL {
        let configured = UserDefaults.standard.string(forKey: "pia.cloud_base_url")
            ?? ProcessInfo.processInfo.environment["PIA_CLOUD_URL"]
            ?? UserDefaults.standard.string(forKey: "pia.server_base_url")
            ?? ProcessInfo.processInfo.environment["PIA_SERVER_URL"]
            ?? "http://127.0.0.1:8765/api"
        return URL(string: configured) ?? URL(string: "http://127.0.0.1:8765/api")!
    }
}

private func displayTaskStatus(_ status: TaskStatus) -> String {
    switch status {
    case .waitingApproval: return "待处理"
    case .blocked: return "已被规则拦截"
    case .done, .approved: return "已完成"
    case .failed, .retryable, .timeout: return "需要处理"
    case .queued: return "排队中"
    case .planning, .running, .reviewing: return "分析中"
    case .paused: return "已暂停"
    case .rejected: return "已拒绝"
    case .noAction: return "暂不行动"
    case .cancelled: return "已取消"
    case .expired: return "已过期"
    }
}

private enum PiaPalette {
    static func onAccent(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 6.0 / 255, green: 62.0 / 255, blue: 50.0 / 255)
            : .white
    }

    static func accent(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 158.0 / 255, green: 216.0 / 255, blue: 197.0 / 255)
            : Color(red: 20.0 / 255, green: 107.0 / 255, blue: 95.0 / 255)
    }

    static func negative(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 1, green: 180.0 / 255, blue: 171.0 / 255)
            : Color(red: 179.0 / 255, green: 38.0 / 255, blue: 30.0 / 255)
    }
}

private struct TaskStatusLabel: View {
    let status: TaskStatus
    @Environment(\.colorScheme) private var colorScheme

    private var color: Color {
        switch status {
        case .blocked, .failed, .retryable, .timeout: PiaPalette.negative(colorScheme)
        case .waitingApproval, .planning, .running, .reviewing: PiaPalette.accent(colorScheme)
        default: .secondary
        }
    }

    var body: some View {
        HStack(spacing: 8) {
            Circle().fill(color).frame(width: 8, height: 8).accessibilityHidden(true)
            Text(displayTaskStatus(status)).font(.subheadline).foregroundStyle(color)
        }
        .accessibilityElement(children: .combine)
    }
}

@main
struct PiaApp: App {
    #if os(iOS)
    @UIApplicationDelegateAdaptor(PiaAppDelegate.self) private var appDelegate
    private let refreshCoordinator: PiaBackgroundRefreshCoordinator

    init() {
        let coordinator = PiaBackgroundRefreshCoordinator {
            let store = KeychainTokenStore()
            guard let stored = try? store.load(), !stored.isEmpty else {
                return false
            }
            let client = PiaAPIClient(
                baseURL: PiaCloudConfiguration.baseURL,
                token: stored
            )
            do {
                let cursor = UserDefaults.standard.integer(forKey: "pia.sync_cursor")
                let sync = try await client.sync(cursor: cursor)
                UserDefaults.standard.set(sync.nextCursor, forKey: "pia.sync_cursor")
                _ = try await client.notifications(unreadOnly: true)
                return true
            } catch {
                return false
            }
        }
        coordinator.register()
        try? coordinator.schedule()
        refreshCoordinator = coordinator
        Task { @MainActor in
            let center = UNUserNotificationCenter.current()
            let granted = (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
            guard granted else { return }
            UIApplication.shared.registerForRemoteNotifications()
        }
    }
    #endif

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    @State private var client = PiaAPIClient(baseURL: PiaCloudConfiguration.baseURL)
    private let tokenStore = KeychainTokenStore()
    #if os(iOS)
    private let pushTokenStore = PiaPushTokenStore()
    #endif
    @State private var token = ""
    @State private var connected = false
    @State private var tokenLoaded = false
    @State private var tasks: [ResearchTask] = []
    @State private var notifications: [NotificationItem] = []
    @State private var errorMessage: String?
    @State private var selectedTab = 0
    @State private var connecting = false
    @State private var refreshing = false
    @State private var creatingReview = false
    @State private var markingRead = false
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Group {
            if connected {
                workspace
            } else {
                NavigationStack {
                    login
                        .navigationTitle("Pia")
                }
            }
        }
        .tint(PiaPalette.accent(colorScheme))
        .task {
            if !tokenLoaded {
                tokenLoaded = true
                if let stored = try? tokenStore.load(), !stored.isEmpty {
                    token = stored
                    await connect()
                }
            } else if connected {
                await refresh()
            }
        }
    }

    private var login: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("投资研究")
                    .font(.title2.weight(.medium))
                Text("查看研究结论、核对依据，由你决定下一步")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                SecureField("访问令牌", text: $token)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()
                    .disabled(connecting)
                    #if os(iOS)
                    .textInputAutocapitalization(.never)
                    #endif
                Button {
                    Task { await connect() }
                } label: {
                    HStack(spacing: 8) {
                        if connecting { ProgressView().controlSize(.small) }
                        Text(connecting ? "正在连接" : "连接")
                    }
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .foregroundStyle(PiaPalette.onAccent(colorScheme))
                }
                .buttonStyle(.borderedProminent)
                .disabled(connecting || token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if let errorMessage {
                    Text(errorMessage).foregroundStyle(PiaPalette.negative(colorScheme))
                }
            }
            .frame(maxWidth: 560, alignment: .leading)
            .padding(24)
            .frame(maxWidth: .infinity)
        }
    }

    private var workspace: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                todayTab
                    .navigationTitle("Pia · 今天")
                    .toolbar { refreshToolbar }
            }
                .tabItem { Label("今天", systemImage: "sun.max") }
                .tag(0)
            NavigationStack {
                researchTab
                    .navigationTitle("Pia · 研究")
                    .toolbar { refreshToolbar }
            }
                .tabItem { Label("研究", systemImage: "chart.line.uptrend.xyaxis") }
                .tag(1)
            NavigationStack {
                alertsTab
                    .navigationTitle("Pia · 通知")
                    .toolbar { refreshToolbar }
            }
                .tabItem { Label("通知", systemImage: "bell") }
                .tag(2)
        }
    }

    private var todayTab: some View {
        List {
            workspaceStatus
            Section { setupCard }
            Section {
                summaryRow(title: "研究记录", value: tasks.count, caption: "所有复盘")
                summaryRow(title: "未读通知", value: notifications.filter { $0.readAt == nil }.count, caption: "需要关注")
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #endif
        .refreshable { await refresh() }
    }

    private var setupCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(tasks.isEmpty ? "开始研究" : "今日复盘")
                .font(.title3.weight(.medium))
            Text(tasks.isEmpty ? "完成一次收盘复盘，查看结论与依据" : "已有 \(tasks.count) 份研究记录")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Button {
                Task { await createReview() }
            } label: {
                HStack(spacing: 8) {
                    if creatingReview { ProgressView().controlSize(.small) }
                    else { Image(systemName: "plus.circle").frame(width: 20, height: 20).accessibilityHidden(true) }
                    Text(creatingReview ? "正在创建复盘" : (tasks.isEmpty ? "开始第一次复盘" : "开始今日复盘"))
                }
                .frame(maxWidth: .infinity, minHeight: 44)
                .foregroundStyle(PiaPalette.onAccent(colorScheme))
            }
            .buttonStyle(.borderedProminent)
            .disabled(creatingReview || refreshing)
        }
        .padding(.vertical, 8)
    }

    private var researchTab: some View {
        List {
            workspaceStatus
            Section {
                Button {
                    Task { await createReview() }
                } label: {
                    Label { Text(creatingReview ? "正在创建复盘" : "开始今日复盘") } icon: {
                        Image(systemName: "plus.circle").frame(width: 20, height: 20)
                    }
                }
                .disabled(creatingReview || refreshing)
            }
            Section("你的研究") {
                if tasks.isEmpty && !refreshing {
                    Text("暂无研究记录")
                        .foregroundStyle(.secondary)
                }
                ForEach(tasks.filter { $0.status == .waitingApproval } + tasks.filter { $0.status != .waitingApproval }) { task in
                    NavigationLink {
                        TaskDetailView(client: client, task: task)
                            .onDisappear { Task { await refresh() } }
                    } label: {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(task.researchTitle)
                                .font(.headline.weight(.medium))
                            TaskStatusLabel(status: task.status)
                            Text("数据 \(task.researchDate) · 创建于 \(task.createdDisplay) · #\(task.id.suffix(6))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .refreshable { await refresh() }
    }

    private var alertsTab: some View {
        List {
            workspaceStatus
            Section("通知") {
                if notifications.isEmpty && !refreshing {
                    Text("暂无需要关注的通知")
                        .foregroundStyle(.secondary)
                }
                ForEach(notifications) { notification in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(notification.title).font(.headline.weight(.medium))
                        Text(notification.body).font(.subheadline)
                        Text(notification.createdAt).font(.caption).foregroundStyle(.secondary)
                        Text(notification.eventType).font(.caption).foregroundStyle(.secondary)
                        if notification.readAt == nil {
                            Button("标记已读") {
                                Task { await markRead(notification.id) }
                            }
                            .buttonStyle(.borderless)
                            .disabled(markingRead || refreshing)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .refreshable { await refresh() }
    }

    private func summaryRow(title: String, value: Int, caption: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            LabeledContent {
                Text(value, format: .number).font(.title2.weight(.medium)).monospacedDigit()
            } label: {
                Text(title)
            }
            Text(caption).font(.caption).foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var workspaceStatus: some View {
        if refreshing || creatingReview || markingRead {
            Section {
                ProgressView(creatingReview ? "正在创建复盘" : (markingRead ? "正在标记已读" : "正在刷新"))
            }
        }
        if let errorMessage {
            Section {
                Text(errorMessage).foregroundStyle(PiaPalette.negative(colorScheme))
                Button("重新加载") { Task { await refresh() } }
                    .disabled(refreshing || creatingReview || markingRead)
            }
        }
    }

    @ToolbarContentBuilder
    private var refreshToolbar: some ToolbarContent {
        ToolbarItem(placement: .primaryAction) {
            Button {
                Task { await refresh() }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .frame(width: 20, height: 20)
                    .frame(minWidth: 44, minHeight: 44)
            }
            .accessibilityLabel("刷新")
            .help("刷新")
            .disabled(refreshing || creatingReview || markingRead)
        }
    }

    private func markRead(_ id: String) async {
        guard !markingRead, !refreshing else { return }
        markingRead = true
        errorMessage = nil
        defer { markingRead = false }
        do {
            try await client.markNotificationRead(id)
            await refresh()
        } catch {
            errorMessage = researchErrorMessage(error, fallback: "标记通知失败，请重试。")
        }
    }

    private func refresh() async {
        guard !refreshing else { return }
        refreshing = true
        errorMessage = nil
        defer { refreshing = false }
        do {
            async let taskResponse = client.tasks()
            async let notificationResponse = client.notifications()
            tasks = try await taskResponse.tasks
            notifications = try await notificationResponse.notifications
            let cursor = UserDefaults.standard.integer(forKey: "pia.sync_cursor")
            let sync = try await client.sync(cursor: cursor)
            UserDefaults.standard.set(sync.nextCursor, forKey: "pia.sync_cursor")
            #if os(iOS)
            let pushToken = pushTokenStore.load()
            #else
            let pushToken: String? = nil
            #endif
            _ = try? await client.registerDevice(
                DeviceRegistration(
                    deviceID: deviceID,
                    platform: "ios",
                    deviceName: "Pia iOS",
                    pushToken: pushToken
                )
            )
            errorMessage = nil
        } catch {
            errorMessage = researchErrorMessage(error, fallback: "刷新失败，请重试。")
        }
    }

    private func createReview() async {
        guard !creatingReview, !refreshing else { return }
        creatingReview = true
        errorMessage = nil
        defer { creatingReview = false }
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone(identifier: "Asia/Shanghai")
        do {
            _ = try await client.createTask(
                CreateTaskRequest(
                    triggerType: "MarketClose",
                    target: ["as_of": .string(formatter.string(from: Date()))]
                ),
                idempotencyKey: UUID().uuidString
            )
            selectedTab = 1
            await refresh()
        } catch {
            errorMessage = researchErrorMessage(error, fallback: "创建收盘复盘失败，请重试。")
        }
    }

    private func connect() async {
        guard !connecting else { return }
        connecting = true
        errorMessage = nil
        defer { connecting = false }
        await client.setToken(token)
        do {
            _ = try await client.health()
            try? tokenStore.save(token)
            connected = true
            await refresh()
        } catch {
            connected = false
            errorMessage = researchErrorMessage(error, fallback: "连接研究服务失败，请检查服务地址。")
        }
    }

    private var deviceID: String {
        if let existing = UserDefaults.standard.string(forKey: "pia.device_id") {
            return existing
        }
        let created = UUID().uuidString
        UserDefaults.standard.set(created, forKey: "pia.device_id")
        return created
    }


}

private struct TaskDetailView: View {
    let client: PiaAPIClient
    let task: ResearchTask
    @State private var detail: TaskDetailResponse?
    @State private var liveEventCount = 0
    @State private var errorMessage: String?
    @State private var busy = false
    @State private var loading = false
    @State private var showingProgress = false
    @State private var actionsVerified = false
    @State private var evidenceExpanded = false
    @State private var traceExpanded = false
    @State private var rulesExpanded = false
    @State private var reviewExpanded = false
    @Environment(\.colorScheme) private var colorScheme

    private var currentTask: ResearchTask { detail?.task ?? task }
    private var currentStatus: TaskStatus { currentTask.status }
    private var canReview: Bool { actionsVerified && currentStatus == .waitingApproval }
    private var canApprove: Bool { canReview && detail?.canConfirmRecommendation == true }

    var body: some View {
        List {
            if showingProgress || busy {
                Section { ProgressView(busy ? "正在提交" : "正在读取研究") }
            }
            if let errorMessage {
                Section {
                    Text(errorMessage).foregroundStyle(PiaPalette.negative(colorScheme))
                    Button("重新加载") { Task { await load() } }
                        .disabled(loading || busy)
                }
            }
            let rules = ResearchRule.from(detail?.decision)
            if let decision = detail?.decision {
                Section("研究结论") {
                    let status = stringValue(decision["status"]) ?? "分析中"
                    Text(status == "WATCH" ? "观察" : TaskStatus(rawValue: status).map(displayTaskStatus) ?? status)
                        .font(.headline)
                    if let blocker = rules.first(where: \.isBlocking) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(blocker.title)
                            Text(blocker.comparison).font(.subheadline).foregroundStyle(.secondary)
                        }
                    }
                    if let rationale = stringValue(decision["next_action"]) {
                        Text(researchNextAction(rationale)).foregroundStyle(.secondary)
                    }
                    LabeledContent("数据日期", value: currentTask.researchDate)
                    if let risk = stringValue(decision["risk_level"]) {
                        LabeledContent("风险", value: researchLevel(risk))
                    }
                    if let confidence = stringValue(decision["confidence"]) {
                        LabeledContent("置信度", value: researchLevel(confidence))
                    }
                }
            } else {
                Section(currentTask.researchTitle) {
                    TaskStatusLabel(status: currentStatus)
                    LabeledContent("数据日期", value: currentTask.researchDate)
                }
            }
            if canReview {
                Section {
                    DisclosureGroup(canApprove ? "查看确认选项" : "查看处理选项", isExpanded: $reviewExpanded) {
                        Text(canApprove ? "可确认建议" : "待处理 · 仅供研究")
                            .font(.headline)
                        LabeledContent("风险", value: researchLevel(stringValue(detail?.decision?["risk_level"]) ?? "—"))
                        LabeledContent("规则版本", value: currentTask.ruleSnapshotID ?? "—")
                        LabeledContent("数据日期", value: currentTask.researchDate)
                        if canApprove {
                            Button("接受建议") { performApproval("APPROVE") }
                                .buttonStyle(.borderedProminent)
                        }
                        Button("暂不行动") { performApproval("NO_ACTION") }
                        Button("继续研究") { performApproval("REQUEST_MORE_RESEARCH") }
                        if detail?.canMarkAsWatch == true {
                            Button("加入关注") { performApproval("MARK_AS_WATCH") }
                        }
                        Button("拒绝建议", role: .destructive) { performApproval("REJECT") }
                    }
                    .disabled(busy || loading)
                }
            }
            if detail?.decision != nil {
                Section {
                    DisclosureGroup("规则与风险 · \(rules.count)", isExpanded: $rulesExpanded) {
                        if rules.isEmpty {
                            Text("暂无规则触发记录").foregroundStyle(.secondary)
                        }
                        ForEach(Array(rules.enumerated()), id: \.offset) { _, rule in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(rule.title)
                                Text(rule.comparison).font(.subheadline).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            Section {
                DisclosureGroup("依据 · \(detail?.evidence.count ?? 0)", isExpanded: $evidenceExpanded) {
                    if detail?.evidence.isEmpty != false {
                        Text(loading ? "正在读取依据" : "暂无可引用的依据")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(evidenceRows) { row in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(row.evidence.title).font(.headline.weight(.medium))
                                Text(row.evidence.excerpt ?? "暂无摘要").font(.subheadline)
                                Text("\(row.evidence.source) · \(row.evidence.asOf) · \(researchEvidenceQuality(row.evidence))")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                if let provider = row.evidence.providerID {
                                    Text("数据源：\(provider)").font(.caption).foregroundStyle(.secondary)
                                }
                                if let usedBy = row.evidence.usedBy, !usedBy.isEmpty {
                                    Text("被使用于：\(usedBy.joined(separator: " · "))")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .padding(.vertical, 4)
                        }
                    }
                }
            }
            Section {
                DisclosureGroup("分析过程 · \(detail?.trace.count ?? 0)", isExpanded: $traceExpanded) {
                    if liveEventCount > 0 {
                        Text("已收到 \(liveEventCount) 次实时更新")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if let trace = detail?.trace, !trace.isEmpty {
                        ForEach(Array(trace.enumerated()), id: \.offset) { _, run in
                            Text(researchAgentLabel(stringValue(run["agent_name"])))
                                .font(.subheadline)
                        }
                    } else {
                        Text("分析还没有开始")
                            .foregroundStyle(.secondary)
                    }
                }
            }
            if actionsVerified && hasTaskControls {
                Section("任务控制") {
                if currentStatus == .queued {
                    Button("取消", role: .destructive) {
                        performControl { try await client.cancel(taskID: task.id, reason: "Cancelled from iOS") }
                    }
                } else if currentStatus == .paused {
                    Button("继续运行") { performControl { try await client.resume(taskID: task.id) } }
                    Button("取消", role: .destructive) {
                        performControl { try await client.cancel(taskID: task.id, reason: "Cancelled from iOS") }
                    }
                } else if [.planning, .running, .reviewing].contains(currentStatus) {
                    Button("暂停") { performControl { try await client.pause(taskID: task.id) } }
                    Button("取消", role: .destructive) {
                        performControl { try await client.cancel(taskID: task.id, reason: "Cancelled from iOS") }
                    }
                } else if [.retryable, .failed, .timeout].contains(currentStatus) {
                    Button("人工接管") {
                        performControl {
                            _ = try await client.takeover(
                                taskID: task.id,
                                notes: "Taken over from iOS"
                            )
                        }
                    }
                    Button("重试") { performControl { try await client.retry(taskID: task.id) } }
                }
                }
                .disabled(busy || loading)
            }
        }
        .navigationTitle(currentTask.researchTitle)
        .refreshable { await load() }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await load() }
                } label: {
                    Image(systemName: "arrow.clockwise").frame(width: 20, height: 20).frame(minWidth: 44, minHeight: 44)
                }
                .accessibilityLabel("刷新")
                .help("刷新")
                .disabled(loading || busy)
            }
        }
        .task {
            await load()
            await streamEvents()
        }
    }

    private var hasTaskControls: Bool {
        [.queued, .paused, .planning, .running, .reviewing, .retryable, .failed, .timeout].contains(currentStatus)
    }

    private struct EvidenceRow: Identifiable {
        let id: String
        let evidence: Evidence
    }

    private var evidenceRows: [EvidenceRow] {
        var occurrences: [String: Int] = [:]
        return (detail?.evidence ?? []).map { evidence in
            let identity = evidence.id ?? "\(evidence.source)|\(evidence.asOf)|\(evidence.title)"
            let occurrence = occurrences[identity, default: 0]
            occurrences[identity] = occurrence + 1
            return EvidenceRow(id: "\(identity)|\(occurrence)", evidence: evidence)
        }
    }

    private func load(showProgress: Bool = true) async {
        guard !loading, !busy else { return }
        loading = true
        showingProgress = showProgress
        defer {
            loading = false
            showingProgress = false
        }
        do {
            detail = try await client.task(task.id)
            actionsVerified = true
            if currentStatus == .blocked { rulesExpanded = true }
            errorMessage = nil
        } catch {
            actionsVerified = false
            errorMessage = researchErrorMessage(error, fallback: "读取研究失败，请刷新重试。")
        }
    }

    private func streamEvents() async {
        do {
            try await client.streamTaskEvents(taskID: task.id) { _ in
                Task { @MainActor in
                    liveEventCount += 1
                    await load(showProgress: false)
                }
            }
        } catch {
            // The detail view remains usable through explicit refresh when SSE
            // is unavailable or the task reaches a terminal state.
        }
    }

    private func performApproval(_ action: String) {
        guard !busy, !loading, canReview else { return }
        if action == "APPROVE", !canApprove { return }
        if action == "MARK_AS_WATCH", detail?.canMarkAsWatch != true { return }
        busy = true
        errorMessage = nil
        Task {
            do {
                detail = try await client.approve(taskID: task.id, action: action, notes: "Reviewed in iOS")
                errorMessage = nil
            } catch {
                actionsVerified = false
                errorMessage = researchErrorMessage(error, fallback: "提交处理结果失败，请刷新后重试。")
            }
            busy = false
        }
    }

    private func performControl<T: Sendable>(_ operation: @escaping () async throws -> T) {
        guard !busy, !loading, actionsVerified else { return }
        busy = true
        errorMessage = nil
        Task {
            do {
                _ = try await operation()
                detail = try await client.task(task.id)
                actionsVerified = true
            } catch {
                actionsVerified = false
                errorMessage = researchErrorMessage(error, fallback: "更新研究任务失败，请刷新后重试。")
            }
            busy = false
        }
    }

    private func stringValue(_ value: JSONValue?) -> String? {
        guard let value else { return nil }
        if case .string(let text) = value { return text }
        if case .number(let number) = value { return number.formatted() }
        return nil
    }
}
