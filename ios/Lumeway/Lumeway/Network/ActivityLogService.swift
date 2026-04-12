import Foundation

final class ActivityLogService {
    private let api = APIClient.shared

    func getEntries() async throws -> ActivityLogResponse {
        try await api.get("/api/activity-log")
    }

    func addEntry(actionType: String, description: String, date: String, contactName: String? = nil, organization: String? = nil) async throws -> SimpleOkResponse {
        var body: [String: Any] = [
            "action_type": actionType,
            "description": description,
            "date": date
        ]
        if let c = contactName { body["contact_name"] = c }
        if let o = organization { body["organization"] = o }
        return try await api.post("/api/activity-log", body: body)
    }

    func deleteEntry(id: Int) async throws -> SimpleOkResponse {
        try await api.delete("/api/activity-log/\(id)")
    }
}

struct ActivityLogResponse: Codable {
    let entries: [ActivityEntry]
}

struct ActivityEntry: Codable, Identifiable {
    let id: Int
    let actionType: String?
    let contactName: String?
    let organization: String?
    let description: String?
    let date: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, description, date, organization
        case actionType = "action_type"
        case contactName = "contact_name"
        case createdAt = "created_at"
    }
}
