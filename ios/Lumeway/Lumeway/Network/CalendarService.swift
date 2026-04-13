import Foundation

final class CalendarService {
    private let api = APIClient.shared

    func getDeadlines() async throws -> DeadlinesResponse {
        try await api.get("/api/deadlines")
    }

    func addDeadline(title: String, dueDate: String, category: String? = nil, notes: String? = nil) async throws -> SimpleOkResponse {
        var body: [String: Any] = ["title": title, "deadline_date": dueDate]
        if let cat = category { body["transition_type"] = cat }
        if let n = notes { body["note"] = n }
        return try await api.post("/api/deadlines", body: body)
    }

    func updateDeadline(id: Int, title: String? = nil, dueDate: String? = nil, notes: String? = nil) async throws -> SimpleOkResponse {
        var body: [String: Any] = [:]
        if let t = title { body["title"] = t }
        if let d = dueDate { body["deadline_date"] = d }
        if let n = notes { body["note"] = n }
        return try await api.put("/api/deadlines/\(id)", body: body)
    }

    func toggleDeadline(id: Int) async throws -> SimpleOkResponse {
        try await api.post("/api/deadlines/\(id)/toggle")
    }

    func deleteDeadline(id: Int) async throws -> SimpleOkResponse {
        try await api.delete("/api/deadlines/\(id)")
    }
}

struct DeadlinesResponse: Codable {
    let deadlines: [DeadlineItem]
}

struct DeadlineItem: Codable, Identifiable {
    let id: Int
    let title: String?
    let dueDate: String?
    let completed: Bool?
    let transitionType: String?
    let note: String?
    let source: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, note, source
        case dueDate = "deadline_date"
        case completed = "is_completed"
        case transitionType = "transition_type"
        case createdAt = "created_at"
    }
}
