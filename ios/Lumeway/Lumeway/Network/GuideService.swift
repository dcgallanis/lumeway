import Foundation

final class GuideService {
    private let api = APIClient.shared

    func listGuides() async throws -> GuideListResponse {
        try await api.get("/api/guides")
    }

    func getGuide(transition: String) async throws -> GuideDetailResponse {
        try await api.get("/api/guides/\(transition)")
    }
}

// MARK: - Response Models

struct GuideListResponse: Codable {
    let transitions: [GuideTransition]
    let effectiveTier: String?

    enum CodingKeys: String, CodingKey {
        case transitions
        case effectiveTier = "effective_tier"
    }
}

struct GuideTransition: Codable, Identifiable {
    let key: String
    let label: String
    let hasAccess: Bool

    var id: String { key }

    enum CodingKeys: String, CodingKey {
        case key, label
        case hasAccess = "has_access"
    }
}

struct GuideDetailResponse: Codable {
    let transition: String
    let hasFullAccess: Bool
    let effectiveTier: String?
    let guide: GuideContent

    enum CodingKeys: String, CodingKey {
        case transition, guide
        case hasFullAccess = "has_full_access"
        case effectiveTier = "effective_tier"
    }
}

struct GuideContent: Codable {
    let label: String?
    let categories: [GuideCategory]
}

struct GuideCategory: Codable, Identifiable {
    let name: String
    let risk: String?
    let tasks: [GuideTask]

    var id: String { name }
}

struct GuideTask: Codable, Identifiable {
    let id: String
    let title: String
    let risk: String?
    let what: String?
    let why: String?
    let steps: [String]?
    let terms: [GuideTerm]?
    let contacts: String?
    let mistakes: [String]?
    let crossRef: [String]?
    let script: GuideScript?

    enum CodingKeys: String, CodingKey {
        case id, title, risk, what, why, steps, terms, contacts, mistakes, script
        case crossRef = "crossRef"
    }
}

struct GuideTerm: Codable, Identifiable {
    let term: String
    let def: String

    var id: String { term }
}

struct GuideScript: Codable {
    let intro: String?
    let lines: [String]?
    let note: String?
}
