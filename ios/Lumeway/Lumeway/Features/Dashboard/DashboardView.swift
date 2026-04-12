import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var appState: AppState
    @State private var checklistItems: [FullChecklistItem] = []
    @State private var funGreeting: String = ""
    @State private var selectedQuickAction: Int? = nil
    @State private var showChat = false

    private let checklistService = ChecklistService()

    private let funGreetings = [
        "Let's make today count.",
        "One step at a time.",
        "You've totally got this.",
        "Small steps, big wins.",
        "Progress looks great on you.",
        "You showed up. That's huge.",
        "Your future self says thanks.",
        "Let's check something off today.",
        "Every step forward matters.",
        "You're doing better than you think.",
        "Look at you, showing up again.",
    ]

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
                    VStack(spacing: 22) {
                        // Greeting header
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 4) {
                                if let user = appState.user {
                                    Text("Hey, \(user.displayName ?? "there")")
                                        .font(.lumeDisplayMedium)
                                        .foregroundColor(.lumeNavy)
                                }

                                Text(funGreeting)
                                    .font(.custom("CormorantGaramond-Italic", size: 16))
                                    .foregroundColor(.lumeAccent)
                            }

                            Spacer()

                            // Refresh button
                            Button {
                                Task {
                                    await appState.loadDashboard()
                                    await loadChecklist()
                                }
                            } label: {
                                Image(systemName: "arrow.triangle.2.circlepath")
                                    .font(.system(size: 16, weight: .medium))
                                    .foregroundColor(.lumeMuted)
                                    .padding(8)
                            }

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

                        // Journey progress card
                        JourneyCard(
                            completed: checklistItems.filter(\.isCompleted).count,
                            total: checklistItems.count,
                            thisWeekTasks: thisWeekTasks
                        )
                        .padding(.horizontal, 20)

                        // This week's tasks
                        if !thisWeekTasks.isEmpty {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("This Week")
                                    .font(.lumeSectionTitle)
                                    .foregroundColor(.lumeNavy)
                                    .padding(.horizontal, 24)

                                ForEach(thisWeekTasks.prefix(4)) { task in
                                    ThisWeekTaskRow(task: task) {
                                        toggleTask(task)
                                    }
                                    .padding(.horizontal, 20)
                                }
                            }
                        }

                        // Quick links — 2x3 grid linking to everything
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Your Tools")
                                .font(.lumeSectionTitle)
                                .foregroundColor(.lumeNavy)
                                .padding(.horizontal, 24)

                            LazyVGrid(columns: [
                                GridItem(.flexible(), spacing: 12),
                                GridItem(.flexible(), spacing: 12),
                                GridItem(.flexible(), spacing: 12)
                            ], spacing: 12) {
                                // Tab-based navigation
                                QuickLinkTile(
                                    icon: "checklist",
                                    label: "Checklist",
                                    color: .lumeGreen
                                ) { selectedQuickAction = 1 }

                                QuickLinkTile(
                                    icon: "bubble.left.and.bubble.right",
                                    label: "Community",
                                    color: .lumeAccent
                                ) { selectedQuickAction = 2 }

                                QuickLinkTile(
                                    icon: "message",
                                    label: "Chat",
                                    color: .lumeNavy
                                ) { selectedQuickAction = 3 }

                                // Direct NavigationLink to actual pages
                                NavigationLink { CalendarView() } label: {
                                    QuickLinkContent(icon: "calendar", label: "Calendar", color: .lumeGold)
                                }

                                NavigationLink { NotesView() } label: {
                                    QuickLinkContent(icon: "pencil.line", label: "Notes", color: Color(hex: "5E8C9A"))
                                }

                                NavigationLink { GuidesView() } label: {
                                    QuickLinkContent(icon: "book", label: "Guides", color: .lumeGold)
                                }

                                NavigationLink { FilesView() } label: {
                                    QuickLinkContent(icon: "folder", label: "Files", color: Color(hex: "7B6B8D"))
                                }

                                NavigationLink { ActivityLogView() } label: {
                                    QuickLinkContent(icon: "note.text", label: "Activity", color: .lumeGreen)
                                }

                                NavigationLink { MoreView() } label: {
                                    QuickLinkContent(icon: "person", label: "Profile", color: Color(hex: "7B6B8D"))
                                }
                            }
                            .padding(.horizontal, 20)
                        }

                        // Upcoming deadlines
                        if let deadlines = appState.dashboardData?.deadlines,
                           !deadlines.isEmpty {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Deadlines")
                                    .font(.lumeSectionTitle)
                                    .foregroundColor(.lumeNavy)
                                    .padding(.horizontal, 24)

                                DeadlineSection(deadlines: Array(deadlines.prefix(3)))
                                    .padding(.horizontal, 20)
                            }
                        }

                        // Today's Focus — taps to switch to Checklist tab
                        if let nextTask = checklistItems.first(where: { !$0.isCompleted }) {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Next Up")
                                    .font(.lumeSectionTitle)
                                    .foregroundColor(.lumeNavy)
                                    .padding(.horizontal, 24)

                                Button {
                                    NotificationCenter.default.post(name: .navigateToChecklist, object: nil)
                                } label: {
                                    TodayFocusCard(task: nextTask)
                                }
                                .buttonStyle(.plain)
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
                snapshotTasks = [] // Reset snapshot on appear
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

    /// Tasks in current phase — includes recently checked items so they don't vanish
    private var thisWeekTasks: [FullChecklistItem] {
        // If we have snapshotted tasks from initial load, show those
        if !snapshotTasks.isEmpty { return snapshotTasks }
        let incomplete = checklistItems.filter { !$0.isCompleted }
        guard let currentPhase = incomplete.first?.phase else { return [] }
        return checklistItems.filter { $0.phase == currentPhase }
    }

    @State private var snapshotTasks: [FullChecklistItem] = []

    private func toggleTask(_ task: FullChecklistItem) {
        Task {
            do {
                _ = try await checklistService.toggleItem(id: task.id)
                // Reload data but keep snapshot so tasks stay visible
                let response = try await checklistService.getChecklist()
                checklistItems = response.items
                // Update snapshot: find same phase, show all items (completed stay visible)
                if snapshotTasks.isEmpty {
                    // First toggle — snapshot the current phase tasks
                    let phase = task.phase
                    snapshotTasks = checklistItems.filter { $0.phase == phase }
                } else {
                    // Update existing snapshot with new completion states
                    let phase = snapshotTasks.first?.phase
                    snapshotTasks = checklistItems.filter { $0.phase == phase }
                }
            } catch {}
        }
    }

    private func loadChecklist() async {
        do {
            let response = try await checklistService.getChecklist()
            checklistItems = response.items
        } catch {}
    }
}

// MARK: - Journey Card (replaces ActiveTransitionCard)

struct JourneyCard: View {
    let completed: Int
    let total: Int
    let thisWeekTasks: [FullChecklistItem]

    private var progress: CGFloat {
        total > 0 ? CGFloat(completed) / CGFloat(total) : 0
    }

    private var percentage: Int {
        Int(progress * 100)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Hero title
            Text("Your Journey")
                .font(.lumeHeadingMedium)
                .foregroundColor(.white)

            // Progress circle + stats
            HStack(spacing: 20) {
                // Circular progress
                ZStack {
                    Circle()
                        .stroke(Color.white.opacity(0.12), lineWidth: 5)
                        .frame(width: 72, height: 72)

                    Circle()
                        .trim(from: 0, to: progress)
                        .stroke(
                            LinearGradient(
                                colors: [.lumeGold, .lumeAccent],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            ),
                            style: StrokeStyle(lineWidth: 5, lineCap: .round)
                        )
                        .frame(width: 72, height: 72)
                        .rotationEffect(.degrees(-90))

                    Text("\(percentage)%")
                        .font(.lumeBodySemibold)
                        .foregroundColor(.white)
                }

                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 6) {
                        Text("\(completed)")
                            .font(.lumeHeadingSmall)
                            .foregroundColor(.white)
                        Text("of \(total) tasks done")
                            .font(.lumeCaptionLight)
                            .foregroundColor(.white.opacity(0.6))
                    }

                    if !thisWeekTasks.isEmpty {
                        Text("\(thisWeekTasks.count) task\(thisWeekTasks.count == 1 ? "" : "s") this week")
                            .font(.lumeSmall)
                            .foregroundColor(.lumeGreen)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(Color.lumeGreen.opacity(0.15))
                            .cornerRadius(8)
                    }
                }

                Spacer()
            }

            // Progress bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.white.opacity(0.12))
                        .frame(height: 4)

                    RoundedRectangle(cornerRadius: 3)
                        .fill(
                            LinearGradient(
                                colors: [.lumeGold, .lumeGreen],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: geo.size.width * progress, height: 4)
                }
            }
            .frame(height: 4)
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

// MARK: - This Week Task Row

struct ThisWeekTaskRow: View {
    let task: FullChecklistItem
    let onToggle: () -> Void

    var body: some View {
        HStack(spacing: 14) {
            Button(action: onToggle) {
                ZStack {
                    Circle()
                        .stroke(task.isCompleted ? Color.lumeGreen : Color.lumeBorder, lineWidth: 2)
                        .frame(width: 22, height: 22)
                    if task.isCompleted {
                        Image(systemName: "checkmark")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(.lumeGreen)
                    }
                }
            }

            Text(task.title)
                .font(.lumeBody)
                .foregroundColor(task.isCompleted ? .lumeMuted : .lumeNavy)
                .strikethrough(task.isCompleted)
                .lineLimit(2)

            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 13)
        .background(Color.lumeWarmWhite)
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.lumeBorder, lineWidth: 1)
        )
    }
}

// MARK: - Quick Link Tile (compact 3-column)

struct QuickLinkTile: View {
    let icon: String
    let label: String
    let color: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10)
                        .fill(color.opacity(0.1))
                        .frame(width: 36, height: 36)
                    Image(systemName: icon)
                        .font(.system(size: 15))
                        .foregroundColor(color)
                }

                Text(label)
                    .font(.lumeSmall)
                    .foregroundColor(.lumeNavy)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(Color.lumeWarmWhite)
            .cornerRadius(14)
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(Color.lumeBorder, lineWidth: 1)
            )
        }
    }
}

// MARK: - Quick Link Content (for NavigationLink labels)

struct QuickLinkContent: View {
    let icon: String
    let label: String
    let color: Color

    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                RoundedRectangle(cornerRadius: 10)
                    .fill(color.opacity(0.1))
                    .frame(width: 36, height: 36)
                Image(systemName: icon)
                    .font(.system(size: 15))
                    .foregroundColor(color)
            }

            Text(label)
                .font(.lumeSmall)
                .foregroundColor(.lumeNavy)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
        .background(Color.lumeWarmWhite)
        .cornerRadius(14)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.lumeBorder, lineWidth: 1)
        )
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
                Image(systemName: "arrow.right")
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
