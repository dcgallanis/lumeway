import Foundation
import SwiftData
import Network

/// Manages offline caching and sync for all data types.
/// Fetches from API when online, falls back to SwiftData cache when offline,
/// and queues mutations for later sync.
@MainActor
final class OfflineRepository: ObservableObject {
    static let shared = OfflineRepository()

    @Published var isOnline = true

    private let monitor = NWPathMonitor()
    private let monitorQueue = DispatchQueue(label: "NetworkMonitor")
    private var modelContext: ModelContext?

    private let checklistService = ChecklistService()
    private let guideService = GuideService()
    private let notesService = NotesService()

    private init() {
        monitor.pathUpdateHandler = { [weak self] path in
            Task { @MainActor in
                let wasOffline = self?.isOnline == false
                self?.isOnline = path.status == .satisfied
                // When coming back online, flush pending actions
                if wasOffline && path.status == .satisfied {
                    await self?.syncPendingActions()
                }
            }
        }
        monitor.start(queue: monitorQueue)
    }

    func configure(modelContext: ModelContext) {
        self.modelContext = modelContext
    }

    // MARK: - Checklist

    func getChecklist() async -> [FullChecklistItem] {
        // Try API first
        if isOnline {
            do {
                let response = try await checklistService.getChecklist()
                await cacheChecklistItems(response.items)
                return response.items
            } catch {
                print("Checklist fetch failed, using cache: \(error)")
            }
        }

        // Fall back to cache
        return await loadCachedChecklist()
    }

    func toggleChecklistItem(id: Int) async -> Bool? {
        if isOnline {
            do {
                let response = try await checklistService.toggleItem(id: id)
                return response.isCompleted
            } catch {
                print("Toggle failed, queueing: \(error)")
            }
        }

        // Queue for later sync
        await queueAction(type: "toggle", itemId: id)

        // Optimistically update cache
        return await toggleCachedItem(id: id)
    }

    func skipChecklistItem(id: Int) async -> Bool {
        if isOnline {
            do {
                _ = try await checklistService.skipItem(id: id)
                return true
            } catch {
                print("Skip failed, queueing: \(error)")
            }
        }

        await queueAction(type: "skip", itemId: id)
        return true
    }

    // MARK: - Guides

    func getGuide(transition: String) async -> GuideDetailResponse? {
        if isOnline {
            do {
                let response = try await guideService.getGuide(transition: transition)
                await cacheGuide(transition: transition, response: response)
                return response
            } catch {
                print("Guide fetch failed, using cache: \(error)")
            }
        }

        return await loadCachedGuide(transition: transition)
    }

    // MARK: - Sync Engine

    func syncPendingActions() async {
        guard let context = modelContext else { return }

        let descriptor = FetchDescriptor<PendingAction>(
            sortBy: [SortDescriptor(\.createdAt)]
        )

        guard let actions = try? context.fetch(descriptor), !actions.isEmpty else { return }

        print("Syncing \(actions.count) pending actions...")

        for action in actions {
            var success = false

            switch action.actionType {
            case "toggle":
                if let id = action.itemId {
                    do {
                        _ = try await checklistService.toggleItem(id: id)
                        success = true
                    } catch { /* retry later */ }
                }
            case "skip":
                if let id = action.itemId {
                    do {
                        _ = try await checklistService.skipItem(id: id)
                        success = true
                    } catch { /* retry later */ }
                }
            default:
                success = true // Unknown action, remove it
            }

            if success {
                context.delete(action)
            } else {
                action.retryCount += 1
                if action.retryCount > 5 {
                    context.delete(action) // Give up after 5 retries
                }
            }
        }

        try? context.save()
    }

    // MARK: - Cache Operations

    private func cacheChecklistItems(_ items: [FullChecklistItem]) async {
        guard let context = modelContext else { return }

        // Clear existing cached items
        try? context.delete(model: CachedChecklistItem.self)

        for item in items {
            let cached = CachedChecklistItem(
                itemId: item.id,
                title: item.title,
                phase: item.phase,
                completed: item.isCompleted,
                sortOrder: item.sortOrder ?? 0,
                transitionType: item.transitionType
            )
            context.insert(cached)
        }

        try? context.save()
    }

    private func loadCachedChecklist() async -> [FullChecklistItem] {
        guard let context = modelContext else { return [] }

        let descriptor = FetchDescriptor<CachedChecklistItem>(
            sortBy: [SortDescriptor(\.sortOrder), SortDescriptor(\.itemId)]
        )

        guard let cached = try? context.fetch(descriptor) else { return [] }

        return cached.map { item in
            FullChecklistItem(
                id: item.itemId,
                transitionType: item.transitionType,
                phase: item.phase,
                itemText: item.title,
                isCompleted: item.completed,
                completedAt: nil,
                sortOrder: item.sortOrder
            )
        }
    }

    private func toggleCachedItem(id: Int) async -> Bool? {
        guard let context = modelContext else { return nil }

        var descriptor = FetchDescriptor<CachedChecklistItem>(
            predicate: #Predicate { $0.itemId == id }
        )
        descriptor.fetchLimit = 1

        guard let items = try? context.fetch(descriptor), let item = items.first else { return nil }

        item.completed.toggle()
        try? context.save()
        return item.completed
    }

    private func cacheGuide(transition: String, response: GuideDetailResponse) async {
        guard let context = modelContext else { return }

        // Encode response to JSON data
        guard let data = try? JSONEncoder().encode(response) else { return }

        // Upsert
        var descriptor = FetchDescriptor<CachedGuide>(
            predicate: #Predicate { $0.transition == transition }
        )
        descriptor.fetchLimit = 1

        if let existing = try? context.fetch(descriptor).first {
            existing.jsonData = data
            existing.lastSynced = Date()
        } else {
            let cached = CachedGuide(transition: transition, jsonData: data)
            context.insert(cached)
        }

        try? context.save()
    }

    private func loadCachedGuide(transition: String) async -> GuideDetailResponse? {
        guard let context = modelContext else { return nil }

        var descriptor = FetchDescriptor<CachedGuide>(
            predicate: #Predicate { $0.transition == transition }
        )
        descriptor.fetchLimit = 1

        guard let cached = try? context.fetch(descriptor).first else { return nil }
        return try? JSONDecoder().decode(GuideDetailResponse.self, from: cached.jsonData)
    }

    private func queueAction(type: String, itemId: Int? = nil, payload: String? = nil) async {
        guard let context = modelContext else { return }

        let action = PendingAction(actionType: type, itemId: itemId, payload: payload)
        context.insert(action)
        try? context.save()
    }
}
