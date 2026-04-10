import Foundation

final class NotesService {
    private let api = APIClient.shared

    func getNotes() async throws -> NotesResponse {
        try await api.get("/api/notes")
    }

    func createNote(content: String) async throws -> NoteCreateResponse {
        try await api.post("/api/notes", body: ["content": content])
    }

    func updateNote(id: Int, content: String) async throws -> SimpleOkResponse {
        try await api.put("/api/notes/\(id)", body: ["content": content])
    }

    func deleteNote(id: Int) async throws -> SimpleOkResponse {
        try await api.delete("/api/notes/\(id)")
    }
}

struct NotesResponse: Codable {
    let notes: [NoteItem]
}

struct NoteItem: Codable, Identifiable {
    let id: Int
    let content: String
    let createdAt: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, content
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct NoteCreateResponse: Codable {
    let ok: Bool?
    let id: Int?
    let error: String?
}
