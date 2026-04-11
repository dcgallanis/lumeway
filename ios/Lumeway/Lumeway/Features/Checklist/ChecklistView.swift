import SwiftUI
import UIKit

// Phase colors for color coding
private let phaseColors: [Color] = [
    Color(hex: "C4704E"), // terracotta
    Color(hex: "2C4A5E"), // navy
    Color(hex: "B8977E"), // gold
    Color(hex: "4A7C59"), // green
    Color(hex: "7B6B8D"), // purple
    Color(hex: "5E8C9A"), // teal
]

struct ChecklistView: View {
    @EnvironmentObject var appState: AppState
    @State private var items: [FullChecklistItem] = []
    @State private var isLoading = true
    @State private var toastMessage: String?
    @State private var expandedPhases: Set<String> = []

    private let service = ChecklistService()

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
                // Subtle warm gradient
                LinearGradient(
                    colors: [Color(hex: "F5F2ED"), Color(hex: "FAF7F2")],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                if isLoading {
                    ProgressView()
                        .tint(.lumeAccent)
                } else if items.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "sun.max.fill")
                            .font(.system(size: 48, weight: .light))
                            .foregroundColor(.lumeGold)
                        Text("Your checklist will appear here")
                            .font(.lumeDisplaySmall)
                            .foregroundColor(.lumeNavy)
                        Text("Complete onboarding to get your\npersonalized action plan.")
                            .font(.lumeBodyLight)
                            .foregroundColor(.lumeMuted)
                            .multilineTextAlignment(.center)
                    }
                } else {
                    ScrollView {
                        VStack(spacing: 0) {
                            // Color-blocked header
                            ZStack {
                                Color.lumeNavy

                                VStack(spacing: 10) {
                                    if let transition = appState.user?.transitionType {
                                        Text(transition.replacingOccurrences(of: "-", with: " ").uppercased())
                                            .font(.lumeSmall)
                                            .foregroundColor(.lumeAccent)
                                            .tracking(1)
                                    }

                                    Text("Your Checklist")
                                        .font(.lumeDisplayMedium)
                                        .foregroundColor(.white)

                                    let completed = items.filter(\.isCompleted).count
                                    Text("\(completed) of \(items.count) completed")
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
                                                .frame(width: items.count > 0 ? geo.size.width * CGFloat(completed) / CGFloat(items.count) : 0, height: 6)
                                        }
                                    }
                                    .frame(height: 6)
                                    .padding(.horizontal, 20)
                                }
                                .padding(.vertical, 28)
                            }
                            .cornerRadius(20, corners: [.bottomLeft, .bottomRight])

                            // Collapsible phase sections
                            VStack(spacing: 12) {
                                ForEach(Array(groupedPhases.enumerated()), id: \.element.phase) { idx, group in
                                    let color = phaseColors[idx % phaseColors.count]

                                    CollapsiblePhaseSection(
                                        phase: group.phase,
                                        items: group.items,
                                        color: color,
                                        isExpanded: expandedPhases.contains(group.phase),
                                        onToggleExpand: {
                                            withAnimation(.easeInOut(duration: 0.25)) {
                                                if expandedPhases.contains(group.phase) {
                                                    expandedPhases.remove(group.phase)
                                                } else {
                                                    expandedPhases.insert(group.phase)
                                                }
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
                            }
                            .padding(.horizontal, 20)
                            .padding(.top, 16)

                            Spacer().frame(height: 100)
                        }
                    }
                    .ignoresSafeArea(edges: .top)
                }

                // Toast overlay
                if let toast = toastMessage {
                    VStack {
                        Spacer()
                        HStack(spacing: 8) {
                            Image(systemName: "sun.max.fill")
                                .font(.system(size: 14))
                                .foregroundColor(.lumeGold)
                            Text(toast)
                                .font(.lumeBody)
                                .foregroundColor(.lumeText)
                        }
                        .padding(.horizontal, 24)
                        .padding(.vertical, 14)
                        .background(Color.lumeWarmWhite)
                        .cornerRadius(24)
                        .shadow(color: .black.opacity(0.12), radius: 12, y: 4)
                        .padding(.bottom, 32)
                    }
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .zIndex(10)
                }
            }
            .navigationBarHidden(true)
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
        return order.map { phase in
            let phaseItems = dict[phase]!
            let sorted = phaseItems.filter { !$0.isCompleted } + phaseItems.filter(\.isCompleted)
            return (phase: phase, items: sorted)
        }
    }

    private func loadChecklist() async {
        do {
            let response = try await service.getChecklist()
            withAnimation {
                items = response.items
                isLoading = false
            }
            // Auto-expand first incomplete phase
            if expandedPhases.isEmpty {
                if let firstIncomplete = groupedPhases.first(where: { group in
                    group.items.contains(where: { !$0.isCompleted })
                }) {
                    expandedPhases.insert(firstIncomplete.phase)
                }
            }
        } catch {
            isLoading = false
        }
    }

    private func toggleItem(_ item: FullChecklistItem) async {
        do {
            let response = try await service.toggleItem(id: item.id)
            if let idx = items.firstIndex(where: { $0.id == item.id }) {
                let wasCompleted = items[idx].isCompleted
                await loadChecklist()
                if !wasCompleted && response.isCompleted == true {
                    UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                    showToast(completionMessages.randomElement() ?? "Done.")
                }
            }
        } catch {
            UINotificationFeedbackGenerator().notificationOccurred(.error)
        }
    }

    private func skipItem(_ item: FullChecklistItem) async {
        do {
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            _ = try await service.skipItem(id: item.id)
            showToast("No pressure. It'll be here when you're ready.")
            await loadChecklist()
        } catch {}
    }

    private func showToast(_ message: String) {
        withAnimation(.easeInOut(duration: 0.3)) { toastMessage = message }
        Task {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            withAnimation(.easeInOut(duration: 0.3)) { toastMessage = nil }
        }
    }
}

// MARK: - Collapsible Phase Section

struct CollapsiblePhaseSection: View {
    let phase: String
    let items: [FullChecklistItem]
    let color: Color
    let isExpanded: Bool
    let onToggleExpand: () -> Void
    let onToggleItem: (FullChecklistItem) -> Void
    let onSkipItem: (FullChecklistItem) -> Void

    private var completedCount: Int { items.filter(\.isCompleted).count }
    private var allDone: Bool { completedCount == items.count }

    var body: some View {
        VStack(spacing: 0) {
            // Phase header — color coded
            Button(action: onToggleExpand) {
                HStack(spacing: 12) {
                    // Color bar
                    RoundedRectangle(cornerRadius: 3)
                        .fill(color)
                        .frame(width: 5, height: 36)

                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 8) {
                            Text(phase)
                                .font(.lumeBodyMedium)
                                .foregroundColor(.lumeNavy)

                            if allDone {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.system(size: 14))
                                    .foregroundColor(.lumeGreen)
                            }
                        }

                        Text("\(completedCount)/\(items.count) complete")
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }

                    Spacer()

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(color)
                }
                .padding(16)
                .background(color.opacity(0.06))
            }

            if isExpanded {
                VStack(spacing: 0) {
                    ForEach(items) { item in
                        ChecklistItemRow(
                            item: item,
                            color: color,
                            onToggle: { onToggleItem(item) },
                            onSkip: { onSkipItem(item) }
                        )

                        if item.id != items.last?.id {
                            Divider()
                                .padding(.leading, 54)
                        }
                    }
                }
                .padding(.bottom, 4)
            }
        }
        .background(Color.lumeWarmWhite)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(color.opacity(0.15), lineWidth: 1)
        )
    }
}

// MARK: - Checklist Item Row

struct ChecklistItemRow: View {
    let item: FullChecklistItem
    let color: Color
    let onToggle: () -> Void
    let onSkip: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            // Toggle circle
            Button(action: onToggle) {
                ZStack {
                    Circle()
                        .stroke(item.isCompleted ? Color.clear : color.opacity(0.3), lineWidth: 2)
                        .frame(width: 26, height: 26)

                    if item.isCompleted {
                        Circle()
                            .fill(color)
                            .frame(width: 26, height: 26)
                        Image(systemName: "checkmark")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundColor(.white)
                    }
                }
            }

            Text(item.title)
                .font(.lumeCaption)
                .foregroundColor(item.isCompleted ? .lumeMuted : .lumeNavy)
                .strikethrough(item.isCompleted)
                .opacity(item.isCompleted ? 0.6 : 1)

            Spacer()

            if !item.isCompleted {
                Button(action: onSkip) {
                    Text("Skip")
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(Color.lumeBorder.opacity(0.4))
                        .cornerRadius(8)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 11)
    }
}

// MARK: - Rounded Corner Helper

struct RoundedCorner: Shape {
    var radius: CGFloat = .infinity
    var corners: UIRectCorner = .allCorners

    func path(in rect: CGRect) -> Path {
        let path = UIBezierPath(roundedRect: rect, byRoundingCorners: corners, cornerRadii: CGSize(width: radius, height: radius))
        return Path(path.cgPath)
    }
}

extension View {
    func cornerRadius(_ radius: CGFloat, corners: UIRectCorner) -> some View {
        clipShape(RoundedCorner(radius: radius, corners: corners))
    }
}
