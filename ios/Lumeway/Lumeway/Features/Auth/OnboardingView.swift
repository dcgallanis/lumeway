import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject var appState: AppState

    @State private var selectedTransition: String?
    @State private var isSaving = false

    private let transitions: [(key: String, label: String, emoji: String, desc: String)] = [
        ("job-loss", "Job Loss & Income Crisis", "💼", "Laid off, fired, or furloughed"),
        ("estate", "Death & Estate", "🕊️", "Navigating loss and estate settlement"),
        ("divorce", "Divorce & Separation", "⚖️", "Ending a marriage or partnership"),
        ("disability", "Disability & Benefits", "🩺", "New diagnosis or disability claim"),
        ("relocation", "Moving & Relocation", "🏠", "Moving to a new city or state"),
        ("retirement", "Retirement Planning", "🌅", "Planning your next chapter"),
        // ("addiction", "Addiction & Recovery", "🫂", "Supporting a loved one"),  // hidden until launch
    ]

    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()

            ScrollView {
                VStack(spacing: 0) {
                    Spacer().frame(height: 60)

                    VStack(spacing: 8) {
                        Text("What are you\ngoing through?")
                            .font(.lumeHeadingMedium)
                            .foregroundColor(.lumeText)
                            .multilineTextAlignment(.center)

                        Text("This helps us show you the right steps.")
                            .font(.lumeCaptionLight)
                            .foregroundColor(.lumeMuted)
                    }
                    .padding(.bottom, 32)

                    // Transition grid
                    LazyVGrid(columns: [
                        GridItem(.flexible(), spacing: 12),
                        GridItem(.flexible(), spacing: 12)
                    ], spacing: 12) {
                        ForEach(transitions, id: \.key) { item in
                            TransitionCard(
                                emoji: item.emoji,
                                label: item.label,
                                desc: item.desc,
                                isSelected: selectedTransition == item.key
                            ) {
                                withAnimation(.easeInOut(duration: 0.15)) {
                                    selectedTransition = item.key
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 24)
                    .padding(.bottom, 32)

                    // Continue button
                    if let selected = selectedTransition {
                        Button {
                            Task { await saveTransition(selected) }
                        } label: {
                            if isSaving {
                                ProgressView().tint(.white)
                            } else {
                                Text("Continue")
                            }
                        }
                        .buttonStyle(LumePrimaryButtonStyle())
                        .frame(maxWidth: .infinity)
                        .padding(.horizontal, 32)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    }

                    Spacer().frame(height: 48)
                }
            }
        }
    }

    private func saveTransition(_ transition: String) async {
        isSaving = true
        defer { isSaving = false }

        let dashService = DashboardService()
        let checklistService = ChecklistService()

        // Save transition type to user profile
        do {
            try await dashService.updateSettings(
                displayName: nil,
                usState: nil,
                transitionType: transition
            )
        } catch {
            // Continue anyway — we can retry later
        }

        // Initialize checklist for this transition
        do {
            _ = try await checklistService.initChecklist(transitionType: transition)
        } catch {
            // Continue — checklist can be initialized later
        }

        appState.needsOnboarding = false
    }
}

struct TransitionCard: View {
    let emoji: String
    let label: String
    let desc: String
    let isSelected: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 8) {
                Text(emoji)
                    .font(.lumeDisplayMedium)

                Text(label)
                    .font(.lumeCaption)
                    .fontWeight(.medium)
                    .foregroundColor(.lumeText)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)

                Text(desc)
                    .font(.lumeSmall)
                    .foregroundColor(.lumeMuted)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 20)
            .padding(.horizontal, 12)
            .background(isSelected ? Color.lumeNavy.opacity(0.06) : Color.lumeWarmWhite)
            .cornerRadius(16)
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(isSelected ? Color.lumeNavy : Color.lumeBorder, lineWidth: isSelected ? 2 : 1)
            )
        }
    }
}
