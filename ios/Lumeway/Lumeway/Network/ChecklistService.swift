import Foundation

final class ChecklistService {
    private let api = APIClient.shared

    func getChecklist() async throws -> ChecklistResponse {
        try await api.get("/api/checklist")
    }

    func toggleItem(id: Int) async throws -> ToggleResponse {
        try await api.post("/api/checklist/\(id)/toggle")
    }

    func skipItem(id: Int) async throws -> SimpleOkResponse {
        try await api.post("/api/checklist/\(id)/skip")
    }

    func initChecklist(transitionType: String) async throws -> SimpleOkResponse {
        try await api.post("/api/checklist/init", body: ["transition_type": transitionType])
    }
}

struct ChecklistResponse: Codable {
    let items: [FullChecklistItem]
}

struct FullChecklistItem: Codable, Identifiable {
    let id: Int
    let transitionType: String?
    let phase: String?
    let itemText: String?
    let isCompleted: Bool
    let completedAt: String?
    let sortOrder: Int?

    var title: String { itemText ?? "" }

    enum CodingKeys: String, CodingKey {
        case id
        case transitionType = "transition_type"
        case phase
        case itemText = "item_text"
        case isCompleted = "is_completed"
        case completedAt = "completed_at"
        case sortOrder = "sort_order"
    }
}

struct ToggleResponse: Codable {
    let ok: Bool?
    let isCompleted: Bool?

    enum CodingKeys: String, CodingKey {
        case ok
        case isCompleted = "is_completed"
    }
}

struct SimpleOkResponse: Codable {
    let ok: Bool?
    let message: String?
    let error: String?
}
