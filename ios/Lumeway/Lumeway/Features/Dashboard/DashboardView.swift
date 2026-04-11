import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var appState: AppState
    @State private var checklistItems: [FullChecklistItem] = []
    @State private var funGreeting: String = ""
    @State private var selectedQuickAction: Int? = nil

    private let checklistService = ChecklistService()

    private let funGreetings = [
        "Let's make today count.",
        "One step at a time, champ.",
        "You've totally got this.",
        "Small steps, big wins.",
        "Progress looks great on you.",
        "You showed up. That's huge.",
        "Your future self says thanks.",
        "Let's check something off today.",
        "Every step forward matters.",
        "You're doing better than you think.",
        "Ready to crush it?",
        "Look at you, showing up again.",
    ]

    var body: some View {
        NavigationStack {
            ZStack {
                // Warm gradient background
                LinearGradient(
                    colors: [Color(hex: "FAF7F2"), Color(hex: "F5F0EA")],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        // Fun greeting - BIG bold display font
                        HStack {
                            VStack(alignment: .leading, spacing: 6) {
                                if let user = appState.user {
                                    Text("Hey, \(user.displayName ?? "there") 👋")
                                        .font(.lumeDisplayMedium)
                                        .foregroundColor(.lumeNavy)
                                }

                                Text(funGreeting)
                                    .font(.lumeBodyLight)
                                    .foregroundColor(.lumeAccent)
                                    .italic()
                            }

                            Spacer()

                            // Avatar
                            if let user = appState.user {
                                ZStack {
                                    Circle()
                                        .fill(Color.lumeGreen.opacity(0.15))
                                        .frame(width: 42, height: 42)
                                    Text(String((user.displayName ?? user.email).prefix(1)).uppercased())
                                        .font(.lumeBodySemibold)
                                        .foregroundColor(.lumeGreen)
                                }
                            }
                        }
                        .padding(.horizontal, 24)
                        .padding(.top, 20)

                        // Active Transition Card
                        if let transition = appState.user?.transitionType {
                            ActiveTransitionCard(
                                transition: transition,
                                completed: checklistItems.filter(\.isCompleted).count,
                                total: checklistItems.count,
                                urgentCount: urgentTaskCount
                            )
                            .padding(.horizontal, 20)
                        }

                        // Quick Actions — colorful pills
                        VStack(alignment: .leading, spacing: 12) {
                            Text("QUICK ACTIONS")
                                .font(.lumeSmall)
                                .fontWeight(.semibold)
                                .foregroundColor(.lumeMuted)
                                .tracking(1)
                                .padding(.horizontal, 24)

                            LazyVGrid(columns: [
                                GridItem(.flexible(), spacing: 12),
                                GridItem(.flexible(), spacing: 12)
                            ], spacing: 12) {
                                QuickActionPill(
                                    icon: "checkmark",
                                    label: "My Checklist",
                                    bgColor: Color.lumeGreen.opacity(0.1),
                                    iconColor: .lumeGreen,
                                    action: { selectedQuickAction = 1 }
                                )
                                QuickActionPill(
                                    icon: "book.fill",
                                    label: "Guides",
                                    bgColor: Color.lumeAccent.opacity(0.1),
                                    iconColor: .lumeAccent,
                                    action: { selectedQuickAction = 2 }
                                )
                                QuickActionPill(
                                    icon: "folder.fill",
                                    label: "My Files",
                                    bgColor: Color.lumeNavy.opacity(0.08),
                                    iconColor: .lumeNavy,
                                    action: { selectedQuickAction = 3 }
                                )
                                QuickActionPill(
                                    icon: "sun.max.fill",
                                    label: "Resources",
                                    bgColor: Color.lumeGold.opacity(0.12),
                                    iconColor: .lumeGold,
                                    action: {}
                                )
                            }
                            .padding(.horizontal, 20)
                        }

                        // Today's Focus - sage green card
                        if let nextTask = checklistItems.first(where: { !$0.isCompleted }) {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("TODAY'S FOCUS")
                                    .font(.lumeSmall)
                                    .fontWeight(.semibold)
                                    .foregroundColor(.lumeMuted)
                                    .tracking(1)
                                    .padding(.horizontal, 24)

                                TodayFocusCard(task: nextTask)
                                    .padding(.horizontal, 20)
                            }
                        }

                        // Upcoming deadlines
                        if let deadlines = appState.dashboardData?.deadlines,
                           !deadlines.isEmpty {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("DEADLINES")
                                    .font(.lumeSmall)
                                    .fontWeight(.semibold)
                                    .foregroundColor(.lumeMuted)
                                    .tracking(1)
                                    .padding(.horizontal, 24)

                                DeadlineSection(deadlines: Array(deadlines.prefix(3)))
                                    .padding(.horizontal, 20)
                            }
                        }

                        Spacer().frame(height: 100)
                    }
                }
            }
            .navigationBarHidden(true)
            .refreshable {
                await appState.loadDashboard()
                await loadChecklist()
                funGreeting = funGreetings.randomElement() ?? ""
            }
            .task {
                await loadChecklist()
                funGreeting = funGreetings.randomElement() ?? ""
            }
            .onChange(of: selectedQuickAction) { _, tab in
                if let tab = tab {
                    NotificationCenter.default.post(name: .switchToTab, object: nil, userInfo: ["tab": tab])
                    selectedQuickAction = nil
                }
            }
        }
    }

    private var urgentTaskCount: Int {
        let incomplete = checklistItems.filter { !$0.isCompleted }
        guard let phase = incomplete.first?.phase else { return 0 }
        return incomplete.filter { $0.phase == phase }.count
    }

    private func loadChecklist() async {
        do {
            let response = try await checklistService.getChecklist()
            checklistItems = response.items
        } catch {}
    }
}

// MARK: - Active Transition Card

struct ActiveTransitionCard: View {
    let transition: String
    let completed: Int
    let total: Int
    let urgentCount: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 6) {
                    Text("YOUR JOURNEY")
                        .font(.lumeSmall)
                        .foregroundColor(.white.opacity(0.5))
                        .tracking(1)

                    Text(transition.replacingOccurrences(of: "-", with: " ").capitalized)
                        .font(.lumeDisplaySmall)
                        .foregroundColor(.white)
                }

                Spacer()

                // Sun-like progress circle
                ZStack {
                    Circle()
                        .stroke(Color.white.opacity(0.15), lineWidth: 3)
                        .frame(width: 52, height: 52)

                    Circle()
                        .trim(from: 0, to: total > 0 ? CGFloat(completed) / CGFloat(total) : 0)
                        .stroke(Color.lumeGold, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                        .frame(width: 52, height: 52)
                        .rotationEffect(.degrees(-90))

                    VStack(spacing: 0) {
                        Text("\(completed)")
                            .font(.lumeBodySemibold)
                            .foregroundColor(.white)
                        Text("of \(total)")
                            .font(.system(size: 9))
                            .foregroundColor(.white.opacity(0.6))
                    }
                }
            }

            // Green progress bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.white.opacity(0.15))
                        .frame(height: 5)

                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.lumeGreen)
                        .frame(width: total > 0 ? geo.size.width * CGFloat(completed) / CGFloat(total) : 0, height: 5)
                }
            }
            .frame(height: 5)

            HStack {
                if urgentCount > 0 {
                    Text("\(urgentCount) urgent task\(urgentCount == 1 ? "" : "s")")
                        .font(.lumeSmall)
                        .foregroundColor(.lumeGreen)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(Color.lumeGreen.opacity(0.15))
                        .cornerRadius(10)
                }
                Spacer()
                HStack(spacing: 4) {
                    Text("View all")
                        .font(.lumeSmall)
                        .foregroundColor(.white.opacity(0.6))
                    Image(systemName: "chevron.right")
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.4))
                }
            }
        }
        .padding(22)
        .background(
            RoundedRectangle(cornerRadius: 20)
                .fill(
                    LinearGradient(
                        colors: [Color.lumeNavy, Color(hex: "1E3A4C")],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
        )
    }
}

// MARK: - Quick Action Pill (colorful)

struct QuickActionPill: View {
    let icon: String
    let label: String
    let bgColor: Color
    let iconColor: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(iconColor)
                Text(label)
                    .font(.lumeCaption)
                    .fontWeight(.medium)
                    .foregroundColor(.lumeNavy)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(bgColor)
            .cornerRadius(14)
        }
    }
}

// MARK: - Today's Focus Card

struct TodayFocusCard: View {
    let task: FullChecklistItem

    var body: some View {
        HStack(spacing: 14) {
            ZStack {
                Circle()
                    .fill(Color.lumeAccent.opacity(0.12))
                    .frame(width: 38, height: 38)
                Image(systemName: "exclamationmark")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.lumeAccent)
            }

            VStack(alignment: .leading, spacing: 3) {
                Text(task.title)
                    .font(.lumeBodyMedium)
                    .foregroundColor(.lumeNavy)

                if let phase = task.phase {
                    Text(phase)
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)
                }
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.lumeMuted)
        }
        .padding(16)
        .background(Color.lumeAccent.opacity(0.06))
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.lumeAccent.opacity(0.12), lineWidth: 1)
        )
    }
}

// MARK: - Deadline Section

struct DeadlineSection: View {
    let deadlines: [Deadline]

    var body: some View {
        VStack(spacing: 10) {
            ForEach(deadlines, id: \.id) { deadline in
                HStack(spacing: 12) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(urgencyColor(deadline))
                        .frame(width: 4, height: 32)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(deadline.title ?? "")
                            .font(.lumeCaption)
                            .foregroundColor(.lumeNavy)
                        if let days = deadline.daysRemaining {
                            Text(deadlineText(days))
                                .font(.lumeSmall)
                                .foregroundColor(days <= 3 ? .lumeAccent : .lumeMuted)
                        }
                    }
                    Spacer()
                }
                .padding(14)
                .background(Color.lumeWarmWhite)
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.lumeBorder, lineWidth: 1)
                )
            }
        }
    }

    private func deadlineText(_ days: Int) -> String {
        if days < 0 { return "This was due \(abs(days)) day\(abs(days) == 1 ? "" : "s") ago" }
        if days == 0 { return "Due today" }
        if days <= 3 { return "Due in \(days) day\(days == 1 ? "" : "s")" }
        return "You have \(days) days left"
    }

    private func urgencyColor(_ deadline: Deadline) -> Color {
        guard let days = deadline.daysRemaining else { return .lumeMuted }
        if days <= 3 { return .lumeAccent }
        if days <= 14 { return .lumeGold }
        return .lumeGreen
    }
}
