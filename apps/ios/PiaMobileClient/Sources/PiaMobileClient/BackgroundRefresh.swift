import Foundation

#if os(iOS)
@preconcurrency import BackgroundTasks

public final class PiaBackgroundRefreshCoordinator: NSObject, Sendable {
    public let identifier: String
    private let handler: @Sendable () async -> Bool

    public init(
        identifier: String = "com.pia.investment.refresh",
        handler: @escaping @Sendable () async -> Bool
    ) {
        self.identifier = identifier
        self.handler = handler
    }

    public func register() {
        // The legacy callback hands completion to a single task on the main queue.
        BGTaskScheduler.shared.register(forTaskWithIdentifier: identifier, using: .main) { [handler] task in
            guard let refreshTask = task as? BGAppRefreshTask else {
                task.setTaskCompleted(success: false)
                return
            }
            Task { @MainActor in
                let success = await handler()
                refreshTask.setTaskCompleted(success: success)
            }
        }
    }

    public func schedule(after interval: TimeInterval = 15 * 60) throws {
        let request = BGAppRefreshTaskRequest(identifier: identifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: max(60, interval))
        try BGTaskScheduler.shared.submit(request)
    }
}
#else

public struct PiaBackgroundRefreshCoordinator: Sendable {
    public init(identifier: String = "com.pia.investment.refresh", handler: @escaping @Sendable () async -> Bool = { false }) {}
    public func register() {}
}
#endif
