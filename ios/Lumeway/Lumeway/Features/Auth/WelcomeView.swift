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

                    // Sunrise illustration
                    ZStack {
                        // Glow behind sun
                        Circle()
                            .fill(
                                RadialGradient(
                                    colors: [Color.lumeGold.opacity(0.2), Color.clear],
                                    center: .center,
                                    startRadius: 20,
                                    endRadius: 120
                                )
                            )
                            .frame(width: 240, height: 240)
                            .scaleEffect(animateSun ? 1.1 : 0.9)

                        // Sun rays
                        ForEach(0..<14, id: \.self) { i in
                            Rectangle()
                                .fill(
                                    LinearGradient(
                                        colors: [Color.lumeGold.opacity(0.35), Color.lumeGold.opacity(0.0)],
                                        startPoint: .bottom,
                                        endPoint: .top
                                    )
                                )
                                .frame(width: 2.5, height: 80)
                                .offset(y: -50)
                                .rotationEffect(.degrees(Double(i) * 12.86 - 90))
                                .opacity(animateRays ? 1 : 0)
                        }

                        // Sun semicircle
                        Circle()
                            .fill(
                                LinearGradient(
                                    colors: [Color.lumeAccent.opacity(0.5), Color.lumeGold.opacity(0.3)],
                                    startPoint: .top,
                                    endPoint: .bottom
                                )
                            )
                            .frame(width: 140, height: 140)
                            .offset(y: 35)
                            .mask(
                                Rectangle()
                                    .frame(width: 180, height: 80)
                                    .offset(y: -30)
                            )
                    }
                    .frame(height: 110)
                    .padding(.bottom, 32)

                    // Brand name
                    Text("LUMEWAY")
                        .font(.lumeLogoText)
                        .tracking(4)
                        .foregroundColor(.white.opacity(0.5))
                        .padding(.bottom, 20)

                    // Tagline
                    VStack(spacing: 6) {
                        Text("When life changes,")
                            .font(.lumeHeadingMedium)
                            .foregroundColor(.white)

                        Text("find your way through.")
                            .font(.lumeHeadingItalic)
                            .foregroundColor(.lumeGold)
                    }
                    .padding(.bottom, 14)

                    Text("Lumeway guides you through life's hardest\nmoments — one clear step at a time.")
                        .font(.lumeBodyLight)
                        .foregroundColor(.white.opacity(0.5))
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                        .padding(.horizontal, 40)

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
                                    Text("Get started free")
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
