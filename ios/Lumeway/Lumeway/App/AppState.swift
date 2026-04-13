import SwiftUI
import SwiftData
import Combine

@MainActor
final class AppState: ObservableObject {
    @Published var isAuthenticated = false
    @Published var isLoading = true
    @Published var user: User?
    @Published var dashboardData: DashboardData?
    @Published var effectiveTier: String = "free"
    @Published var categoryAccess: [String: String] = [:]
    @Published var activeTransitions: [String] = []
    @Published var needsOnboarding = false
    @Published var justLoggedIn = false

    let offlineRepo = OfflineRepository.shared
    private let authService = AuthService()
    private let dashboardService = DashboardService()

    init() {
        Task { await checkAuth() }
        NotificationCenter.default.addObserver(forName: .purchaseCompleted, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in
                await self?.loadDashboard()
            }
        }
    }

    func configureModelContext(_ context: ModelContext) {
        offlineRepo.configure(modelContext: context)
    }

    func checkAuth() async {
        isLoading = true
        defer { isLoading = false }

        guard KeychainHelper.getToken() != nil else {
            isAuthenticated = false
            return
        }

        do {
            let me = try await authService.getMe()
            if me.loggedIn {
                self.user = me.user
                self.isAuthenticated = true
                self.needsOnboarding = me.user?.transitionType == nil
                // Sync community icon from server to local storage
                if let icon = me.user?.communityIcon, !icon.isEmpty {
                    UserDefaults.standard.set(icon, forKey: "selectedProfileEmoji")
                    UserDefaults.standard.set(icon, forKey: "community_icon")
                }
                if let bg = me.user?.communityIconBg, !bg.isEmpty {
                    UserDefaults.standard.set(bg, forKey: "community_icon_bg")
                    UserDefaults.standard.set(bg, forKey: "selectedIconBgColor")
                }
            } else {
                self.isAuthenticated = false
                KeychainHelper.deleteToken()
            }
        } catch {
            self.isAuthenticated = false
            KeychainHelper.deleteToken()
        }
    }

    func login(token: String, refreshToken: String, user: User) {
        KeychainHelper.saveToken(token)
        KeychainHelper.saveRefreshToken(refreshToken)
        self.user = user
        self.isAuthenticated = true
        self.needsOnboarding = user.transitionType == nil
        self.justLoggedIn = true
        // Sync community icon from server to local storage
        if let icon = user.communityIcon, !icon.isEmpty {
            UserDefaults.standard.set(icon, forKey: "selectedProfileEmoji")
            UserDefaults.standard.set(icon, forKey: "community_icon")
        }
        if let bg = user.communityIconBg, !bg.isEmpty {
            UserDefaults.standard.set(bg, forKey: "community_icon_bg")
            UserDefaults.standard.set(bg, forKey: "selectedIconBgColor")
        }
    }

    func logout() {
        KeychainHelper.deleteToken()
        KeychainHelper.deleteRefreshToken()
        self.user = nil
        self.isAuthenticated = false
        self.dashboardData = nil
        self.effectiveTier = "free"
        self.categoryAccess = [:]
        self.activeTransitions = []
    }

    func loadDashboard() async {
        do {
            let data = try await dashboardService.getDashboardData()
            self.dashboardData = data
            self.effectiveTier = data.effectiveTier ?? "free"
            self.categoryAccess = data.categoryAccess ?? [:]
            self.activeTransitions = data.activeTransitions ?? []
        } catch {
            print("Dashboard load error: \(error)")
        }
    }
}
