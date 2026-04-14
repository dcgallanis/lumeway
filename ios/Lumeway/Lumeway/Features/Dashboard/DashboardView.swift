import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var appState: AppState
    @State private var checklistItems: [FullChecklistItem] = []
    @State private var showChat = false
    @State private var isRefreshing = false
    @State private var showEditQuickLinks = false
    @State private var directGoals: [GoalItem] = []
    @AppStorage("quickLinkPages") private var quickLinkPagesRaw: String = "checklist,calendar,guides"

    private let checklistService = ChecklistService()
    private let goalService = GoalService()

    private var quickLinkPages: [NavPage] {
        let keys = quickLinkPagesRaw.split(separator: ",").map(String.init)
        return keys.compactMap { NavPage(rawValue: $0) }
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
                    VStack(spacing: 22) {
                        // ── Motivational navy card (includes refresh + profile) ──
                        MotivationCard(
                            userName: appState.user?.displayName ?? "there",
                            userInitial: String((appState.user?.displayName ?? appState.user?.email ?? "U").prefix(1)).uppercased(),
                            completedThisWeek: thisWeekTasks.filter(\.isCompleted).count,
                            totalThisWeek: thisWeekTasks.count,
                            allCompleted: checklistItems.filter(\.isCompleted).count,
                            allTotal: checklistItems.count,
                            isRefreshing: isRefreshing,
                            onRefresh: {
                                Task {
                                    isRefreshing = true
                                    await appState.loadDashboard()
                                    await loadChecklist()
                                    await loadGoals()
                                    isRefreshing = false
                                }
                            },
                            profileDestination: { MoreView(isEmbedded: true) }
                        )
                        .padding(.horizontal, 20)
                        .padding(.top, 12)

                        // ── Checklist section ──
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text("Checklist")
                                    .font(.lumeSectionTitle)
                                    .foregroundColor(.lumeNavy)
                                Spacer()
                                NavigationLink {
                                    ChecklistView(isEmbedded: true)
                                } label: {
                                    Text("View all")
                                        .font(.lumeSmall)
                                        .foregroundColor(.lumeAccent)
                                }
                            }
                            .padding(.horizontal, 24)

                            if thisWeekTasks.isEmpty {
                                HStack(spacing: 12) {
                                    Image(systemName: "checkmark.seal.fill")
                                        .font(.system(size: 20))
                                        .foregroundColor(.lumeGreen)
                                    Text("You're all caught up. Nice work.")
                                        .font(.lumeBody)
                                        .foregroundColor(.lumeMuted)
                                    Spacer()
                                }
                                .padding(.horizontal, 16)
                                .padding(.vertical, 14)
                                .background(Color.lumeGreen.opacity(0.06))
                                .cornerRadius(12)
                                .padding(.horizontal, 20)
                            } else {
                                ForEach(thisWeekTasks.prefix(4)) { task in
                                    ThisWeekTaskRow(task: task, onToggle: { toggleTask(task) })
                                        .padding(.horizontal, 20)
                                }
                            }
                        }

                        // ── Quick Links — labeled grid, customizable ──
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text("Quick Links")
                                    .font(.lumeSectionTitle)
                                    .foregroundColor(.lumeNavy)
                                Spacer()
                                Button {
                                    showEditQuickLinks = true
                                } label: {
                                    Image(systemName: "pencil")
                                        .font(.system(size: 12, weight: .medium))
                                        .foregroundColor(.lumeAccent)
                                        .padding(6)
                                        .background(Color.lumeAccent.opacity(0.08))
                                        .cornerRadius(8)
                                }
                            }
                            .padding(.horizontal, 24)

                            LazyVGrid(columns: [
                                GridItem(.flexible(), spacing: 12),
                                GridItem(.flexible(), spacing: 12),
                                GridItem(.flexible(), spacing: 12)
                            ], spacing: 12) {
                                ForEach(quickLinkPages) { page in
                                    NavigationLink {
                                        page.embeddedDestination
                                    } label: {
                                        QuickLinkContent(icon: page.icon, label: page.label, color: page.color)
                                    }
                                }
                            }
                            .padding(.horizontal, 20)
                        }

                        // ── Your Goals ──
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text("Your Goals")
                                    .font(.lumeSectionTitle)
                                    .foregroundColor(.lumeNavy)
                                Spacer()
                                NavigationLink {
                                    GoalsView(isEmbedded: true)
                                } label: {
                                    Text("Manage")
                                        .font(.lumeSmall)
                                        .foregroundColor(.lumeAccent)
                                }
                            }
                            .padding(.horizontal, 24)

                            if hasGoals {
                                // Show actual goals from either source
                                if !directGoals.isEmpty {
                                    ForEach(directGoals) { goal in
                                        HStack(spacing: 12) {
                                            Image(systemName: goal.isCompleted ? "checkmark.circle.fill" : "circle")
                                                .font(.system(size: 18))
                                                .foregroundColor(goal.isCompleted ? .lumeGreen : .lumeGold)
                                            VStack(alignment: .leading, spacing: 2) {
                                                Text(goal.title)
                                                    .font(.lumeBody)
                                                    .foregroundColor(goal.isCompleted ? .lumeMuted : .lumeNavy)
                                                    .strikethrough(goal.isCompleted)
                                                if !goal.timeframe.isEmpty {
                                                    Text(goal.timeframe.capitalized)
                                                        .font(.lumeSmall)
                                                        .foregroundColor(.lumeMuted)
                                                }
                                            }
                                            Spacer()
                                        }
                                        .padding(.horizontal, 16)
                                        .padding(.vertical, 12)
                                        .background(Color.lumeWarmWhite)
                                        .cornerRadius(12)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 12)
                                                .stroke(Color.lumeBorder, lineWidth: 1)
                                        )
                                        .padding(.horizontal, 20)
                                    }
                                } else if let goals = appState.dashboardData?.goals {
                                    ForEach(goals) { goal in
                                        HStack(spacing: 12) {
                                            Image(systemName: goal.isCompleted == true ? "checkmark.circle.fill" : "circle")
                                                .font(.system(size: 18))
                                                .foregroundColor(goal.isCompleted == true ? .lumeGreen : .lumeGold)
                                            VStack(alignment: .leading, spacing: 2) {
                                                Text(goal.title ?? "")
                                                    .font(.lumeBody)
                                                    .foregroundColor(goal.isCompleted == true ? .lumeMuted : .lumeNavy)
                                                    .strikethrough(goal.isCompleted == true)
                                                if let tf = goal.timeframe, !tf.isEmpty {
                                                    Text(tf.capitalized)
                                                        .font(.lumeSmall)
                                                        .foregroundColor(.lumeMuted)
                                                }
                                            }
                                            Spacer()
                                        }
                                        .padding(.horizontal, 16)
                                        .padding(.vertical, 12)
                                        .background(Color.lumeWarmWhite)
                                        .cornerRadius(12)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 12)
                                                .stroke(Color.lumeBorder, lineWidth: 1)
                                        )
                                        .padding(.horizontal, 20)
                                    }
                                }
                            } else {
                                NavigationLink {
                                    GoalsView(isEmbedded: true)
                                } label: {
                                    HStack(spacing: 10) {
                                        Image(systemName: "plus.circle.fill")
                                            .font(.system(size: 18))
                                        Text("Set your own goal")
                                            .font(.lumeBodyMedium)
                                    }
                                    .foregroundColor(.lumeAccent)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 16)
                                    .background(Color.lumeAccent.opacity(0.06))
                                    .cornerRadius(14)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 14)
                                            .stroke(Color.lumeAccent.opacity(0.15), lineWidth: 1)
                                    )
                                    .padding(.horizontal, 20)
                                }
                            }
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

                        Spacer().frame(height: 100)
                    }
                }
            }
            .navigationBarHidden(true)
            .sheet(isPresented: $showEditQuickLinks) {
                EditQuickLinksSheet(quickLinkPagesRaw: $quickLinkPagesRaw)
                    .presentationDetents([.medium, .large])
            }
            .refreshable {
                await appState.loadDashboard()
                await loadChecklist()
                await loadGoals()
            }
            .task {
                snapshotTasks = [] // Reset snapshot on appear
                await loadChecklist()
                await loadGoals()
            }
        }
    }

    /// Whether the user has any goals from either data source
    private var hasGoals: Bool {
        if !directGoals.isEmpty { return true }
        if let goals = appState.dashboardData?.goals, !goals.isEmpty { return true }
        return false
    }

    /// Tasks in current phase — includes recently checked items so they don't vanish
    private var thisWeekTasks: [FullChecklistItem] {
        // If we have snapshotted tasks from initial load, show those
        if !snapshotTasks.isEmpty { return snapshotTasks }
        let incomplete = checklistItems.filter { !$0.isCompleted }
        guard let currentPhase = incomplete.first?.phase else { return [] }
        return incomplete.filter { $0.phase == currentPhase }
    }

    @State private var snapshotTasks: [FullChecklistItem] = []

    private func toggleTask(_ task: FullChecklistItem) {
        Task {
            do {
                // Snapshot which task IDs are currently visible BEFORE toggling
                if snapshotTasks.isEmpty {
                    snapshotTasks = thisWeekTasks
                }
                let visibleIds = Set(snapshotTasks.map(\.id))

                _ = try await checklistService.toggleItem(id: task.id)
                let response = try await checklistService.getChecklist()
                checklistItems = response.items

                // Update snapshot: only include tasks that were already showing
                snapshotTasks = checklistItems.filter { visibleIds.contains($0.id) }
            } catch {}
        }
    }

    private func loadChecklist() async {
        do {
            let response = try await checklistService.getChecklist()
            checklistItems = response.items
        } catch {}
    }

    private func loadGoals() async {
        do {
            let response = try await goalService.getGoals()
            directGoals = response.goals
        } catch {}
    }
}

// MARK: - Week at a Glance Card

struct WeekAtGlanceCard: View {
    let tasks: [FullChecklistItem]
    let allCompleted: Int
    let allTotal: Int
    let onToggle: (FullChecklistItem) -> Void

    private var weekCompleted: Int {
        tasks.filter(\.isCompleted).count
    }

    private var weekProgress: CGFloat {
        tasks.isEmpty ? 0 : CGFloat(weekCompleted) / CGFloat(tasks.count)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Your Week")
                        .font(.lumeHeadingMedium)
                        .foregroundColor(.white)

                    if tasks.isEmpty {
                        Text("You're all caught up")
                            .font(.lumeCaption)
                            .foregroundColor(.white.opacity(0.5))
                    } else {
                        Text("\(weekCompleted) of \(tasks.count) done this week")
                            .font(.lumeCaption)
                            .foregroundColor(.white.opacity(0.6))
                    }
                }
                Spacer()

                // Small overall badge
                if allTotal > 0 {
                    VStack(spacing: 2) {
                        Text("\(allCompleted)/\(allTotal)")
                            .font(.lumeSmall)
                            .fontWeight(.medium)
                            .foregroundColor(.white)
                        Text("overall")
                            .font(.system(size: 9))
                            .foregroundColor(.white.opacity(0.4))
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color.white.opacity(0.1))
                    .cornerRadius(10)
                }
            }

            // Weekly progress bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.white.opacity(0.12))
                        .frame(height: 6)

                    RoundedRectangle(cornerRadius: 4)
                        .fill(
                            LinearGradient(
                                colors: [.lumeGold, .lumeGreen],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: geo.size.width * weekProgress, height: 6)
                }
            }
            .frame(height: 6)

            // Task list (max 4)
            if !tasks.isEmpty {
                VStack(spacing: 8) {
                    ForEach(tasks.prefix(4)) { task in
                        HStack(spacing: 12) {
                            Button {
                                onToggle(task)
                            } label: {
                                ZStack {
                                    Circle()
                                        .stroke(task.isCompleted ? Color.lumeGreen : Color.white.opacity(0.3), lineWidth: 1.5)
                                        .frame(width: 22, height: 22)
                                    if task.isCompleted {
                                        Image(systemName: "checkmark")
                                            .font(.system(size: 10, weight: .bold))
                                            .foregroundColor(.lumeGreen)
                                    }
                                }
                            }

                            Text(task.title)
                                .font(.lumeCaption)
                                .foregroundColor(task.isCompleted ? .white.opacity(0.4) : .white.opacity(0.85))
                                .strikethrough(task.isCompleted, color: .white.opacity(0.3))
                                .lineLimit(1)

                            Spacer()
                        }
                    }
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

// MARK: - Motivation Card (navy, personalized encouragement + circular progress)

struct MotivationCard<Destination: View>: View {
    let userName: String
    let userInitial: String
    let completedThisWeek: Int
    let totalThisWeek: Int
    let allCompleted: Int
    let allTotal: Int
    let isRefreshing: Bool
    let onRefresh: () -> Void
    @ViewBuilder let profileDestination: () -> Destination

    // Rotating motivational sayings
    private static var sayings: [String] {
        [
            "You're doing better than you think.",
            "One step at a time. You've got this.",
            "Progress, not perfection.",
            "Every small win matters.",
            "Be kind to yourself today.",
            "You're building something new.",
            "Breathe. You're moving forward.",
            "Trust the process.",
            "Today is a fresh start.",
            "You don't have to figure it all out today.",
            "Courage looks different every day.",
            "You've already survived 100% of your hardest days.",
        ]
    }

    private var motivationalSaying: String {
        // Rotate based on day of year so it changes daily
        let day = Calendar.current.ordinality(of: .day, in: .year, for: Date()) ?? 0
        return Self.sayings[day % Self.sayings.count]
    }

    private var weekProgress: CGFloat {
        guard totalThisWeek > 0 else { return 0 }
        return CGFloat(completedThisWeek) / CGFloat(totalThisWeek)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Top row: greeting + refresh + profile
            HStack(alignment: .top) {
                Text("Hey, \(userName)")
                    .font(.custom("CormorantGaramond-Bold", size: 34))
                    .foregroundColor(.white)

                Spacer()

                // Refresh button
                Button(action: onRefresh) {
                    if isRefreshing {
                        ProgressView()
                            .tint(.white.opacity(0.6))
                            .frame(width: 32, height: 32)
                    } else {
                        Image(systemName: "arrow.triangle.2.circlepath")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.white.opacity(0.5))
                            .frame(width: 32, height: 32)
                    }
                }

                // Profile avatar
                NavigationLink {
                    profileDestination()
                } label: {
                    ZStack {
                        Circle()
                            .fill(Color.white.opacity(0.15))
                            .frame(width: 36, height: 36)
                        Text(userInitial)
                            .font(.custom("Montserrat-SemiBold", size: 14))
                            .foregroundColor(.white)
                    }
                }
            }

            Spacer().frame(height: 18)

            // Middle: circular progress + motivational saying
            HStack(spacing: 20) {
                // Circular progress ring
                ZStack {
                    Circle()
                        .stroke(Color.white.opacity(0.12), lineWidth: 5)
                        .frame(width: 72, height: 72)

                    Circle()
                        .trim(from: 0, to: weekProgress)
                        .stroke(
                            LinearGradient(
                                colors: [.lumeGold, .lumeGreen],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            ),
                            style: StrokeStyle(lineWidth: 5, lineCap: .round)
                        )
                        .frame(width: 72, height: 72)
                        .rotationEffect(.degrees(-90))

                    VStack(spacing: 1) {
                        Text("\(completedThisWeek)/\(totalThisWeek)")
                            .font(.custom("Montserrat-SemiBold", size: 15))
                            .foregroundColor(.white)
                        Text("this week")
                            .font(.custom("Montserrat-Regular", size: 9))
                            .foregroundColor(.white.opacity(0.45))
                    }
                }

                // Motivational saying in terracotta
                VStack(alignment: .leading, spacing: 6) {
                    Text(motivationalSaying)
                        .font(.custom("Montserrat-Medium", size: 15))
                        .foregroundColor(.lumeAccent)
                        .lineSpacing(4)
                        .fixedSize(horizontal: false, vertical: true)

                    if allTotal > 0 {
                        Text("\(allCompleted) of \(allTotal) overall")
                            .font(.custom("Montserrat-Regular", size: 12))
                            .foregroundColor(.white.opacity(0.4))
                    }
                }

                Spacer()
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 22)
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

// MARK: - Goal Suggestion Row

struct GoalSuggestionRow: View {
    let icon: String
    let text: String
    let color: Color

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundColor(color)
                .frame(width: 28, height: 28)
                .background(color.opacity(0.1))
                .cornerRadius(8)
            Text(text)
                .font(.lumeBody)
                .foregroundColor(.lumeMuted)
            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .background(Color.lumeWarmWhite)
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.lumeBorder, lineWidth: 1)
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

            NavigationLink {
                TaskDetailView(item: task, color: .lumeNavy)
            } label: {
                HStack {
                    Text(task.title)
                        .font(.lumeBody)
                        .foregroundColor(task.isCompleted ? .lumeMuted : .lumeNavy)
                        .strikethrough(task.isCompleted)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)

                    Spacer()

                    if !task.isCompleted {
                        Image(systemName: "chevron.right")
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(.lumeBorder)
                    }
                }
            }
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

// MARK: - Quick Link Content (for NavigationLink labels)

struct QuickLinkContent: View {
    let icon: String
    let label: String
    let color: Color
    var isLocked: Bool = false

    var body: some View {
        ZStack(alignment: .topTrailing) {
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

            if isLocked {
                Image(systemName: "lock.fill")
                    .font(.system(size: 8))
                    .foregroundColor(.lumeGold)
                    .padding(4)
                    .background(Color.lumeGold.opacity(0.12))
                    .cornerRadius(6)
                    .padding(6)
            }
        }
    }
}

// MARK: - Quick Link Icon (icon-only for dashboard)

struct QuickLinkIcon: View {
    let icon: String
    let color: Color

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 16)
                .fill(color.opacity(0.1))
                .frame(width: 56, height: 56)
            Image(systemName: icon)
                .font(.system(size: 22))
                .foregroundColor(color)
        }
    }
}

// MARK: - Edit Quick Links Sheet

struct EditQuickLinksSheet: View {
    @Binding var quickLinkPagesRaw: String
    @Environment(\.dismiss) var dismiss
    @State private var selectedPages: [NavPage] = []

    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()

            VStack(spacing: 0) {
                // Sticky header with save
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Quick Links")
                            .font(.lumeDisplaySmall)
                            .foregroundColor(.lumeNavy)
                        Text("Choose which tools appear on your dashboard.")
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }
                    Spacer()
                    Button {
                        quickLinkPagesRaw = selectedPages.map(\.rawValue).joined(separator: ",")
                        dismiss()
                    } label: {
                        Text("Save")
                            .font(.lumeBodySemibold)
                            .foregroundColor(.white)
                            .padding(.horizontal, 20)
                            .padding(.vertical, 10)
                            .background(selectedPages.isEmpty ? Color.lumeMuted : Color.lumeAccent)
                            .cornerRadius(20)
                    }
                    .disabled(selectedPages.isEmpty)
                }
                .padding(.horizontal, 24)
                .padding(.top, 20)
                .padding(.bottom, 12)

                ScrollView {
                    VStack(spacing: 20) {
                // Current quick links preview
                if !selectedPages.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("SELECTED · \(selectedPages.count)")
                            .font(.lumeSmall)
                            .fontWeight(.semibold)
                            .foregroundColor(.lumeMuted)
                            .tracking(1)

                        // Wrap in a scrollable row so it doesn't overflow
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 12) {
                                ForEach(selectedPages) { page in
                                    VStack(spacing: 6) {
                                        QuickLinkIcon(icon: page.icon, color: page.color)
                                        Text(page.label)
                                            .font(.system(size: 10))
                                            .foregroundColor(.lumeMuted)
                                    }
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 24)
                }

                // All pages
                VStack(alignment: .leading, spacing: 10) {
                    Text("ALL TOOLS")
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

                                Text(page.label)
                                    .font(.lumeBodyMedium)
                                    .foregroundColor(.lumeNavy)

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

                Spacer().frame(height: 20)
                    } // VStack inside ScrollView
                } // ScrollView
            } // VStack
        } // ZStack
        .environment(\.colorScheme, .light)
        .onAppear {
            let keys = quickLinkPagesRaw.split(separator: ",").map(String.init)
            selectedPages = keys.compactMap { NavPage(rawValue: $0) }
        }
    }

    private func togglePage(_ page: NavPage) {
        if let idx = selectedPages.firstIndex(of: page) {
            selectedPages.remove(at: idx)
        } else {
            selectedPages.append(page)
        }
    }
}

// MARK: - Today's Focus Card

/// Map raw phase names to friendly labels
private func friendlyPhaseName(_ phase: String) -> String {
    let lower = phase.lowercased()
    if lower.contains("first 24") || lower.contains("24 hour") { return "Today" }
    if lower.contains("first week") { return "This Week" }
    if lower.contains("first month") { return "This Month" }
    return phase
}

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
                    Text(friendlyPhaseName(phase))
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
                        if let days = daysRemaining(for: deadline) {
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

    private func daysRemaining(for deadline: Deadline) -> Int? {
        guard let dateStr = deadline.dueDate else { return nil }
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        guard let date = formatter.date(from: String(dateStr.prefix(10))) else { return nil }
        return Calendar.current.dateComponents([.day], from: Calendar.current.startOfDay(for: Date()), to: Calendar.current.startOfDay(for: date)).day
    }

    private func urgencyColor(_ deadline: Deadline) -> Color {
        guard let days = daysRemaining(for: deadline) else { return .lumeMuted }
        if days <= 3 { return .lumeAccent }
        if days <= 14 { return .lumeGold }
        return .lumeGreen
    }
}
