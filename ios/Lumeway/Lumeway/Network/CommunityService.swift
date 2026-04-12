import Foundation

final class CommunityService {
    private let api = APIClient.shared

    func getPosts(category: String? = nil, transition: String? = nil, page: Int = 1) async throws -> CommunityPostsResponse {
        var path = "/api/community/posts?page=\(page)"
        if let cat = category, !cat.isEmpty { path += "&category=\(cat)" }
        if let trans = transition, !trans.isEmpty { path += "&transition=\(trans)" }
        return try await api.get(path)
    }

    func getPost(id: Int) async throws -> CommunityPostDetailResponse {
        try await api.get("/api/community/posts/\(id)")
    }

    func createPost(title: String, body: String, category: String, displayName: String, icon: String, transitionCategory: String? = nil) async throws -> SimpleOkResponse {
        var params: [String: Any] = [
            "title": title,
            "body": body,
            "category": category,
            "display_name": displayName,
            "icon": icon
        ]
        if let trans = transitionCategory { params["transition_category"] = trans }
        return try await api.post("/api/community/posts", body: params)
    }

    func createReply(postId: Int, body: String, displayName: String, icon: String) async throws -> SimpleOkResponse {
        try await api.post("/api/community/posts/\(postId)/replies", body: [
            "body": body,
            "display_name": displayName,
            "icon": icon
        ])
    }

    func toggleLike(postId: Int? = nil, replyId: Int? = nil) async throws -> CommunityLikeResponse {
        var body: [String: Any] = [:]
        if let pid = postId { body["post_id"] = pid }
        if let rid = replyId { body["reply_id"] = rid }
        return try await api.post("/api/community/like", body: body)
    }

    func deletePost(id: Int) async throws -> SimpleOkResponse {
        try await api.delete("/api/community/posts/\(id)")
    }

    func deleteReply(id: Int) async throws -> SimpleOkResponse {
        try await api.delete("/api/community/replies/\(id)")
    }
}

// MARK: - Response Models

struct CommunityPostsResponse: Codable {
    let posts: [CommunityPost]
    let total: Int
    let page: Int
    let perPage: Int
    let categories: [CommunityCategory]?
    let transitions: [TransitionLabel]?

    enum CodingKeys: String, CodingKey {
        case posts, total, page, categories, transitions
        case perPage = "per_page"
    }
}

struct CommunityPost: Codable, Identifiable {
    let id: Int
    let userId: Int
    let displayName: String?
    let category: String?
    let title: String?
    let body: String?
    let isPinned: Bool?
    let createdAt: String?
    let updatedAt: String?
    let replyCount: Int?
    let transitionCategory: String?
    let likeCount: Int?
    let icon: String?
    let isAuthor: Bool?

    enum CodingKeys: String, CodingKey {
        case id, category, title, body, icon
        case userId = "user_id"
        case displayName = "display_name"
        case isPinned = "is_pinned"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case replyCount = "reply_count"
        case transitionCategory = "transition_category"
        case likeCount = "like_count"
        case isAuthor = "is_author"
    }
}

struct CommunityReply: Codable, Identifiable {
    let id: Int
    let postId: Int
    let userId: Int
    let displayName: String?
    let body: String?
    let createdAt: String?
    let likeCount: Int?
    let icon: String?
    let isAuthor: Bool?

    enum CodingKeys: String, CodingKey {
        case id, body, icon
        case postId = "post_id"
        case userId = "user_id"
        case displayName = "display_name"
        case createdAt = "created_at"
        case likeCount = "like_count"
        case isAuthor = "is_author"
    }
}

struct CommunityPostDetailResponse: Codable {
    let post: CommunityPost
    let replies: [CommunityReply]
    let userLikes: [String: Bool]?

    enum CodingKeys: String, CodingKey {
        case post, replies
        case userLikes = "user_likes"
    }
}

struct CommunityCategory: Codable {
    let id: String
    let label: String
    let icon: String?
}

struct TransitionLabel: Codable {
    let id: String
    let label: String
}

struct CommunityLikeResponse: Codable {
    let ok: Bool?
    let liked: Bool?
    let likeCount: Int?

    enum CodingKeys: String, CodingKey {
        case ok, liked
        case likeCount = "like_count"
    }
}
