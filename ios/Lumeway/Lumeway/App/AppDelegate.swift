import UIKit
import CoreText

/// Handles system-level callbacks that SwiftUI lifecycle doesn't cover,
/// primarily push notification device token registration.
class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        // Register custom fonts at startup to guarantee availability
        registerCustomFonts()
        return true
    }

    /// Explicitly register all custom font files from the bundle.
    /// This ensures fonts are available even if Info.plist registration
    /// doesn't work due to Xcode project configuration quirks.
    private func registerCustomFonts() {
        let fontFiles = [
            "CormorantGaramond-Regular", "CormorantGaramond-Italic",
            "CormorantGaramond-SemiBold", "CormorantGaramond-Bold",
            "Montserrat-Light", "Montserrat-Regular",
            "Montserrat-Medium", "Montserrat-SemiBold",
            "LibreBaskerville-Regular", "LibreBaskerville-Italic",
            "LibreBaskerville-Bold"
        ]

        for fontName in fontFiles {
            if let fontURL = Bundle.main.url(forResource: fontName, withExtension: "ttf", subdirectory: "Fonts") ?? Bundle.main.url(forResource: fontName, withExtension: "ttf") {
                CTFontManagerRegisterFontsForURL(fontURL as CFURL, .process, nil)
            }
        }

        // Debug: print available custom fonts to verify registration
        #if DEBUG
        let families = ["Cormorant Garamond", "Montserrat", "Libre Baskerville"]
        for family in families {
            let names = UIFont.fontNames(forFamilyName: family)
            if names.isEmpty {
                print("⚠️ Font family '\(family)' NOT found in bundle")
            } else {
                print("✅ Font family '\(family)': \(names)")
            }
        }
        #endif
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        Task { @MainActor in
            PushNotificationManager.shared.setDeviceToken(deviceToken)
        }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("Push registration failed: \(error)")
    }

    // MARK: - UNUserNotificationCenterDelegate

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        // Show notifications even when app is in foreground
        return [.banner, .sound]
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        let category = response.notification.request.content.categoryIdentifier

        switch category {
        case "DEADLINE", "DEADLINE_URGENT":
            // Could navigate to checklist tab
            NotificationCenter.default.post(name: .navigateToChecklist, object: nil)
        case "DAILY_CHECKIN":
            NotificationCenter.default.post(name: .navigateToDashboard, object: nil)
        default:
            break
        }
    }
}

extension Notification.Name {
    static let navigateToChecklist = Notification.Name("navigateToChecklist")
    static let navigateToDashboard = Notification.Name("navigateToDashboard")
    static let switchToTab = Notification.Name("switchToTab")
    static let purchaseCompleted = Notification.Name("purchaseCompleted")
}
