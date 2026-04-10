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
                Color.lumeCream.ignoresSafeArea()

                VStack(spacing: 0) {
                    Spacer().frame(height: 80)

                    // Header
                    VStack(spacing: 8) {
                        Image(systemName: "sun.max")
                            .font(.system(size: 36, weight: .light))
                            .foregroundColor(.lumeAccent)
                            .padding(.bottom, 8)

                        Text("Enter your email")
                            .font(.lumeHeadingSmall)
                            .foregroundColor(.lumeText)

                        Text("We'll send you a code to sign in.\nNo password needed.")
                            .font(.lumeCaptionLight)
                            .foregroundColor(.lumeMuted)
                            .multilineTextAlignment(.center)
                            .lineSpacing(3)
                    }
                    .padding(.bottom, 40)

                    // Email field
                    VStack(spacing: 16) {
                        TextField("your@email.com", text: $email)
                            .keyboardType(.emailAddress)
                            .textContentType(.emailAddress)
                            .autocapitalization(.none)
                            .disableAutocorrection(true)
                            .font(.lumeBody)
                            .padding(16)
                            .background(Color.lumeWarmWhite)
                            .cornerRadius(12)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color.lumeBorder, lineWidth: 1)
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
                            } else {
                                Text("Send code")
                            }
                        }
                        .buttonStyle(LumePrimaryButtonStyle())
                        .frame(maxWidth: .infinity)
                        .disabled(email.isEmpty || isSending)
                        .opacity(email.isEmpty ? 0.5 : 1)
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
