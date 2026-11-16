import Foundation
import Security

public struct KeychainTokenStore: Sendable {
    private let service: String
    private let account: String

    public init(
        service: String = "com.pia.investment.auth",
        account: String = "bearer-token"
    ) {
        self.service = service
        self.account = account
    }

    public func save(_ token: String) throws {
        let data = Data(token.utf8)
        let query = baseQuery()
        let attributes: [CFString: Any] = [kSecValueData: data]
        let updateStatus = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if updateStatus == errSecSuccess {
            return
        }
        guard updateStatus == errSecItemNotFound else {
            throw KeychainTokenStoreError.status(updateStatus)
        }
        var insert = query
        insert[kSecValueData as String] = data
        let insertStatus = SecItemAdd(insert as CFDictionary, nil)
        guard insertStatus == errSecSuccess else {
            throw KeychainTokenStoreError.status(insertStatus)
        }
    }

    public func load() throws -> String? {
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess, let data = result as? Data else {
            throw KeychainTokenStoreError.status(status)
        }
        return String(data: data, encoding: .utf8)
    }

    public func delete() throws {
        let status = SecItemDelete(baseQuery() as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainTokenStoreError.status(status)
        }
    }

    private func baseQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }
}

public enum KeychainTokenStoreError: Error, Equatable, Sendable {
    case status(OSStatus)
}
