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
    var isEmbedded: Bool = false
    @Environment(\.dismiss) var dismiss

    @EnvironmentObject var appState: AppState
    @State private var items: [FullChecklistItem] = []
    @State private var isLoading = true
    @State private var toastMessage: String?
    @State private var expandedPhases: Set<String> = []
    @State private var showConfetti = false
    @State private var confettiMessage: String?
    @State private var selectedTransition: String? = nil

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
        OptionalNavigationStack(isEmbedded: isEmbedded) {
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
                                    Text("Your Checklist")
                                        .font(.lumeDisplayMedium)
                                        .foregroundColor(.white)

                                    // Overall progress
                                    let visibleItems = filteredItems
                                    let allCompleted = visibleItems.filter(\.isCompleted).count
                                    let allTotal = visibleItems.count

                                    Text("\(allCompleted) of \(allTotal) tasks done")
                                        .font(.lumeCaption)
                                        .foregroundColor(.white.opacity(0.6))

                                    // Progress bar — overall
                                    GeometryReader { geo in
                                        ZStack(alignment: .leading) {
                                            RoundedRectangle(cornerRadius: 4)
                                                .fill(Color.white.opacity(0.15))
                                                .frame(height: 6)

                                            RoundedRectangle(cornerRadius: 4)
                                                .fill(Color.lumeGreen)
                                                .frame(width: allTotal > 0 ? geo.size.width * CGFloat(allCompleted) / CGFloat(allTotal) : 0, height: 6)
                                        }
                                    }
                                    .frame(height: 6)
                                    .padding(.horizontal, 20)

                                    // Transition selector pills (when multiple checklists) — wrapping layout
                                    if transitionTypes.count > 1 {
                                        WrappingHStack(spacing: 8) {
                                            TransitionPill(label: "All", isSelected: selectedTransition == nil) {
                                                withAnimation(.easeInOut(duration: 0.2)) { selectedTransition = nil }
                                            }
                                            ForEach(transitionTypes, id: \.self) { t in
                                                TransitionPill(label: friendlyTransitionName(t), isSelected: selectedTransition == t) {
                                                    withAnimation(.easeInOut(duration: 0.2)) { selectedTransition = t }
                                                }
                                            }
                                        }
                                        .padding(.horizontal, 20)
                                        .padding(.top, 4)
                                    }
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

                            // Active + upcoming phases (reordered)
                            VStack(spacing: 12) {
                                ForEach(Array(reorderedPhases.enumerated()), id: \.element.phase) { idx, group in
                                    let color = phaseColors[idx % phaseColors.count]

                                    CollapsiblePhaseSection(
                                        phase: group.displayName,
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

                                // Completed phases — collapsed at bottom
                                if !completedPhaseItems.isEmpty {
                                    CollapsiblePhaseSection(
                                        phase: "Completed Tasks",
                                        items: completedPhaseItems,
                                        color: .lumeGreen,
                                        isExpanded: expandedPhases.contains("__completed__"),
                                        onToggleExpand: {
                                            withAnimation(.easeInOut(duration: 0.25)) {
                                                if expandedPhases.contains("__completed__") {
                                                    expandedPhases.remove("__completed__")
                                                } else {
                                                    expandedPhases.insert("__completed__")
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

                // Confetti + milestone overlay
                if showConfetti {
                    ConfettiOverlay()
                        .ignoresSafeArea()
                        .allowsHitTesting(false)
                        .zIndex(20)
                }

                if let milestone = confettiMessage {
                    VStack {
                        Spacer()
                        VStack(spacing: 8) {
                            Text("🎉")
                                .font(.system(size: 36))
                            Text(milestone)
                                .font(.lumeHeadingSmall)
                                .foregroundColor(.lumeNavy)
                                .multilineTextAlignment(.center)
                        }
                        .padding(24)
                        .background(Color.lumeWarmWhite)
                        .cornerRadius(20)
                        .shadow(color: .black.opacity(0.15), radius: 16, y: 6)
                        Spacer()
                    }
                    .transition(.scale.combined(with: .opacity))
                    .zIndex(15)
                    .onTapGesture {
                        withAnimation { confettiMessage = nil; showConfetti = false }
                    }
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

    /// All unique transition types in the data
    private var transitionTypes: [String] {
        var seen: [String] = []
        for item in items {
            let t = item.transitionType ?? "general"
            if !seen.contains(t) { seen.append(t) }
        }
        return seen
    }

    /// Items filtered by selected transition (or all if nil)
    private var filteredItems: [FullChecklistItem] {
        guard let selected = selectedTransition else { return items }
        return items.filter { ($0.transitionType ?? "general") == selected }
    }

    /// Friendly name for transition type
    private func friendlyTransitionName(_ t: String) -> String {
        switch t.lowercased() {
        case "estate": return "Loss of Loved One"
        case "divorce": return "Divorce"
        case "job-loss": return "Job Loss"
        case "relocation": return "Relocation"
        case "disability": return "Disability"
        case "retirement": return "Retirement"
        default: return t.capitalized
        }
    }

    /// Items in the current (first incomplete) phase — used for header progress
    private var currentPhaseItems: [FullChecklistItem] {
        let filtered = filteredItems
        let incomplete = filtered.filter { !$0.isCompleted }
        guard let currentPhase = incomplete.first?.phase else {
            guard let lastPhase = filtered.last?.phase else { return filtered }
            return filtered.filter { $0.phase == lastPhase }
        }
        return filtered.filter { $0.phase == currentPhase }
    }

    /// Display name for phases — "Today" for the current active phase
    private func phaseDisplayName(_ phase: String, isFirst: Bool) -> String {
        if isFirst { return "Today" }
        let lower = phase.lowercased()
        if lower.contains("first 24") || lower.contains("24 hour") { return "Today" }
        if lower.contains("first week") || lower.contains("this week") { return "This Week" }
        if lower.contains("first month") || lower.contains("this month") { return "This Month" }
        return phase
    }

    /// Active and upcoming phases (not fully completed), reordered
    private var reorderedPhases: [(phase: String, displayName: String, items: [FullChecklistItem])] {
        let groups = groupedPhases
        var active: [(phase: String, displayName: String, items: [FullChecklistItem])] = []
        var isFirstActive = true

        for group in groups {
            let hasIncomplete = group.items.contains(where: { !$0.isCompleted })
            if hasIncomplete {
                let name = phaseDisplayName(group.phase, isFirst: isFirstActive)
                active.append((phase: group.phase, displayName: name, items: group.items))
                isFirstActive = false
            }
        }
        return active
    }

    /// All items from fully completed phases — collapsed at bottom
    private var completedPhaseItems: [FullChecklistItem] {
        let groups = groupedPhases
        var completed: [FullChecklistItem] = []
        for group in groups {
            let allDone = group.items.allSatisfy(\.isCompleted)
            if allDone && !group.items.isEmpty {
                completed.append(contentsOf: group.items)
            }
        }
        return completed
    }

    private var groupedPhases: [(phase: String, items: [FullChecklistItem])] {
        let source = filteredItems
        var dict: [String: [FullChecklistItem]] = [:]
        var order: [String] = []

        let showingAll = selectedTransition == nil && transitionTypes.count > 1

        for item in source {
            let transition = item.transitionType ?? "general"
            let phase = item.phase ?? "Other"
            // When viewing a single transition or "All" with multiple, use transition prefix
            let key: String
            if showingAll {
                key = "\(friendlyTransitionName(transition)): \(phase)"
            } else {
                key = phase
            }
            if dict[key] == nil { order.append(key) }
            dict[key, default: []].append(item)
        }
        return order.map { key in
            let phaseItems = dict[key]!
            let sorted = phaseItems.filter { !$0.isCompleted } + phaseItems.filter(\.isCompleted)
            return (phase: key, items: sorted)
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
                let itemPhase = items[idx].phase ?? "Other"

                await loadChecklist()

                if !wasCompleted && response.isCompleted == true {
                    UIImpactFeedbackGenerator(style: .medium).impactOccurred()

                    // Check if entire phase is now complete
                    let phaseItems = items.filter { $0.phase == itemPhase }
                    let allDone = phaseItems.allSatisfy(\.isCompleted)

                    if allDone && !phaseItems.isEmpty {
                        // Phase complete — confetti!
                        triggerConfetti(for: itemPhase)
                    } else {
                        showToast(completionMessages.randomElement() ?? "Done.")
                    }
                }
            }
        } catch {
            UINotificationFeedbackGenerator().notificationOccurred(.error)
        }
    }

    private let milestoneMessages = [
        "You handled it. That takes real strength.",
        "Every single one. Well done.",
        "Section complete. You're making real progress.",
        "That's a whole section done. Take a moment.",
        "Incredible. Keep this momentum going.",
    ]

    private func triggerConfetti(for phase: String) {
        let msg = milestoneMessages.randomElement() ?? "Section complete."
        withAnimation(.spring(response: 0.5, dampingFraction: 0.7)) {
            showConfetti = true
            confettiMessage = msg
        }
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        Task {
            try? await Task.sleep(nanoseconds: 4_000_000_000)
            withAnimation(.easeOut(duration: 0.5)) {
                showConfetti = false
                confettiMessage = nil
            }
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
                .background(color.opacity(0.05))
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
                                .padding(.leading, 48)
                        }
                    }
                }
                .padding(.bottom, 4)
                .background(color.opacity(0.03))
            }
        }
        .background(Color.lumeWarmWhite)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(color.opacity(0.12), lineWidth: 1)
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
        HStack(spacing: 10) {
            // Toggle circle with generous tap target
            Button(action: onToggle) {
                ZStack {
                    // Invisible hit area
                    Color.clear
                        .frame(width: 44, height: 44)

                    Circle()
                        .stroke(item.isCompleted ? Color.clear : color.opacity(0.25), lineWidth: 1.5)
                        .frame(width: 22, height: 22)

                    if item.isCompleted {
                        Circle()
                            .fill(color.opacity(0.8))
                            .frame(width: 22, height: 22)
                        Image(systemName: "checkmark")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(.white)
                    }
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            NavigationLink {
                TaskDetailView(item: item, color: color)
            } label: {
                HStack(spacing: 6) {
                    Text(item.title)
                        .font(.lumeBody)
                        .foregroundColor(item.isCompleted ? .lumeMuted : .lumeText)
                        .strikethrough(item.isCompleted)
                        .opacity(item.isCompleted ? 0.5 : 1)
                        .multilineTextAlignment(.leading)

                    Spacer()

                    if !item.isCompleted {
                        Image(systemName: "chevron.right")
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(color.opacity(0.3))
                    }
                }
            }

            if !item.isCompleted {
                Button(action: onSkip) {
                    Text("Later")
                        .font(.lumeSmall)
                        .foregroundColor(color.opacity(0.7))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(color.opacity(0.06))
                        .cornerRadius(8)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
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

// MARK: - Confetti Overlay

struct ConfettiOverlay: View {
    @State private var particles: [ConfettiParticle] = []

    private let colors: [Color] = [
        .lumeAccent, .lumeGold, .lumeGreen, Color(hex: "5E8C9A"),
        Color(hex: "7B6B8D"), .lumeBlush, Color(hex: "D4896C")
    ]

    var body: some View {
        GeometryReader { geo in
            ZStack {
                ForEach(particles) { particle in
                    Circle()
                        .fill(particle.color)
                        .frame(width: particle.size, height: particle.size)
                        .position(particle.position)
                        .opacity(particle.opacity)
                }
            }
            .onAppear {
                createParticles(in: geo.size)
            }
        }
    }

    private func createParticles(in size: CGSize) {
        for i in 0..<60 {
            let particle = ConfettiParticle(
                id: i,
                color: colors.randomElement() ?? .lumeGold,
                size: CGFloat.random(in: 4...10),
                position: CGPoint(x: CGFloat.random(in: 0...size.width), y: -20),
                opacity: 1
            )
            particles.append(particle)

            let delay = Double.random(in: 0...0.8)
            let duration = Double.random(in: 1.5...3.0)
            let endX = particle.position.x + CGFloat.random(in: -60...60)
            let endY = size.height + 40

            withAnimation(.easeIn(duration: duration).delay(delay)) {
                if let idx = particles.firstIndex(where: { $0.id == i }) {
                    particles[idx].position = CGPoint(x: endX, y: endY)
                    particles[idx].opacity = 0
                }
            }
        }
    }
}

struct ConfettiParticle: Identifiable {
    let id: Int
    let color: Color
    let size: CGFloat
    var position: CGPoint
    var opacity: Double
}

// MARK: - Transition Pill

struct TransitionPill: View {
    let label: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.lumeCaption)
                .foregroundColor(isSelected ? .lumeNavy : .white.opacity(0.7))
                .padding(.horizontal, 14)
                .padding(.vertical, 7)
                .background(isSelected ? Color.white : Color.white.opacity(0.12))
                .cornerRadius(18)
        }
    }
}

// MARK: - Wrapping HStack (flow layout for pills)

struct WrappingHStack: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = layout(subviews: subviews, maxWidth: proposal.width ?? .infinity)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = layout(subviews: subviews, maxWidth: bounds.width)
        for (index, position) in result.positions.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y), proposal: .unspecified)
        }
    }

    private func layout(subviews: Subviews, maxWidth: CGFloat) -> (size: CGSize, positions: [CGPoint]) {
        var positions: [CGPoint] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var maxX: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth && x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            positions.append(CGPoint(x: x, y: y))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
            maxX = max(maxX, x - spacing)
        }

        return (CGSize(width: maxX, height: y + rowHeight), positions)
    }
}
