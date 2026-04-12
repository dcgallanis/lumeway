import SwiftUI

struct MoreView: View {
    @EnvironmentObject var appState: AppState
    @State private var showLogoutConfirm = false
    @State private var showAvatarPicker = false
    @AppStorage("selectedProfileEmoji") private var selectedProfileEmoji = "☀️"

    private var emojiColor: Color {
        bgColorForIcon(selectedProfileEmoji)
    }

    /// Convert tier string to Roman numeral display
    private var tierDisplay: String {
        guard let tier = appState.user?.tier, !tier.isEmpty else {
            return "Tier I"
        }
        switch tier.lowercased() {
        case "free": return "Tier I"
        case "starter": return "Tier II"
        case "pass": return "Tier III"
        case "unlimited": return "Tier IV"
        default: return "Tier I"
        }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                // Subtle gradient background instead of flat cream
                LinearGradient(
                    colors: [Color(hex: "F5F0EA"), Color(hex: "FAF7F2"), Color(hex: "F0EDE8")],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 0) {
                        // Color-blocked profile header
                        ZStack {
                            LinearGradient(
                                colors: [Color.lumeNavy, Color(hex: "3A5A6E")],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )

                            VStack(spacing: 14) {
                                // Tappable avatar
                                Button {
                                    showAvatarPicker = true
                                } label: {
                                    ZStack {
                                        Circle()
                                            .fill(emojiColor.opacity(0.3))
                                            .frame(width: 76, height: 76)
                                        Circle()
                                            .stroke(Color.white.opacity(0.3), lineWidth: 2)
                                            .frame(width: 76, height: 76)
                                        Text(selectedProfileEmoji)
                                            .font(.system(size: 34))

                                        // Edit badge
                                        ZStack {
                                            Circle()
                                                .fill(Color.lumeGold)
                                                .frame(width: 22, height: 22)
                                            Image(systemName: "pencil")
                                                .font(.system(size: 10, weight: .bold))
                                                .foregroundColor(.white)
                                        }
                                        .offset(x: 28, y: 28)
                                    }
                                }

                                if let user = appState.user {
                                    Text(user.displayName ?? "Your Account")
                                        .font(.lumeDisplaySmall)
                                        .foregroundColor(.white)

                                    Text(user.email)
                                        .font(.lumeCaption)
                                        .foregroundColor(.white.opacity(0.6))

                                    // Tier pill with Roman numeral
                                    Text(tierDisplay)
                                        .font(.lumeSmall)
                                        .fontWeight(.semibold)
                                        .foregroundColor(.lumeGold)
                                        .tracking(1)
                                        .padding(.horizontal, 16)
                                        .padding(.vertical, 6)
                                        .background(Color.white.opacity(0.1))
                                        .cornerRadius(20)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 20)
                                                .stroke(Color.lumeGold.opacity(0.3), lineWidth: 1)
                                        )
                                }
                            }
                            .padding(.top, 60)
                            .padding(.bottom, 32)
                        }
                        .cornerRadius(24, corners: [.bottomLeft, .bottomRight])

                        // Settings sections
                        VStack(spacing: 20) {
                            // Account section
                            VStack(spacing: 0) {
                                SettingSectionHeader(title: "ACCOUNT")

                                VStack(spacing: 0) {
                                    NavigationLink {
                                        AccountSettingsView()
                                    } label: {
                                        ProfileSettingRow(
                                            icon: "person.crop.circle",
                                            label: "Edit Profile",
                                            iconColor: Color(hex: "2C4A5E"),
                                            bgColor: Color(hex: "E4E8EE")
                                        )
                                    }

                                    Divider().padding(.leading, 62)

                                    NavigationLink {
                                        NotificationsSettingsView()
                                    } label: {
                                        ProfileSettingRow(
                                            icon: "bell.badge.fill",
                                            label: "Notifications",
                                            iconColor: Color(hex: "C4704E"),
                                            bgColor: Color(hex: "F0EAE0")
                                        )
                                    }
                                }
                                .background(Color.lumeWarmWhite)
                                .cornerRadius(16)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 16)
                                        .stroke(Color.lumeBorder, lineWidth: 1)
                                )
                            }

                            // Support section
                            VStack(spacing: 0) {
                                SettingSectionHeader(title: "SUPPORT")

                                VStack(spacing: 0) {
                                    ProfileSettingRow(
                                        icon: "lifepreserver.fill",
                                        label: "Help & FAQ",
                                        iconColor: Color(hex: "4A7C59"),
                                        bgColor: Color(hex: "E8F0E4")
                                    )

                                    Divider().padding(.leading, 62)

                                    ProfileSettingRow(
                                        icon: "paperplane.fill",
                                        label: "Contact Us",
                                        iconColor: Color(hex: "5E8C9A"),
                                        bgColor: Color(hex: "E0EDF0")
                                    )

                                    Divider().padding(.leading, 62)

                                    ProfileSettingRow(
                                        icon: "hand.raised.fill",
                                        label: "Privacy Policy",
                                        iconColor: Color(hex: "7B6B8D"),
                                        bgColor: Color(hex: "EDE8F0")
                                    )
                                }
                                .background(Color.lumeWarmWhite)
                                .cornerRadius(16)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 16)
                                        .stroke(Color.lumeBorder, lineWidth: 1)
                                )
                            }

                            // App section
                            VStack(spacing: 0) {
                                SettingSectionHeader(title: "APP")

                                VStack(spacing: 0) {
                                    ProfileSettingRow(
                                        icon: "sparkles",
                                        label: "Rate Lumeway",
                                        iconColor: Color(hex: "B8977E"),
                                        bgColor: Color(hex: "F0EAE0")
                                    )

                                    Divider().padding(.leading, 62)

                                    ProfileSettingRow(
                                        icon: "heart.circle.fill",
                                        label: "Share with a friend",
                                        iconColor: Color(hex: "D4896C"),
                                        bgColor: Color(hex: "F5EAE4")
                                    )
                                }
                                .background(Color.lumeWarmWhite)
                                .cornerRadius(16)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 16)
                                        .stroke(Color.lumeBorder, lineWidth: 1)
                                )
                            }

                            // Sign out
                            Button {
                                showLogoutConfirm = true
                            } label: {
                                HStack(spacing: 8) {
                                    Image(systemName: "rectangle.portrait.and.arrow.right")
                                        .font(.system(size: 14))
                                    Text("Sign Out")
                                        .font(.lumeBodyMedium)
                                }
                                .foregroundColor(.lumeAccent)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 14)
                                .background(Color.lumeAccent.opacity(0.06))
                                .cornerRadius(14)
                            }

                            // Version
                            Text("Lumeway v1.0")
                                .font(.lumeSmall)
                                .foregroundColor(.lumeMuted)
                                .padding(.bottom, 100)
                        }
                        .padding(.horizontal, 20)
                        .padding(.top, 20)
                    }
                }
                .ignoresSafeArea(edges: .top)
            }
            .navigationBarHidden(true)
            .confirmationDialog("Sign out?", isPresented: $showLogoutConfirm) {
                Button("Sign out", role: .destructive) {
                    appState.logout()
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("You can always sign back in with your email.")
            }
            .sheet(isPresented: $showAvatarPicker) {
                EmojiAvatarPickerSheet(selectedEmoji: $selectedProfileEmoji)
                    .presentationDetents([.medium])
            }
        }
    }
}

// MARK: - Emoji Avatar Picker (matches site dashboard icons)

struct EmojiAvatarPickerSheet: View {
    @Binding var selectedEmoji: String
    @AppStorage("selectedIconBgColor") private var selectedBgColorHex: String = ""
    @Environment(\.dismiss) var dismiss

    let columns = [GridItem(.adaptive(minimum: 60), spacing: 14)]

    private let bgColorOptions: [(String, Color)] = [
        ("", Color.clear), // "Auto" — use default
        ("B8977E", Color(hex: "B8977E")),   // gold
        ("C4704E", Color(hex: "C4704E")),   // terracotta
        ("4A7C59", Color(hex: "4A7C59")),   // green
        ("5E8C9A", Color(hex: "5E8C9A")),   // teal
        ("2C4A5E", Color(hex: "2C4A5E")),   // navy
        ("7B6B8D", Color(hex: "7B6B8D")),   // purple
        ("D4896C", Color(hex: "D4896C")),   // blush
        ("6B7B8D", Color(hex: "6B7B8D")),   // muted
    ]

    private var effectiveBgColor: Color {
        if selectedBgColorHex.isEmpty {
            return bgColorForIcon(selectedEmoji)
        }
        return Color(hex: selectedBgColorHex)
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                HStack {
                    Text("Choose your icon")
                        .font(.lumeDisplaySmall)
                        .foregroundColor(.lumeNavy)
                    Spacer()
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 24))
                            .foregroundColor(.lumeMuted)
                    }
                }
                .padding(.horizontal, 24)
                .padding(.top, 20)

                // Emoji grid
                LazyVGrid(columns: columns, spacing: 14) {
                    ForEach(communityEmojiIcons, id: \.self) { emoji in
                        Button {
                            selectedEmoji = emoji
                            UserDefaults.standard.set(emoji, forKey: "community_icon")
                        } label: {
                            ZStack {
                                Circle()
                                    .fill(effectiveBgColor.opacity(selectedEmoji == emoji ? 0.35 : 0.15))
                                    .frame(width: 56, height: 56)
                                if selectedEmoji == emoji {
                                    Circle()
                                        .stroke(effectiveBgColor, lineWidth: 2.5)
                                        .frame(width: 56, height: 56)
                                }
                                Text(emoji)
                                    .font(.system(size: 26))
                            }
                        }
                    }
                }
                .padding(.horizontal, 24)

                // Background color picker
                VStack(alignment: .leading, spacing: 10) {
                    Text("BACKGROUND COLOR")
                        .font(.lumeSmall)
                        .fontWeight(.semibold)
                        .foregroundColor(.lumeMuted)
                        .tracking(1)

                    HStack(spacing: 12) {
                        ForEach(bgColorOptions, id: \.0) { hex, color in
                            Button {
                                selectedBgColorHex = hex
                                UserDefaults.standard.set(hex, forKey: "community_icon_bg")
                            } label: {
                                ZStack {
                                    if hex.isEmpty {
                                        // Auto option
                                        Circle()
                                            .fill(bgColorForIcon(selectedEmoji))
                                            .frame(width: 32, height: 32)
                                        Text("A")
                                            .font(.system(size: 11, weight: .bold))
                                            .foregroundColor(.white)
                                    } else {
                                        Circle()
                                            .fill(color)
                                            .frame(width: 32, height: 32)
                                    }

                                    if selectedBgColorHex == hex {
                                        Circle()
                                            .stroke(Color.white, lineWidth: 2)
                                            .frame(width: 32, height: 32)
                                        Circle()
                                            .stroke(color.isEmpty ? bgColorForIcon(selectedEmoji) : color, lineWidth: 3)
                                            .frame(width: 38, height: 38)
                                    }
                                }
                            }
                        }
                    }
                }
                .padding(.horizontal, 24)

                // Preview
                HStack(spacing: 12) {
                    ZStack {
                        Circle()
                            .fill(effectiveBgColor)
                            .frame(width: 44, height: 44)
                        Text(selectedEmoji)
                            .font(.system(size: 22))
                    }

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Your preview")
                            .font(.lumeCaption)
                            .fontWeight(.medium)
                            .foregroundColor(.lumeNavy)
                        Text("This is how you'll appear in the community")
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }

                    Spacer()
                }
                .padding(.horizontal, 24)

                // Done button
                Button {
                    dismiss()
                } label: {
                    Text("Done")
                        .font(.lumeBodySemibold)
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Color.lumeAccent)
                        .cornerRadius(28)
                }
                .padding(.horizontal, 24)

                Spacer().frame(height: 20)
            }
        }
    }
}

// MARK: - Setting Components

struct SettingSectionHeader: View {
    let title: String

    var body: some View {
        HStack {
            Text(title)
                .font(.lumeSmall)
                .fontWeight(.semibold)
                .foregroundColor(.lumeMuted)
                .tracking(1)
            Spacer()
        }
        .padding(.horizontal, 4)
        .padding(.bottom, 8)
    }
}

struct ProfileSettingRow: View {
    let icon: String
    let label: String
    let iconColor: Color
    let bgColor: Color

    var body: some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 10)
                    .fill(bgColor)
                    .frame(width: 36, height: 36)
                Image(systemName: icon)
                    .font(.system(size: 15))
                    .foregroundColor(iconColor)
            }

            Text(label)
                .font(.lumeBody)
                .foregroundColor(.lumeNavy)

            Spacer()

            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.lumeBorder)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 13)
    }
}

// MARK: - Account Settings (Edit Profile)

struct AccountSettingsView: View {
    @EnvironmentObject var appState: AppState
    @AppStorage("selectedProfileEmoji") private var selectedProfileEmoji = "☀️"
    @State private var displayName = ""
    @State private var usState = ""
    @State private var communityName = ""
    @State private var isSaving = false
    @State private var showSaved = false
    @State private var showAvatarPicker = false

    private let service = DashboardService()

    private let usStates = [
        "", "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
        "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
        "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
        "VA","WA","WV","WI","WY","DC"
    ]

    private var emojiColor: Color {
        bgColorForIcon(selectedProfileEmoji)
    }

    /// Convert tier string to Roman numeral display
    private var tierDisplay: String {
        guard let tier = appState.user?.tier, !tier.isEmpty else {
            return "Tier I"
        }
        switch tier.lowercased() {
        case "free": return "Tier I"
        case "starter": return "Tier II"
        case "pass": return "Tier III"
        case "unlimited": return "Tier IV"
        default: return "Tier I"
        }
    }

    private var tierLabel: String {
        guard let tier = appState.user?.tier, !tier.isEmpty else {
            return "Free"
        }
        return tier.capitalized
    }

    var body: some View {
        ZStack {
            Color(hex: "F0EDE8").ignoresSafeArea()

            ScrollView {
                VStack(spacing: 0) {
                    // Color-blocked header
                    ZStack {
                        Color.lumeNavy

                        VStack(spacing: 12) {
                            // Tappable avatar
                            Button {
                                showAvatarPicker = true
                            } label: {
                                ZStack {
                                    Circle()
                                        .fill(emojiColor.opacity(0.3))
                                        .frame(width: 68, height: 68)
                                    Circle()
                                        .stroke(Color.white.opacity(0.3), lineWidth: 2)
                                        .frame(width: 68, height: 68)
                                    Text(selectedProfileEmoji)
                                        .font(.system(size: 30))

                                    ZStack {
                                        Circle()
                                            .fill(Color.lumeGold)
                                            .frame(width: 20, height: 20)
                                        Image(systemName: "pencil")
                                            .font(.system(size: 9, weight: .bold))
                                            .foregroundColor(.white)
                                    }
                                    .offset(x: 24, y: 24)
                                }
                            }

                            Text("Edit Profile")
                                .font(.lumeDisplaySmall)
                                .foregroundColor(.white)
                        }
                        .padding(.top, 60)
                        .padding(.bottom, 28)
                    }
                    .cornerRadius(20, corners: [.bottomLeft, .bottomRight])

                    // Form fields
                    VStack(spacing: 18) {
                        // Display name
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Display Name")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)

                            TextField("Your name", text: $displayName)
                                .font(.lumeBody)
                                .foregroundColor(.lumeText)
                                .padding(14)
                                .background(Color.lumeWarmWhite)
                                .cornerRadius(12)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.lumeBorder, lineWidth: 1)
                                )
                        }

                        // Community name
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Community Name")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)

                            TextField("Anonymous", text: $communityName)
                                .font(.lumeBody)
                                .foregroundColor(.lumeText)
                                .padding(14)
                                .background(Color.lumeWarmWhite)
                                .cornerRadius(12)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.lumeBorder, lineWidth: 1)
                                )

                            Text("This is how others see you in the community. Leave blank for Anonymous.")
                                .font(.lumeSmall)
                                .foregroundColor(.lumeMuted)
                        }

                        // US State
                        VStack(alignment: .leading, spacing: 8) {
                            Text("State")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)

                            Picker("State", selection: $usState) {
                                Text("Select state").tag("")
                                ForEach(usStates.filter { !$0.isEmpty }, id: \.self) { state in
                                    Text(state).tag(state)
                                }
                            }
                            .pickerStyle(.menu)
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.lumeWarmWhite)
                            .cornerRadius(12)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color.lumeBorder, lineWidth: 1)
                            )
                        }

                        // Bundle / Tier (read-only)
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Your Plan")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)

                            HStack(spacing: 10) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 8)
                                        .fill(Color.lumeGold.opacity(0.1))
                                        .frame(width: 32, height: 32)
                                    Image(systemName: "crown.fill")
                                        .font(.system(size: 14))
                                        .foregroundColor(.lumeGold)
                                }

                                VStack(alignment: .leading, spacing: 2) {
                                    Text(tierDisplay)
                                        .font(.lumeBodyMedium)
                                        .foregroundColor(.lumeNavy)
                                    Text("\(tierLabel) Plan")
                                        .font(.lumeSmall)
                                        .foregroundColor(.lumeMuted)
                                }

                                Spacer()

                                Text("Manage")
                                    .font(.lumeSmall)
                                    .foregroundColor(.lumeAccent)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 5)
                                    .background(Color.lumeAccent.opacity(0.08))
                                    .cornerRadius(8)
                            }
                            .padding(14)
                            .background(Color.lumeWarmWhite)
                            .cornerRadius(12)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color.lumeBorder, lineWidth: 1)
                            )
                        }

                        // Save button
                        Button {
                            Task { await saveSettings() }
                        } label: {
                            if isSaving {
                                ProgressView()
                                    .tint(.white)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 14)
                            } else {
                                Text(showSaved ? "Saved!" : "Save Changes")
                                    .font(.lumeBodySemibold)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 14)
                            }
                        }
                        .foregroundColor(.white)
                        .background(
                            RoundedRectangle(cornerRadius: 28)
                                .fill(showSaved ? Color.lumeGreen : Color.lumeAccent)
                        )
                        .disabled(isSaving)
                    }
                    .padding(24)
                }
            }
            .ignoresSafeArea(edges: .top)
        }
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            displayName = appState.user?.displayName ?? ""
            usState = appState.user?.usState ?? ""
            communityName = UserDefaults.standard.string(forKey: "community_display_name") ?? "Anonymous"
        }
        .sheet(isPresented: $showAvatarPicker) {
            EmojiAvatarPickerSheet(selectedEmoji: $selectedProfileEmoji)
                .presentationDetents([.medium])
        }
    }

    private func saveSettings() async {
        isSaving = true
        defer { isSaving = false }
        do {
            try await service.updateSettings(
                displayName: displayName,
                usState: usState
            )
            // Save community name locally (syncs with site localStorage approach)
            let comName = communityName.trimmingCharacters(in: .whitespaces)
            UserDefaults.standard.set(comName.isEmpty ? "Anonymous" : comName, forKey: "community_display_name")
            withAnimation { showSaved = true }
            Task {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                withAnimation { showSaved = false }
            }
        } catch {}
    }
}

// MARK: - Notifications Settings

struct NotificationsSettingsView: View {
    @State private var dailyReminder = true
    @State private var reminderTime = Date()
    @State private var deadlineAlerts = true

    var body: some View {
        ZStack {
            Color(hex: "F0EDE8").ignoresSafeArea()

            ScrollView {
                VStack(spacing: 0) {
                    // Color-blocked header
                    ZStack {
                        Color.lumeNavy

                        VStack(spacing: 10) {
                            Image(systemName: "bell.badge.fill")
                                .font(.system(size: 28))
                                .foregroundColor(.lumeGold)
                            Text("Notifications")
                                .font(.lumeDisplaySmall)
                                .foregroundColor(.white)
                        }
                        .padding(.top, 60)
                        .padding(.bottom, 28)
                    }
                    .cornerRadius(20, corners: [.bottomLeft, .bottomRight])

                    VStack(spacing: 16) {
                        // Daily reminder
                        VStack(spacing: 0) {
                            HStack {
                                HStack(spacing: 10) {
                                    ZStack {
                                        RoundedRectangle(cornerRadius: 8)
                                            .fill(Color(hex: "F0EAE0"))
                                            .frame(width: 32, height: 32)
                                        Image(systemName: "sun.max.fill")
                                            .font(.system(size: 14))
                                            .foregroundColor(Color(hex: "C4704E"))
                                    }
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text("Daily Check-in")
                                            .font(.lumeBodyMedium)
                                            .foregroundColor(.lumeNavy)
                                        Text("A gentle nudge to review your tasks")
                                            .font(.lumeSmall)
                                            .foregroundColor(.lumeMuted)
                                    }
                                }
                                Spacer()
                                Toggle("", isOn: $dailyReminder)
                                    .tint(.lumeGreen)
                            }
                            .padding(16)

                            if dailyReminder {
                                Divider().padding(.horizontal, 16)
                                HStack {
                                    Text("Time")
                                        .font(.lumeCaption)
                                        .foregroundColor(.lumeNavy)
                                    Spacer()
                                    DatePicker("", selection: $reminderTime, displayedComponents: .hourAndMinute)
                                        .labelsHidden()
                                }
                                .padding(16)
                            }
                        }
                        .background(Color.lumeWarmWhite)
                        .cornerRadius(14)
                        .overlay(
                            RoundedRectangle(cornerRadius: 14)
                                .stroke(Color.lumeBorder, lineWidth: 1)
                        )

                        // Deadline alerts
                        HStack {
                            HStack(spacing: 10) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 8)
                                        .fill(Color(hex: "E8F0E4"))
                                        .frame(width: 32, height: 32)
                                    Image(systemName: "calendar.badge.clock")
                                        .font(.system(size: 14))
                                        .foregroundColor(Color(hex: "4A7C59"))
                                }
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Deadline Alerts")
                                        .font(.lumeBodyMedium)
                                        .foregroundColor(.lumeNavy)
                                    Text("Get notified before important deadlines")
                                        .font(.lumeSmall)
                                        .foregroundColor(.lumeMuted)
                                }
                            }
                            Spacer()
                            Toggle("", isOn: $deadlineAlerts)
                                .tint(.lumeGreen)
                        }
                        .padding(16)
                        .background(Color.lumeWarmWhite)
                        .cornerRadius(14)
                        .overlay(
                            RoundedRectangle(cornerRadius: 14)
                                .stroke(Color.lumeBorder, lineWidth: 1)
                        )
                    }
                    .padding(24)
                }
            }
            .ignoresSafeArea(edges: .top)
        }
        .navigationBarTitleDisplayMode(.inline)
        .onChange(of: dailyReminder) { _, enabled in
            if enabled {
                let hour = Calendar.current.component(.hour, from: reminderTime)
                let minute = Calendar.current.component(.minute, from: reminderTime)
                Task {
                    await PushNotificationManager.shared.scheduleDailyReminder(enabled: enabled, hour: hour, minute: minute)
                }
            }
        }
    }
}
