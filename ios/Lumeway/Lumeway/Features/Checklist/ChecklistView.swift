import SwiftUI
import UIKit

struct ChecklistView: View {
    @EnvironmentObject var appState: AppState
    @State private var expandedPhase: String?
    @State private var items: [FullChecklistItem] = []
    @State private var isLoading = true
    @State private var toastMessage: String?

    private let service = ChecklistService()

    // Warm completion messages (matches web dashboard psychology)
    private let completionMessages = [
        "One less thing to worry about.",
        "That one's done. Take a breath.",
        "Handled. You're making progress.",
        "Nice. One step closer.",
        "Done. You're moving forward.",
        "Checked off. You've got this.",
        "Progress. Every step counts.",
        "That's real momentum."
    ]

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                if isLoading {
                    ProgressView()
                        .tint(.lumeAccent)
                } else if items.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "checklist")
                            .font(.system(size: 48, weight: .light))
                            .foregroundColor(.lumeMuted)
                        Text("Your checklist will appear here")
                            .font(.lumeBody)
                            .foregroundColor(.lumeMuted)
                        Text("Complete onboarding to get your\npersonalized action plan.")
                            .font(.lumeCaptionLight)
                            .foregroundColor(.lumeMuted)
                            .multilineTextAlignment(.center)
                    }
                } else {
                    ScrollView {
                        VStack(spacing: 16) {
                            // Progress bar
                            ChecklistProgressBar(
                                completed: items.filter(\.isCompleted).count,
                                total: items.count
                            )
                            .padding(.horizontal, 24)

                            ForEach(groupedPhases, id: \.phase) { group in
                                PhaseSection(
                                    phase: group.phase,
                                    items: group.items,
                                    isExpanded: expandedPhase == group.phase,
                                    onToggle: {
                                        withAnimation(.easeInOut(duration: 0.2)) {
                                            expandedPhase = expandedPhase == group.phase ? nil : group.phase
                                        }
                                    },
                                    onToggleItem: { item in
                                        Task { await toggleItem(item) }
                                    },
                                    onSkipItem: { item in
                                        Task { await skipItem(item) }
                                    }
                                )
                            }

                            Spacer().frame(height: 32)
                        }
                        .padding(.top, 16)
                    }
                }

                // Toast overlay
                if let toast = toastMessage {
                    VStack {
                        Spacer()
                        Text(toast)
                            .font(.lumeBody)
                            .foregroundColor(.lumeText)
                            .padding(.horizontal, 24)
                            .padding(.vertical, 14)
                            .background(Color.lumeWarmWhite)
                            .cornerRadius(24)
                            .shadow(color: .black.opacity(0.1), radius: 12, y: 4)
                            .padding(.bottom, 32)
                    }
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .zIndex(10)
                }
            }
            .navigationTitle("Checklist")
            .navigationBarTitleDisplayMode(.large)
            .task { await loadChecklist() }
            .refreshable { await loadChecklist() }
        }
    }

    private var groupedPhases: [(phase: String, items: [FullChecklistItem])] {
        var dict: [String: [FullChecklistItem]] = [:]
        var order: [String] = []
        for item in items {
            let phase = item.phase ?? "Other"
            if dict[phase] == nil { order.append(phase) }
            dict[phase, default: []].append(item)
        }
        return order.map { (phase: $0, items: dict[$0]!) }
    }

    private func loadChecklist() async {
        do {
            let response = try await service.getChecklist()
            withAnimation {
                items = response.items
                isLoading = false
            }
            // Auto-expand first incomplete phase
            if expandedPhase == nil {
                let phases = groupedPhases
                expandedPhase = phases.first(where: { group in
                    group.items.contains(where: { !$0.isCompleted })
                })?.phase ?? phases.first?.phase
            }
        } catch {
            isLoading = false
            print("Checklist load error: \(error)")
        }
    }

    private func toggleItem(_ item: FullChecklistItem) async {
        do {
            let response = try await service.toggleItem(id: item.id)
            if let idx = items.firstIndex(where: { $0.id == item.id }) {
                let wasCompleted = items[idx].isCompleted
                // Reload to get fresh state
                await loadChecklist()

                // Show toast + haptic if marking complete (not un-completing)
                if !wasCompleted && response.isCompleted == true {
                    let generator = UIImpactFeedbackGenerator(style: .medium)
                    generator.impactOccurred()
                    showToast(completionMessages.randomElement() ?? "Done.")

                    // Check if phase is now fully complete for milestone haptic
                    let phase = item.phase ?? "Other"
                    if let group = groupedPhases.first(where: { $0.phase == phase }),
                       group.items.allSatisfy(\.isCompleted) {
                        let notify = UINotificationFeedbackGenerator()
                        notify.notificationOccurred(.success)
                    }
                }
            }
        } catch {
            let generator = UINotificationFeedbackGenerator()
            generator.notificationOccurred(.error)
            print("Toggle error: \(error)")
        }
    }

    private func skipItem(_ item: FullChecklistItem) async {
        do {
            let generator = UIImpactFeedbackGenerator(style: .light)
            generator.impactOccurred()
            _ = try await service.skipItem(id: item.id)
            showToast("No pressure. This task will be here when you're ready.")
            await loadChecklist()
        } catch {
            print("Skip error: \(error)")
        }
    }

    private func showToast(_ message: String) {
        withAnimation(.easeInOut(duration: 0.3)) {
            toastMessage = message
        }
        Task {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            withAnimation(.easeInOut(duration: 0.3)) {
                toastMessage = nil
            }
        }
    }
}

// MARK: - Progress Bar

struct ChecklistProgressBar: View {
    let completed: Int
    let total: Int

    var body: some View {
        VStack(spacing: 8) {
            HStack {
                Text("Progress")
                    .font(.lumeCaption)
                    .foregroundColor(.lumeText)
                Spacer()
                Text("\(completed) of \(total)")
                    .font(.lumeSmall)
                    .foregroundColor(.lumeMuted)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.lumeBorder)
                        .frame(height: 6)

                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.lumeGold)
                        .frame(width: total > 0 ? geo.size.width * CGFloat(completed) / CGFloat(total) : 0, height: 6)
                        .animation(.easeInOut(duration: 0.3), value: completed)
                }
            }
            .frame(height: 6)
        }
    }
}

// MARK: - Phase Section

struct PhaseSection: View {
    let phase: String
    let items: [FullChecklistItem]
    let isExpanded: Bool
    let onToggle: () -> Void
    let onToggleItem: (FullChecklistItem) -> Void
    let onSkipItem: (FullChecklistItem) -> Void

    private var completedCount: Int {
        items.filter(\.isCompleted).count
    }

    private var allComplete: Bool {
        completedCount == items.count
    }

    var body: some View {
        VStack(spacing: 0) {
            // Phase header
            Button(action: onToggle) {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 8) {
                            Text(phase)
                                .font(.lumeBodyMedium)
                                .foregroundColor(.lumeText)
                            if allComplete {
                                Image(systemName: "checkmark.seal.fill")
                                    .font(.system(size: 14))
                                    .foregroundColor(.lumeGreen)
                            }
                        }
                        Text("\(completedCount) of \(items.count) complete")
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }
                    Spacer()
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(.lumeMuted)
                }
                .padding(16)
            }

            if isExpanded {
                Divider().padding(.horizontal, 16)

                ForEach(items) { item in
                    ChecklistRow(
                        item: item,
                        onToggle: { onToggleItem(item) },
                        onSkip: { onSkipItem(item) }
                    )
                }
            }
        }
        .background(Color.lumeWarmWhite)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.lumeBorder, lineWidth: 1)
        )
        .padding(.horizontal, 24)
    }
}

// MARK: - Checklist Row

struct ChecklistRow: View {
    let item: FullChecklistItem
    let onToggle: () -> Void
    let onSkip: () -> Void
    @State private var showActions = false

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Toggle button
            Button(action: onToggle) {
                Image(systemName: item.isCompleted ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 22))
                    .foregroundColor(item.isCompleted ? .lumeGreen : .lumeBorder)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(item.title)
                    .font(.lumeCaption)
                    .foregroundColor(item.isCompleted ? .lumeMuted : .lumeText)
                    .strikethrough(item.isCompleted)
            }

            Spacer()

            // Skip button (only for incomplete items)
            if !item.isCompleted {
                Button {
                    onSkip()
                } label: {
                    Text("Skip")
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }
}
