import Foundation

final class AuthService {
    private let api = APIClient.shared

    func sendCode(email: String) async throws -> SendCodeResponse {
        try await api.post("/api/auth/send-code", body: ["email": email])
    }

    func verifyCode(email: String, code: String) async throws -> VerifyCodeResponse {
        try await api.post("/api/auth/verify-code", body: ["email": email, "code": code])
    }

    func getMe() async throws -> AuthMeResponse {
        try await api.get("/api/auth/me")
    }

    func logout() async throws {
        try await api.post("/api/auth/logout")
    }
}
