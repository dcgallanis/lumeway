import UIKit

/// Handles system-level callbacks that SwiftUI lifecycle doesn't cover,
/// primarily push notification device token registration.
class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {

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
}
