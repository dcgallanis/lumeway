import SwiftUI

struct LoginView: View {
    @Environment(\.dismiss) var dismiss
    @EnvironmentObject var appState: AppState

    @State private var email = ""
    @State private var isSending = false
    @State private var showVerify = false
    @State private var errorMessage: String?

    private let authService = AuthService()

    var body: some View {
        NavigationStack {
            ZStack {
                // Warm gradient background
                LinearGradient(
                    colors: [Color.lumeCream, Color.lumeAccent.opacity(0.06)],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                VStack(spacing: 0) {
                    Spacer().frame(height: 80)

                    // Header
                    VStack(spacing: 12) {
                        ZStack {
                            Circle()
                                .fill(Color.lumeAccent.opacity(0.1))
                                .frame(width: 72, height: 72)
                            Image(systemName: "sun.max.fill")
                                .font(.system(size: 32, weight: .light))
                                .foregroundStyle(
                                    LinearGradient(
                                        colors: [.lumeAccent, .lumeGold],
                                        startPoint: .topLeading,
                                        endPoint: .bottomTrailing
                                    )
                                )
                        }
                        .padding(.bottom, 4)

                        Text("Welcome back")
                            .font(.lumeHeadingSmall)
                            .foregroundColor(.lumeNavy)

                        Text("Enter your email and we'll send\nyou a sign-in code. No password needed.")
                            .font(.lumeBodyLight)
                            .foregroundColor(.lumeMuted)
                            .multilineTextAlignment(.center)
                            .lineSpacing(3)
                    }
                    .padding(.bottom, 40)

                    // Email field
                    VStack(spacing: 16) {
                        ZStack(alignment: .leading) {
                            if email.isEmpty {
                                Text("your@email.com")
                                    .font(.lumeBody)
                                    .foregroundColor(.lumeMuted.opacity(0.6))
                                    .padding(.leading, 16)
                            }
                            TextField("", text: $email)
                                .keyboardType(.emailAddress)
                                .textContentType(.emailAddress)
                                .autocapitalization(.none)
                                .disableAutocorrection(true)
                                .font(.lumeBody)
                                .foregroundColor(.lumeText)
                                .padding(16)
                        }
                        .background(Color.lumeWarmWhite)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(email.isEmpty ? Color.lumeBorder : Color.lumeAccent.opacity(0.5), lineWidth: 1)
                        )

                        if let error = errorMessage {
                            Text(error)
                                .font(.lumeCaption)
                                .foregroundColor(.lumeAccent)
                        }

                        Button {
                            Task { await sendCode() }
                        } label: {
                            if isSending {
                                ProgressView()
                                    .tint(.white)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 16)
                            } else {
                                Text("Send code")
                                    .font(.lumeBodySemibold)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 16)
                            }
                        }
                        .foregroundColor(.white)
                        .background(
                            RoundedRectangle(cornerRadius: 14)
                                .fill(email.isEmpty ? Color.lumeMuted.opacity(0.3) : Color.lumeAccent)
                        )
                        .disabled(email.isEmpty || isSending)
                    }
                    .padding(.horizontal, 32)

                    Spacer()
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                            .foregroundColor(.lumeMuted)
                    }
                }
            }
            .navigationDestination(isPresented: $showVerify) {
                VerifyCodeView(email: email)
            }
        }
    }

    private func sendCode() async {
        isSending = true
        errorMessage = nil
        defer { isSending = false }

        do {
            let response = try await authService.sendCode(email: email.lowercased().trimmingCharacters(in: .whitespaces))
            if response.ok == true {
                showVerify = true
            } else {
                errorMessage = response.error ?? "Something went wrong. Try again."
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
