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
                                // Welcome message
                                if messages.isEmpty {
                                    WelcomeBubble()
                                        .padding(.top, 24)
                                }

                                ForEach(messages) { msg in
                                    ChatBubble(message: msg)
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
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.lumeMuted)
                    }
                }
            }
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

    var body: some View {
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
        .padding(.horizontal, 8)
    }
}

// MARK: - Welcome Bubble

struct WelcomeBubble: View {
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 8) {
                Text("Hi, I'm your Lumeway Navigator.")
                    .font(.lumeBodyMedium)
                    .foregroundColor(.lumeText)
                Text("I can help you understand your checklist, explain next steps, or answer questions about your transition. What would you like to know?")
                    .font(.lumeBody)
                    .foregroundColor(.lumeMuted)
            }
            .padding(16)
            .background(Color.lumeWarmWhite)
            .cornerRadius(20)
            .overlay(
                RoundedRectangle(cornerRadius: 20)
                    .stroke(Color.lumeBorder, lineWidth: 1)
            )

            Spacer(minLength: 40)
        }
        .padding(.horizontal, 8)
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
