import Foundation

public actor PiaAPIClient {
    private let baseURL: URL
    private let session: URLSession
    private var token: String?
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(baseURL: URL, token: String? = nil, session: URLSession = .shared) {
        if baseURL.absoluteString.hasSuffix("/") {
            self.baseURL = baseURL
        } else {
            self.baseURL = URL(string: "\(baseURL.absoluteString)/") ?? baseURL
        }
        self.token = token
        self.session = session
    }

    public func setToken(_ token: String?) {
        self.token = token?.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public func health() async throws -> HealthResponse {
        try await request(path: "/health")
    }

    public func tasks() async throws -> TaskListResponse {
        try await request(path: "/tasks")
    }

    public func task(_ id: String) async throws -> TaskDetailResponse {
        try await request(path: "/tasks/\(id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id)")
    }

    public func createTask(_ payload: CreateTaskRequest, idempotencyKey: String? = nil) async throws -> TaskResponse {
        var headers: [String: String] = [:]
        if let idempotencyKey {
            headers["Idempotency-Key"] = idempotencyKey
        }
        return try await request(path: "/tasks", method: "POST", body: payload, headers: headers)
    }

    public func approve(taskID: String, action: String, notes: String? = nil) async throws -> TaskDetailResponse {
        let body = ApprovalRequest(action: action, notes: notes)
        let _: TaskResponse = try await request(path: "/tasks/\(taskID)/approve", method: "POST", body: body)
        return try await task(taskID)
    }

    public func pause(taskID: String) async throws -> TaskResponse {
        try await request(path: "/tasks/\(taskID)/pause", method: "POST")
    }

    public func resume(taskID: String) async throws -> TaskResponse {
        try await request(path: "/tasks/\(taskID)/resume", method: "POST")
    }

    public func retry(taskID: String) async throws -> TaskResponse {
        try await request(path: "/tasks/\(taskID)/retry", method: "POST")
    }

    public func cancel(taskID: String, reason: String? = nil) async throws -> TaskResponse {
        let path = "/tasks/\(taskID)/cancel"
        if let reason {
            return try await request(
                path: path,
                method: "POST",
                body: CancelRequest(reason: reason)
            )
        }
        return try await request(path: path, method: "POST")
    }

    public func takeover(taskID: String, notes: String? = nil) async throws -> TaskContextResponse {
        let path = "/tasks/\(taskID)/takeover"
        if let notes {
            return try await request(
                path: path,
                method: "POST",
                body: TakeoverRequest(notes: notes)
            )
        }
        return try await request(path: path, method: "POST")
    }

    public func taskContext(taskID: String) async throws -> TaskContextResponse {
        try await request(path: "/tasks/\(taskID)/context")
    }

    public func notifications(unreadOnly: Bool = false) async throws -> NotificationListResponse {
        try await request(path: "/notifications?unread=\(unreadOnly ? "1" : "0")")
    }

    public func markNotificationRead(_ id: String) async throws {
        let _: StatusResponse = try await request(
            path: "/notifications/\(id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id)/read",
            method: "POST"
        )
    }

    public func devices() async throws -> DeviceListResponse {
        try await request(path: "/devices")
    }

    public func registerDevice(_ device: DeviceRegistration) async throws -> DeviceRegistration {
        try await request(path: "/devices", method: "POST", body: device)
    }

    public func unregisterDevice(_ deviceID: String) async throws -> DeviceUnregisterResponse {
        try await request(
            path: "/devices/\(deviceID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? deviceID)",
            method: "DELETE"
        )
    }

    public func sync(cursor: Int = 0, limit: Int = 100) async throws -> SyncResponse {
        try await request(path: "/sync?cursor=\(max(0, cursor))&limit=\(min(max(1, limit), 500))")
    }

    public func taskEventsURL(taskID: String) -> URL {
        baseURL.appendingPathComponent("tasks/\(taskID)/events")
    }

    public func streamTaskEvents(
        taskID: String,
        onEvent: @escaping @Sendable (TaskEvent) -> Void
    ) async throws {
        var request = URLRequest(url: taskEventsURL(taskID: taskID))
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        if let token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (bytes, response) = try await session.bytes(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw PiaAPIError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw PiaAPIError.http(status: httpResponse.statusCode, body: "")
        }

        var eventType = "message"
        var dataLines: [String] = []
        for try await line in bytes.lines {
            let normalized = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if normalized.isEmpty {
                if let event = decodeTaskEvent(
                    eventType: eventType,
                    data: dataLines.joined(separator: "\n")
                ) {
                    onEvent(event)
                }
                eventType = "message"
                dataLines.removeAll(keepingCapacity: true)
                continue
            }
            if normalized.hasPrefix("event:") {
                eventType = normalized.dropFirst("event:".count)
                    .trimmingCharacters(in: .whitespaces)
            } else if normalized.hasPrefix("data:") {
                dataLines.append(
                    normalized.dropFirst("data:".count)
                        .trimmingCharacters(in: .whitespaces)
                )
            }
        }
        if let event = decodeTaskEvent(
            eventType: eventType,
            data: dataLines.joined(separator: "\n")
        ) {
            onEvent(event)
        }
    }

    private func decodeTaskEvent(eventType: String, data: String) -> TaskEvent? {
        guard let raw = data.data(using: .utf8),
              let object = try? decoder.decode([String: JSONValue].self, from: raw)
        else {
            return nil
        }
        let payload: [String: JSONValue]
        if case .object(let nested)? = object["payload"] {
            payload = nested
        } else {
            payload = object
        }
        let resolvedType: String
        if case .string(let value)? = object["event_type"], !value.isEmpty {
            resolvedType = value
        } else {
            resolvedType = eventType
        }
        let createdAt: String?
        if case .string(let value)? = object["created_at"] {
            createdAt = value
        } else {
            createdAt = nil
        }
        return TaskEvent(
            eventType: resolvedType,
            payload: payload,
            createdAt: createdAt
        )
    }

    private func request<Response: Decodable>(
        path: String,
        method: String = "GET",
        body: (any Encodable)? = nil,
        headers: [String: String] = [:]
    ) async throws -> Response {
        guard let url = URL(
            string: path.trimmingCharacters(in: CharacterSet(charactersIn: "/")),
            relativeTo: baseURL
        ) else {
            throw PiaAPIError.invalidResponse
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        headers.forEach { request.setValue($0.value, forHTTPHeaderField: $0.key) }
        if let body {
            request.httpBody = try encoder.encode(AnyEncodable(body))
        }
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw PiaAPIError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw PiaAPIError.http(
                status: httpResponse.statusCode,
                body: String(data: data, encoding: .utf8) ?? ""
            )
        }
        do {
            return try decoder.decode(Response.self, from: data)
        } catch {
            throw PiaAPIError.decoding(error.localizedDescription)
        }
    }
}

private struct AnyEncodable: Encodable {
    private let encodeValue: (Encoder) throws -> Void

    init(_ value: any Encodable) {
        self.encodeValue = value.encode
    }

    func encode(to encoder: Encoder) throws {
        try encodeValue(encoder)
    }
}

private struct StatusResponse: Decodable {
    let status: String
    let notificationID: String?

    enum CodingKeys: String, CodingKey {
        case status
        case notificationID = "notification_id"
    }
}
