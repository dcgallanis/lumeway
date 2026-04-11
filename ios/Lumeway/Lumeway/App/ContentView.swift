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
    @State private var showSubtext = false
    @State private var dismissing = false

    private let greetings = [
        ("Welcome back!", "Let's keep the momentum going."),
        ("Hey, you're here!", "Ready to knock some things out?"),
        ("Look who's back!", "Your checklist missed you."),
        ("Good to see you!", "Let's pick up where you left off."),
        ("You showed up.", "That's half the battle. Let's go."),
    ]

    private var greeting: (String, String) {
        greetings.randomElement() ?? greetings[0]
    }

    var body: some View {
        ZStack {
            Color.lumeNavy.ignoresSafeArea()

            VStack(spacing: 20) {
                Spacer()

                Image(systemName: "sun.max.fill")
                    .font(.system(size: 64, weight: .light))
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

                Text(greeting.0)
                    .font(.lumeHeadingLarge)
                    .foregroundColor(.white)
                    .opacity(showText ? 1 : 0)
                    .offset(y: showText ? 0 : 20)

                Text(greeting.1)
                    .font(.lumeBodyLight)
                    .foregroundColor(.white.opacity(0.6))
                    .opacity(showSubtext ? 1 : 0)

                Spacer()
            }
            .opacity(dismissing ? 0 : 1)
        }
        .onAppear {
            withAnimation(.spring(response: 0.6, dampingFraction: 0.7)) {
                showSun = true
            }
            withAnimation(.easeOut(duration: 0.5).delay(0.3)) {
                showText = true
            }
            withAnimation(.easeOut(duration: 0.4).delay(0.6)) {
                showSubtext = true
            }
            Task {
                try? await Task.sleep(nanoseconds: 2_500_000_000)
                withAnimation(.easeIn(duration: 0.4)) {
                    dismissing = true
                }
                try? await Task.sleep(nanoseconds: 400_000_000)
                appState.justLoggedIn = false
            }
        }
    }
}

// MARK: - Main Tab View

struct MainTabView: View {
    @EnvironmentObject var appState: AppState
    @State private var selectedTab = 0

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

                GuidesView()
                    .tabItem {
                        Image(systemName: selectedTab == 2 ? "book.fill" : "book")
                        Text("Guides")
                    }
                    .tag(2)

                FilesView()
                    .tabItem {
                        Image(systemName: selectedTab == 3 ? "folder.fill" : "folder")
                        Text("Files")
                    }
                    .tag(3)

                MoreView()
                    .tabItem {
                        Image(systemName: selectedTab == 4 ? "person.fill" : "person")
                        Text("Profile")
                    }
                    .tag(4)
            }
            .tint(.lumeAccent)
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
