import SwiftUI

// Pastel card backgrounds
private let categoryBgColors: [Color] = [
    Color(hex: "E8F0E4"), // sage
    Color(hex: "DAE8E0"), // seafoam
    Color(hex: "E4E8EE"), // blue-gray
    Color(hex: "F0EAE0"), // warm cream
    Color(hex: "E0E8E4"), // mint
    Color(hex: "EAE4E0"), // blush
    Color(hex: "E4EAE8"), // light teal
    Color(hex: "EEE8E0"), // linen
]

private let categoryAccentColors: [Color] = [
    Color(hex: "2C4A5E"), // navy
    Color(hex: "4A7C59"), // green
    Color(hex: "5E8C9A"), // teal
    Color(hex: "C4704E"), // terracotta
    Color(hex: "6B8E6B"), // sage
    Color(hex: "B8977E"), // gold
    Color(hex: "7B6B8D"), // purple
    Color(hex: "9B7653"), // brown
]

// Varied bullet icons per category instead of all suns
private let categoryBullets: [String] = [
    "leaf.fill", "shield.fill", "building.2.fill", "heart.fill",
    "graduationcap.fill", "briefcase.fill", "house.fill", "star.fill"
]

struct GuidesView: View {
    @EnvironmentObject var appState: AppState
    @State private var guideData: GuideDetailResponse?
    @State private var allGuides: [String: GuideDetailResponse] = [:]
    @State private var isLoading = true
    @State private var searchText = ""
    @State private var expandedTransitions: Set<String> = []

    private let service = GuideService()

    var body: some View {
        NavigationStack {
            ZStack {
                // Soft sage-cream gradient
                LinearGradient(
                    colors: [Color(hex: "F2F5F0"), Color(hex: "FAF7F2")],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                if isLoading {
                    ProgressView()
                        .tint(.lumeAccent)
                } else if let guide = guideData, !guide.guide.categories.isEmpty {
                    ScrollView {
                        VStack(spacing: 0) {
                            // Color-blocked header
                            ZStack {
                                Color.lumeNavy

                                VStack(spacing: 10) {
                                    Image(systemName: "book.fill")
                                        .font(.system(size: 28))
                                        .foregroundColor(.lumeGold)

                                    Text("Your Guides")
                                        .font(.lumeDisplayMedium)
                                        .foregroundColor(.white)

                                    if !allTransitionKeys.isEmpty {
                                        Text("\(allTransitionKeys.count) transition\(allTransitionKeys.count == 1 ? "" : "s")")
                                            .font(.lumeCaption)
                                            .foregroundColor(.white.opacity(0.6))
                                    }
                                }
                                .padding(.top, 60)
                                .padding(.bottom, 28)
                            }
                            .cornerRadius(20, corners: [.bottomLeft, .bottomRight])

                            // Search bar — warm cream
                            HStack(spacing: 10) {
                                Image(systemName: "magnifyingglass")
                                    .font(.system(size: 14))
                                    .foregroundColor(.lumeMuted)

                                TextField("Search guides...", text: $searchText)
                                    .font(.lumeBody)
                                    .foregroundColor(.lumeText)
                            }
                            .padding(12)
                            .background(Color.lumeWarmWhite)
                            .cornerRadius(12)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color.lumeBorder, lineWidth: 1)
                            )
                            .padding(.horizontal, 20)
                            .padding(.top, 16)
                            .padding(.bottom, 8)

                            // Transition sections — show all purchased transitions
                            ForEach(allTransitionKeys, id: \.self) { transition in
                                let guideResp = allGuides[transition] ?? guide
                                let cats = filteredCategories(for: guideResp)
                                if !cats.isEmpty {
                                    TransitionGuideSection(
                                        transitionName: transition.replacingOccurrences(of: "-", with: " ").capitalized,
                                        categories: cats,
                                        hasFullAccess: guideResp.hasFullAccess,
                                        isExpanded: expandedTransitions.contains(transition),
                                        onToggle: {
                                            withAnimation(.easeInOut(duration: 0.25)) {
                                                if expandedTransitions.contains(transition) {
                                                    expandedTransitions.remove(transition)
                                                } else {
                                                    expandedTransitions.insert(transition)
                                                }
                                            }
                                        }
                                    )
                                    .padding(.horizontal, 20)
                                    .padding(.top, 8)
                                }
                            }

                            Spacer().frame(height: 100)
                        }
                    }
                    .ignoresSafeArea(edges: .top)
                } else {
                    VStack(spacing: 16) {
                        Image(systemName: "book.fill")
                            .font(.system(size: 48, weight: .light))
                            .foregroundColor(.lumeGold)
                        Text("Your Guide Library")
                            .font(.lumeDisplaySmall)
                            .foregroundColor(.lumeNavy)
                        Text("Guides are tailored to\nyour specific needs.")
                            .font(.lumeBodyLight)
                            .foregroundColor(.lumeMuted)
                            .multilineTextAlignment(.center)
                    }
                }
            }
            .navigationBarHidden(true)
            .task {
                await loadGuides()
                // Auto-expand all transitions
                for t in allTransitionKeys {
                    expandedTransitions.insert(t)
                }
            }
            .refreshable { await loadGuides() }
        }
    }

    /// All transition keys the user has access to (primary + purchased)
    private var allTransitionKeys: [String] {
        var keys: [String] = []
        if let primary = appState.user?.transitionType {
            keys.append(primary)
        }
        // Add any additional active transitions from purchases
        for t in appState.activeTransitions where !keys.contains(t) {
            keys.append(t)
        }
        return keys
    }

    private func filteredCategories(for guideResp: GuideDetailResponse) -> [GuideCategory] {
        let cats = guideResp.guide.categories
        if searchText.isEmpty { return cats }
        return cats.filter { cat in
            cat.name.localizedCaseInsensitiveContains(searchText) ||
            cat.tasks.contains(where: { $0.title.localizedCaseInsensitiveContains(searchText) })
        }
    }

    private func loadGuides() async {
        let transitions = allTransitionKeys
        guard !transitions.isEmpty else {
            isLoading = false
            return
        }
        do {
            // Load primary transition
            let primary = transitions[0]
            guideData = try await service.getGuide(transition: primary)
            allGuides[primary] = guideData

            // Load additional purchased transitions in parallel
            await withTaskGroup(of: (String, GuideDetailResponse?).self) { group in
                for t in transitions.dropFirst() {
                    group.addTask {
                        let resp = try? await self.service.getGuide(transition: t)
                        return (t, resp)
                    }
                }
                for await (key, resp) in group {
                    if let resp = resp {
                        allGuides[key] = resp
                    }
                }
            }

            isLoading = false
        } catch {
            isLoading = false
        }
    }
}

// MARK: - Transition Guide Section (collapsible)

struct TransitionGuideSection: View {
    let transitionName: String
    let categories: [GuideCategory]
    let hasFullAccess: Bool
    let isExpanded: Bool
    let onToggle: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Collapsible transition header
            Button(action: onToggle) {
                HStack(spacing: 12) {
                    Image(systemName: "sun.max.fill")
                        .font(.system(size: 18))
                        .foregroundColor(.lumeGold)

                    Text(transitionName)
                        .font(.lumeDisplaySmall)
                        .foregroundColor(.lumeNavy)

                    Spacer()

                    Text("\(categories.count) categories")
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.lumeNavy)
                }
                .padding(18)
                .background(Color.lumeWarmWhite)
                .cornerRadius(16)
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.lumeBorder, lineWidth: 1)
                )
            }

            if isExpanded {
                VStack(spacing: 10) {
                    ForEach(Array(categories.enumerated()), id: \.element.id) { idx, cat in
                        NavigationLink {
                            GuideCategoryDetailView(
                                category: cat,
                                hasFullAccess: hasFullAccess,
                                themeColor: categoryAccentColors[idx % categoryAccentColors.count]
                            )
                        } label: {
                            GuideCategoryCard(
                                label: cat.name,
                                taskCount: cat.tasks.count,
                                bgColor: categoryBgColors[idx % categoryBgColors.count],
                                accentColor: categoryAccentColors[idx % categoryAccentColors.count],
                                bulletIcon: categoryBullets[idx % categoryBullets.count]
                            )
                        }
                    }
                }
                .padding(.top, 10)
            }
        }
    }
}

// MARK: - Category Card

struct GuideCategoryCard: View {
    let label: String
    let taskCount: Int
    let bgColor: Color
    let accentColor: Color
    let bulletIcon: String

    var body: some View {
        HStack(spacing: 14) {
            ZStack {
                Circle()
                    .fill(accentColor.opacity(0.12))
                    .frame(width: 36, height: 36)
                Image(systemName: bulletIcon)
                    .font(.system(size: 15))
                    .foregroundColor(accentColor)
            }

            VStack(alignment: .leading, spacing: 3) {
                Text(label)
                    .font(.lumeBodyMedium)
                    .foregroundColor(.lumeNavy)

                Text("\(taskCount) guide\(taskCount == 1 ? "" : "s")")
                    .font(.lumeSmall)
                    .foregroundColor(.lumeMuted)
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(accentColor.opacity(0.5))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(bgColor)
        .cornerRadius(14)
    }
}

// MARK: - Category Detail View

struct GuideCategoryDetailView: View {
    let category: GuideCategory
    let hasFullAccess: Bool
    let themeColor: Color

    // Pastel version of the theme color for backgrounds
    private var pastelBg: Color {
        themeColor.opacity(0.08)
    }

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [Color(hex: "F2F5F0"), Color(hex: "FAF7F2")],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            ScrollView {
                VStack(spacing: 0) {
                    // Navy color-blocked header
                    ZStack {
                        Color.lumeNavy

                        VStack(spacing: 10) {
                            // Category icon in pastel circle
                            ZStack {
                                Circle()
                                    .fill(Color.white.opacity(0.12))
                                    .frame(width: 48, height: 48)
                                Image(systemName: "book.fill")
                                    .font(.system(size: 20))
                                    .foregroundColor(.lumeGold)
                            }

                            Text(category.name)
                                .font(.lumeDisplaySmall)
                                .foregroundColor(.white)

                            Text("\(category.tasks.count) guide\(category.tasks.count == 1 ? "" : "s")")
                                .font(.lumeCaption)
                                .foregroundColor(.white.opacity(0.6))
                        }
                        .padding(.top, 60)
                        .padding(.bottom, 28)
                    }
                    .cornerRadius(20, corners: [.bottomLeft, .bottomRight])

                    // Pastel category banner
                    HStack(spacing: 12) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(themeColor)
                            .frame(width: 4, height: 28)

                        Text(category.name)
                            .font(.lumeHeadingSmall)
                            .foregroundColor(.lumeNavy)

                        Spacer()
                    }
                    .padding(16)
                    .background(pastelBg)
                    .cornerRadius(14)
                    .overlay(
                        RoundedRectangle(cornerRadius: 14)
                            .stroke(themeColor.opacity(0.12), lineWidth: 1)
                    )
                    .padding(.horizontal, 20)
                    .padding(.top, 16)

                    VStack(spacing: 12) {
                        ForEach(Array(category.tasks.enumerated()), id: \.element.id) { idx, task in
                            GuideTaskCard(
                                task: task,
                                hasFullAccess: hasFullAccess,
                                themeColor: themeColor,
                                pastelBg: categoryBgColors[idx % categoryBgColors.count],
                                bulletIcon: categoryBullets[idx % categoryBullets.count]
                            )
                        }
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, 12)
                    .padding(.bottom, 100)
                }
            }
            .ignoresSafeArea(edges: .top)
        }
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - Task Card

struct GuideTaskCard: View {
    let task: GuideTask
    let hasFullAccess: Bool
    let themeColor: Color
    let pastelBg: Color
    let bulletIcon: String
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Collapsible header
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            } label: {
                HStack(alignment: .center, spacing: 12) {
                    ZStack {
                        Circle()
                            .fill(themeColor.opacity(0.1))
                            .frame(width: 32, height: 32)
                        Image(systemName: bulletIcon)
                            .font(.system(size: 13))
                            .foregroundColor(themeColor)
                    }

                    Text(task.title)
                        .font(.lumeDisplaySmall)
                        .foregroundColor(.lumeNavy)
                        .multilineTextAlignment(.leading)

                    Spacer()
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(themeColor)
                }
                .padding(16)
                .background(pastelBg.opacity(0.6))
            }

            if isExpanded {
                // Color accent bar
                Rectangle()
                    .fill(themeColor)
                    .frame(height: 2)
                    .padding(.horizontal, 16)

                VStack(alignment: .leading, spacing: 18) {
                    if let what = task.what, !what.isEmpty {
                        GuideSectionBlock(title: "What", content: what, color: .lumeNavy)
                    }

                    if let why = task.why, !why.isEmpty {
                        GuideSectionBlock(title: "Why it matters", content: why, color: .lumeNavy)
                    }

                    if hasFullAccess {
                        if let steps = task.steps, !steps.isEmpty {
                            VStack(alignment: .leading, spacing: 10) {
                                Text("Steps")
                                    .font(.lumeHeadingSmall)
                                    .foregroundColor(.lumeNavy)

                                ForEach(Array(steps.enumerated()), id: \.offset) { idx, step in
                                    HStack(alignment: .top, spacing: 10) {
                                        ZStack {
                                            Circle()
                                                .fill(themeColor.opacity(0.1))
                                                .frame(width: 26, height: 26)
                                            Text("\(idx + 1)")
                                                .font(.lumeSmall)
                                                .fontWeight(.bold)
                                                .foregroundColor(themeColor)
                                        }
                                        Text(step)
                                            .font(.lumeBody)
                                            .foregroundColor(.lumeText)
                                            .lineSpacing(3)
                                    }
                                }
                            }
                        }

                        if let terms = task.terms, !terms.isEmpty {
                            VStack(alignment: .leading, spacing: 10) {
                                Text("Key terms")
                                    .font(.lumeHeadingSmall)
                                    .foregroundColor(.lumeNavy)

                                ForEach(terms) { term in
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(term.term)
                                            .font(.lumeBodyMedium)
                                            .foregroundColor(.lumeNavy)
                                        Text(term.def)
                                            .font(.lumeBody)
                                            .foregroundColor(.lumeMuted)
                                            .lineSpacing(2)
                                    }
                                    .padding(14)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .background(pastelBg.opacity(0.5))
                                    .cornerRadius(12)
                                }
                            }
                        }

                        if let mistakes = task.mistakes, !mistakes.isEmpty {
                            VStack(alignment: .leading, spacing: 10) {
                                Text("Good to know")
                                    .font(.lumeHeadingSmall)
                                    .foregroundColor(.lumeGold)

                                ForEach(mistakes, id: \.self) { mistake in
                                    HStack(alignment: .top, spacing: 10) {
                                        Image(systemName: "lightbulb.fill")
                                            .font(.system(size: 12))
                                            .foregroundColor(.lumeGold)
                                            .padding(.top, 2)
                                        Text(mistake)
                                            .font(.lumeBody)
                                            .foregroundColor(.lumeText)
                                            .lineSpacing(2)
                                    }
                                }
                            }
                        }

                        if let script = task.script {
                            VStack(alignment: .leading, spacing: 10) {
                                Text("What to say")
                                    .font(.lumeHeadingSmall)
                                    .foregroundColor(.lumeNavy)

                                if let intro = script.intro {
                                    Text(intro)
                                        .font(.lumeBodyLight)
                                        .foregroundColor(.lumeMuted)
                                        .italic()
                                }

                                if let lines = script.lines {
                                    ForEach(lines, id: \.self) { line in
                                        Text("\"\(line)\"")
                                            .font(.lumeBody)
                                            .foregroundColor(.lumeText)
                                            .italic()
                                            .padding(14)
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                            .background(pastelBg.opacity(0.5))
                                            .cornerRadius(12)
                                    }
                                }

                                if let note = script.note {
                                    Text(note)
                                        .font(.lumeSmall)
                                        .foregroundColor(.lumeMuted)
                                        .italic()
                                }
                            }
                        }

                        if let contacts = task.contacts, !contacts.isEmpty {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Contact")
                                    .font(.lumeHeadingSmall)
                                    .foregroundColor(.lumeNavy)
                                Text(contacts)
                                    .font(.lumeBody)
                                    .foregroundColor(.lumeMuted)
                            }
                        }
                    } else {
                        UpgradePromptCard(themeColor: themeColor)
                    }
                }
                .padding(16)
                .background(Color.lumeWarmWhite)
            }
        }
        .background(Color.lumeWarmWhite)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(themeColor.opacity(0.12), lineWidth: 1)
        )
    }
}

// MARK: - Helper Views

struct GuideSectionBlock: View {
    let title: String
    let content: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.lumeHeadingSmall)
                .foregroundColor(color)
            Text(content)
                .font(.lumeBody)
                .foregroundColor(.lumeText)
                .lineSpacing(3)
        }
    }
}

struct UpgradePromptCard: View {
    let themeColor: Color

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "lock.fill")
                .font(.system(size: 20))
                .foregroundColor(.lumeGold)
            Text("Unlock full guide")
                .font(.lumeBodyMedium)
                .foregroundColor(.lumeNavy)
            Text("Get step-by-step instructions,\nscripts, and expert tips.")
                .font(.lumeSmall)
                .foregroundColor(.lumeMuted)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(24)
        .background(themeColor.opacity(0.04))
        .cornerRadius(14)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(themeColor.opacity(0.15), lineWidth: 1)
        )
    }
}
