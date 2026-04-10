import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var appState: AppState
    @State private var checklistItems: [FullChecklistItem] = []

    private let checklistService = ChecklistService()

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 24) {
                        // Greeting
                        if let user = appState.user {
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(greeting)
                                        .font(.lumeCaptionLight)
                                        .foregroundColor(.lumeMuted)
                                    Text(user.displayName ?? "there")
                                        .font(.lumeHeadingSmall)
                                        .foregroundColor(.lumeText)
                                }
                                Spacer()
                            }
                            .padding(.horizontal, 24)
                            .padding(.top, 16)
                        }

                        // Progress summary card
                        if let stats = appState.dashboardData?.checklist {
                            ProgressCard(stats: stats)
                                .padding(.horizontal, 24)
                        }

                        // Next task highlight
                        if let nextTask = checklistItems.first(where: { !$0.isCompleted }) {
                            NextTaskCard(task: nextTask)
                                .padding(.horizontal, 24)
                        }

                        // Upcoming deadlines
                        if let deadlines = appState.dashboardData?.deadlines,
                           !deadlines.isEmpty {
                            DeadlineSection(deadlines: Array(deadlines.prefix(3)))
                                .padding(.horizontal, 24)
                        }

                        // Recent chat sessions
                        if let sessions = appState.dashboardData?.sessions,
                           !sessions.isEmpty {
                            RecentChatsSection(sessions: Array(sessions.prefix(3)))
                                .padding(.horizontal, 24)
                        }

                        Spacer().frame(height: 32)
                    }
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Text("LUMEWAY")
                        .font(.lumeLogoText)
                        .foregroundColor(.lumeNavy)
                }
            }
            .refreshable {
                await appState.loadDashboard()
                await loadChecklist()
            }
            .task { await loadChecklist() }
        }
    }

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        if hour < 12 { return "Good morning," }
        if hour < 17 { return "Good afternoon," }
        return "Good evening,"
    }

    private func loadChecklist() async {
        do {
            let response = try await checklistService.getChecklist()
            checklistItems = response.items
        } catch {
            // Silently fail — dashboard still works without checklist
        }
    }
}

// MARK: - Progress Card

struct ProgressCard: View {
    let stats: ChecklistStats

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text("Your progress")
                    .font(.lumeBodyMedium)
                    .foregroundColor(.lumeText)
                Spacer()
                Text("\(stats.completed ?? 0) of \(stats.total ?? 0)")
                    .font(.lumeCaption)
                    .foregroundColor(.lumeMuted)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.lumeBorder)
                        .frame(height: 8)

                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.lumeGold)
                        .frame(width: progressWidth(total: geo.size.width), height: 8)
                        .animation(.easeInOut(duration: 0.5), value: stats.completed)
                }
            }
            .frame(height: 8)
        }
        .padding(20)
        .background(Color.lumeWarmWhite)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.lumeBorder, lineWidth: 1)
        )
    }

    private func progressWidth(total: CGFloat) -> CGFloat {
        let done = stats.completed ?? 0
        let all = stats.total ?? 1
        guard all > 0 else { return 0 }
        return total * CGFloat(done) / CGFloat(all)
    }
}

// MARK: - Next Task Card

struct NextTaskCard: View {
    let task: FullChecklistItem

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "arrow.right.circle.fill")
                    .font(.system(size: 14))
                    .foregroundColor(.lumeGold)
                Text("Next step")
                    .font(.lumeSmall)
                    .foregroundColor(.lumeGold)
            }

            Text(task.title)
                .font(.lumeBodyMedium)
                .foregroundColor(.lumeText)

            if let phase = task.phase {
                Text(phase)
                    .font(.lumeSmall)
                    .foregroundColor(.lumeMuted)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Color.lumeGold.opacity(0.06))
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.lumeGold.opacity(0.3), lineWidth: 1)
        )
    }
}

// MARK: - Deadline Section

struct DeadlineSection: View {
    let deadlines: [Deadline]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Upcoming deadlines")
                .font(.lumeBodyMedium)
                .foregroundColor(.lumeText)

            ForEach(deadlines, id: \.id) { deadline in
                HStack(spacing: 12) {
                    Circle()
                        .fill(urgencyColor(deadline))
                        .frame(width: 8, height: 8)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(deadline.title ?? "")
                            .font(.lumeCaption)
                            .foregroundColor(.lumeText)
                        if let days = deadline.daysRemaining {
                            Text("You have \(days) day\(days == 1 ? "" : "s") left")
                                .font(.lumeSmall)
                                .foregroundColor(.lumeMuted)
                        }
                    }
                    Spacer()
                }
                .padding(16)
                .background(Color.lumeWarmWhite)
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.lumeBorder, lineWidth: 1)
                )
            }
        }
    }

    private func urgencyColor(_ deadline: Deadline) -> Color {
        guard let days = deadline.daysRemaining else { return .lumeMuted }
        if days <= 7 { return .lumeAccent }
        if days <= 14 { return .lumeGold }
        return .lumeGreen
    }
}

// MARK: - Recent Chats Section

struct RecentChatsSection: View {
    let sessions: [ChatSessionSummary]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Recent conversations")
                .font(.lumeBodyMedium)
                .foregroundColor(.lumeText)

            ForEach(sessions) { session in
                HStack(spacing: 12) {
                    Image(systemName: "bubble.left")
                        .font(.system(size: 16))
                        .foregroundColor(.lumeNavy)

                    VStack(alignment: .leading, spacing: 2) {
                        if let cat = session.transitionCategory {
                            Text(cat.replacingOccurrences(of: "-", with: " ").capitalized)
                                .font(.lumeCaption)
                                .foregroundColor(.lumeText)
                        }
                        if let count = session.messageCount {
                            Text("\(count) messages")
                                .font(.lumeSmall)
                                .foregroundColor(.lumeMuted)
                        }
                    }
                    Spacer()
                }
                .padding(12)
                .background(Color.lumeWarmWhite)
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.lumeBorder, lineWidth: 1)
                )
            }
        }
    }
}
