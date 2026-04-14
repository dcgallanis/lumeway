import SwiftUI

@MainActor
final class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var inputText = ""
    @Published var isStreaming = false
    @Published var sessionId: String? = nil {
        didSet {
            // Persist session ID so chat memory survives app restarts
            if let sid = sessionId {
                UserDefaults.standard.set(sid, forKey: "nc_last_session_id")
            } else {
                UserDefaults.standard.removeObject(forKey: "nc_last_session_id")
            }
        }
    }
    @Published var conversationHistory: [[String: String]] = []
    @Published var hasLoadedInitialSession = false

    let api = APIClient.shared
    let notesService = NotesService()

    /// Restore the most recent conversation on first load
    func loadMostRecentSession() async {
        guard !hasLoadedInitialSession else { return }
        hasLoadedInitialSession = true

        // First try the persisted session ID
        if let lastSid = UserDefaults.standard.string(forKey: "nc_last_session_id") {
            do {
                let response: ChatHistoryResponse = try await api.get("/api/dashboard/history/\(lastSid)")
                if !response.messages.isEmpty {
                    restoreSession(sid: lastSid, messages: response.messages)
                    return
                }
            } catch {
                // Session may have been deleted or expired — fall through
            }
        }

        // Fallback: fetch session list and load the most recent one
        do {
            let sessionsResponse: ChatSessionsResponse = try await api.get("/api/chat/sessions")
            if let latest = sessionsResponse.sessions.first {
                let response: ChatHistoryResponse = try await api.get("/api/dashboard/history/\(latest.id)")
                if !response.messages.isEmpty {
                    restoreSession(sid: latest.id, messages: response.messages)
                }
            }
        } catch {
            print("Could not load recent chat session: \(error)")
        }
    }

    func restoreSession(sid: String, messages: [ChatHistoryMessage]) {
        self.sessionId = sid
        self.messages = messages.enumerated().map { index, msg in
            ChatMessage(
                id: "\(sid)-\(index)",
                role: msg.role == "user" ? .user : .assistant,
                content: msg.content
            )
        }
        self.conversationHistory = messages.map { ["role": $0.role, "content": $0.content] }
    }
}

struct NavigatorChatView: View {
    var isEmbedded: Bool = false

    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) var dismiss

    @EnvironmentObject var vm: ChatViewModel
    @State private var showHistory = false

    var body: some View {
        OptionalNavigationStack(isEmbedded: isEmbedded) {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Messages
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(spacing: 16) {
                                // Welcome message with suggestion pills
                                if vm.messages.isEmpty {
                                    WelcomeBubble(onSuggestionTap: { suggestion in
                                        vm.inputText = suggestion
                                        sendMessage()
                                    }, activeTransitions: appState.activeTransitions)
                                    .padding(.top, 24)
                                }

                                ForEach(vm.messages) { msg in
                                    ChatBubble(message: msg, onSave: msg.role == .assistant ? {
                                        saveChatToChecklist()
                                    } : nil, onQuickReply: msg.role == .assistant ? { reply in
                                        vm.inputText = reply
                                        sendMessage()
                                    } : nil)
                                        .id(msg.id)
                                }

                                if vm.isStreaming {
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
                        .onChange(of: vm.messages.count) { _, _ in
                            withAnimation {
                                proxy.scrollTo(vm.messages.last?.id, anchor: .bottom)
                            }
                        }
                        .onChange(of: vm.isStreaming) { _, streaming in
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
                        TextField("Tell me what\u{2019}s going on\u{2026}", text: $vm.inputText, axis: .vertical)
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
                                .foregroundColor(vm.inputText.trimmingCharacters(in: .whitespaces).isEmpty ? .lumeBorder : .lumeNavy)
                        }
                        .disabled(vm.inputText.trimmingCharacters(in: .whitespaces).isEmpty || vm.isStreaming)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(Color.lumeCream)

                    // Footer disclaimer
                    Text("Lumeway is a guidance tool, not a licensed professional. Always consult a qualified advisor.")
                        .font(.system(size: 11))
                        .foregroundColor(.lumeMuted)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 24)
                        .padding(.bottom, 8)
                        .background(Color.lumeCream)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.lumeCream, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.light, for: .navigationBar)
            .tint(.lumeNavy)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    VStack(spacing: 1) {
                        Text("Navigator")
                            .font(.lumeBodyMedium)
                            .foregroundColor(.lumeText)
                        Text("Your Navigator")
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Menu {
                        Button {
                            showHistory = true
                        } label: {
                            Label("Chat History", systemImage: "clock.arrow.circlepath")
                        }
                        Button {
                            saveChatToChecklist()
                        } label: {
                            Label("Save to Checklist", systemImage: "checklist")
                        }
                        Button {
                            vm.messages = []
                            vm.inputText = ""
                            vm.sessionId = nil
                            vm.conversationHistory = []
                        } label: {
                            Label("New Conversation", systemImage: "arrow.counterclockwise")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                            .foregroundColor(.lumeMuted)
                    }
                }
            }
            .sheet(isPresented: $showHistory) {
                ChatHistorySheet(onSelectSession: { session in
                    showHistory = false
                    Task { await loadSession(session.id) }
                })
                .environmentObject(appState)
            }
            .onAppear {
                Task { await vm.loadMostRecentSession() }
            }
        }
    }

    private func saveChatToChecklist() {
        Task {
            // Build conversation history for the init-from-chat endpoint
            let history = vm.messages.map { msg -> [String: String] in
                ["role": msg.role == .user ? "user" : "assistant", "content": msg.content]
            }
            guard !history.isEmpty else { return }

            // Determine transition type from app state
            let transitionType = appState.user?.transitionType ?? appState.activeTransitions.first ?? "general"

            do {
                let body: [String: Any] = [
                    "history": history,
                    "transition_type": transitionType
                ]
                let _: SimpleOkResponse = try await vm.api.post("/api/checklist/init-from-chat", body: body)
            } catch {
                // Fallback: save as note if checklist extraction fails
                _ = try? await vm.notesService.createNote(content: "From Navigator chat:\n\n\(vm.messages.last(where: { $0.role == .assistant })?.content ?? "")")
            }
        }
    }

    private func sendMessage() {
        let text = vm.inputText.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }

        let userMsg = ChatMessage(id: UUID().uuidString, role: .user, content: text)
        vm.messages.append(userMsg)
        vm.inputText = ""

        Task {
            await streamResponse(for: text)
        }
    }

    private func streamResponse(for question: String) async {
        vm.isStreaming = true
        defer { vm.isStreaming = false }

        let assistantId = UUID().uuidString
        var accumulated = ""

        do {
            var body: [String: Any] = [
                "message": question,
                "history": vm.conversationHistory.map { $0 as [String: Any] }
            ]
            if let sid = vm.sessionId {
                body["session_id"] = sid
            }

            let stream = vm.api.stream("/chat", body: body)

            for try await chunk in stream {
                if chunk.hasPrefix("[DONE]") {
                    let jsonStr = String(chunk.dropFirst(6))
                    if let data = jsonStr.data(using: .utf8),
                       let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                        if let sid = json["session_id"] as? String {
                            vm.sessionId = sid
                        }
                        if let history = json["history"] as? [[String: String]] {
                            vm.conversationHistory = history
                        }
                    }
                    continue
                }

                accumulated += chunk
                if let idx = vm.messages.firstIndex(where: { $0.id == assistantId }) {
                    vm.messages[idx] = ChatMessage(id: assistantId, role: .assistant, content: accumulated)
                } else {
                    vm.messages.append(ChatMessage(id: assistantId, role: .assistant, content: accumulated))
                }
            }
        } catch {
            let errorMsg = ChatMessage(
                id: assistantId,
                role: .assistant,
                content: "I'm having trouble connecting right now. Please try again in a moment."
            )
            if let idx = vm.messages.firstIndex(where: { $0.id == assistantId }) {
                vm.messages[idx] = errorMsg
            } else {
                vm.messages.append(errorMsg)
            }
        }
    }

    private func loadSession(_ sid: String) async {
        do {
            let response: ChatHistoryResponse = try await vm.api.get("/api/dashboard/history/\(sid)")
            vm.restoreSession(sid: sid, messages: response.messages)
        } catch {
            print("Failed to load session: \(error)")
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
    var onQuickReply: ((String) -> Void)?
    @State private var saved = false

    /// Parse quick replies from `[QUICK_REPLIES: A | B | C]` and return (cleaned text, options).
    private var parsed: (text: String, quickReplies: [String]) {
        let content = message.content
        let pattern = #"\[QUICK_REPLIES:\s*(.+?)\]"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: content, range: NSRange(content.startIndex..., in: content)),
              let repliesRange = Range(match.range(at: 1), in: content) else {
            return (content, [])
        }
        let replies = content[repliesRange]
            .split(separator: "|")
            .map { $0.trimmingCharacters(in: .whitespaces) }
        let cleaned = content.replacingOccurrences(of: pattern, with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return (cleaned, replies)
    }

    private func renderMarkdown(_ text: String) -> Text {
        if let attributed = try? AttributedString(markdown: text, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
            return Text(attributed)
        }
        return Text(text)
    }

    var body: some View {
        VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 6) {
            HStack {
                if message.role == .user { Spacer(minLength: 60) }

                renderMarkdown(parsed.text)
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

            // Quick reply pills for assistant messages
            if message.role == .assistant && !parsed.quickReplies.isEmpty {
                FlowLayout(spacing: 8) {
                    ForEach(parsed.quickReplies, id: \.self) { reply in
                        Button {
                            onQuickReply?(reply)
                        } label: {
                            Text(reply)
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
                .padding(.top, 4)
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
    var activeTransitions: [String] = []

    private var starters: [String] {
        // If user has active transitions, show context-aware starters
        if !activeTransitions.isEmpty {
            var contextStarters: [String] = [
                "What should I focus on next?",
                "Help me understand my checklist",
                "I have a question about a deadline",
            ]
            // Add transition-specific starters
            for transition in activeTransitions.prefix(2) {
                switch transition {
                case "job-loss":
                    contextStarters.insert("What\u{2019}s the most urgent thing for my job loss situation?", at: 0)
                case "estate":
                    contextStarters.insert("Walk me through what I need to handle for the estate", at: 0)
                case "divorce":
                    contextStarters.insert("What should I be documenting for my divorce?", at: 0)
                case "disability":
                    contextStarters.insert("Help me with my disability benefits application", at: 0)
                case "relocation":
                    contextStarters.insert("What do I need to update for my move?", at: 0)
                case "retirement":
                    contextStarters.insert("What retirement deadlines should I know about?", at: 0)
                default: break
                }
            }
            contextStarters.append("I\u{2019}m feeling overwhelmed")
            return contextStarters
        }

        // Default starters for new/free users
        return [
            "I recently lost a loved one and don\u{2019}t know where to start.",
            "I just got laid off. What do I need to do right away?",
            "I\u{2019}m going through a divorce and feel completely overwhelmed.",
            "I\u{2019}m moving to a new state and need help with everything.",
            "I\u{2019}m applying for disability benefits and don\u{2019}t know where to begin.",
            "I\u{2019}m getting ready to retire and want to make sure I don\u{2019}t miss anything.",
            "Something else is going on\u{2026}",
        ]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Heading & subtext
            VStack(alignment: .leading, spacing: 12) {
                Text("You don\u{2019}t have to figure this out alone.")
                    .font(.lumeBodyMedium)
                    .foregroundColor(.lumeText)

                Text("Lumeway helps you understand the process and timeline for life\u{2019}s hardest transitions \u{2014} with planning tools to keep you organized and a Transition Navigator to walk you through what comes next.")
                    .font(.lumeBody)
                    .foregroundColor(.lumeMuted)
                    .fixedSize(horizontal: false, vertical: true)

                // Disclaimer
                Text("Lumeway is a guidance tool \u{2014} not a lawyer, financial advisor, or licensed professional. The information provided is for general educational purposes only and should not be considered legal, financial, or medical advice. Always consult a qualified professional for decisions specific to your situation.")
                    .font(.system(size: 11))
                    .foregroundColor(.lumeMuted)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 4)
            }
            .padding(16)
            .background(Color.lumeWarmWhite)
            .cornerRadius(20)
            .overlay(
                RoundedRectangle(cornerRadius: 20)
                    .stroke(Color.lumeBorder, lineWidth: 1)
            )

            // Starter buttons
            VStack(alignment: .leading, spacing: 10) {
                Text("Where are you right now?")
                    .font(.lumeBodyMedium)
                    .foregroundColor(.lumeText)
                    .padding(.bottom, 2)

                ForEach(starters, id: \.self) { starter in
                    Button {
                        onSuggestionTap?(starter)
                    } label: {
                        Text(starter)
                            .font(.lumeBody)
                            .foregroundColor(.lumeNavy)
                            .multilineTextAlignment(.leading)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 12)
                            .background(Color.lumeWarmWhite)
                            .cornerRadius(16)
                            .overlay(
                                RoundedRectangle(cornerRadius: 16)
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

// MARK: - Chat History

struct ChatHistoryMessage: Codable {
    let role: String
    let content: String
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case role, content
        case createdAt = "created_at"
    }
}

struct ChatHistoryResponse: Codable {
    let messages: [ChatHistoryMessage]
}

struct ChatSessionsResponse: Codable {
    let sessions: [ChatSessionItem]

    struct ChatSessionItem: Codable {
        let id: String
        let startedAt: String?
        let preview: String?

        enum CodingKeys: String, CodingKey {
            case id, preview
            case startedAt = "started_at"
        }
    }
}

struct ChatHistorySheet: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) var dismiss
    var onSelectSession: (ChatSessionSummary) -> Void

    var sessions: [ChatSessionSummary] {
        appState.dashboardData?.sessions ?? []
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                if sessions.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "bubble.left.and.bubble.right")
                            .font(.system(size: 36))
                            .foregroundColor(.lumeBorder)
                        Text("No previous conversations")
                            .font(.lumeBody)
                            .foregroundColor(.lumeMuted)
                    }
                } else {
                    ScrollView {
                        LazyVStack(spacing: 0) {
                            ForEach(sessions) { session in
                                Button {
                                    onSelectSession(session)
                                } label: {
                                    HStack(spacing: 14) {
                                        Image(systemName: "bubble.left.fill")
                                            .font(.system(size: 14))
                                            .foregroundColor(.lumeNavy.opacity(0.6))

                                        VStack(alignment: .leading, spacing: 4) {
                                            Text(session.preview ?? "Chat session")
                                                .font(.lumeBody)
                                                .foregroundColor(.lumeText)
                                                .lineLimit(2)
                                                .multilineTextAlignment(.leading)

                                            if let date = session.startedAt {
                                                Text(formatSessionDate(date))
                                                    .font(.lumeSmall)
                                                    .foregroundColor(.lumeMuted)
                                            }
                                        }

                                        Spacer()

                                        Image(systemName: "chevron.right")
                                            .font(.system(size: 12))
                                            .foregroundColor(.lumeBorder)
                                    }
                                    .padding(.horizontal, 20)
                                    .padding(.vertical, 14)
                                }

                                Divider()
                                    .padding(.leading, 48)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Chat History")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
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

    private func formatSessionDate(_ dateStr: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: dateStr) {
            let display = DateFormatter()
            display.dateStyle = .medium
            display.timeStyle = .short
            return display.string(from: date)
        }
        // Try without fractional seconds
        formatter.formatOptions = [.withInternetDateTime]
        if let date = formatter.date(from: dateStr) {
            let display = DateFormatter()
            display.dateStyle = .medium
            display.timeStyle = .short
            return display.string(from: date)
        }
        return dateStr
    }
}
