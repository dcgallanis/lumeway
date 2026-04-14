import SwiftUI

struct WelcomeView: View {
    @EnvironmentObject var appState: AppState
    @State private var email = ""
    @State private var isSending = false
    @State private var showVerify = false
    @State private var errorMessage: String?
    @State private var animateRays = false
    @State private var animateSun = false
    @FocusState private var emailFocused: Bool

    private let authService = AuthService()

    var body: some View {
        NavigationStack {
            ZStack {
                // Full navy hero
                Color.lumeNavy.ignoresSafeArea()

                VStack(spacing: 0) {
                    Spacer()

                    // Lumeway sun icon — matches brand
                    ZStack {
                        Circle()
                            .fill(
                                RadialGradient(
                                    colors: [Color.lumeGold.opacity(0.15), Color.clear],
                                    center: .center,
                                    startRadius: 20,
                                    endRadius: 100
                                )
                            )
                            .frame(width: 200, height: 200)
                            .scaleEffect(animateSun ? 1.08 : 0.95)

                        Image(systemName: "sun.max.fill")
                            .font(.system(size: 72, weight: .light))
                            .foregroundStyle(
                                LinearGradient(
                                    colors: [.lumeAccent, .lumeGold],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            .opacity(animateRays ? 1 : 0.3)
                    }
                    .padding(.bottom, 36)

                    // Brand name — hero display
                    Text("LUMEWAY")
                        .font(.custom("CormorantGaramond-Bold", size: 48))
                        .tracking(5)
                        .foregroundColor(.white)
                        .padding(.bottom, 20)

                    // Tagline
                    VStack(spacing: 6) {
                        Text("When life changes,")
                            .font(.custom("Montserrat-SemiBold", size: 18))
                            .foregroundColor(.white)

                        Text("find your way through.")
                            .font(.custom("Montserrat-Medium", size: 18).italic())
                            .foregroundColor(.lumeGold)
                    }

                    Spacer()

                    // Email input — the terracotta pill IS the entry point
                    VStack(spacing: 14) {
                        // Email field
                        ZStack(alignment: .leading) {
                            if email.isEmpty {
                                Text("Enter your email to get started")
                                    .font(.lumeBody)
                                    .foregroundColor(.white.opacity(0.35))
                                    .padding(.leading, 20)
                            }
                            TextField("", text: $email)
                                .keyboardType(.emailAddress)
                                .textContentType(.emailAddress)
                                .autocapitalization(.none)
                                .disableAutocorrection(true)
                                .font(.lumeBody)
                                .foregroundColor(.white)
                                .padding(.horizontal, 20)
                                .padding(.vertical, 16)
                                .focused($emailFocused)
                        }
                        .background(Color.white.opacity(0.08))
                        .cornerRadius(28)
                        .overlay(
                            RoundedRectangle(cornerRadius: 28)
                                .stroke(emailFocused ? Color.lumeGold.opacity(0.5) : Color.white.opacity(0.12), lineWidth: 1)
                        )

                        if let error = errorMessage {
                            Text(error)
                                .font(.lumeSmall)
                                .foregroundColor(.lumeGold)
                        }

                        // Send code button — terracotta pill
                        Button {
                            Task { await sendCode() }
                        } label: {
                            if isSending {
                                ProgressView()
                                    .tint(.white)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 16)
                            } else {
                                HStack(spacing: 8) {
                                    Text("Get started")
                                        .font(.lumeBodySemibold)
                                    Image(systemName: "arrow.right")
                                        .font(.system(size: 14, weight: .semibold))
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 16)
                            }
                        }
                        .foregroundColor(.white)
                        .background(
                            RoundedRectangle(cornerRadius: 28)
                                .fill(email.isEmpty ? Color.lumeAccent.opacity(0.4) : Color.lumeAccent)
                        )
                        .disabled(email.isEmpty || isSending)
                    }
                    .padding(.horizontal, 32)
                    .padding(.bottom, 56)
                }
            }
            .onAppear {
                withAnimation(.easeOut(duration: 1.2)) {
                    animateRays = true
                }
                withAnimation(.easeInOut(duration: 2.0).repeatForever(autoreverses: true)) {
                    animateSun = true
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
