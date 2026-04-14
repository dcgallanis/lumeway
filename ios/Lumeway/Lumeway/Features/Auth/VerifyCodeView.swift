import SwiftUI

struct VerifyCodeView: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) var dismiss

    let email: String
    var prefillCode: String? = nil

    @State private var digits: [String] = Array(repeating: "", count: 6)
    @FocusState private var focusedField: Int?
    @State private var isVerifying = false
    @State private var errorMessage: String?
    @State private var canResend = false
    @State private var resendCountdown = 30

    private let authService = AuthService()
    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer().frame(height: 60)

                VStack(spacing: 8) {
                    Text("Check your email")
                        .font(.lumeHeadingSmall)
                        .foregroundColor(.lumeText)

                    Text("We sent a 6-digit code to")
                        .font(.lumeCaptionLight)
                        .foregroundColor(.lumeMuted)
                    Text(email)
                        .font(.lumeCaption)
                        .foregroundColor(.lumeNavy)
                }
                .padding(.bottom, 40)

                // 6-digit code entry
                HStack(spacing: 10) {
                    ForEach(0..<6, id: \.self) { index in
                        TextField("", text: $digits[index])
                            .keyboardType(.numberPad)
                            .textContentType(.oneTimeCode)
                            .multilineTextAlignment(.center)
                            .font(.system(size: 24, weight: .medium, design: .monospaced))
                            .foregroundColor(.lumeText)
                            .frame(width: 48, height: 56)
                            .background(Color.lumeWarmWhite)
                            .cornerRadius(12)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(
                                        focusedField == index ? Color.lumeNavy : Color.lumeBorder,
                                        lineWidth: focusedField == index ? 2 : 1
                                    )
                            )
                            .focused($focusedField, equals: index)
                            .onChange(of: digits[index]) { _, newValue in
                                handleDigitChange(index: index, value: newValue)
                            }
                    }
                }
                .padding(.horizontal, 32)
                .padding(.bottom, 16)

                if let error = errorMessage {
                    Text(error)
                        .font(.lumeCaption)
                        .foregroundColor(.lumeAccent)
                        .padding(.bottom, 8)
                }

                if isVerifying {
                    ProgressView()
                        .tint(.lumeAccent)
                        .padding(.top, 16)
                }

                Spacer().frame(height: 32)

                // Resend
                if canResend {
                    Button("Send a new code") {
                        Task { await resendCode() }
                    }
                    .font(.lumeCaption)
                    .foregroundColor(.lumeNavy)
                } else {
                    Text("Resend in \(resendCountdown)s")
                        .font(.lumeCaptionLight)
                        .foregroundColor(.lumeMuted)
                }

                Spacer()
            }
        }
        .onAppear {
            if let code = prefillCode, code.count == 6 {
                // Auto-fill demo code
                for (i, ch) in code.enumerated() {
                    digits[i] = String(ch)
                }
                Task { await verifyCode() }
            } else {
                focusedField = 0
            }
        }
        .onReceive(timer) { _ in
            if resendCountdown > 0 {
                resendCountdown -= 1
            } else {
                canResend = true
            }
        }
    }

    private func handleDigitChange(index: Int, value: String) {
        // Only keep last character, digits only
        let filtered = value.filter { $0.isNumber }
        if filtered.count > 1 {
            // Pasted full code
            let chars = Array(filtered.prefix(6))
            for (i, ch) in chars.enumerated() {
                digits[i] = String(ch)
            }
            if chars.count >= 6 {
                focusedField = nil
                Task { await verifyCode() }
            } else {
                focusedField = chars.count
            }
            return
        }

        digits[index] = String(filtered.prefix(1))

        if !filtered.isEmpty && index < 5 {
            focusedField = index + 1
        }

        // Auto-submit when all 6 filled
        let code = digits.joined()
        if code.count == 6 {
            focusedField = nil
            Task { await verifyCode() }
        }
    }

    private func verifyCode() async {
        let code = digits.joined()
        guard code.count == 6 else { return }

        isVerifying = true
        errorMessage = nil
        defer { isVerifying = false }

        do {
            let response = try await authService.verifyCode(email: email, code: code)
            if response.ok == true, let token = response.token, let user = response.user {
                appState.login(
                    token: token,
                    refreshToken: response.refreshToken ?? "",
                    user: user
                )
            } else {
                errorMessage = response.error ?? "Invalid code. Try again."
                digits = Array(repeating: "", count: 6)
                focusedField = 0
            }
        } catch {
            errorMessage = "Something went wrong. Try again."
            digits = Array(repeating: "", count: 6)
            focusedField = 0
        }
    }

    private func resendCode() async {
        canResend = false
        resendCountdown = 30
        _ = try? await authService.sendCode(email: email)
    }
}
