import Foundation

public enum TaskStatus: String, Codable, Sendable {
    case queued = "QUEUED"
    case planning = "PLANNING"
    case running = "RUNNING"
    case reviewing = "REVIEWING"
    case paused = "PAUSED"
    case waitingApproval = "WAITING_APPROVAL"
    case approved = "APPROVED"
    case rejected = "REJECTED"
    case blocked = "BLOCKED"
    case noAction = "NO_ACTION"
    case retryable = "RETRYABLE"
    case failed = "FAILED"
    case timeout = "TIMEOUT"
    case cancelled = "CANCELLED"
    case expired = "EXPIRED"
    case done = "DONE"
}

public enum JSONValue: Codable, Sendable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value")
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }
}

public struct ResearchTask: Codable, Identifiable, Sendable {
    public let id: String
    public let triggerType: String
    public let status: TaskStatus
    public let target: [String: JSONValue]?
    public let createdAt: String
    public let dataSnapshotID: String?
    public let ruleSnapshotID: String?

    public init(
        id: String,
        triggerType: String,
        status: TaskStatus,
        target: [String: JSONValue]? = nil,
        createdAt: String,
        dataSnapshotID: String? = nil,
        ruleSnapshotID: String? = nil
    ) {
        self.id = id
        self.triggerType = triggerType
        self.status = status
        self.target = target
        self.createdAt = createdAt
        self.dataSnapshotID = dataSnapshotID
        self.ruleSnapshotID = ruleSnapshotID
    }

    enum CodingKeys: String, CodingKey {
        case id
        case triggerType = "trigger_type"
        case status
        case target
        case createdAt = "created_at"
        case dataSnapshotID = "data_snapshot_id"
        case ruleSnapshotID = "rule_snapshot_id"
    }
}

public struct Evidence: Codable, Sendable {
    public let id: String?
    public let source: String
    public let providerID: String?
    public let title: String
    public let observedAt: String
    public let asOf: String
    public let expiresAt: String?
    public let quality: String
    public let excerpt: String?
    public let snapshotID: String?
    public let usedBy: [String]?

    enum CodingKeys: String, CodingKey {
        case id, source, providerID = "provider_id", title, quality, excerpt, usedBy = "used_by"
        case observedAt = "observed_at"
        case asOf = "as_of"
        case expiresAt = "expires_at"
        case snapshotID = "snapshot_id"
    }
}

public struct TaskListResponse: Codable, Sendable {
    public let tasks: [ResearchTask]
}

public struct TaskResponse: Codable, Sendable {
    public let task: ResearchTask
}

public struct TaskDetailResponse: Codable, Sendable {
    public let task: ResearchTask
    public let decision: [String: JSONValue]?
    public let evidence: [Evidence]
    public let trace: [[String: JSONValue]]
    public let approvals: [[String: JSONValue]]
    public let events: [[String: JSONValue]]
}

public struct TaskEvent: Sendable {
    public let eventType: String
    public let payload: [String: JSONValue]
    public let createdAt: String?

    public init(
        eventType: String,
        payload: [String: JSONValue],
        createdAt: String? = nil
    ) {
        self.eventType = eventType
        self.payload = payload
        self.createdAt = createdAt
    }
}

public struct TaskContextResponse: Codable, Sendable {
    public let exportedAt: String
    public let taskDetail: TaskDetailResponse
    public let profile: [String: JSONValue]
    public let rules: [String: JSONValue]
    public let ruleSnapshotID: String

    enum CodingKeys: String, CodingKey {
        case exportedAt = "exported_at"
        case taskDetail = "task_detail"
        case profile
        case rules
        case ruleSnapshotID = "rule_snapshot_id"
    }
}

public struct HealthResponse: Codable, Sendable {
    public let status: String
    public let runtime: String
    public let provider: [String: JSONValue]
    public let llm: [String: JSONValue]
}

public struct NotificationItem: Codable, Identifiable, Sendable {
    public let id: String
    public let taskID: String?
    public let eventType: String
    public let title: String
    public let body: String
    public let createdAt: String
    public let readAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, body
        case taskID = "task_id"
        case eventType = "event_type"
        case createdAt = "created_at"
        case readAt = "read_at"
    }
}

public struct NotificationListResponse: Codable, Sendable {
    public let notifications: [NotificationItem]
}

public struct DeviceRegistration: Codable, Sendable, Identifiable {
    public let deviceID: String
    public let userID: String?
    public let platform: String
    public let deviceName: String?
    public let pushToken: String?
    public let createdAt: String?
    public let lastSeenAt: String?
    public let active: Bool?

    public var id: String { deviceID }

    public init(
        deviceID: String,
        platform: String,
        deviceName: String? = nil,
        pushToken: String? = nil,
        userID: String? = nil,
        createdAt: String? = nil,
        lastSeenAt: String? = nil,
        active: Bool? = nil
    ) {
        self.deviceID = deviceID
        self.userID = userID
        self.platform = platform
        self.deviceName = deviceName
        self.pushToken = pushToken
        self.createdAt = createdAt
        self.lastSeenAt = lastSeenAt
        self.active = active
    }

    enum CodingKeys: String, CodingKey {
        case deviceID = "device_id"
        case userID = "user_id"
        case platform
        case deviceName = "device_name"
        case pushToken = "push_token"
        case createdAt = "created_at"
        case lastSeenAt = "last_seen_at"
        case active
    }
}

public struct DeviceListResponse: Codable, Sendable {
    public let devices: [DeviceRegistration]
}

public struct DeviceUnregisterResponse: Codable, Sendable {
    public let status: String
    public let deviceID: String

    enum CodingKeys: String, CodingKey {
        case status
        case deviceID = "device_id"
    }
}

public struct SyncChange: Codable, Sendable {
    public let cursor: Int
    public let taskID: String?
    public let eventType: String
    public let payload: [String: JSONValue]
    public let createdAt: String

    enum CodingKeys: String, CodingKey {
        case cursor
        case taskID = "task_id"
        case eventType = "event_type"
        case payload
        case createdAt = "created_at"
    }
}

public struct SyncResponse: Codable, Sendable {
    public let cursor: Int
    public let nextCursor: Int
    public let hasMore: Bool
    public let changes: [SyncChange]

    enum CodingKeys: String, CodingKey {
        case cursor
        case nextCursor = "next_cursor"
        case hasMore = "has_more"
        case changes
    }
}

public struct CreateTaskRequest: Encodable, Sendable {
    public let triggerType: String
    public let target: [String: JSONValue]
    public let fixture: [String: String]?

    public init(
        triggerType: String,
        target: [String: JSONValue],
        fixture: [String: String]? = nil
    ) {
        self.triggerType = triggerType
        self.target = target
        self.fixture = fixture
    }

    enum CodingKeys: String, CodingKey {
        case triggerType = "trigger_type"
        case target
        case fixture
    }
}

public struct ApprovalRequest: Encodable, Sendable {
    public let action: String
    public let notes: String?
}

public struct CancelRequest: Encodable, Sendable {
    public let reason: String?
}

public struct TakeoverRequest: Encodable, Sendable {
    public let notes: String?
}

public enum PiaAPIError: Error, Equatable, Sendable {
    case invalidResponse
    case http(status: Int, body: String)
    case decoding(String)
}
