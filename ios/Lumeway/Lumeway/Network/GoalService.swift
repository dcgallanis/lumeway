import Foundation

final class GoalService {
    private let api = APIClient.shared

    func getGoals() async throws -> GoalsResponse {
        try await api.get("/api/goals")
    }

    func createGoal(title: String, timeframe: String, targetDate: String?) async throws -> SimpleOkResponse {
        var body: [String: Any] = [
            "title": title,
            "timeframe": timeframe
        ]
        if let targetDate {
            body["target_date"] = targetDate
        }
        return try await api.post("/api/goals", body: body)
    }

    func toggleGoal(id: Int) async throws -> GoalToggleResponse {
        try await api.post("/api/goals/\(id)/toggle")
    }

    func deleteGoal(id: Int) async throws -> SimpleOkResponse {
        try await api.delete("/api/goals/\(id)")
    }

    func updateGoal(id: Int, title: String, timeframe: String, targetDate: String?) async throws -> SimpleOkResponse {
        var body: [String: Any] = [
            "title": title,
            "timeframe": timeframe
        ]
        if let targetDate {
            body["target_date"] = targetDate
        }
        return try await api.put("/api/goals/\(id)", body: body)
    }
}

// MARK: - Response Models

struct GoalsResponse: Codable {
    let goals: [GoalItem]
}

struct GoalItem: Codable, Identifiable {
    let id: Int
    let title: String
    let timeframe: String
    let targetDate: String?
    let isCompleted: Bool
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case timeframe
        case targetDate = "target_date"
        case isCompleted = "is_completed"
        case createdAt = "created_at"
    }
}

struct GoalToggleResponse: Codable {
    let ok: Bool?
    let isCompleted: Bool?

    enum CodingKeys: String, CodingKey {
        case ok
        case isCompleted = "is_completed"
    }
}
