import SwiftUI

struct ContentView: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.modelContext) private var modelContext

    var body: some View {
        Group {
            if appState.isLoading {
                LaunchView()
            } else if !appState.isAuthenticated {
                WelcomeView()
            } else if appState.needsOnboarding {
                OnboardingView()
            } else if appState.justLoggedIn {
                WelcomeBannerView()
            } else {
                MainTabView()
            }
        }
        .animation(.easeInOut(duration: 0.3), value: appState.isAuthenticated)
        .animation(.easeInOut(duration: 0.3), value: appState.isLoading)
        .animation(.easeInOut(duration: 0.3), value: appState.justLoggedIn)
        .onAppear {
            appState.configureModelContext(modelContext)
        }
    }
}

// MARK: - Launch Screen

struct LaunchView: View {
    @State private var pulse = false

    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()
            VStack(spacing: 16) {
                Image(systemName: "sun.max.fill")
                    .font(.system(size: 48, weight: .light))
                    .foregroundStyle(
                        LinearGradient(
                            colors: [.lumeAccent, .lumeGold],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .scaleEffect(pulse ? 1.08 : 1.0)
                    .animation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true), value: pulse)

                Text("LUMEWAY")
                    .font(.lumeLogoText)
                    .tracking(3)
                    .foregroundColor(.lumeNavy)
            }
            .onAppear { pulse = true }
        }
    }
}

// MARK: - Welcome Banner (after login)

struct WelcomeBannerView: View {
    @EnvironmentObject var appState: AppState
    @State private var showSun = false
    @State private var showText = false
    @State private var showStats = false
    @State private var checklistItems: [FullChecklistItem] = []
    @State private var dismissing = false

    private let checklistService = ChecklistService()

    private let greetings = [
        "Welcome back",
        "Hey, you're here",
        "Look who's back",
        "Good to see you",
    ]

    private var greeting: String {
        greetings.randomElement() ?? greetings[0]
    }

    private var completedCount: Int {
        checklistItems.filter(\.isCompleted).count
    }

    // Calculate streak: consecutive days with at least one completion
    private var streakDays: Int {
        let calendar = Calendar.current
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"

        let completionDates: Set<String> = Set(checklistItems.compactMap { item in
            guard item.isCompleted, let dateStr = item.completedAt else { return nil }
            if let date = formatter.date(from: String(dateStr.prefix(19))) {
                let df = DateFormatter()
                df.dateFormat = "yyyy-MM-dd"
                return df.string(from: date)
            }
            return nil
        })

        guard !completionDates.isEmpty else { return 0 }

        var streak = 0
        var checkDate = Date()
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd"

        for _ in 0..<365 {
            if completionDates.contains(df.string(from: checkDate)) {
                streak += 1
                checkDate = calendar.date(byAdding: .day, value: -1, to: checkDate) ?? checkDate
            } else if streak == 0 {
                // Today might not have activity yet, check yesterday
                checkDate = calendar.date(byAdding: .day, value: -1, to: checkDate) ?? checkDate
                if completionDates.contains(df.string(from: checkDate)) {
                    streak += 1
                    checkDate = calendar.date(byAdding: .day, value: -1, to: checkDate) ?? checkDate
                } else {
                    break
                }
            } else {
                break
            }
        }
        return streak
    }

    var body: some View {
        ZStack {
            Color.lumeNavy.ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                // Sun icon
                Image(systemName: "sun.max.fill")
                    .font(.system(size: 56, weight: .light))
                    .foregroundStyle(
                        LinearGradient(
                            colors: [.lumeAccent, .lumeGold],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .scaleEffect(showSun ? 1.0 : 0.3)
                    .opacity(showSun ? 1 : 0)
                    .rotationEffect(.degrees(showSun ? 0 : -90))

                Spacer().frame(height: 20)

                // Greeting
                Text(greeting)
                    .font(.lumeHeadingLarge)
                    .foregroundColor(.white)
                    .opacity(showText ? 1 : 0)
                    .offset(y: showText ? 0 : 20)

                Text("Let's continue your journey")
                    .font(.lumeBodyLight)
                    .foregroundColor(.white.opacity(0.5))
                    .opacity(showText ? 1 : 0)
                    .padding(.top, 6)

                Spacer().frame(height: 36)

                // Stats cards
                VStack(spacing: 12) {
                    WelcomeStatRow(
                        icon: "checkmark.circle.fill",
                        iconColor: .lumeGreen,
                        text: "\(completedCount) task\(completedCount == 1 ? "" : "s") completed"
                    )

                    if streakDays > 0 {
                        WelcomeStatRow(
                            icon: "flame.fill",
                            iconColor: .lumeGold,
                            text: "\(streakDays) day streak"
                        )
                    }

                    if let noteCount = appState.dashboardData?.notes?.count, noteCount > 0 {
                        WelcomeStatRow(
                            icon: "doc.text.fill",
                            iconColor: Color(hex: "5E8C9A"),
                            text: "\(noteCount) note\(noteCount == 1 ? "" : "s") saved"
                        )
                    }
                }
                .padding(.horizontal, 32)
                .opacity(showStats ? 1 : 0)
                .offset(y: showStats ? 0 : 16)

                Spacer()

                // Continue button
                Button {
                    withAnimation(.easeIn(duration: 0.3)) {
                        dismissing = true
                    }
                    Task {
                        try? await Task.sleep(nanoseconds: 300_000_000)
                        appState.justLoggedIn = false
                    }
                } label: {
                    Text("Continue")
                        .font(.lumeBodySemibold)
                        .foregroundColor(.lumeNavy)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(Color.lumeBlush)
                        .cornerRadius(28)
                }
                .padding(.horizontal, 32)
                .padding(.bottom, 48)
                .opacity(showStats ? 1 : 0)
            }
            .opacity(dismissing ? 0 : 1)
        }
        .task {
            // Load stats
            do {
                let response = try await checklistService.getChecklist()
                checklistItems = response.items
            } catch {}

            // Animate in
            withAnimation(.spring(response: 0.6, dampingFraction: 0.7)) {
                showSun = true
            }
            withAnimation(.easeOut(duration: 0.5).delay(0.3)) {
                showText = true
            }
            withAnimation(.easeOut(duration: 0.5).delay(0.7)) {
                showStats = true
            }
        }
    }
}

struct WelcomeStatRow: View {
    let icon: String
    let iconColor: Color
    let text: String

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: icon)
                .font(.system(size: 18))
                .foregroundColor(iconColor)
                .frame(width: 24)

            Text(text)
                .font(.lumeBodyMedium)
                .foregroundColor(.white.opacity(0.85))

            Spacer()
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
        .background(Color.white.opacity(0.08))
        .cornerRadius(14)
    }
}

// MARK: - Main Tab View

struct MainTabView: View {
    @EnvironmentObject var appState: AppState
    @State private var selectedTab = 0
    @State private var hubNavigationId = UUID()

    init() {
        // Clean tab bar appearance — removes gray/orange bars on scroll
        let tabAppearance = UITabBarAppearance()
        tabAppearance.configureWithOpaqueBackground()
        tabAppearance.backgroundColor = UIColor(Color.lumeCream)
        tabAppearance.shadowColor = .clear
        UITabBar.appearance().standardAppearance = tabAppearance
        UITabBar.appearance().scrollEdgeAppearance = tabAppearance

        // Clean navigation bar — removes gray bar on scroll
        let navAppearance = UINavigationBarAppearance()
        navAppearance.configureWithTransparentBackground()
        navAppearance.shadowColor = .clear
        UINavigationBar.appearance().standardAppearance = navAppearance
        UINavigationBar.appearance().scrollEdgeAppearance = navAppearance
        UINavigationBar.appearance().compactAppearance = navAppearance
    }

    var body: some View {
        VStack(spacing: 0) {
            // Offline banner
            if !appState.offlineRepo.isOnline {
                HStack(spacing: 6) {
                    Image(systemName: "wifi.slash")
                        .font(.system(size: 12))
                    Text("You're offline. Changes will sync when you reconnect.")
                        .font(.lumeSmall)
                }
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 8)
                .background(Color.lumeMuted)
            }

            TabView(selection: $selectedTab) {
                DashboardView()
                    .tabItem {
                        Image(systemName: selectedTab == 0 ? "house.fill" : "house")
                        Text("Home")
                    }
                    .tag(0)

                ChecklistView()
                    .tabItem {
                        Image(systemName: selectedTab == 1 ? "checklist.checked" : "checklist")
                        Text("Checklist")
                    }
                    .tag(1)

                CommunityView()
                    .tabItem {
                        Image(systemName: selectedTab == 2 ? "bubble.left.and.bubble.right.fill" : "bubble.left.and.bubble.right")
                        Text("Community")
                    }
                    .tag(2)

                NavigatorChatView()
                    .tabItem {
                        Image(systemName: selectedTab == 3 ? "message.fill" : "message")
                        Text("Chat")
                    }
                    .tag(3)

                HubView()
                    .id(hubNavigationId)
                    .tabItem {
                        Image(systemName: selectedTab == 4 ? "square.grid.2x2.fill" : "square.grid.2x2")
                        Text("Hub")
                    }
                    .tag(4)
            }
            .tint(.lumeAccent)
            .onChange(of: selectedTab) { oldTab, newTab in
                // Reset Hub to root when navigating to it from another tab
                if newTab == 4 && oldTab != 4 {
                    hubNavigationId = UUID()
                }
            }
        }
        .task {
            await appState.loadDashboard()
            let pushManager = PushNotificationManager.shared
            await pushManager.requestPermission()
            if let deadlines = appState.dashboardData?.deadlines {
                await pushManager.scheduleDeadlineReminders(deadlines: deadlines)
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .navigateToChecklist)) { _ in
            selectedTab = 1
        }
        .onReceive(NotificationCenter.default.publisher(for: .navigateToDashboard)) { _ in
            selectedTab = 0
        }
        .onReceive(NotificationCenter.default.publisher(for: .switchToTab)) { notification in
            if let tab = notification.userInfo?["tab"] as? Int {
                selectedTab = tab
            }
        }
    }
}

// MARK: - Hub View (Calendar, Activity Log, Notes, Guides, Files, Profile)

struct HubView: View {
    @EnvironmentObject var appState: AppState

    private var isFree: Bool {
        appState.effectiveTier == "free"
    }

    var body: some View {
        NavigationStack {
            ZStack {
                LinearGradient(
                    colors: [Color(hex: "FAF7F2"), Color(hex: "F5F0EA")],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        // User greeting
                        HStack {
                            Text("Your Hub")
                                .font(.lumeHeadingLarge)
                                .foregroundColor(.lumeNavy)
                            Spacer()
                        }
                        .padding(.horizontal, 24)
                        .padding(.top, 20)

                        // Tools grid
                        VStack(spacing: 14) {
                            HStack(spacing: 14) {
                                NavigationLink {
                                    CalendarView()
                                } label: {
                                    HubTile(
                                        icon: "calendar",
                                        title: "Calendar",
                                        subtitle: "Deadlines & dates",
                                        color: .lumeAccent
                                    )
                                }

                                NavigationLink {
                                    ActivityLogView()
                                } label: {
                                    HubTile(
                                        icon: "note.text",
                                        title: "Activity Log",
                                        subtitle: "Track your actions",
                                        color: .lumeGreen
                                    )
                                }
                            }

                            HStack(spacing: 14) {
                                NavigationLink {
                                    NotesView()
                                } label: {
                                    HubTile(
                                        icon: "pencil.line",
                                        title: "Notes",
                                        subtitle: "Your thoughts",
                                        color: Color(hex: "5E8C9A")
                                    )
                                }

                                NavigationLink {
                                    GuidesView()
                                } label: {
                                    HubTile(
                                        icon: "book.fill",
                                        title: "Guides",
                                        subtitle: isFree ? "Upgrade to unlock" : "Step-by-step help",
                                        color: .lumeGold,
                                        isLocked: isFree
                                    )
                                }
                            }

                            HStack(spacing: 14) {
                                NavigationLink {
                                    FilesView()
                                } label: {
                                    HubTile(
                                        icon: "folder.fill",
                                        title: "Files",
                                        subtitle: isFree ? "Upgrade to unlock" : "Your documents",
                                        color: .lumeNavy,
                                        isLocked: isFree
                                    )
                                }

                                NavigationLink {
                                    MoreView()
                                } label: {
                                    HubTile(
                                        icon: "person.fill",
                                        title: "Profile",
                                        subtitle: "Account & settings",
                                        color: Color(hex: "7B6B8D")
                                    )
                                }
                            }
                        }
                        .padding(.horizontal, 20)

                        Spacer().frame(height: 100)
                    }
                }
            }
            .navigationBarHidden(true)
        }
    }
}

// MARK: - Hub Tile

struct HubTile: View {
    let icon: String
    let title: String
    let subtitle: String
    let color: Color
    var isLocked: Bool = false

    var body: some View {
        ZStack(alignment: .topTrailing) {
            VStack(alignment: .leading, spacing: 10) {
                ZStack {
                    RoundedRectangle(cornerRadius: 12)
                        .fill(color.opacity(0.12))
                        .frame(width: 42, height: 42)
                    Image(systemName: icon)
                        .font(.system(size: 18))
                        .foregroundColor(color)
                }

                Text(title)
                    .font(.lumeSectionTitle)
                    .foregroundColor(.lumeNavy)

                Text(subtitle)
                    .font(.lumeCaptionLight)
                    .foregroundColor(.lumeMuted)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
            .background(Color.lumeWarmWhite)
            .cornerRadius(16)
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(Color.lumeBorder, lineWidth: 1)
            )

            if isLocked {
                Image(systemName: "lock.fill")
                    .font(.system(size: 10))
                    .foregroundColor(.lumeGold)
                    .padding(6)
                    .background(Color.lumeGold.opacity(0.12))
                    .cornerRadius(8)
                    .padding(10)
            }
        }
    }
}
