import Foundation
import StoreKit

/// Manages in-app purchases via StoreKit 2.
/// Products mirror the web pricing: individual transition passes and bundles.
@MainActor
final class StoreKitManager: ObservableObject {
    static let shared = StoreKitManager()

    @Published var products: [Product] = []
    @Published var purchasedProductIDs: Set<String> = []
    @Published var isLoading = false

    // Product identifiers matching App Store Connect configuration
    static let productIDs: Set<String> = [
        "co.lumeway.pass.estate",
        "co.lumeway.pass.divorce",
        "co.lumeway.pass.jobloss",
        "co.lumeway.pass.disability",
        "co.lumeway.pass.relocation",
        "co.lumeway.pass.retirement",
        "co.lumeway.pass.addiction",
        "co.lumeway.bundle.pick3",
        "co.lumeway.bundle.all",
    ]

    private var transactionListener: Task<Void, Error>?

    private init() {
        transactionListener = listenForTransactions()
        Task { await loadProducts() }
    }

    deinit {
        transactionListener?.cancel()
    }

    // MARK: - Load Products

    func loadProducts() async {
        isLoading = true
        do {
            products = try await Product.products(for: Self.productIDs)
                .sorted { $0.price < $1.price }
            isLoading = false
        } catch {
            print("Failed to load products: \(error)")
            isLoading = false
        }
    }

    // MARK: - Purchase

    func purchase(_ product: Product) async throws -> Bool {
        let result = try await product.purchase()

        switch result {
        case .success(let verification):
            let transaction = try checkVerified(verification)
            await fulfillPurchase(product: product, transaction: transaction)
            await transaction.finish()
            return true

        case .pending:
            // Transaction waiting for approval (Ask to Buy, etc.)
            return false

        case .userCancelled:
            return false

        @unknown default:
            return false
        }
    }

    // MARK: - Restore Purchases

    func restorePurchases() async {
        for await result in Transaction.currentEntitlements {
            if let transaction = try? checkVerified(result) {
                purchasedProductIDs.insert(transaction.productID)
                await transaction.finish()
            }
        }
    }

    // MARK: - Check Access

    func hasAccess(to transition: String) -> Bool {
        let passID = "co.lumeway.pass.\(transition)"
        return purchasedProductIDs.contains(passID)
            || purchasedProductIDs.contains("co.lumeway.bundle.all")
            || purchasedProductIDs.contains("co.lumeway.bundle.pick3") // simplified check
    }

    // MARK: - Product Helpers

    func product(for transition: String) -> Product? {
        let passID = "co.lumeway.pass.\(transition)"
        return products.first { $0.id == passID }
    }

    var bundleAllProduct: Product? {
        products.first { $0.id == "co.lumeway.bundle.all" }
    }

    var bundlePick3Product: Product? {
        products.first { $0.id == "co.lumeway.bundle.pick3" }
    }

    // MARK: - Private

    private func listenForTransactions() -> Task<Void, Error> {
        Task.detached {
            for await result in Transaction.updates {
                if let transaction = try? self.checkVerified(result) {
                    await self.fulfillPurchase(product: nil, transaction: transaction)
                    await transaction.finish()
                }
            }
        }
    }

    private nonisolated func checkVerified<T>(_ result: VerificationResult<T>) throws -> T {
        switch result {
        case .unverified(_, let error):
            throw error
        case .verified(let safe):
            return safe
        }
    }

    private func fulfillPurchase(product: Product?, transaction: Transaction) async {
        purchasedProductIDs.insert(transaction.productID)

        // Notify backend of the purchase
        let api = APIClient.shared
        do {
            try await api.post("/api/iap/verify", body: [
                "product_id": transaction.productID,
                "transaction_id": String(transaction.id),
                "original_id": String(transaction.originalID),
            ])
            // Notify app to refresh tier and dashboard data
            NotificationCenter.default.post(name: .purchaseCompleted, object: nil)
        } catch {
            print("Failed to verify purchase with server: \(error)")
        }
    }
}
