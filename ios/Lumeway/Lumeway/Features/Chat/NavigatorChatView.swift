import SwiftUI

struct NavigatorChatView: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) var dismiss

    @State private var messages: [ChatMessage] = []
    @State private var inputText = ""
    @State private var isStreaming = false
    @State private var scrollToBottom = false

    private let api = APIClient.shared

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Messages
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(spacing: 16) {
                                // Welcome message with suggestion pills
                                if messages.isEmpty {
                                    WelcomeBubble(onSuggestionTap: { suggestion in
                                        inputText = suggestion
                                        sendMessage()
                                    })
                                    .padding(.top, 24)
                                }

                                ForEach(messages) { msg in
                                    ChatBubble(message: msg, onSave: msg.role == .assistant ? {
                                        saveMessageAsNote(msg.content)
                                    } : nil)
                                        .id(msg.id)
                                }

                                if isStreaming {
                                    HStack {
                                        TypingIndicator()
                                        Spacer()
                                    }
                                    .padding(.horizontal, 24)
                                    .id("typing")
                                }
                            }
                            .padding(.horizontal, 16)
                            .padding(.bottom, 16)
                        }
                        .onChange(of: messages.count) { _, _ in
                            withAnimation {
                                proxy.scrollTo(messages.last?.id, anchor: .bottom)
                            }
                        }
                        .onChange(of: isStreaming) { _, streaming in
                            if streaming {
                                withAnimation {
                                    proxy.scrollTo("typing", anchor: .bottom)
                                }
                            }
                        }
                    }

                    Divider()

                    // Input bar
                    HStack(spacing: 12) {
                        TextField("Ask anything...", text: $inputText, axis: .vertical)
                            .font(.lumeBody)
                            .foregroundColor(.lumeText)
                            .lineLimit(1...4)
                            .padding(12)
                            .background(Color.lumeWarmWhite)
                            .cornerRadius(20)
                            .overlay(
                                RoundedRectangle(cornerRadius: 20)
                                    .stroke(Color.lumeBorder, lineWidth: 1)
                            )

                        Button {
                            sendMessage()
                        } label: {
                            Image(systemName: "arrow.up.circle.fill")
                                .font(.system(size: 32))
                                .foregroundColor(inputText.trimmingCharacters(in: .whitespaces).isEmpty ? .lumeBorder : .lumeNavy)
                        }
                        .disabled(inputText.trimmingCharacters(in: .whitespaces).isEmpty || isStreaming)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(Color.lumeCream)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.lumeCream, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    VStack(spacing: 1) {
                        Text("Navigator")
                            .font(.lumeBodyMedium)
                            .foregroundColor(.lumeText)
                        Text("AI Assistant")
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        messages = []
                        inputText = ""
                    } label: {
                        Image(systemName: "arrow.counterclockwise.circle.fill")
                            .foregroundColor(.lumeMuted)
                    }
                }
            }
        }
    }

    private let notesService = NotesService()

    private func saveMessageAsNote(_ content: String) {
        Task {
            _ = try? await notesService.createNote(content: "From Navigator chat:\n\n\(content)")
        }
    }

    private func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }

        let userMsg = ChatMessage(id: UUID().uuidString, role: .user, content: text)
        messages.append(userMsg)
        inputText = ""

        Task {
            await streamResponse(for: text)
        }
    }

    private func streamResponse(for question: String) async {
        isStreaming = true
        defer { isStreaming = false }

        let assistantId = UUID().uuidString
        var accumulated = ""

        do {
            let body: [String: Any] = ["message": question]
            let stream = api.stream("/api/chat", body: body)

            for try await chunk in stream {
                accumulated += chunk
                // Update or create the assistant message
                if let idx = messages.firstIndex(where: { $0.id == assistantId }) {
                    messages[idx] = ChatMessage(id: assistantId, role: .assistant, content: accumulated)
                } else {
                    messages.append(ChatMessage(id: assistantId, role: .assistant, content: accumulated))
                }
            }
        } catch {
            let errorMsg = ChatMessage(
                id: assistantId,
                role: .assistant,
                content: "I'm having trouble connecting right now. Please try again in a moment."
            )
            if let idx = messages.firstIndex(where: { $0.id == assistantId }) {
                messages[idx] = errorMsg
            } else {
                messages.append(errorMsg)
            }
        }
    }
}

// MARK: - Data

struct ChatMessage: Identifiable {
    let id: String
    let role: MessageRole
    let content: String

    enum MessageRole {
        case user, assistant
    }
}

// MARK: - Chat Bubble

struct ChatBubble: View {
    let message: ChatMessage
    var onSave: (() -> Void)?
    @State private var saved = false

    var body: some View {
        VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 6) {
            HStack {
                if message.role == .user { Spacer(minLength: 60) }

                Text(message.content)
                    .font(.lumeBody)
                    .foregroundColor(message.role == .user ? .white : .lumeText)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(
                        message.role == .user ? Color.lumeNavy : Color.lumeWarmWhite
                    )
                    .cornerRadius(20)
                    .overlay(
                        message.role == .assistant ?
                        RoundedRectangle(cornerRadius: 20)
                            .stroke(Color.lumeBorder, lineWidth: 1) : nil
                    )

                if message.role == .assistant { Spacer(minLength: 60) }
            }

            // Save button for assistant messages
            if message.role == .assistant {
                Button {
                    saved = true
                    onSave?()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: saved ? "bookmark.fill" : "bookmark")
                            .font(.system(size: 11))
                        Text(saved ? "Saved" : "Save")
                            .font(.lumeSmall)
                    }
                    .foregroundColor(saved ? .lumeGreen : .lumeMuted)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                }
            }
        }
        .padding(.horizontal, 8)
    }
}

// MARK: - Welcome Bubble

struct WelcomeBubble: View {
    var onSuggestionTap: ((String) -> Void)?

    private let suggestions = [
        "What should I do first?",
        "Explain my checklist",
        "What documents do I need?",
        "Help me understand deadlines",
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Hi, I'm your Lumeway Navigator.")
                        .font(.lumeBodyMedium)
                        .foregroundColor(.lumeText)
                    Text("I can help you understand your checklist, explain next steps, or answer any questions.")
                        .font(.lumeBody)
                        .foregroundColor(.lumeMuted)
                }
                Spacer(minLength: 20)
            }
            .padding(16)
            .background(Color.lumeWarmWhite)
            .cornerRadius(20)
            .overlay(
                RoundedRectangle(cornerRadius: 20)
                    .stroke(Color.lumeBorder, lineWidth: 1)
            )

            // Suggestion pills
            FlowLayout(spacing: 8) {
                ForEach(suggestions, id: \.self) { suggestion in
                    Button {
                        onSuggestionTap?(suggestion)
                    } label: {
                        Text(suggestion)
                            .font(.lumeCaption)
                            .foregroundColor(.lumeNavy)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 9)
                            .background(Color.lumeWarmWhite)
                            .cornerRadius(20)
                            .overlay(
                                RoundedRectangle(cornerRadius: 20)
                                    .stroke(Color.lumeBorder, lineWidth: 1)
                            )
                    }
                }
            }
        }
        .padding(.horizontal, 8)
    }
}

// MARK: - Flow Layout for pills

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = computeLayout(proposal: proposal, subviews: subviews)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = computeLayout(proposal: proposal, subviews: subviews)
        for (index, position) in result.positions.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y), proposal: .unspecified)
        }
    }

    private func computeLayout(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, positions: [CGPoint]) {
        let maxWidth = proposal.width ?? .infinity
        var positions: [CGPoint] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0

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
        }

        return (CGSize(width: maxWidth, height: y + rowHeight), positions)
    }
}

// MARK: - Typing Indicator

struct TypingIndicator: View {
    @State private var dotIndex = 0
    private let timer = Timer.publish(every: 0.4, on: .main, in: .common).autoconnect()

    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .fill(Color.lumeMuted)
                    .frame(width: 6, height: 6)
                    .opacity(dotIndex == i ? 1 : 0.3)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(Color.lumeWarmWhite)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.lumeBorder, lineWidth: 1)
        )
        .onReceive(timer) { _ in
            dotIndex = (dotIndex + 1) % 3
        }
    }
}
