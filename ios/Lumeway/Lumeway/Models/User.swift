import Foundation

struct User: Codable, Identifiable {
    let id: Int
    let email: String
    let displayName: String?
    let transitionType: String?
    let usState: String?
    let createdAt: String?
    let tier: String?
    let creditCents: Int?
    let activeTransitions: [String]?
    let communityIcon: String?
    let communityIconBg: String?

    enum CodingKeys: String, CodingKey {
        case id, email
        case displayName = "display_name"
        case transitionType = "transition_type"
        case usState = "us_state"
        case createdAt = "created_at"
        case tier
        case creditCents = "credit_cents"
        case activeTransitions = "active_transitions"
        case communityIcon = "community_icon"
        case communityIconBg = "community_icon_bg"
    }
}

struct AuthMeResponse: Codable {
    let loggedIn: Bool
    let user: User?

    enum CodingKeys: String, CodingKey {
        case loggedIn = "logged_in"
        case user
    }
}

struct SendCodeResponse: Codable {
    let ok: Bool?
    let error: String?
}

struct VerifyCodeResponse: Codable {
    let ok: Bool?
    let token: String?
    let refreshToken: String?
    let user: User?
    let error: String?
    let needsOnboarding: Bool?

    enum CodingKeys: String, CodingKey {
        case ok, token, user, error
        case refreshToken = "refresh_token"
        case needsOnboarding = "needs_onboarding"
    }
}
