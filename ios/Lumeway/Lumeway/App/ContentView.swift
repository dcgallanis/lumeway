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
    @State private var dismissing = false
    @State private var thinkingIndex = 0

    private let thinkingWords = [
        "Gathering your stuff...",
        "Sorting your checklist...",
        "Checking your deadlines...",
        "Brewing some motivation...",
        "Counting your wins...",
        "Rounding up your notes...",
        "Polishing your progress...",
        "Finding where you left off...",
        "Warming up the dashboard...",
        "Putting your ducks in a row...",
    ]

    var body: some View {
        ZStack {
            Color.lumeNavy.ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                // Sun icon
                Image(systemName: "sun.max.fill")
                    .font(.system(size: 68, weight: .light))
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

                Spacer().frame(height: 28)

                // "Hey, there" or "Hey, name"
                Text("Hey, \(appState.user?.displayName ?? "there").")
                    .font(.custom("CormorantGaramond-Bold", size: 36))
                    .foregroundColor(.white)
                    .opacity(showText ? 1 : 0)
                    .offset(y: showText ? 0 : 16)

                Spacer().frame(height: 8)

                // "Loading your dashboard"
                Text("Loading your dashboard")
                    .font(.custom("Montserrat-Regular", size: 14))
                    .foregroundColor(.white.opacity(0.5))
                    .opacity(showText ? 1 : 0)

                Spacer().frame(height: 24)

                // Rotating fun thinking words
                Text(thinkingWords[thinkingIndex])
                    .font(.custom("Montserrat-Medium", size: 22).italic())
                    .foregroundColor(.lumeAccent)
                    .opacity(showText ? 1 : 0)
                    .animation(.easeInOut(duration: 0.3), value: thinkingIndex)
                    .id("thinking-\(thinkingIndex)")
                    .transition(.opacity)

                Spacer()
            }
            .opacity(dismissing ? 0 : 1)
        }
        .task {
            // Animate in
            withAnimation(.spring(response: 0.6, dampingFraction: 0.7)) {
                showSun = true
            }
            withAnimation(.easeOut(duration: 0.5).delay(0.2)) {
                showText = true
            }

            // Rotate thinking words with progressive timing — each stays a bit longer
            let delays: [UInt64] = [800_000_000, 1_000_000_000, 1_200_000_000, 1_400_000_000, 1_200_000_000]
            for i in 0..<delays.count {
                try? await Task.sleep(nanoseconds: delays[i])
                withAnimation(.easeInOut(duration: 0.25)) {
                    thinkingIndex = (i + 1) % thinkingWords.count
                }
            }

            // Auto-dismiss
            try? await Task.sleep(nanoseconds: 500_000_000)
            withAnimation(.easeIn(duration: 0.35)) {
                dismissing = true
            }
            try? await Task.sleep(nanoseconds: 350_000_000)
            appState.justLoggedIn = false
        }
    }
}

// MARK: - Main Tab View

// All navigable pages (excluding Home and Hub which are always fixed)
enum NavPage: String, CaseIterable, Identifiable {
    case checklist = "checklist"
    case community = "community"
    case chat = "chat"
    case goals = "goals"
    case calendar = "calendar"
    case activityLog = "activity_log"
    case notes = "notes"
    case guides = "guides"
    case files = "files"
    case profile = "profile"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .checklist: return "Checklist"
        case .community: return "Community"
        case .chat: return "Chat"
        case .goals: return "Goals"
        case .calendar: return "Calendar"
        case .activityLog: return "Activity"
        case .notes: return "Notes"
        case .guides: return "Guides"
        case .files: return "Files"
        case .profile: return "Profile"
        }
    }

    var icon: String {
        switch self {
        case .checklist: return "checklist"
        case .community: return "bubble.left.and.bubble.right"
        case .chat: return "message"
        case .goals: return "target"
        case .calendar: return "calendar"
        case .activityLog: return "note.text"
        case .notes: return "pencil.line"
        case .guides: return "book.fill"
        case .files: return "folder.fill"
        case .profile: return "person.fill"
        }
    }

    var filledIcon: String {
        switch self {
        case .checklist: return "checklist.checked"
        case .community: return "bubble.left.and.bubble.right.fill"
        case .chat: return "message.fill"
        case .goals: return "target"
        case .calendar: return "calendar"
        case .activityLog: return "note.text"
        case .notes: return "pencil.line"
        case .guides: return "book.fill"
        case .files: return "folder.fill"
        case .profile: return "person.fill"
        }
    }

    var color: Color {
        switch self {
        case .checklist: return .lumeGreen
        case .community: return .lumeAccent
        case .chat: return .lumeNavy
        case .goals: return .lumeGold
        case .calendar: return .lumeAccent
        case .activityLog: return .lumeGreen
        case .notes: return Color(hex: "5E8C9A")
        case .guides: return .lumeGold
        case .files: return .lumeNavy
        case .profile: return Color(hex: "7B6B8D")
        }
    }

    var subtitle: String {
        switch self {
        case .checklist: return "Your tasks"
        case .community: return "Connect & share"
        case .chat: return "Your Navigator"
        case .goals: return "Track your goals"
        case .calendar: return "Deadlines & dates"
        case .activityLog: return "Track your actions"
        case .notes: return "Your thoughts"
        case .guides: return "Step-by-step help"
        case .files: return "Your documents"
        case .profile: return "Account & settings"
        }
    }

    @ViewBuilder
    var destination: some View {
        switch self {
        case .checklist: ChecklistView()
        case .community: CommunityView()
        case .chat: NavigatorChatView()
        case .goals: GoalsView()
        case .calendar: CalendarView()
        case .activityLog: ActivityLogView()
        case .notes: NotesView()
        case .guides: GuidesView()
        case .files: FilesView()
        case .profile: MoreView()
        }
    }

    /// Destination without its own NavigationStack — for use inside Hub/Dashboard NavigationLinks
    @ViewBuilder
    var embeddedDestination: some View {
        switch self {
        case .checklist: ChecklistView(isEmbedded: true)
        case .community: CommunityView(isEmbedded: true)
        case .chat: NavigatorChatView(isEmbedded: true)
        case .goals: GoalsView(isEmbedded: true)
        case .calendar: CalendarView(isEmbedded: true)
        case .activityLog: ActivityLogView(isEmbedded: true)
        case .notes: NotesView(isEmbedded: true)
        case .guides: GuidesView(isEmbedded: true)
        case .files: FilesView(isEmbedded: true)
        case .profile: MoreView(isEmbedded: true)
        }
    }
}

/// Default tab bar pages (besides Home=0 and Hub=4)
let defaultTabPages: [NavPage] = [.checklist, .community, .chat]

struct MainTabView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var chatViewModel = ChatViewModel()
    @State private var selectedTab = 0
    @AppStorage("tabBarPages") private var tabBarPagesRaw: String = "checklist,community,chat"

    var tabPages: [NavPage] {
        let keys = tabBarPagesRaw.split(separator: ",").map(String.init)
        return keys.compactMap { NavPage(rawValue: $0) }
    }

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

                // Dynamic middle tabs (user-configurable)
                ForEach(Array(tabPages.enumerated()), id: \.element.id) { idx, page in
                    page.destination
                        .tabItem {
                            Image(systemName: selectedTab == (idx + 1) ? page.filledIcon : page.icon)
                            Text(page.label)
                        }
                        .tag(idx + 1)
                }

                HubView()
                    .tabItem {
                        Image(systemName: selectedTab == 4 ? "square.grid.2x2.fill" : "square.grid.2x2")
                        Text("Hub")
                    }
                    .tag(4)
            }
            .tint(.lumeAccent)
            .environmentObject(chatViewModel)
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
            // Find Checklist in dynamic tabs
            if let idx = tabPages.firstIndex(of: .checklist) {
                selectedTab = idx + 1
            }
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
    @AppStorage("tabBarPages") private var tabBarPagesRaw: String = "checklist,community,chat"
    @State private var showPersonalize = false
    @State var path = NavigationPath()

    var body: some View {
        NavigationStack(path: $path) {
            ZStack {
                LinearGradient(
                    colors: [Color(hex: "FAF7F2"), Color(hex: "F5F0EA")],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        // Header with personalize button
                        HStack {
                            Text("Your Hub")
                                .font(.lumeHeadingLarge)
                                .foregroundColor(.lumeNavy)
                            Spacer()
                            Button {
                                showPersonalize = true
                            } label: {
                                HStack(spacing: 5) {
                                    Image(systemName: "slider.horizontal.3")
                                        .font(.system(size: 13))
                                    Text("Personalize")
                                        .font(.lumeSmall)
                                }
                                .foregroundColor(.lumeAccent)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 7)
                                .background(Color.lumeAccent.opacity(0.08))
                                .cornerRadius(20)
                            }
                        }
                        .padding(.horizontal, 24)
                        .padding(.top, 20)

                        // All tools grid — 3-column, same style as dashboard
                        let columns = [
                            GridItem(.flexible(), spacing: 12),
                            GridItem(.flexible(), spacing: 12),
                            GridItem(.flexible(), spacing: 12)
                        ]
                        LazyVGrid(columns: columns, spacing: 12) {
                            ForEach(NavPage.allCases) { page in
                                Button {
                                    path.append(page)
                                } label: {
                                    QuickLinkContent(icon: page.icon, label: page.label, color: page.color)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.horizontal, 20)

                        Spacer().frame(height: 100)
                    }
                }
            }
            .navigationBarHidden(true)
            .navigationDestination(for: NavPage.self) { page in
                page.embeddedDestination
            }
            .sheet(isPresented: $showPersonalize) {
                PersonalizeTabsSheet(tabBarPagesRaw: $tabBarPagesRaw)
                    .presentationDetents([.medium, .large])
            }
        }
    }
}

// MARK: - Personalize Tabs Sheet

struct PersonalizeTabsSheet: View {
    @Binding var tabBarPagesRaw: String
    @Environment(\.dismiss) var dismiss
    @State private var selectedPages: [NavPage] = []

    private let maxTabs = 3

    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()

        ScrollView {
            VStack(spacing: 20) {
                // Header with Save button
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Personalize Navigation")
                            .font(.lumeDisplaySmall)
                            .foregroundColor(.lumeNavy)
                        Text("Choose 3 pages for your bottom nav bar. The rest will appear in Hub.")
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }
                    Spacer()
                    Button {
                        tabBarPagesRaw = selectedPages.map(\.rawValue).joined(separator: ",")
                        dismiss()
                    } label: {
                        Text("Save")
                            .font(.lumeBodySemibold)
                            .foregroundColor(.white)
                            .padding(.horizontal, 20)
                            .padding(.vertical, 10)
                            .background(selectedPages.count == maxTabs ? Color.lumeAccent : Color.lumeMuted)
                            .cornerRadius(20)
                    }
                    .disabled(selectedPages.count != maxTabs)
                }
                .padding(.horizontal, 24)
                .padding(.top, 20)

                // Current tab bar preview
                VStack(alignment: .leading, spacing: 10) {
                    Text("TAB BAR")
                        .font(.lumeSmall)
                        .fontWeight(.semibold)
                        .foregroundColor(.lumeMuted)
                        .tracking(1)

                    HStack(spacing: 0) {
                        // Fixed Home
                        VStack(spacing: 4) {
                            Image(systemName: "house.fill")
                                .font(.system(size: 16))
                            Text("Home")
                                .font(.system(size: 9))
                        }
                        .foregroundColor(.lumeAccent)
                        .frame(maxWidth: .infinity)

                        ForEach(selectedPages, id: \.id) { page in
                            VStack(spacing: 4) {
                                Image(systemName: page.filledIcon)
                                    .font(.system(size: 16))
                                Text(page.label)
                                    .font(.system(size: 9))
                            }
                            .foregroundColor(.lumeMuted)
                            .frame(maxWidth: .infinity)
                        }

                        // Show placeholders for remaining slots
                        ForEach(0..<(maxTabs - selectedPages.count), id: \.self) { _ in
                            VStack(spacing: 4) {
                                Image(systemName: "plus.circle.dotted")
                                    .font(.system(size: 16))
                                Text("Choose")
                                    .font(.system(size: 9))
                            }
                            .foregroundColor(.lumeBorder)
                            .frame(maxWidth: .infinity)
                        }

                        // Fixed Hub
                        VStack(spacing: 4) {
                            Image(systemName: "square.grid.2x2.fill")
                                .font(.system(size: 16))
                            Text("Hub")
                                .font(.system(size: 9))
                        }
                        .foregroundColor(.lumeAccent)
                        .frame(maxWidth: .infinity)
                    }
                    .padding(.vertical, 12)
                    .background(Color.lumeWarmWhite)
                    .cornerRadius(12)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(Color.lumeBorder, lineWidth: 1)
                    )
                }
                .padding(.horizontal, 24)

                // All pages list
                VStack(alignment: .leading, spacing: 10) {
                    Text("AVAILABLE PAGES")
                        .font(.lumeSmall)
                        .fontWeight(.semibold)
                        .foregroundColor(.lumeMuted)
                        .tracking(1)

                    ForEach(NavPage.allCases) { page in
                        let isSelected = selectedPages.contains(page)
                        Button {
                            togglePage(page)
                        } label: {
                            HStack(spacing: 14) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 10)
                                        .fill(page.color.opacity(0.12))
                                        .frame(width: 36, height: 36)
                                    Image(systemName: page.icon)
                                        .font(.system(size: 15))
                                        .foregroundColor(page.color)
                                }

                                VStack(alignment: .leading, spacing: 2) {
                                    Text(page.label)
                                        .font(.lumeBodyMedium)
                                        .foregroundColor(.lumeNavy)
                                    Text(isSelected ? "In tab bar" : "In Hub")
                                        .font(.lumeSmall)
                                        .foregroundColor(.lumeMuted)
                                }

                                Spacer()

                                ZStack {
                                    RoundedRectangle(cornerRadius: 8)
                                        .fill(isSelected ? Color.lumeAccent : Color.lumeBorder.opacity(0.3))
                                        .frame(width: 28, height: 28)
                                    if isSelected {
                                        Image(systemName: "checkmark")
                                            .font(.system(size: 12, weight: .bold))
                                            .foregroundColor(.white)
                                    }
                                }
                            }
                            .padding(12)
                            .background(isSelected ? Color.lumeAccent.opacity(0.04) : Color.lumeWarmWhite)
                            .cornerRadius(12)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(isSelected ? Color.lumeAccent.opacity(0.2) : Color.lumeBorder, lineWidth: 1)
                            )
                        }
                    }
                }
                .padding(.horizontal, 24)

                if selectedPages.count != maxTabs {
                    Text("Select exactly 3 pages for your tab bar")
                        .font(.lumeSmall)
                        .foregroundColor(.lumeAccent)
                        .padding(.horizontal, 24)
                }

                Spacer().frame(height: 20)
            }
        }
        } // ZStack
        .environment(\.colorScheme, .light)
        .onAppear {
            let keys = tabBarPagesRaw.split(separator: ",").map(String.init)
            selectedPages = keys.compactMap { NavPage(rawValue: $0) }
        }
    }

    private func togglePage(_ page: NavPage) {
        if let idx = selectedPages.firstIndex(of: page) {
            selectedPages.remove(at: idx)
        } else if selectedPages.count < maxTabs {
            selectedPages.append(page)
        }
    }
}
