import Foundation

struct DashboardData: Codable {
    let user: User?
    let sessions: [ChatSessionSummary]?
    let checklist: ChecklistStats?
    let purchases: [Purchase]?
    let goals: [Goal]?
    let deadlines: [Deadline]?
    let documentsNeeded: [DocumentNeeded]?
    let notes: [Note]?
    let effectiveTier: String?
    let categoryAccess: [String: String]?
    let creditCents: Int?
    let activeTransitions: [String]?

    enum CodingKeys: String, CodingKey {
        case user, sessions, checklist, purchases, goals, deadlines, notes
        case documentsNeeded = "documents_needed"
        case effectiveTier = "effective_tier"
        case categoryAccess = "category_access"
        case creditCents = "credit_cents"
        case activeTransitions = "active_transitions"
    }
}

struct ChatSessionSummary: Codable, Identifiable {
    let id: String
    let startedAt: String?
    let transitionCategory: String?
    let messageCount: Int?
    let preview: String?

    enum CodingKeys: String, CodingKey {
        case id, preview
        case startedAt = "started_at"
        case transitionCategory = "transition_category"
        case messageCount = "message_count"
    }
}

struct ChecklistStats: Codable {
    let total: Int?
    let completed: Int?
    let items: [ChecklistItem]?
}

struct ChecklistItem: Codable, Identifiable {
    let id: Int
    let taskText: String?
    let phase: String?
    let completed: Bool?
    let skipped: Bool?
    let sortOrder: Int?
    let risk: String?

    var title: String? { taskText }

    enum CodingKeys: String, CodingKey {
        case id
        case taskText = "task_text"
        case phase, completed, skipped, risk
        case sortOrder = "sort_order"
    }
}

struct Deadline: Codable, Identifiable {
    let id: Int
    let title: String?
    let dueDate: String?
    let completed: Bool?
    let transitionType: String?
    let note: String?
    let source: String?

    enum CodingKeys: String, CodingKey {
        case id, title, note, source
        case dueDate = "deadline_date"
        case completed = "is_completed"
        case transitionType = "transition_type"
    }
}

struct Goal: Codable, Identifiable {
    let id: Int
    let title: String?
    let timeframe: String?
    let targetDate: String?
    let isCompleted: Bool?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, timeframe
        case targetDate = "target_date"
        case isCompleted = "is_completed"
        case createdAt = "created_at"
    }
}

struct Note: Codable, Identifiable {
    let id: Int
    let content: String
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, content
        case createdAt = "created_at"
    }
}

struct DocumentNeeded: Codable, Identifiable {
    let id: Int
    let name: String?
    let gathered: Bool?
    let note: String?

    var obtained: Bool? { gathered }

    enum CodingKeys: String, CodingKey {
        case id, name, gathered, note
    }
}

struct Purchase: Codable, Identifiable {
    let id: Int?
    let productId: String?
    let amount: Int?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case productId = "product_id"
        case amount
        case createdAt = "created_at"
    }
}
