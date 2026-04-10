import SwiftUI

struct WelcomeView: View {
    @State private var showLogin = false

    var body: some View {
        ZStack {
            Color.lumeCream.ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                // Logo
                VStack(spacing: 12) {
                    Image(systemName: "sun.max")
                        .font(.system(size: 56, weight: .light))
                        .foregroundColor(.lumeAccent)

                    Text("LUMEWAY")
                        .font(.lumeLogoText)
                        .tracking(3)
                        .foregroundColor(.lumeNavy)
                }
                .padding(.bottom, 48)

                // Headline
                VStack(spacing: 16) {
                    Text("When life changes,")
                        .font(.lumeHeadingMedium)
                        .foregroundColor(.lumeText)
                    Text("find your way through.")
                        .font(.lumeHeadingItalic)
                        .foregroundColor(.lumeAccentLight)
                }
                .multilineTextAlignment(.center)
                .padding(.bottom, 16)

                Text("Step-by-step guidance for life's hardest transitions.\nJob loss, estate, divorce, disability, and more.")
                    .font(.lumeBodyLight)
                    .foregroundColor(.lumeMuted)
                    .multilineTextAlignment(.center)
                    .lineSpacing(4)
                    .padding(.horizontal, 40)

                Spacer()

                // CTAs
                VStack(spacing: 12) {
                    Button("Get started") {
                        showLogin = true
                    }
                    .buttonStyle(LumePrimaryButtonStyle())
                    .frame(maxWidth: .infinity)

                    Button("Sign in") {
                        showLogin = true
                    }
                    .font(.lumeBodyMedium)
                    .foregroundColor(.lumeNavy)
                    .padding(.vertical, 14)
                }
                .padding(.horizontal, 32)
                .padding(.bottom, 48)
            }
        }
        .fullScreenCover(isPresented: $showLogin) {
            LoginView()
        }
    }
}
