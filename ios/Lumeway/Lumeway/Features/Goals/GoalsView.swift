import SwiftUI
import UIKit

struct GoalsView: View {
    var isEmbedded: Bool = false

    @State private var goals: [GoalItem] = []
    @State private var isLoading = true
    @State private var showAddSheet = false
    @State private var showCompletedSection = false
    @State private var toastMessage: String?

    private let service = GoalService()

    private var activeGoals: [GoalItem] {
        goals.filter { !$0.isCompleted }
    }

    private var completedGoals: [GoalItem] {
        goals.filter(\.isCompleted)
    }

    var body: some View {
        OptionalNavigationStack(isEmbedded: isEmbedded) {
            ZStack {
                LinearGradient(
                    colors: [Color(hex: "F5F2ED"), Color(hex: "FAF7F2")],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                if isLoading {
                    ProgressView()
                        .tint(.lumeAccent)
                } else if goals.isEmpty {
                    emptyState
                } else {
                    goalsList
                }

                // Floating add button
                if !isLoading {
                    VStack {
                        Spacer()
                        HStack {
                            Spacer()
                            Button(action: { showAddSheet = true }) {
                                Image(systemName: "plus")
                                    .font(.system(size: 22, weight: .semibold))
                                    .foregroundColor(.white)
                                    .frame(width: 56, height: 56)
                                    .background(Color.lumeAccent)
                                    .clipShape(Circle())
                                    .shadow(color: Color.lumeAccent.opacity(0.35), radius: 10, y: 4)
                            }
                            .padding(.trailing, 24)
                            .padding(.bottom, 32)
                        }
                    }
                }

                // Toast overlay
                if let toast = toastMessage {
                    VStack {
                        Spacer()
                        HStack(spacing: 8) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 14))
                                .foregroundColor(.lumeGreen)
                            Text(toast)
                                .font(.lumeBody)
                                .foregroundColor(.lumeText)
                        }
                        .padding(.horizontal, 24)
                        .padding(.vertical, 14)
                        .background(Color.lumeWarmWhite)
                        .cornerRadius(24)
                        .shadow(color: .black.opacity(0.12), radius: 12, y: 4)
                        .padding(.bottom, 100)
                    }
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .zIndex(10)
                }
            }
            .navigationBarHidden(true)
            .task { await loadGoals() }
            .refreshable { await loadGoals() }
            .sheet(isPresented: $showAddSheet) {
                AddGoalSheet(onSave: { title, timeframe, targetDate in
                    Task { await createGoal(title: title, timeframe: timeframe, targetDate: targetDate) }
                })
                .presentationDetents([.medium])
            }
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "lightbulb.fill")
                .font(.system(size: 48, weight: .light))
                .foregroundColor(.lumeGold)
            Text("Set a goal to get started")
                .font(.lumeDisplaySmall)
                .foregroundColor(.lumeNavy)
            Text("Goals help you stay focused\nthrough your transition.")
                .font(.lumeBodyLight)
                .foregroundColor(.lumeMuted)
                .multilineTextAlignment(.center)

            Button(action: { showAddSheet = true }) {
                Text("Add Your First Goal")
                    .font(.lumeBodyMedium)
                    .foregroundColor(.white)
                    .padding(.horizontal, 28)
                    .padding(.vertical, 14)
                    .background(Color.lumeAccent)
                    .cornerRadius(24)
            }
            .padding(.top, 8)
        }
    }

    // MARK: - Goals List

    private var goalsList: some View {
        ScrollView {
            VStack(spacing: 0) {
                // Header
                ZStack {
                    Color.lumeNavy

                    VStack(spacing: 10) {
                        Text("Your Goals")
                            .font(.lumeDisplayMedium)
                            .foregroundColor(.white)

                        let completed = completedGoals.count
                        let total = goals.count
                        Text("\(completed) of \(total) completed")
                            .font(.lumeCaption)
                            .foregroundColor(.white.opacity(0.6))

                        // Progress bar
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                RoundedRectangle(cornerRadius: 4)
                                    .fill(Color.white.opacity(0.15))
                                    .frame(height: 6)

                                RoundedRectangle(cornerRadius: 4)
                                    .fill(Color.lumeGreen)
                                    .frame(
                                        width: total > 0
                                            ? geo.size.width * CGFloat(completed) / CGFloat(total)
                                            : 0,
                                        height: 6
                                    )
                            }
                        }
                        .frame(height: 6)
                        .padding(.horizontal, 20)
                    }
                    .padding(.top, 60)
                    .padding(.bottom, 28)
                }
                .overlay(alignment: .topLeading) {
                    if isEmbedded {
                        EmbeddedBackButton()
                            .padding(.leading, 16)
                            .padding(.top, 54)
                    }
                }
                .cornerRadius(20, corners: [.bottomLeft, .bottomRight])

                // Active goals
                VStack(spacing: 12) {
                    if !activeGoals.isEmpty {
                        activeGoalsSection
                    }

                    if !completedGoals.isEmpty {
                        completedGoalsSection
                    }
                }
                .padding(.horizontal, 20)
                .padding(.top, 16)

                Spacer().frame(height: 120)
            }
        }
        .ignoresSafeArea(edges: .top)
    }

    // MARK: - Active Goals Section

    private var activeGoalsSection: some View {
        VStack(spacing: 0) {
            // Section header
            HStack(spacing: 12) {
                RoundedRectangle(cornerRadius: 3)
                    .fill(Color.lumeAccent)
                    .frame(width: 5, height: 36)

                VStack(alignment: .leading, spacing: 3) {
                    Text("Active")
                        .font(.lumeBodyMedium)
                        .foregroundColor(.lumeNavy)

                    Text("\(activeGoals.count) goal\(activeGoals.count == 1 ? "" : "s")")
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)
                }

                Spacer()
            }
            .padding(16)
            .background(Color.lumeAccent.opacity(0.05))

            // Goal rows
            ForEach(activeGoals) { goal in
                GoalRow(goal: goal, onToggle: {
                    Task { await toggleGoal(goal) }
                })

                if goal.id != activeGoals.last?.id {
                    Divider()
                        .padding(.leading, 48)
                }
            }
            .onDelete { offsets in
                let goalsToDelete = offsets.map { activeGoals[$0] }
                for goal in goalsToDelete {
                    Task { await deleteGoal(goal) }
                }
            }
            .padding(.bottom, 4)
            .background(Color.lumeAccent.opacity(0.03))
        }
        .background(Color.lumeWarmWhite)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.lumeAccent.opacity(0.12), lineWidth: 1)
        )
    }

    // MARK: - Completed Goals Section

    private var completedGoalsSection: some View {
        VStack(spacing: 0) {
            Button(action: {
                withAnimation(.easeInOut(duration: 0.25)) {
                    showCompletedSection.toggle()
                }
            }) {
                HStack(spacing: 12) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.lumeGreen)
                        .frame(width: 5, height: 36)

                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 8) {
                            Text("Completed")
                                .font(.lumeBodyMedium)
                                .foregroundColor(.lumeNavy)

                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 14))
                                .foregroundColor(.lumeGreen)
                        }

                        Text("\(completedGoals.count) goal\(completedGoals.count == 1 ? "" : "s")")
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }

                    Spacer()

                    Image(systemName: showCompletedSection ? "chevron.up" : "chevron.down")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.lumeGreen)
                }
                .padding(16)
                .background(Color.lumeGreen.opacity(0.05))
            }

            if showCompletedSection {
                ForEach(completedGoals) { goal in
                    GoalRow(goal: goal, onToggle: {
                        Task { await toggleGoal(goal) }
                    })

                    if goal.id != completedGoals.last?.id {
                        Divider()
                            .padding(.leading, 48)
                    }
                }
                .padding(.bottom, 4)
                .background(Color.lumeGreen.opacity(0.03))
            }
        }
        .background(Color.lumeWarmWhite)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.lumeGreen.opacity(0.12), lineWidth: 1)
        )
    }

    // MARK: - Actions

    private func loadGoals() async {
        do {
            let response: GoalsResponse = try await service.getGoals()
            withAnimation {
                goals = response.goals
                isLoading = false
            }
        } catch {
            isLoading = false
        }
    }

    private func toggleGoal(_ goal: GoalItem) async {
        do {
            let response = try await service.toggleGoal(id: goal.id)
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()

            await loadGoals()

            if response.isCompleted == true {
                showToast("Goal completed. Nice work.")
            }
        } catch {
            UINotificationFeedbackGenerator().notificationOccurred(.error)
        }
    }

    private func createGoal(title: String, timeframe: String, targetDate: String?) async {
        do {
            _ = try await service.createGoal(title: title, timeframe: timeframe, targetDate: targetDate)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            showToast("Goal added.")
            await loadGoals()
        } catch {
            UINotificationFeedbackGenerator().notificationOccurred(.error)
        }
    }

    private func deleteGoal(_ goal: GoalItem) async {
        do {
            _ = try await service.deleteGoal(id: goal.id)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            showToast("Goal removed.")
            await loadGoals()
        } catch {
            UINotificationFeedbackGenerator().notificationOccurred(.error)
        }
    }

    private func showToast(_ message: String) {
        withAnimation(.easeInOut(duration: 0.3)) { toastMessage = message }
        Task {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            withAnimation(.easeInOut(duration: 0.3)) { toastMessage = nil }
        }
    }
}

// MARK: - Goal Row

private struct GoalRow: View {
    let goal: GoalItem
    let onToggle: () -> Void

    private static let timeframeColors: [String: Color] = [
        "This Week": .lumeAccent,
        "This Month": .lumeNavy,
        "This Quarter": .lumeGold,
        "Ongoing": .lumeGreen
    ]

    var body: some View {
        HStack(spacing: 10) {
            // Checkbox circle
            Button(action: onToggle) {
                ZStack {
                    Circle()
                        .stroke(
                            goal.isCompleted ? Color.clear : Color.lumeAccent.opacity(0.25),
                            lineWidth: 1.5
                        )
                        .frame(width: 20, height: 20)

                    if goal.isCompleted {
                        Circle()
                            .fill(Color.lumeGreen.opacity(0.8))
                            .frame(width: 20, height: 20)
                        Image(systemName: "checkmark")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(.white)
                    }
                }
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(goal.title)
                    .font(.lumeBody)
                    .foregroundColor(goal.isCompleted ? .lumeMuted : .lumeText)
                    .strikethrough(goal.isCompleted)
                    .opacity(goal.isCompleted ? 0.5 : 1)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)

                HStack(spacing: 8) {
                    // Timeframe tag
                    Text(goal.timeframe)
                        .font(.lumeSmall)
                        .foregroundColor(Self.timeframeColors[goal.timeframe] ?? .lumeMuted)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(
                            (Self.timeframeColors[goal.timeframe] ?? .lumeMuted).opacity(0.08)
                        )
                        .cornerRadius(6)

                    // Target date if present
                    if let targetDate = goal.targetDate, !targetDate.isEmpty {
                        HStack(spacing: 3) {
                            Image(systemName: "calendar")
                                .font(.system(size: 10))
                            Text(formatDate(targetDate))
                                .font(.lumeSmall)
                        }
                        .foregroundColor(.lumeMuted)
                    }
                }
            }

            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    private func formatDate(_ dateString: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withFullDate]
        if let date = formatter.date(from: String(dateString.prefix(10))) {
            let display = DateFormatter()
            display.dateFormat = "MMM d"
            return display.string(from: date)
        }
        return String(dateString.prefix(10))
    }
}

// MARK: - Add Goal Sheet

private struct AddGoalSheet: View {
    let onSave: (String, String, String?) -> Void

    @Environment(\.dismiss) var dismiss
    @State private var title = ""
    @State private var selectedTimeframe = "This Week"
    @State private var hasTargetDate = false
    @State private var targetDate = Date()

    private let timeframes = ["This Week", "This Month", "This Quarter", "Ongoing"]

    var body: some View {
        NavigationStack {
            ZStack {
                LinearGradient(
                    colors: [Color(hex: "F5F2ED"), Color(hex: "FAF7F2")],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        // Title field
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Goal")
                                .font(.lumeSectionTitle)
                                .foregroundColor(.lumeNavy)

                            TextField("What do you want to achieve?", text: $title)
                                .font(.lumeBody)
                                .foregroundColor(.lumeText)
                                .padding(16)
                                .background(Color.lumeWarmWhite)
                                .cornerRadius(12)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.lumeBorder, lineWidth: 1)
                                )
                        }

                        // Timeframe picker
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Timeframe")
                                .font(.lumeSectionTitle)
                                .foregroundColor(.lumeNavy)

                            HStack(spacing: 8) {
                                ForEach(timeframes, id: \.self) { tf in
                                    Button(action: { selectedTimeframe = tf }) {
                                        Text(tf)
                                            .font(.lumeSmall)
                                            .foregroundColor(
                                                selectedTimeframe == tf ? .white : .lumeNavy
                                            )
                                            .padding(.horizontal, 14)
                                            .padding(.vertical, 9)
                                            .background(
                                                selectedTimeframe == tf
                                                    ? Color.lumeAccent
                                                    : Color.lumeWarmWhite
                                            )
                                            .cornerRadius(10)
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 10)
                                                    .stroke(
                                                        selectedTimeframe == tf
                                                            ? Color.clear
                                                            : Color.lumeBorder,
                                                        lineWidth: 1
                                                    )
                                            )
                                    }
                                }
                            }
                        }

                        // Target date toggle + picker
                        VStack(alignment: .leading, spacing: 8) {
                            Toggle(isOn: $hasTargetDate) {
                                Text("Target Date")
                                    .font(.lumeSectionTitle)
                                    .foregroundColor(.lumeNavy)
                            }
                            .tint(.lumeAccent)

                            if hasTargetDate {
                                DatePicker(
                                    "Date",
                                    selection: $targetDate,
                                    in: Date()...,
                                    displayedComponents: .date
                                )
                                .datePickerStyle(.graphical)
                                .tint(.lumeAccent)
                                .padding(12)
                                .background(Color.lumeWarmWhite)
                                .cornerRadius(12)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.lumeBorder, lineWidth: 1)
                                )
                            }
                        }

                        // Save button
                        Button(action: save) {
                            Text("Save Goal")
                                .font(.lumeBodyMedium)
                                .foregroundColor(.white)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 16)
                                .background(
                                    title.trimmingCharacters(in: .whitespaces).isEmpty
                                        ? Color.lumeMuted.opacity(0.4)
                                        : Color.lumeAccent
                                )
                                .cornerRadius(14)
                        }
                        .disabled(title.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                    .padding(24)
                }
            }
            .navigationTitle("Add Goal")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color(hex: "F5F2ED"), for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.light, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .foregroundColor(.lumeAccent)
                }
            }
        }
    }

    private func save() {
        let trimmed = title.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }

        var dateString: String?
        if hasTargetDate {
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd"
            dateString = formatter.string(from: targetDate)
        }

        onSave(trimmed, selectedTimeframe, dateString)
        dismiss()
    }
}
