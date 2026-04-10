import Foundation
import SwiftData

@Model
final class CachedChecklistItem {
    @Attribute(.unique) var itemId: Int
    var title: String
    var phase: String?
    var risk: String?
    var completed: Bool
    var sortOrder: Int
    var lastSynced: Date

    init(itemId: Int, title: String, phase: String? = nil, risk: String? = nil, completed: Bool = false, sortOrder: Int = 0) {
        self.itemId = itemId
        self.title = title
        self.phase = phase
        self.risk = risk
        self.completed = completed
        self.sortOrder = sortOrder
        self.lastSynced = Date()
    }
}

@Model
final class CachedDeadline {
    @Attribute(.unique) var deadlineId: Int
    var title: String
    var dueDate: String?
    var daysRemaining: Int?
    var completed: Bool
    var lastSynced: Date

    init(deadlineId: Int, title: String, dueDate: String? = nil, daysRemaining: Int? = nil, completed: Bool = false) {
        self.deadlineId = deadlineId
        self.title = title
        self.dueDate = dueDate
        self.daysRemaining = daysRemaining
        self.completed = completed
        self.lastSynced = Date()
    }
}

@Model
final class CachedNote {
    @Attribute(.unique) var noteId: Int
    var content: String
    var category: String?
    var createdAt: String?
    var lastSynced: Date

    init(noteId: Int, content: String, category: String? = nil, createdAt: String? = nil) {
        self.noteId = noteId
        self.content = content
        self.category = category
        self.createdAt = createdAt
        self.lastSynced = Date()
    }
}
