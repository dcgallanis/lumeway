import SwiftUI
import SwiftData

@main
struct LumewayApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
        }
        .modelContainer(for: [
            CachedChecklistItem.self,
            CachedDeadline.self,
            CachedNote.self
        ])
    }
}
