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
            } else {
                MainTabView()
            }
        }
        .animation(.easeInOut(duration: 0.3), value: appState.isAuthenticated)
        .animation(.easeInOut(duration: 0.3), value: appState.isLoading)
        .onAppear {
            appState.configureModelContext(modelContext)
        }
    }
}

struct LaunchView: View {
    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()
            VStack(spacing: 16) {
                Image(systemName: "sun.max")
                    .font(.system(size: 48, weight: .light))
                    .foregroundColor(.lumeAccent)
                Text("LUMEWAY")
                    .font(.lumeLogoText)
                    .foregroundColor(.lumeNavy)
            }
        }
    }
}

struct MainTabView: View {
    @EnvironmentObject var appState: AppState
    @State private var selectedTab = 0
    @State private var showChat = false

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
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
                        Label("Home", systemImage: "house")
                    }
                    .tag(0)

                ChecklistView()
                    .tabItem {
                        Label("Checklist", systemImage: "checklist")
                    }
                    .tag(1)

                GuidesView()
                    .tabItem {
                        Label("Guides", systemImage: "book")
                    }
                    .tag(2)

                FilesView()
                    .tabItem {
                        Label("Files", systemImage: "folder")
                    }
                    .tag(3)

                MoreView()
                    .tabItem {
                        Label("More", systemImage: "ellipsis.circle")
                    }
                    .tag(4)
            }
            .tint(.lumeAccent)
            } // close VStack

            // Floating AI Navigator button
            Button {
                showChat = true
            } label: {
                Image(systemName: "bubble.left.fill")
                    .font(.system(size: 22))
                    .foregroundColor(.white)
                    .frame(width: 56, height: 56)
                    .background(Color.lumeNavy)
                    .clipShape(Circle())
                    .shadow(color: .black.opacity(0.15), radius: 8, y: 4)
            }
            .padding(.trailing, 20)
            .padding(.bottom, 90)
        }
        .sheet(isPresented: $showChat) {
            NavigatorChatView()
        }
        .task {
            await appState.loadDashboard()

            // Set up notifications after dashboard loads
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
    }
}
