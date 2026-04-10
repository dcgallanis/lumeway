import Foundation
import SwiftData

@Model
final class CachedChecklistItem {
    @Attribute(.unique) var itemId: Int
    var title: String
    var phase: String?
    var completed: Bool
    var sortOrder: Int
    var transitionType: String?
    var lastSynced: Date

    init(itemId: Int, title: String, phase: String? = nil, completed: Bool = false, sortOrder: Int = 0, transitionType: String? = nil) {
        self.itemId = itemId
        self.title = title
        self.phase = phase
        self.completed = completed
        self.sortOrder = sortOrder
        self.transitionType = transitionType
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
    var transitionType: String?
    var note: String?
    var lastSynced: Date

    init(deadlineId: Int, title: String, dueDate: String? = nil, daysRemaining: Int? = nil, completed: Bool = false, transitionType: String? = nil, note: String? = nil) {
        self.deadlineId = deadlineId
        self.title = title
        self.dueDate = dueDate
        self.daysRemaining = daysRemaining
        self.completed = completed
        self.transitionType = transitionType
        self.note = note
        self.lastSynced = Date()
    }
}

@Model
final class CachedNote {
    @Attribute(.unique) var noteId: Int
    var content: String
    var createdAt: String?
    var updatedAt: String?
    var lastSynced: Date

    init(noteId: Int, content: String, createdAt: String? = nil, updatedAt: String? = nil) {
        self.noteId = noteId
        self.content = content
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.lastSynced = Date()
    }
}

@Model
final class CachedGuide {
    @Attribute(.unique) var transition: String
    var jsonData: Data
    var lastSynced: Date

    init(transition: String, jsonData: Data) {
        self.transition = transition
        self.jsonData = jsonData
        self.lastSynced = Date()
    }
}

@Model
final class PendingAction {
    var actionType: String   // "toggle", "skip", "note_create", "note_update", "note_delete"
    var itemId: Int?
    var payload: String?     // JSON string for extra data
    var createdAt: Date
    var retryCount: Int

    init(actionType: String, itemId: Int? = nil, payload: String? = nil) {
        self.actionType = actionType
        self.itemId = itemId
        self.payload = payload
        self.createdAt = Date()
        self.retryCount = 0
    }
}
