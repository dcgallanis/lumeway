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

// MARK: - Placeholder Setting Views

struct AccountSettingsView: View {
    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()
            Text("Account settings coming soon")
                .font(.lumeBody)
                .foregroundColor(.lumeMuted)
        }
        .navigationTitle("Account")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct NotificationsSettingsView: View {
    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()
            Text("Notification preferences coming soon")
                .font(.lumeBody)
                .foregroundColor(.lumeMuted)
        }
        .navigationTitle("Notifications")
        .navigationBarTitleDisplayMode(.inline)
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
