import SwiftUI

struct GuidesView: View {
    @EnvironmentObject var appState: AppState
    @State private var guideData: GuideDetailResponse?
    @State private var isLoading = true
    @State private var searchText = ""

    private let service = GuideService()

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                if isLoading {
                    ProgressView()
                        .tint(.lumeAccent)
                } else if let guide = guideData, !guide.guide.categories.isEmpty {
                    ScrollView {
                        LazyVGrid(columns: [
                            GridItem(.flexible(), spacing: 12),
                            GridItem(.flexible(), spacing: 12)
                        ], spacing: 12) {
                            ForEach(filteredCategories) { cat in
                                NavigationLink {
                                    GuideCategoryDetailView(
                                        category: cat,
                                        hasFullAccess: guide.hasFullAccess
                                    )
                                } label: {
                                    GuideCategoryCard(
                                        label: cat.name,
                                        taskCount: cat.tasks.count
                                    )
                                }
                            }
                        }
                        .padding(24)
                    }
                } else {
                    VStack(spacing: 16) {
                        Image(systemName: "book")
                            .font(.system(size: 48, weight: .light))
                            .foregroundColor(.lumeMuted)
                        Text("Your guide library will appear here")
                            .font(.lumeBody)
                            .foregroundColor(.lumeMuted)
                        Text("Guides are tailored to your\ntransition type.")
                            .font(.lumeCaptionLight)
                            .foregroundColor(.lumeMuted)
                            .multilineTextAlignment(.center)
                    }
                }
            }
            .navigationTitle("Guides")
            .navigationBarTitleDisplayMode(.large)
            .searchable(text: $searchText, prompt: "Search guides")
            .task { await loadGuides() }
            .refreshable { await loadGuides() }
        }
    }

    private var filteredCategories: [GuideCategory] {
        guard let cats = guideData?.guide.categories else { return [] }
        if searchText.isEmpty { return cats }
        return cats.filter { cat in
            cat.name.localizedCaseInsensitiveContains(searchText) ||
            cat.tasks.contains(where: { $0.title.localizedCaseInsensitiveContains(searchText) })
        }
    }

    private func loadGuides() async {
        guard let transition = appState.user?.transitionType else {
            isLoading = false
            return
        }
        do {
            guideData = try await service.getGuide(transition: transition)
            isLoading = false
        } catch {
            isLoading = false
            print("Guide load error: \(error)")
        }
    }
}

// MARK: - Category Card

struct GuideCategoryCard: View {
    let label: String
    let taskCount: Int

    var body: some View {
        VStack(spacing: 8) {
            Text(label)
                .font(.lumeCaption)
                .fontWeight(.medium)
                .foregroundColor(.lumeText)
                .multilineTextAlignment(.center)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)

            Text("\(taskCount) guide\(taskCount == 1 ? "" : "s")")
                .font(.lumeSmall)
                .foregroundColor(.lumeMuted)

        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 20)
        .padding(.horizontal, 12)
        .background(Color.lumeWarmWhite)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.lumeBorder, lineWidth: 1)
        )
    }
}

// MARK: - Category Detail View

struct GuideCategoryDetailView: View {
    let category: GuideCategory
    let hasFullAccess: Bool

    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()

            ScrollView {
                VStack(spacing: 16) {
                    ForEach(category.tasks) { task in
                        GuideTaskCard(task: task, hasFullAccess: hasFullAccess)
                    }
                }
                .padding(24)
            }
        }
        .navigationTitle(category.name)
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - Task Card

struct GuideTaskCard: View {
    let task: GuideTask
    let hasFullAccess: Bool
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header (always visible)
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            } label: {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(task.title)
                            .font(.lumeBodyMedium)
                            .foregroundColor(.lumeText)
                            .multilineTextAlignment(.leading)

                        }
                    Spacer()
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.lumeMuted)
                }
                .padding(16)
            }

            if isExpanded {
                Divider().padding(.horizontal, 16)

                VStack(alignment: .leading, spacing: 16) {
                    // What
                    if let what = task.what, !what.isEmpty {
                        GuideSection(title: "What", content: what)
                    }

                    // Why
                    if let why = task.why, !why.isEmpty {
                        GuideSection(title: "Why it matters", content: why)
                    }

                    // Steps (gated for free users)
                    if hasFullAccess {
                        if let steps = task.steps, !steps.isEmpty {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Steps")
                                    .font(.lumeCaption)
                                    .fontWeight(.semibold)
                                    .foregroundColor(.lumeNavy)

                                ForEach(Array(steps.enumerated()), id: \.offset) { idx, step in
                                    HStack(alignment: .top, spacing: 8) {
                                        Text("\(idx + 1).")
                                            .font(.lumeCaption)
                                            .foregroundColor(.lumeGold)
                                            .frame(width: 20, alignment: .trailing)
                                        Text(step)
                                            .font(.lumeBody)
                                            .foregroundColor(.lumeText)
                                    }
                                }
                            }
                        }

                        // Terms
                        if let terms = task.terms, !terms.isEmpty {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Key terms")
                                    .font(.lumeCaption)
                                    .fontWeight(.semibold)
                                    .foregroundColor(.lumeNavy)

                                ForEach(terms) { term in
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(term.term)
                                            .font(.lumeCaption)
                                            .fontWeight(.medium)
                                            .foregroundColor(.lumeText)
                                        Text(term.def)
                                            .font(.lumeSmall)
                                            .foregroundColor(.lumeMuted)
                                    }
                                }
                            }
                        }

                        // Mistakes
                        if let mistakes = task.mistakes, !mistakes.isEmpty {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Common mistakes")
                                    .font(.lumeCaption)
                                    .fontWeight(.semibold)
                                    .foregroundColor(.lumeAccent)

                                ForEach(mistakes, id: \.self) { mistake in
                                    HStack(alignment: .top, spacing: 8) {
                                        Image(systemName: "exclamationmark.triangle.fill")
                                            .font(.system(size: 12))
                                            .foregroundColor(.lumeAccent)
                                        Text(mistake)
                                            .font(.lumeSmall)
                                            .foregroundColor(.lumeText)
                                    }
                                }
                            }
                        }

                        // Script
                        if let script = task.script {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Script")
                                    .font(.lumeCaption)
                                    .fontWeight(.semibold)
                                    .foregroundColor(.lumeNavy)

                                if let intro = script.intro {
                                    Text(intro)
                                        .font(.lumeSmall)
                                        .foregroundColor(.lumeMuted)
                                        .italic()
                                }

                                if let lines = script.lines {
                                    ForEach(lines, id: \.self) { line in
                                        Text("\"" + line + "\"")
                                            .font(.lumeBody)
                                            .foregroundColor(.lumeText)
                                            .padding(12)
                                            .background(Color.lumeNavy.opacity(0.04))
                                            .cornerRadius(8)
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

                        // Contacts
                        if let contacts = task.contacts, !contacts.isEmpty {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Contact")
                                    .font(.lumeCaption)
                                    .fontWeight(.semibold)
                                    .foregroundColor(.lumeNavy)
                                Text(contacts)
                                    .font(.lumeSmall)
                                    .foregroundColor(.lumeMuted)
                            }
                        }
                    } else {
                        // Upgrade prompt for free users
                        UpgradePromptCard()
                    }
                }
                .padding(16)
            }
        }
        .background(Color.lumeWarmWhite)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.lumeBorder, lineWidth: 1)
        )
    }
}

// MARK: - Helper Views

struct GuideSection: View {
    let title: String
    let content: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.lumeCaption)
                .fontWeight(.semibold)
                .foregroundColor(.lumeNavy)
            Text(content)
                .font(.lumeBody)
                .foregroundColor(.lumeText)
                .lineSpacing(3)
        }
    }
}

struct UpgradePromptCard: View {
    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "lock.fill")
                .font(.system(size: 20))
                .foregroundColor(.lumeGold)
            Text("Full guide content")
                .font(.lumeCaption)
                .fontWeight(.medium)
                .foregroundColor(.lumeText)
            Text("Unlock step-by-step instructions, scripts, and expert tips.")
                .font(.lumeSmall)
                .foregroundColor(.lumeMuted)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(20)
        .background(Color.lumeGold.opacity(0.06))
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.lumeGold.opacity(0.3), lineWidth: 1)
        )
    }
}
