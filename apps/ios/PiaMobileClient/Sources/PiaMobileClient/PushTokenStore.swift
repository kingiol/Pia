import Foundation

public final class PiaPushTokenStore: @unchecked Sendable {
    private let defaults: UserDefaults
    private let key: String

    public init(
        defaults: UserDefaults = .standard,
        key: String = "pia.apns_device_token"
    ) {
        self.defaults = defaults
        self.key = key
    }

    public func load() -> String? {
        defaults.string(forKey: key)
    }

    public func save(_ token: String) {
        defaults.set(token, forKey: key)
    }

    public func clear() {
        defaults.removeObject(forKey: key)
    }
}
