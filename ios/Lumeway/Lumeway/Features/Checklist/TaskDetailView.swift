import SwiftUI

struct TaskDetailView: View {
    let item: FullChecklistItem
    let color: Color

    @Environment(\.dismiss) var dismiss
    @State private var guide: ItemGuideResponse?
    @State private var isLoading = true
    @State private var loadError = false

    private let guideService = GuideService()

    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    // Header with back button and title
                    VStack(alignment: .leading, spacing: 12) {
                        Button {
                            dismiss()
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "chevron.left")
                                    .font(.system(size: 14, weight: .semibold))
                                Text("Back")
                                    .font(.lumeBody)
                            }
                            .foregroundColor(color)
                        }

                        Text(item.title)
                            .font(.lumeHeadingSmall)
                            .foregroundColor(.lumeNavy)
                    }
                    .padding(.horizontal, 24)
                    .padding(.top, 16)
                    .padding(.bottom, 20)

                    if isLoading {
                        HStack {
                            Spacer()
                            ProgressView()
                                .tint(.lumeAccent)
                                .padding(.vertical, 40)
                            Spacer()
                        }
                    } else if let guide = guide, guide.found {
                        VStack(alignment: .leading, spacing: 20) {
                            // Urgency tag
                            if let urgency = guide.urgency {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text("URGENCY")
                                        .font(.system(size: 11, weight: .semibold))
                                        .tracking(0.5)
                                        .foregroundColor(.lumeMuted)

                                    Text(urgency)
                                        .font(.lumeCaption)
                                        .fontWeight(.medium)
                                        .foregroundColor(urgencyColor(urgency))
                                        .padding(.horizontal, 12)
                                        .padding(.vertical, 5)
                                        .background(urgencyColor(urgency).opacity(0.1))
                                        .cornerRadius(6)
                                }
                            }

                            // How to do this
                            if let howTo = guide.howTo, !howTo.isEmpty {
                                VStack(alignment: .leading, spacing: 10) {
                                    Text("HOW TO DO THIS")
                                        .font(.system(size: 12, weight: .semibold))
                                        .tracking(0.5)
                                        .foregroundColor(Color(hex: "4A7C59"))

                                    Text(howTo)
                                        .font(.lumeBody)
                                        .foregroundColor(.lumeText)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                .padding(18)
                                .background(Color(hex: "4A7C59").opacity(0.06))
                                .cornerRadius(14)
                            }

                            // Steps
                            if let steps = guide.steps, !steps.isEmpty {
                                VStack(alignment: .leading, spacing: 12) {
                                    Text("STEPS")
                                        .font(.system(size: 11, weight: .semibold))
                                        .tracking(0.5)
                                        .foregroundColor(.lumeMuted)

                                    ForEach(Array(steps.enumerated()), id: \.offset) { index, step in
                                        HStack(alignment: .top, spacing: 12) {
                                            Text("\(index + 1)")
                                                .font(.system(size: 13, weight: .bold))
                                                .foregroundColor(color)
                                                .frame(width: 24, height: 24)
                                                .background(color.opacity(0.1))
                                                .cornerRadius(12)

                                            Text(step)
                                                .font(.lumeBody)
                                                .foregroundColor(.lumeText)
                                                .fixedSize(horizontal: false, vertical: true)
                                        }
                                    }
                                }
                            }

                            // Related worksheet
                            if let worksheet = guide.relatedWorksheet, !worksheet.isEmpty {
                                VStack(alignment: .leading, spacing: 10) {
                                    Text("RELATED WORKSHEET")
                                        .font(.system(size: 12, weight: .semibold))
                                        .tracking(0.5)
                                        .foregroundColor(Color(hex: "5E8C9A"))

                                    HStack {
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(worksheet)
                                                .font(.lumeBodyMedium)
                                                .foregroundColor(.lumeNavy)
                                        }
                                        Spacer()
                                        Image(systemName: "chevron.right")
                                            .font(.system(size: 12))
                                            .foregroundColor(.lumeBorder)
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
                        .padding(.horizontal, 24)
                    } else {
                        // No guide found — show generic encouragement
                        VStack(spacing: 16) {
                            Image(systemName: "lightbulb.fill")
                                .font(.system(size: 32))
                                .foregroundColor(.lumeGold)

                            Text("Guide details are being added for this task. In the meantime, you can use the Navigator chat for personalized help.")
                                .font(.lumeBody)
                                .foregroundColor(.lumeMuted)
                                .multilineTextAlignment(.center)
                        }
                        .padding(32)
                    }

                    Spacer().frame(height: 60)
                }
            }
        }
        .navigationBarHidden(true)
        .task {
            await loadGuide()
        }
    }

    private func loadGuide() async {
        do {
            guide = try await guideService.getItemGuide(itemId: item.id)
            isLoading = false
        } catch {
            isLoading = false
            loadError = true
        }
    }

    private func urgencyColor(_ urgency: String) -> Color {
        let lower = urgency.lowercased()
        if lower.contains("24 hour") || lower.contains("today") { return .lumeAccent }
        if lower.contains("7 day") || lower.contains("week") { return .lumeGold }
        if lower.contains("30 day") || lower.contains("month") { return Color(hex: "5E8C9A") }
        return .lumeMuted
    }
}
