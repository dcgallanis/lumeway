import SwiftUI

struct WelcomeView: View {
    @EnvironmentObject var appState: AppState
    @State private var email = ""
    @State private var isSending = false
    @State private var showVerify = false
    @State private var errorMessage: String?
    @State private var showEmailField = false
    @State private var animateRays = false

    private let authService = AuthService()

    var body: some View {
        NavigationStack {
            ZStack {
                // Warm cream background
                Color.lumeCream.ignoresSafeArea()

                VStack(spacing: 0) {
                    Spacer()

                    // Sunrise illustration
                    ZStack {
                        // Sun rays
                        ForEach(0..<12, id: \.self) { i in
                            Rectangle()
                                .fill(
                                    LinearGradient(
                                        colors: [Color.lumeGold.opacity(0.25), Color.lumeGold.opacity(0.02)],
                                        startPoint: .bottom,
                                        endPoint: .top
                                    )
                                )
                                .frame(width: 3, height: 100)
                                .offset(y: -60)
                                .rotationEffect(.degrees(Double(i) * 15 - 82.5))
                                .opacity(animateRays ? 1 : 0)
                        }

                        // Sun semicircle
                        Circle()
                            .fill(
                                LinearGradient(
                                    colors: [Color.lumeAccent.opacity(0.2), Color.lumeGold.opacity(0.1)],
                                    startPoint: .top,
                                    endPoint: .bottom
                                )
                            )
                            .frame(width: 160, height: 160)
                            .offset(y: 40)
                            .mask(
                                Rectangle()
                                    .frame(width: 200, height: 100)
                                    .offset(y: -40)
                            )
                    }
                    .frame(height: 120)
                    .padding(.bottom, 24)

                    if !showEmailField {
                        // Tagline
                        VStack(spacing: 8) {
                            Text("When life changes,")
                                .font(.lumeHeadingMedium)
                                .foregroundColor(.lumeNavy)

                            Text("find your way through.")
                                .font(.lumeHeadingItalic)
                                .foregroundColor(.lumeAccent)
                        }
                        .padding(.bottom, 16)

                        Text("Lumeway guides you through life's hardest\ntransitions — one clear step at a time.")
                            .font(.lumeBodyLight)
                            .foregroundColor(.lumeMuted)
                            .multilineTextAlignment(.center)
                            .lineSpacing(4)
                            .padding(.horizontal, 40)

                        Spacer()

                        // CTA buttons
                        VStack(spacing: 16) {
                            Button {
                                withAnimation(.easeInOut(duration: 0.3)) {
                                    showEmailField = true
                                }
                            } label: {
                                HStack {
                                    Text("Get started free")
                                        .font(.lumeBodySemibold)
                                    Image(systemName: "arrow.right")
                                        .font(.system(size: 14, weight: .medium))
                                }
                                .foregroundColor(.white)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 16)
                                .background(
                                    RoundedRectangle(cornerRadius: 28)
                                        .fill(Color.lumeAccent)
                                )
                            }

                            Button {
                                withAnimation(.easeInOut(duration: 0.3)) {
                                    showEmailField = true
                                }
                            } label: {
                                Text("I already have an account")
                                    .font(.lumeCaption)
                                    .foregroundColor(.lumeMuted)
                            }
                        }
                        .padding(.horizontal, 40)
                        .padding(.bottom, 48)
                    } else {
                        // Email entry
                        VStack(spacing: 8) {
                            Text("Enter your email")
                                .font(.lumeHeadingSmall)
                                .foregroundColor(.lumeNavy)

                            Text("We'll send you a sign-in code.\nNo password needed.")
                                .font(.lumeBodyLight)
                                .foregroundColor(.lumeMuted)
                                .multilineTextAlignment(.center)
                                .lineSpacing(3)
                        }
                        .padding(.bottom, 28)

                        VStack(spacing: 16) {
                            ZStack(alignment: .leading) {
                                if email.isEmpty {
                                    Text("your@email.com")
                                        .font(.lumeBody)
                                        .foregroundColor(.lumeBorder)
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
                                    HStack {
                                        Text("Send code")
                                            .font(.lumeBodySemibold)
                                        Image(systemName: "arrow.right")
                                            .font(.system(size: 14, weight: .medium))
                                    }
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 16)
                                }
                            }
                            .foregroundColor(.white)
                            .background(
                                RoundedRectangle(cornerRadius: 28)
                                    .fill(email.isEmpty ? Color.lumeMuted.opacity(0.3) : Color.lumeAccent)
                            )
                            .disabled(email.isEmpty || isSending)

                            Button {
                                withAnimation(.easeInOut(duration: 0.3)) {
                                    showEmailField = false
                                }
                            } label: {
                                Text("Back")
                                    .font(.lumeCaption)
                                    .foregroundColor(.lumeMuted)
                            }
                        }
                        .padding(.horizontal, 40)

                        Spacer()
                    }
                }
            }
            .onAppear {
                withAnimation(.easeOut(duration: 1.0)) {
                    animateRays = true
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
