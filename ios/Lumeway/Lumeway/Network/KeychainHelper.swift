import Foundation
import Security

enum KeychainHelper {
    private static let service = "co.lumeway.app"
    private static let tokenKey = "auth_token"
    private static let refreshTokenKey = "refresh_token"

    // MARK: - Auth Token

    static func saveToken(_ token: String) {
        save(key: tokenKey, value: token)
    }

    static func getToken() -> String? {
        get(key: tokenKey)
    }

    static func deleteToken() {
        delete(key: tokenKey)
    }

    // MARK: - Refresh Token

    static func saveRefreshToken(_ token: String) {
        save(key: refreshTokenKey, value: token)
    }

    static func getRefreshToken() -> String? {
        get(key: refreshTokenKey)
    }

    static func deleteRefreshToken() {
        delete(key: refreshTokenKey)
    }

    // MARK: - Private

    private static func save(key: String, value: String) {
        guard let data = value.data(using: .utf8) else { return }

        // Delete existing
        delete(key: key)

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock
        ]

        SecItemAdd(query as CFDictionary, nil)
    }

    private static func get(key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        guard status == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static func delete(key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]
        SecItemDelete(query as CFDictionary)
    }
}
