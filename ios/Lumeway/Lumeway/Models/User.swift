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
        case id, email, tier
        case displayName = "display_name"
        case transitionType = "transition_type"
        case usState = "us_state"
        case createdAt = "created_at"
        case creditCents = "credit_cents"
        case activeTransitions = "active_transitions"
        case communityIcon = "community_icon"
        case communityIconBg = "community_icon_bg"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        email = try container.decode(String.self, forKey: .email)
        displayName = try container.decodeIfPresent(String.self, forKey: .displayName)
        transitionType = try container.decodeIfPresent(String.self, forKey: .transitionType)
        usState = try container.decodeIfPresent(String.self, forKey: .usState)
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
        tier = try container.decodeIfPresent(String.self, forKey: .tier)
        creditCents = try container.decodeIfPresent(Int.self, forKey: .creditCents)
        communityIcon = try container.decodeIfPresent(String.self, forKey: .communityIcon)
        communityIconBg = try container.decodeIfPresent(String.self, forKey: .communityIconBg)

        // active_transitions can be [String] or [{"cat": "...", "level": "..."}] from the backend
        if let strings = try? container.decodeIfPresent([String].self, forKey: .activeTransitions) {
            activeTransitions = strings
        } else if let dicts = try? container.decodeIfPresent([[String: String]].self, forKey: .activeTransitions) {
            activeTransitions = dicts.compactMap { $0["cat"] }
        } else {
            activeTransitions = nil
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(email, forKey: .email)
        try container.encodeIfPresent(displayName, forKey: .displayName)
        try container.encodeIfPresent(transitionType, forKey: .transitionType)
        try container.encodeIfPresent(usState, forKey: .usState)
        try container.encodeIfPresent(createdAt, forKey: .createdAt)
        try container.encodeIfPresent(tier, forKey: .tier)
        try container.encodeIfPresent(creditCents, forKey: .creditCents)
        try container.encodeIfPresent(activeTransitions, forKey: .activeTransitions)
        try container.encodeIfPresent(communityIcon, forKey: .communityIcon)
        try container.encodeIfPresent(communityIconBg, forKey: .communityIconBg)
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
    let demo: Bool?
    let demoCode: String?

    enum CodingKeys: String, CodingKey {
        case ok, error, demo
        case demoCode = "demo_code"
    }
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
