import Foundation
import UserNotifications
import UIKit

/// Handles push notification registration, permissions, and local deadline reminders.
@MainActor
final class PushNotificationManager: ObservableObject {
    static let shared = PushNotificationManager()

    @Published var isAuthorized = false
    @Published var deviceToken: String?

    private init() {}

    // MARK: - Permission Request

    func requestPermission() async {
        let center = UNUserNotificationCenter.current()

        do {
            let granted = try await center.requestAuthorization(options: [.alert, .badge, .sound])
            isAuthorized = granted

            if granted {
                // Register for remote notifications on main thread
                UIApplication.shared.registerForRemoteNotifications()
            }
        } catch {
            print("Notification permission error: \(error)")
        }
    }

    func checkCurrentStatus() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        isAuthorized = settings.authorizationStatus == .authorized
    }

    // MARK: - Device Token

    func setDeviceToken(_ tokenData: Data) {
        let token = tokenData.map { String(format: "%02.2hhx", $0) }.joined()
        self.deviceToken = token
        // Send to server
        Task { await registerTokenWithServer(token) }
    }

    private func registerTokenWithServer(_ token: String) async {
        let api = APIClient.shared
        do {
            try await api.post("/api/push/register", body: [
                "token": token,
                "platform": "ios"
            ])
        } catch {
            print("Failed to register push token: \(error)")
        }
    }

    // MARK: - Local Deadline Reminders

    func scheduleDeadlineReminders(deadlines: [Deadline]) async {
        let center = UNUserNotificationCenter.current()

        // Remove existing deadline notifications
        center.removePendingNotificationRequests(withIdentifiers:
            deadlines.map { "deadline-\($0.id)" } +
            deadlines.map { "deadline-urgent-\($0.id)" }
        )

        guard isAuthorized else { return }

        for deadline in deadlines {
            guard let dueDate = deadline.dueDate,
                  let date = parseDate(dueDate),
                  deadline.completed != true else { continue }

            // Schedule reminder 3 days before
            let threeDaysBefore = Calendar.current.date(byAdding: .day, value: -3, to: date)
            if let reminderDate = threeDaysBefore, reminderDate > Date() {
                let content = UNMutableNotificationContent()
                content.title = "Upcoming deadline"
                content.body = "\(deadline.title ?? "A deadline") is due in 3 days."
                content.sound = .default
                content.categoryIdentifier = "DEADLINE"

                let components = Calendar.current.dateComponents([.year, .month, .day, .hour], from: reminderDate)
                let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: false)

                let request = UNNotificationRequest(
                    identifier: "deadline-\(deadline.id)",
                    content: content,
                    trigger: trigger
                )
                try? await center.add(request)
            }

            // Schedule urgent reminder day-of
            if date > Date() {
                let content = UNMutableNotificationContent()
                content.title = "Deadline today"
                content.body = "\(deadline.title ?? "A deadline") is due today."
                content.sound = .default
                content.categoryIdentifier = "DEADLINE_URGENT"

                var components = Calendar.current.dateComponents([.year, .month, .day], from: date)
                components.hour = 9 // 9 AM on the due date

                let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: false)

                let request = UNNotificationRequest(
                    identifier: "deadline-urgent-\(deadline.id)",
                    content: content,
                    trigger: trigger
                )
                try? await center.add(request)
            }
        }
    }

    // MARK: - Daily Check-in Reminder

    func scheduleDailyReminder(enabled: Bool, hour: Int = 9, minute: Int = 0) async {
        let center = UNUserNotificationCenter.current()
        center.removePendingNotificationRequests(withIdentifiers: ["daily-checkin"])

        guard enabled && isAuthorized else { return }

        let content = UNMutableNotificationContent()
        content.title = "Your Lumeway check-in"
        content.body = "Take a moment to review your next step."
        content.sound = .default
        content.categoryIdentifier = "DAILY_CHECKIN"

        var components = DateComponents()
        components.hour = hour
        components.minute = minute

        let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: true)
        let request = UNNotificationRequest(
            identifier: "daily-checkin",
            content: content,
            trigger: trigger
        )

        try? await center.add(request)
    }

    // MARK: - Helpers

    private func parseDate(_ string: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withFullDate, .withDashSeparatorInDate]
        if let date = formatter.date(from: string) { return date }

        // Try with time
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: string)
    }
}
