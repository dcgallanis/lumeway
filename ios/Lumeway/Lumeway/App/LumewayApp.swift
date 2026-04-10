import SwiftUI
import SwiftData

@main
struct LumewayApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
        }
        .modelContainer(for: [
            CachedChecklistItem.self,
            CachedDeadline.self,
            CachedNote.self,
            CachedGuide.self,
            PendingAction.self
        ])
    }
}
