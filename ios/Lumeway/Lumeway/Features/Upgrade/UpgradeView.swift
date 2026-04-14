import SwiftUI
import StoreKit

struct UpgradeView: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) var dismiss
    @StateObject private var store = StoreKitManager.shared

    @State private var isPurchasing = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 32) {
                        Spacer().frame(height: 16)

                        // Header
                        VStack(spacing: 12) {
                            Image(systemName: "sun.max")
                                .font(.system(size: 40, weight: .light))
                                .foregroundColor(.lumeAccent)

                            Text("Unlock your full guide")
                                .font(.lumeHeadingSmall)
                                .foregroundColor(.lumeText)

                            Text("Get step-by-step instructions, scripts,\nkey terms, and expert tips for every task.")
                                .font(.lumeCaptionLight)
                                .foregroundColor(.lumeMuted)
                                .multilineTextAlignment(.center)
                                .lineSpacing(3)
                        }

                        // Feature list
                        VStack(alignment: .leading, spacing: 16) {
                            FeatureRow(icon: "list.number", text: "Detailed step-by-step instructions")
                            FeatureRow(icon: "text.quote", text: "Word-for-word phone scripts")
                            FeatureRow(icon: "book.closed", text: "Key terms explained in plain language")
                            FeatureRow(icon: "exclamationmark.triangle", text: "Common mistakes to avoid")
                            FeatureRow(icon: "person.2", text: "Professional resource contacts")
                            FeatureRow(icon: "bubble.left", text: "Unlimited Navigator chat")
                        }
                        .padding(.horizontal, 32)

                        // Pricing options
                        VStack(spacing: 12) {
                            // Individual pass
                            if let transition = appState.user?.transitionType,
                               let product = store.product(for: transition) {
                                PricingCard(
                                    title: "Bundled Plan",
                                    price: product.displayPrice,
                                    desc: "Full access to your current transition",
                                    isPopular: false
                                ) {
                                    Task { await purchase(product) }
                                }
                            }

                            // All access
                            if let allProduct = store.bundleAllProduct {
                                PricingCard(
                                    title: "Everything",
                                    price: allProduct.displayPrice,
                                    desc: "Full access to all 7 transition guides",
                                    isPopular: true
                                ) {
                                    Task { await purchase(allProduct) }
                                }
                            }

                            // Fallback: web upgrade when no StoreKit products loaded
                            if store.products.isEmpty && !store.isLoading {
                                VStack(spacing: 14) {
                                    Text("Upgrade on the web")
                                        .font(.lumeBodyMedium)
                                        .foregroundColor(.lumeNavy)

                                    Text("In-app purchases are being set up.\nUpgrade on lumeway.co to unlock full access.")
                                        .font(.lumeCaption)
                                        .foregroundColor(.lumeMuted)
                                        .multilineTextAlignment(.center)

                                    Link(destination: URL(string: "https://lumeway.co/pricing")!) {
                                        Text("Go to lumeway.co/pricing")
                                            .font(.lumeBodySemibold)
                                            .foregroundColor(.white)
                                            .frame(maxWidth: .infinity)
                                            .padding(.vertical, 14)
                                            .background(Color.lumeAccent)
                                            .cornerRadius(12)
                                    }
                                }
                                .padding(20)
                                .background(Color.lumeWarmWhite)
                                .cornerRadius(16)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 16)
                                        .stroke(Color.lumeAccent.opacity(0.2), lineWidth: 1)
                                )
                            }
                        }
                        .padding(.horizontal, 24)

                        if let error = errorMessage {
                            Text(error)
                                .font(.lumeCaption)
                                .foregroundColor(.lumeAccent)
                                .padding(.horizontal, 24)
                        }

                        // Restore purchases
                        Button("Restore purchases") {
                            Task { await store.restorePurchases() }
                        }
                        .font(.lumeCaption)
                        .foregroundColor(.lumeMuted)

                        Spacer().frame(height: 32)
                    }
                }
            }
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

    private func purchase(_ product: Product) async {
        isPurchasing = true
        errorMessage = nil
        do {
            let success = try await store.purchase(product)
            if success {
                dismiss()
            }
        } catch {
            errorMessage = "Purchase failed. Please try again."
        }
        isPurchasing = false
    }
}

// MARK: - Feature Row

struct FeatureRow: View {
    let icon: String
    let text: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundColor(.lumeNavy)
                .frame(width: 24)
            Text(text)
                .font(.lumeBody)
                .foregroundColor(.lumeText)
        }
    }
}

// MARK: - Pricing Card

struct PricingCard: View {
    let title: String
    let price: String
    let desc: String
    let isPopular: Bool
    let onPurchase: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            if isPopular {
                Text("Best value")
                    .font(.lumeSmall)
                    .fontWeight(.semibold)
                    .foregroundColor(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
                    .background(Color.lumeGold)
                    .cornerRadius(8)
            }

            Text(title)
                .font(.lumeBodyMedium)
                .foregroundColor(.lumeText)

            Text(price)
                .font(.lumeDisplayMedium)
                .foregroundColor(.lumeNavy)

            Text(desc)
                .font(.lumeSmall)
                .foregroundColor(.lumeMuted)
                .multilineTextAlignment(.center)

            Button(action: onPurchase) {
                Text("Get access")
                    .font(.lumeBodyMedium)
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(isPopular ? Color.lumeAccent : Color.lumeNavy)
                    .cornerRadius(12)
            }
        }
        .padding(20)
        .background(Color.lumeWarmWhite)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(isPopular ? Color.lumeGold : Color.lumeBorder, lineWidth: isPopular ? 2 : 1)
        )
    }
}
