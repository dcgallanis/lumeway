import SwiftUI

// Emoji icons matching the site dashboard picker exactly
let communityEmojiIcons: [String] = ["😊","🌟","🌿","🦋","🌊","🔥","💜","🌸","☀️","🍀","🐾","🎯","💡","🌙","🪴","✨"]

// Background colors for emoji avatars
let communityIconColors: [String: Color] = [
    "😊": Color(hex: "B8977E"),   // gold
    "🌟": Color(hex: "C4704E"),   // terracotta
    "🌿": Color(hex: "4A7C59"),   // green
    "🦋": Color(hex: "5E8C9A"),   // teal
    "🌊": Color(hex: "2C4A5E"),   // navy
    "🔥": Color(hex: "C4704E"),   // terracotta
    "💜": Color(hex: "7B6B8D"),   // purple
    "🌸": Color(hex: "D4896C"),   // blush
    "☀️": Color(hex: "B8977E"),   // gold
    "🍀": Color(hex: "4A7C59"),   // green
    "🐾": Color(hex: "6B7B8D"),   // muted
    "🎯": Color(hex: "C4704E"),   // terracotta
    "💡": Color(hex: "B8977E"),   // gold
    "🌙": Color(hex: "2C4A5E"),   // navy
    "🪴": Color(hex: "4A7C59"),   // green
    "✨": Color(hex: "2C4A5E"),   // navy (Cara's color)
]

func bgColorForIcon(_ icon: String?) -> Color {
    guard let icon = icon else { return Color(hex: "2C4A5E") }
    // Check if user has a custom background color set (for their own icon)
    let userIcon = UserDefaults.standard.string(forKey: "community_icon") ?? "☀️"
    if icon == userIcon {
        let customHex = UserDefaults.standard.string(forKey: "community_icon_bg") ?? ""
        if !customHex.isEmpty {
            return Color(hex: customHex)
        }
    }
    return communityIconColors[icon] ?? Color(hex: "2C4A5E")
}

/// Returns true if this is a Cara (Lumeway team) post
func isCaraPost(_ displayName: String?) -> Bool {
    guard let name = displayName else { return false }
    return name.lowercased() == "cara"
}

struct CommunityView: View {
    var isEmbedded: Bool = false

    @EnvironmentObject var appState: AppState
    @State private var posts: [CommunityPost] = []
    @State private var isLoading = true
    @State private var showNewPost = false
    @State private var selectedPostId: Int? = nil
    @State private var showPostDetail = false
    @State private var selectedCategory: String = "all"

    private let service = CommunityService()

    private let filterCategories = [
        ("all", "All"),
        ("general", "General"),
        ("advice", "Advice"),
        ("wins", "Wins"),
        ("venting", "Venting"),
        ("resources", "Resources"),
    ]

    private var filteredPosts: [CommunityPost] {
        if selectedCategory == "all" { return posts }
        return posts.filter { ($0.category ?? "general") == selectedCategory }
    }

    private var isPaid: Bool {
        let tier = appState.effectiveTier.lowercased()
        return tier != "free"
    }

    var body: some View {
        OptionalNavigationStack(isEmbedded: isEmbedded) {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                if !isPaid {
                    // Free users cannot access Community
                    CommunityLockedView()
                } else {

                ScrollView {
                    VStack(spacing: 14) {
                        // Topic filter pills
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(filterCategories, id: \.0) { cat in
                                    Button {
                                        withAnimation(.easeInOut(duration: 0.2)) {
                                            selectedCategory = cat.0
                                        }
                                    } label: {
                                        Text(cat.1)
                                            .font(.lumeCaption)
                                            .foregroundColor(selectedCategory == cat.0 ? .white : .lumeNavy)
                                            .padding(.horizontal, 14)
                                            .padding(.vertical, 8)
                                            .background(selectedCategory == cat.0 ? Color.lumeAccent : Color.lumeWarmWhite)
                                            .cornerRadius(20)
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 20)
                                                    .stroke(selectedCategory == cat.0 ? Color.clear : Color.lumeBorder, lineWidth: 1)
                                            )
                                    }
                                }
                            }
                            .padding(.horizontal, 20)
                        }
                        .padding(.top, 4)

                        // Welcome card
                        if posts.isEmpty && !isLoading {
                            CommunityWelcomeCard()
                                .padding(.horizontal, 20)
                                .padding(.top, 12)
                        }

                        ForEach(filteredPosts) { post in
                            CommunityPostCard(post: post, onLike: {
                                likePost(post)
                            }, onTap: {
                                selectedPostId = post.id
                                showPostDetail = true
                            })
                            .padding(.horizontal, 20)
                        }

                        Spacer().frame(height: 100)
                    }
                    .padding(.top, 8)
                }

                if isLoading && isPaid {
                    ProgressView()
                        .tint(.lumeAccent)
                }

                } // end else (paid)
            }
            .navigationTitle("Community")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.lumeCream, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.light, for: .navigationBar)
            .tint(.lumeNavy)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showNewPost = true
                    } label: {
                        Image(systemName: "square.and.pencil")
                            .font(.system(size: 18))
                            .foregroundColor(.lumeAccent)
                    }
                }
            }
            .refreshable {
                if isPaid { await loadPosts() }
            }
            .task {
                // Refresh tier data in case it changed (e.g. promo code redeemed on web)
                await appState.loadDashboard()
                if isPaid { await loadPosts() }
            }
            .sheet(isPresented: $showNewPost) {
                NewPostSheet(onPost: { title, body, category in
                    Task { await createPost(title: title, body: body, category: category) }
                })
                .presentationDetents([.large])
                .presentationBackground(Color.lumeCream)
            }
            .sheet(isPresented: $showPostDetail) {
                if let postId = selectedPostId {
                    PostDetailSheet(postId: postId, onDismiss: {
                        Task { await loadPosts() }
                    })
                    .presentationBackground(Color.lumeCream)
                }
            }
        }
    }

    private func loadPosts() async {
        do {
            let response = try await service.getPosts()
            posts = response.posts
            isLoading = false
        } catch {
            isLoading = false
        }
    }

    private func createPost(title: String, body: String, category: String) async {
        let name = UserDefaults.standard.string(forKey: "community_display_name") ?? "Anonymous"
        let icon = UserDefaults.standard.string(forKey: "community_icon") ?? "☀️"
        do {
            _ = try await service.createPost(
                title: title, body: body, category: category,
                displayName: name, icon: icon
            )
            await loadPosts()
        } catch {}
    }

    private func likePost(_ post: CommunityPost) {
        Task {
            do {
                _ = try await service.toggleLike(postId: post.id)
                await loadPosts()
            } catch {}
        }
    }
}

// MARK: - Community Avatar

struct CommunityAvatar: View {
    let icon: String?
    let displayName: String?
    let size: CGFloat

    /// Shows Lumeway sun for Cara and users with the sun emoji default
    private var showLumeSun: Bool {
        isCaraPost(displayName) || icon == nil || icon == "☀️"
    }

    var body: some View {
        if showLumeSun {
            // Lumeway branded sun icon
            ZStack {
                Circle()
                    .fill(Color.lumeNavy)
                    .frame(width: size, height: size)
                Image(systemName: "sun.max.fill")
                    .font(.system(size: size * 0.45))
                    .foregroundStyle(
                        LinearGradient(
                            colors: [.lumeAccent, .lumeGold],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            }
        } else {
            // Regular user: emoji on colored circle
            ZStack {
                Circle()
                    .fill(bgColorForIcon(icon))
                    .frame(width: size, height: size)
                Text(icon ?? "☀️")
                    .font(.system(size: size * 0.5))
            }
        }
    }
}

// MARK: - Welcome Card

struct CommunityWelcomeCard: View {
    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: "sun.max.fill")
                .font(.system(size: 36))
                .foregroundStyle(
                    LinearGradient(
                        colors: [.lumeAccent, .lumeGold],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
            Text("Welcome to the Community")
                .font(.lumeHeadingSmall)
                .foregroundColor(.lumeNavy)
            Text("A safe space to share what you're going through, ask questions, and support others on the same path.")
                .font(.lumeCaptionLight)
                .foregroundColor(.lumeMuted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 16)
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .background(Color.lumeWarmWhite)
        .cornerRadius(20)
        .overlay(
            RoundedRectangle(cornerRadius: 20)
                .stroke(Color.lumeBorder, lineWidth: 1)
        )
    }
}

// MARK: - Post Card

struct CommunityPostCard: View {
    let post: CommunityPost
    let onLike: () -> Void
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 12) {
                // Author row
                HStack(spacing: 10) {
                    CommunityAvatar(icon: post.icon, displayName: post.displayName, size: 34)

                    VStack(alignment: .leading, spacing: 1) {
                        HStack(spacing: 4) {
                            Text(post.displayName ?? "Anonymous")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)
                            if isCaraPost(post.displayName) {
                                Text("Team")
                                    .font(.system(size: 9, weight: .semibold))
                                    .foregroundColor(.lumeGold)
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 1)
                                    .background(Color.lumeGold.opacity(0.12))
                                    .cornerRadius(4)
                            }
                        }
                        Text(timeAgo(post.createdAt))
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }

                    Spacer()

                    if post.isPinned ?? false {
                        Image(systemName: "pin.fill")
                            .font(.system(size: 10))
                            .foregroundColor(.lumeGold)
                    }

                    if let cat = post.category {
                        Text(cat.capitalized)
                            .font(.lumeSmall)
                            .foregroundColor(.lumeAccent)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Color.lumeAccent.opacity(0.08))
                            .cornerRadius(8)
                    }
                }

                // Title & body
                Text(post.title ?? "")
                    .font(.lumeBodyMedium)
                    .foregroundColor(.lumeNavy)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)

                Text(post.body ?? "")
                    .font(.lumeCaptionLight)
                    .foregroundColor(.lumeMuted)
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)

                // Actions
                HStack(spacing: 20) {
                    Button(action: onLike) {
                        HStack(spacing: 5) {
                            Image(systemName: "heart")
                                .font(.system(size: 13))
                            Text("\(post.likeCount ?? 0)")
                                .font(.lumeSmall)
                        }
                        .foregroundColor(.lumeMuted)
                    }

                    HStack(spacing: 5) {
                        Image(systemName: "bubble.left")
                            .font(.system(size: 13))
                        Text("\(post.replyCount ?? 0)")
                            .font(.lumeSmall)
                    }
                    .foregroundColor(.lumeMuted)

                    Spacer()
                }
            }
            .padding(16)
            .background(Color.lumeWarmWhite)
            .cornerRadius(16)
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(Color.lumeBorder, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Post Detail Sheet

struct PostDetailSheet: View {
    let postId: Int
    let onDismiss: () -> Void

    @Environment(\.dismiss) var dismiss
    @State private var post: CommunityPost?
    @State private var replies: [CommunityReply] = []
    @State private var replyText = ""
    @State private var isLoading = true
    @State private var isSending = false
    @State private var replyingTo: CommunityReply? = nil

    private let service = CommunityService()

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                VStack(spacing: 0) {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 16) {
                            if let post = post {
                                // Post header
                                HStack(spacing: 12) {
                                    CommunityAvatar(icon: post.icon, displayName: post.displayName, size: 40)

                                    VStack(alignment: .leading, spacing: 2) {
                                        HStack(spacing: 4) {
                                            Text(post.displayName ?? "Anonymous")
                                                .font(.lumeBodyMedium)
                                                .foregroundColor(.lumeNavy)
                                            if isCaraPost(post.displayName) {
                                                Text("Team")
                                                    .font(.system(size: 9, weight: .semibold))
                                                    .foregroundColor(.lumeGold)
                                                    .padding(.horizontal, 5)
                                                    .padding(.vertical, 1)
                                                    .background(Color.lumeGold.opacity(0.12))
                                                    .cornerRadius(4)
                                            }
                                        }
                                        Text(timeAgo(post.createdAt))
                                            .font(.lumeSmall)
                                            .foregroundColor(.lumeMuted)
                                    }
                                    Spacer()
                                }

                                Text(post.title ?? "")
                                    .font(.lumeHeadingSmall)
                                    .foregroundColor(.lumeNavy)

                                Text(post.body ?? "")
                                    .font(.lumeBody)
                                    .foregroundColor(.lumeText)
                                    .lineSpacing(4)

                                Divider()

                                // Replies header
                                Text("\(replies.count) repl\(replies.count == 1 ? "y" : "ies")")
                                    .font(.lumeCaption)
                                    .fontWeight(.medium)
                                    .foregroundColor(.lumeMuted)

                                if replies.isEmpty {
                                    Text("No replies yet. Be the first to respond.")
                                        .font(.lumeCaptionLight)
                                        .foregroundColor(.lumeMuted)
                                        .padding(.vertical, 8)
                                }

                                ForEach(replies) { reply in
                                    CommunityReplyRow(
                                        reply: reply,
                                        onDelete: reply.isAuthor == true ? {
                                            deleteReply(reply)
                                        } : nil,
                                        onLike: {
                                            likeReply(reply)
                                        },
                                        onReply: {
                                            replyingTo = reply
                                        }
                                    )
                                }
                            }
                        }
                        .padding(20)
                    }

                    // Reply-to context banner
                    if let target = replyingTo {
                        HStack(spacing: 8) {
                            RoundedRectangle(cornerRadius: 2)
                                .fill(Color.lumeAccent)
                                .frame(width: 3, height: 20)
                            Text("Replying to \(target.displayName ?? "Anonymous")")
                                .font(.lumeSmall)
                                .foregroundColor(.lumeMuted)
                            Spacer()
                            Button {
                                replyingTo = nil
                            } label: {
                                Image(systemName: "xmark")
                                    .font(.system(size: 10, weight: .semibold))
                                    .foregroundColor(.lumeMuted)
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(Color.lumeWarmWhite)
                    }

                    // Reply input
                    Divider()
                    HStack(spacing: 12) {
                        TextField(
                            replyingTo != nil ? "Reply to \(replyingTo?.displayName ?? "")..." : "Write a reply...",
                            text: $replyText,
                            axis: .vertical
                        )
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
                            sendReply()
                        } label: {
                            if isSending {
                                ProgressView()
                                    .tint(.lumeAccent)
                            } else {
                                Image(systemName: "arrow.up.circle.fill")
                                    .font(.system(size: 32))
                                    .foregroundColor(replyText.trimmingCharacters(in: .whitespaces).isEmpty ? .lumeBorder : .lumeAccent)
                            }
                        }
                        .disabled(replyText.trimmingCharacters(in: .whitespaces).isEmpty || isSending)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(Color.lumeCream)
                }

                if isLoading {
                    ProgressView()
                        .tint(.lumeAccent)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.lumeCream, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.light, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        onDismiss()
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.lumeMuted)
                    }
                }
            }
            .task {
                await loadPost()
            }
        }
        .environment(\.colorScheme, .light)
    }

    private func loadPost() async {
        do {
            let response = try await service.getPost(id: postId)
            post = response.post
            replies = response.replies
            isLoading = false
        } catch {
            isLoading = false
        }
    }

    private func sendReply() {
        var text = replyText.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }

        // If replying to another reply, prefix with @mention
        if let target = replyingTo {
            let mention = "@\(target.displayName ?? "Anonymous") "
            if !text.hasPrefix(mention) {
                text = mention + text
            }
        }

        let name = UserDefaults.standard.string(forKey: "community_display_name") ?? "Anonymous"
        let icon = UserDefaults.standard.string(forKey: "community_icon") ?? "☀️"

        isSending = true
        Task {
            do {
                _ = try await service.createReply(postId: postId, body: text, displayName: name, icon: icon)
                replyText = ""
                replyingTo = nil
                await loadPost()
            } catch {}
            isSending = false
        }
    }

    private func deleteReply(_ reply: CommunityReply) {
        Task {
            do {
                _ = try await service.deleteReply(id: reply.id)
                await loadPost()
            } catch {}
        }
    }

    private func likeReply(_ reply: CommunityReply) {
        Task {
            do {
                _ = try await service.toggleLike(replyId: reply.id)
                await loadPost()
            } catch {}
        }
    }
}

// MARK: - Reply Row

struct CommunityReplyRow: View {
    let reply: CommunityReply
    var onDelete: (() -> Void)?
    var onLike: (() -> Void)?
    var onReply: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 10) {
                CommunityAvatar(icon: reply.icon, displayName: reply.displayName, size: 30)

                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(reply.displayName ?? "Anonymous")
                            .font(.lumeCaption)
                            .fontWeight(.medium)
                            .foregroundColor(.lumeNavy)
                        if isCaraPost(reply.displayName) {
                            Text("Team")
                                .font(.system(size: 8, weight: .semibold))
                                .foregroundColor(.lumeGold)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background(Color.lumeGold.opacity(0.12))
                                .cornerRadius(3)
                        }
                        Text(timeAgo(reply.createdAt))
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }

                    Text(reply.body ?? "")
                        .font(.lumeBody)
                        .foregroundColor(.lumeText)
                        .lineSpacing(3)

                    // Actions row
                    HStack(spacing: 16) {
                        if let onLike = onLike {
                            Button(action: onLike) {
                                HStack(spacing: 4) {
                                    Image(systemName: "heart")
                                        .font(.system(size: 11))
                                    Text("\(reply.likeCount ?? 0)")
                                        .font(.lumeSmall)
                                }
                                .foregroundColor(.lumeMuted)
                            }
                        }

                        if let onReply = onReply {
                            Button(action: onReply) {
                                HStack(spacing: 4) {
                                    Image(systemName: "arrowshape.turn.up.left")
                                        .font(.system(size: 11))
                                    Text("Reply")
                                        .font(.lumeSmall)
                                }
                                .foregroundColor(.lumeMuted)
                            }
                        }

                        if reply.isAuthor == true, let onDelete = onDelete {
                            Button(action: onDelete) {
                                HStack(spacing: 4) {
                                    Image(systemName: "trash")
                                        .font(.system(size: 10))
                                    Text("Delete")
                                        .font(.lumeSmall)
                                }
                                .foregroundColor(.lumeMuted)
                            }
                        }
                    }
                    .padding(.top, 4)
                }

                Spacer()
            }
        }
        .padding(12)
        .background(Color.lumeWarmWhite)
        .cornerRadius(14)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.lumeBorder, lineWidth: 1)
        )
    }
}

// MARK: - New Post Sheet

struct NewPostSheet: View {
    let onPost: (String, String, String) -> Void
    @Environment(\.dismiss) var dismiss

    @State private var title = ""
    @State private var postBody = ""
    @State private var category = "general"

    private let categories = [
        ("general", "General"),
        ("advice", "Advice"),
        ("wins", "Wins"),
        ("venting", "Venting"),
        ("resources", "Resources"),
    ]

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 18) {
                        // Category picker
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Category")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)

                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 8) {
                                    ForEach(categories, id: \.0) { cat in
                                        Button {
                                            category = cat.0
                                        } label: {
                                            Text(cat.1)
                                                .font(.lumeCaption)
                                                .foregroundColor(category == cat.0 ? .white : .lumeNavy)
                                                .padding(.horizontal, 14)
                                                .padding(.vertical, 8)
                                                .background(category == cat.0 ? Color.lumeAccent : Color.lumeWarmWhite)
                                                .cornerRadius(20)
                                                .overlay(
                                                    RoundedRectangle(cornerRadius: 20)
                                                        .stroke(category == cat.0 ? Color.clear : Color.lumeBorder, lineWidth: 1)
                                                )
                                        }
                                    }
                                }
                            }
                        }

                        // Title
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Title")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)
                            TextField("What's on your mind?", text: $title)
                                .font(.lumeBody)
                                .foregroundColor(.lumeText)
                                .padding(14)
                                .background(Color.lumeWarmWhite)
                                .cornerRadius(12)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.lumeBorder, lineWidth: 1)
                                )
                        }

                        // Body
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Your post")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)
                            TextEditor(text: $postBody)
                                .font(.lumeBody)
                                .foregroundColor(.lumeText)
                                .scrollContentBackground(.hidden)
                                .frame(minHeight: 150)
                                .padding(14)
                                .background(Color.lumeWarmWhite)
                                .cornerRadius(12)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.lumeBorder, lineWidth: 1)
                                )
                        }

                        Button {
                            onPost(title, postBody, category)
                            dismiss()
                        } label: {
                            Text("Post")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(LumePrimaryButtonStyle())
                        .disabled(
                            title.trimmingCharacters(in: .whitespaces).isEmpty ||
                            postBody.trimmingCharacters(in: .whitespaces).isEmpty
                        )
                    }
                    .padding(24)
                }
            }
            .navigationTitle("New Post")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                        .foregroundColor(.lumeMuted)
                }
            }
        }
    }
}

// MARK: - Shared Time Ago

func timeAgo(_ dateStr: String?) -> String {
    guard let str = dateStr else { return "" }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    var date = formatter.date(from: str)
    if date == nil {
        formatter.formatOptions = [.withInternetDateTime]
        date = formatter.date(from: str)
    }
    if date == nil {
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        date = df.date(from: String(str.prefix(19)))
    }
    guard let d = date else { return "" }
    let interval = Date().timeIntervalSince(d)
    if interval < 60 { return "just now" }
    if interval < 3600 { return "\(Int(interval / 60))m ago" }
    if interval < 86400 { return "\(Int(interval / 3600))h ago" }
    let days = Int(interval / 86400)
    if days == 1 { return "yesterday" }
    if days < 30 { return "\(days)d ago" }
    return "\(days / 30)mo ago"
}

// MARK: - Community Locked View (Free Users)

struct CommunityLockedView: View {
    @State private var showUpgrade = false

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            ZStack {
                Circle()
                    .fill(Color.lumeAccent.opacity(0.08))
                    .frame(width: 100, height: 100)
                Image(systemName: "bubble.left.and.bubble.right.fill")
                    .font(.system(size: 38, weight: .light))
                    .foregroundColor(.lumeAccent)
            }

            VStack(spacing: 10) {
                Text("Community")
                    .font(.lumeDisplayMedium)
                    .foregroundColor(.lumeNavy)

                Text("Connect with others going through\nsimilar transitions. Share experiences,\nask questions, and find support.")
                    .font(.lumeBody)
                    .foregroundColor(.lumeMuted)
                    .multilineTextAlignment(.center)
                    .lineSpacing(3)
            }

            VStack(spacing: 8) {
                HStack(spacing: 10) {
                    Image(systemName: "checkmark")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.lumeGreen)
                    Text("Real conversations with real people")
                        .font(.lumeBody)
                        .foregroundColor(.lumeText)
                }

                HStack(spacing: 10) {
                    Image(systemName: "checkmark")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.lumeGreen)
                    Text("Tips and advice from those who've been there")
                        .font(.lumeBody)
                        .foregroundColor(.lumeText)
                }

                HStack(spacing: 10) {
                    Image(systemName: "checkmark")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.lumeGreen)
                    Text("A safe, supportive space")
                        .font(.lumeBody)
                        .foregroundColor(.lumeText)
                }
            }

            Button {
                showUpgrade = true
            } label: {
                Text("Unlock Community Access")
                    .font(.lumeBodySemibold)
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Color.lumeAccent)
                    .cornerRadius(28)
            }
            .padding(.horizontal, 40)

            Spacer()
        }
        .padding(.horizontal, 24)
        .sheet(isPresented: $showUpgrade) {
            UpgradeView()
        }
    }
}
