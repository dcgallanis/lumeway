import Foundation

final class CalendarService {
    private let api = APIClient.shared

    func getDeadlines() async throws -> DeadlinesResponse {
        try await api.get("/api/deadlines")
    }

    func addDeadline(title: String, dueDate: String, category: String? = nil, notes: String? = nil) async throws -> SimpleOkResponse {
        var body: [String: Any] = ["title": title, "due_date": dueDate]
        if let cat = category { body["category"] = cat }
        if let n = notes { body["notes"] = n }
        return try await api.post("/api/deadlines", body: body)
    }

    func updateDeadline(id: Int, title: String? = nil, dueDate: String? = nil, notes: String? = nil) async throws -> SimpleOkResponse {
        var body: [String: Any] = [:]
        if let t = title { body["title"] = t }
        if let d = dueDate { body["due_date"] = d }
        if let n = notes { body["notes"] = n }
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
    let category: String?
    let notes: String?
    let daysRemaining: Int?

    enum CodingKeys: String, CodingKey {
        case id, title, completed, category, notes
        case dueDate = "due_date"
        case daysRemaining = "days_remaining"
    }

    init(id: Int, title: String?, dueDate: String?, completed: Bool?, category: String? = nil, notes: String? = nil, daysRemaining: Int?) {
        self.id = id
        self.title = title
        self.dueDate = dueDate
        self.completed = completed
        self.category = category
        self.notes = notes
        self.daysRemaining = daysRemaining
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        title = try c.decodeIfPresent(String.self, forKey: .title)
        dueDate = try c.decodeIfPresent(String.self, forKey: .dueDate)
        completed = try c.decodeIfPresent(Bool.self, forKey: .completed)
        category = try c.decodeIfPresent(String.self, forKey: .category)
        notes = try c.decodeIfPresent(String.self, forKey: .notes)
        daysRemaining = try c.decodeIfPresent(Int.self, forKey: .daysRemaining)
    }
}
