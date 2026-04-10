import SwiftUI

struct MoreView: View {
    @EnvironmentObject var appState: AppState
    @State private var showLogoutConfirm = false

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                List {
                    // Account section
                    Section {
                        if let user = appState.user {
                            HStack(spacing: 12) {
                                Circle()
                                    .fill(Color.lumeNavy.opacity(0.1))
                                    .frame(width: 44, height: 44)
                                    .overlay(
                                        Text(initials(for: user))
                                            .font(.lumeBodyMedium)
                                            .foregroundColor(.lumeNavy)
                                    )

                                VStack(alignment: .leading, spacing: 2) {
                                    Text(user.displayName ?? "Your Account")
                                        .font(.lumeBodyMedium)
                                        .foregroundColor(.lumeText)
                                    Text(user.email ?? "")
                                        .font(.lumeSmall)
                                        .foregroundColor(.lumeMuted)
                                }
                            }
                            .padding(.vertical, 4)
                        }
                    }

                    // Settings
                    Section("Settings") {
                        NavigationLink {
                            AccountSettingsView()
                        } label: {
                            Label("Account Settings", systemImage: "person.circle")
                        }

                        NavigationLink {
                            NotificationsSettingsView()
                        } label: {
                            Label("Notifications", systemImage: "bell")
                        }
                    }

                    // Support
                    Section("Support") {
                        NavigationLink {
                            HelpView()
                        } label: {
                            Label("Help & FAQ", systemImage: "questionmark.circle")
                        }

                        NavigationLink {
                            ContactView()
                        } label: {
                            Label("Contact Us", systemImage: "envelope")
                        }
                    }

                    // Legal
                    Section("Legal") {
                        NavigationLink {
                            LegalWebView(title: "Terms of Service", path: "/terms")
                        } label: {
                            Label("Terms of Service", systemImage: "doc.text")
                        }

                        NavigationLink {
                            LegalWebView(title: "Privacy Policy", path: "/privacy")
                        } label: {
                            Label("Privacy Policy", systemImage: "hand.raised")
                        }
                    }

                    // Sign out
                    Section {
                        Button(role: .destructive) {
                            showLogoutConfirm = true
                        } label: {
                            Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                        }
                    }
                }
                .listStyle(.insetGrouped)
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("More")
            .navigationBarTitleDisplayMode(.large)
            .alert("Sign out?", isPresented: $showLogoutConfirm) {
                Button("Sign Out", role: .destructive) {
                    appState.logout()
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("You can always sign back in with your email.")
            }
        }
    }

    private func initials(for user: User) -> String {
        if let name = user.displayName, !name.isEmpty {
            let parts = name.split(separator: " ")
            let first = parts.first.map { String($0.prefix(1)).uppercased() } ?? ""
            let last = parts.count > 1 ? String(parts.last!.prefix(1)).uppercased() : ""
            return first + last
        }
        if let email = user.email {
            return String(email.prefix(1)).uppercased()
        }
        return "?"
    }
}

// MARK: - Account Settings

struct AccountSettingsView: View {
    @EnvironmentObject var appState: AppState
    @State private var displayName = ""
    @State private var usState = ""
    @State private var isSaving = false
    @State private var showSaved = false

    private let service = DashboardService()

    private let usStates = [
        "", "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
        "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
        "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
        "VA","WA","WV","WI","WY","DC"
    ]

    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()

            List {
                Section("Profile") {
                    HStack {
                        Text("Display Name")
                            .font(.lumeCaption)
                        Spacer()
                        TextField("Your name", text: $displayName)
                            .font(.lumeBody)
                            .multilineTextAlignment(.trailing)
                    }

                    Picker("State", selection: $usState) {
                        Text("Select state").tag("")
                        ForEach(usStates.dropFirst(), id: \.self) { state in
                            Text(state).tag(state)
                        }
                    }
                }

                if let transition = appState.user?.transitionType {
                    Section("Transition") {
                        HStack {
                            Text("Current transition")
                                .font(.lumeCaption)
                            Spacer()
                            Text(transition.replacingOccurrences(of: "-", with: " ").capitalized)
                                .font(.lumeCaption)
                                .foregroundColor(.lumeMuted)
                        }
                    }
                }

                Section {
                    Button {
                        Task { await save() }
                    } label: {
                        HStack {
                            Spacer()
                            if isSaving {
                                ProgressView().tint(.white)
                            } else {
                                Text(showSaved ? "Saved" : "Save Changes")
                            }
                            Spacer()
                        }
                    }
                    .listRowBackground(Color.lumeNavy)
                    .foregroundColor(.white)
                    .fontWeight(.semibold)
                }
            }
            .listStyle(.insetGrouped)
            .scrollContentBackground(.hidden)
        }
        .navigationTitle("Account")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            displayName = appState.user?.displayName ?? ""
            usState = appState.user?.usState ?? ""
        }
    }

    private func save() async {
        isSaving = true
        do {
            try await service.updateSettings(
                displayName: displayName,
                usState: usState
            )
            showSaved = true
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            showSaved = false
        } catch {
            // Silently fail for now
        }
        isSaving = false
    }
}

// MARK: - Notifications Settings

struct NotificationsSettingsView: View {
    @State private var dailyReminder = true
    @State private var reminderHour = 9
    @State private var deadlineAlerts = true

    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()

            List {
                Section("Daily Check-in") {
                    Toggle("Daily reminder", isOn: $dailyReminder)
                        .tint(.lumeNavy)

                    if dailyReminder {
                        Picker("Reminder time", selection: $reminderHour) {
                            ForEach(6..<22, id: \.self) { hour in
                                Text(formatHour(hour)).tag(hour)
                            }
                        }
                    }
                }

                Section("Deadlines") {
                    Toggle("Deadline alerts", isOn: $deadlineAlerts)
                        .tint(.lumeNavy)

                    Text("Get notified 3 days before and on the day of upcoming deadlines.")
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)
                }

                Section {
                    Button("Save Preferences") {
                        Task {
                            let manager = PushNotificationManager.shared
                            await manager.scheduleDailyReminder(enabled: dailyReminder, hour: reminderHour)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .foregroundColor(.lumeNavy)
                    .fontWeight(.semibold)
                }
            }
            .listStyle(.insetGrouped)
            .scrollContentBackground(.hidden)
        }
        .navigationTitle("Notifications")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func formatHour(_ hour: Int) -> String {
        let h = hour > 12 ? hour - 12 : hour
        let ampm = hour >= 12 ? "PM" : "AM"
        return "\(h):00 \(ampm)"
    }
}

struct HelpView: View {
    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()
            Text("Help & FAQ coming soon")
                .font(.lumeBody)
                .foregroundColor(.lumeMuted)
        }
        .navigationTitle("Help")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct ContactView: View {
    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()
            Text("Contact support coming soon")
                .font(.lumeBody)
                .foregroundColor(.lumeMuted)
        }
        .navigationTitle("Contact")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct LegalWebView: View {
    let title: String
    let path: String

    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()
            Text("Loading \(title)...")
                .font(.lumeBody)
                .foregroundColor(.lumeMuted)
        }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
    }
}
