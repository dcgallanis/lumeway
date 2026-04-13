import Foundation

final class DashboardService {
    private let api = APIClient.shared

    func getDashboardData() async throws -> DashboardData {
        try await api.get("/api/dashboard/data")
    }

    func updateSettings(displayName: String?, usState: String?, transitionType: String? = nil, communityIcon: String? = nil, communityIconBg: String? = nil) async throws {
        var body: [String: Any] = [:]
        if let name = displayName { body["display_name"] = name }
        if let state = usState { body["us_state"] = state }
        if let transition = transitionType { body["transition_type"] = transition }
        if let icon = communityIcon { body["community_icon"] = icon }
        if let bg = communityIconBg { body["community_icon_bg"] = bg }
        try await api.post("/api/account/settings", body: body)
    }
}
