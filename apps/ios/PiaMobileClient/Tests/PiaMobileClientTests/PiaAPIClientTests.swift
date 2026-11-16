import Foundation
import XCTest
@testable import PiaMobileClient

final class PiaAPIClientTests: XCTestCase {
    func testCreateTaskSendsBearerAndIdempotencyHeaders() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        MockURLProtocol.handler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer mobile-token")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "mobile-task-1")
            return Self.response(
                status: 201,
                body: #"{"task":{"id":"task-1","trigger_type":"MarketClose","status":"QUEUED","created_at":"2026-11-07T00:00:00Z"}}"#
            )
        }
        let client = PiaAPIClient(
            baseURL: URL(string: "https://pia.example.test/api/")!,
            token: "mobile-token",
            session: URLSession(configuration: configuration)
        )

        let result = try await client.createTask(
            CreateTaskRequest(
                triggerType: "MarketClose",
                target: ["as_of": .string("2026-11-06")],
                fixture: nil
            ),
            idempotencyKey: "mobile-task-1"
        )

        XCTAssertEqual(result.task.id, "task-1")
        XCTAssertEqual(result.task.status, .queued)
    }

    func testUnauthorizedResponseIsExposed() async {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        MockURLProtocol.handler = { _ in
            Self.response(status: 401, body: #"{"error":"unauthorized"}"#)
        }
        let client = PiaAPIClient(
            baseURL: URL(string: "https://pia.example.test/api/")!,
            session: URLSession(configuration: configuration)
        )

        do {
            _ = try await client.tasks()
            XCTFail("Expected unauthorized error")
        } catch let error as PiaAPIError {
            XCTAssertEqual(error, .http(status: 401, body: #"{"error":"unauthorized"}"#))
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    func testTaskDetailDecodesMixedJsonPayloads() throws {
        let payload = Data(#"""
        {
          "task": {
            "id": "task-2",
            "trigger_type": "StockResearch",
            "status": "WAITING_APPROVAL",
            "target": {"as_of": "2026-11-06", "symbols": ["600000.SH"], "priority": 3},
            "created_at": "2026-11-07T00:00:00Z"
          },
          "decision": {"status": "WAITING_APPROVAL", "confidence": 0.72},
          "evidence": [],
          "trace": [{"agent_name": "Market Agent", "output": {"breadth": 0.4}}],
          "approvals": [],
          "events": []
        }
        """#.utf8)

        let result = try JSONDecoder().decode(TaskDetailResponse.self, from: payload)
        XCTAssertEqual(result.task.id, "task-2")
        XCTAssertEqual(result.task.target?["symbols"], .array([.string("600000.SH")]))
        XCTAssertEqual(result.decision?["confidence"], .number(0.72))
    }

    func testApprovalRefreshesDetailAfterAcknowledgement() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        MockURLProtocol.handler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer mobile-token")
            if request.httpMethod == "POST" {
                XCTAssertEqual(request.url?.path, "/api/tasks/task-approved/approve")
                return Self.response(
                    status: 200,
                    body: #"{"approval_id":"approval-1","task":{"id":"task-approved","trigger_type":"MarketClose","status":"NO_ACTION","created_at":"2026-11-07T00:00:00Z"}}"#
                )
            }
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.path, "/api/tasks/task-approved")
            return Self.response(
                status: 200,
                body: #"{"task":{"id":"task-approved","trigger_type":"MarketClose","status":"NO_ACTION","created_at":"2026-11-07T00:00:00Z"},"decision":null,"evidence":[],"trace":[],"approvals":[{"action":"NO_ACTION"}],"events":[]}"#
            )
        }
        let client = PiaAPIClient(
            baseURL: URL(string: "https://pia.example.test/api/")!,
            token: "mobile-token",
            session: URLSession(configuration: configuration)
        )

        let detail = try await client.approve(taskID: "task-approved", action: "NO_ACTION")

        XCTAssertEqual(detail.task.status, .noAction)
        XCTAssertEqual(detail.approvals.first?["action"], .string("NO_ACTION"))
    }

    func testDeviceRegistrationAndSyncUseCloudContract() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        MockURLProtocol.handler = { request in
            if request.httpMethod == "POST", request.url?.path.hasSuffix("/devices") == true {
                XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer mobile-token")
                return Self.response(
                    status: 201,
                    body: #"{"device_id":"ios-device","platform":"ios","active":true}"#
                )
            }
            XCTAssertEqual(request.url?.path, "/api/sync")
            XCTAssertEqual(request.url?.query, "cursor=4&limit=20")
            return Self.response(
                status: 200,
                body: #"{"cursor":4,"next_cursor":5,"has_more":false,"changes":[{"cursor":5,"event_type":"DEVICE_REGISTERED","payload":{"device_id":"ios-device"},"created_at":"2026-11-07T00:00:00Z"}]}"#
            )
        }
        let client = PiaAPIClient(
            baseURL: URL(string: "https://pia.example.test/api/")!,
            token: "mobile-token",
            session: URLSession(configuration: configuration)
        )

        let device = try await client.registerDevice(
            DeviceRegistration(deviceID: "ios-device", platform: "ios")
        )
        let sync = try await client.sync(cursor: 4, limit: 20)

        XCTAssertEqual(device.deviceID, "ios-device")
        XCTAssertEqual(sync.nextCursor, 5)
        XCTAssertEqual(sync.changes.first?.eventType, "DEVICE_REGISTERED")
    }

    func testPushTokenIsIncludedInDeviceRegistration() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        MockURLProtocol.handler = { request in
            let bodyData = request.httpBody ?? {
                guard let stream = request.httpBodyStream else { return Data() }
                stream.open()
                defer { stream.close() }
                var data = Data()
                var buffer = [UInt8](repeating: 0, count: 1024)
                while stream.hasBytesAvailable {
                    let count = stream.read(&buffer, maxLength: buffer.count)
                    if count <= 0 { break }
                    data.append(buffer, count: count)
                }
                return data
            }()
            let body = try? JSONSerialization.jsonObject(with: bodyData) as? [String: Any]
            XCTAssertEqual(body?["push_token"] as? String, "apns-token")
            return Self.response(
                status: 201,
                body: #"{"device_id":"ios-device","platform":"ios","push_token":"apns-token","active":true}"#
            )
        }
        let client = PiaAPIClient(
            baseURL: URL(string: "https://pia.example.test/api/")!,
            token: "mobile-token",
            session: URLSession(configuration: configuration)
        )

        let device = try await client.registerDevice(
            DeviceRegistration(
                deviceID: "ios-device",
                platform: "ios",
                pushToken: "apns-token"
            )
        )

        XCTAssertEqual(device.pushToken, "apns-token")
    }

    func testCancelTaskSendsReasonAndDecodesContext() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        MockURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/api/tasks/task-3/cancel")
            let bodyData = request.httpBody ?? {
                guard let stream = request.httpBodyStream else { return Data() }
                stream.open()
                defer { stream.close() }
                var data = Data()
                var buffer = [UInt8](repeating: 0, count: 1024)
                while stream.hasBytesAvailable {
                    let count = stream.read(&buffer, maxLength: buffer.count)
                    if count <= 0 { break }
                    data.append(buffer, count: count)
                }
                return data
            }()
            let body = try? JSONSerialization.jsonObject(with: bodyData) as? [String: String]
            XCTAssertEqual(body?["reason"], "user requested")
            return Self.response(
                status: 200,
                body: #"{"task":{"id":"task-3","trigger_type":"MarketClose","status":"CANCELLED","created_at":"2026-11-07T00:00:00Z"}}"#
            )
        }
        let client = PiaAPIClient(
            baseURL: URL(string: "https://pia.example.test/api/")!,
            token: "mobile-token",
            session: URLSession(configuration: configuration)
        )

        let response = try await client.cancel(taskID: "task-3", reason: "user requested")
        XCTAssertEqual(response.task.status, .cancelled)
    }

    func testTaskEventsDecodeAuthenticatedSSEFrames() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        MockURLProtocol.handler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer mobile-token")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "text/event-stream")
            return (
                HTTPURLResponse(
                    url: request.url!,
                    statusCode: 200,
                    httpVersion: nil,
                    headerFields: ["Content-Type": "text/event-stream"]
                )!,
                Data(
                    """
                    event: TASK_STATUS
                    data: {"event_type":"TASK_STATUS","payload":{"status":"RUNNING"},"created_at":"2026-11-07T00:00:00Z"}

                    """.utf8
                )
            )
        }
        let client = PiaAPIClient(
            baseURL: URL(string: "https://pia.example.test/api/")!,
            token: "mobile-token",
            session: URLSession(configuration: configuration)
        )

        let received = EventCollector()
        try await client.streamTaskEvents(taskID: "task-4") { event in
            received.append(event)
        }

        let events = received.values
        XCTAssertEqual(events.count, 1)
        XCTAssertEqual(events[0].eventType, "TASK_STATUS")
        XCTAssertEqual(events[0].createdAt, "2026-11-07T00:00:00Z")
        XCTAssertEqual(events[0].payload["status"], .string("RUNNING"))
    }

    private static func response(status: Int, body: String) -> (HTTPURLResponse, Data) {
        (
            HTTPURLResponse(
                url: URL(string: "https://pia.example.test/api/tasks")!,
                statusCode: status,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!,
            Data(body.utf8)
        )
    }
}

private final class EventCollector: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [TaskEvent] = []

    func append(_ event: TaskEvent) {
        lock.lock()
        storage.append(event)
        lock.unlock()
    }

    var values: [TaskEvent] {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }
}

private final class MockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let handler = Self.handler else { return }
        let (response, data) = handler(request)
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
