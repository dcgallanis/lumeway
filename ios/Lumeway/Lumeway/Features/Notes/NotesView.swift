import SwiftUI

struct NotesView: View {
    var isEmbedded: Bool = false

    @State private var notes: [NoteItem] = []
    @State private var isLoading = true
    @State private var showEditor = false
    @State private var editingNote: NoteItem?
    @State private var editorContent = ""
    @State private var searchText = ""
    @State private var expandedSections: Set<String> = []

    private let service = NotesService()

    // Group notes by time period
    private var groupedNotes: [(label: String, notes: [NoteItem])] {
        let cal = Calendar.current
        let now = Date()
        let formatter = ISO8601DateFormatter()

        var today: [NoteItem] = []
        var thisWeek: [NoteItem] = []
        var thisMonth: [NoteItem] = []
        var earlier: [NoteItem] = []

        for note in filteredNotes {
            guard let dateStr = note.createdAt ?? note.updatedAt,
                  let date = formatter.date(from: dateStr) else {
                earlier.append(note)
                continue
            }
            if cal.isDateInToday(date) {
                today.append(note)
            } else if cal.isDate(date, equalTo: now, toGranularity: .weekOfYear) {
                thisWeek.append(note)
            } else if cal.isDate(date, equalTo: now, toGranularity: .month) {
                thisMonth.append(note)
            } else {
                earlier.append(note)
            }
        }

        var result: [(String, [NoteItem])] = []
        if !today.isEmpty { result.append(("Today", today)) }
        if !thisWeek.isEmpty { result.append(("This Week", thisWeek)) }
        if !thisMonth.isEmpty { result.append(("This Month", thisMonth)) }
        if !earlier.isEmpty { result.append(("Earlier", earlier)) }
        return result
    }

    var body: some View {
        OptionalNavigationStack(isEmbedded: isEmbedded) {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                if isLoading {
                    ProgressView().tint(.lumeAccent)
                } else if notes.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "note.text")
                            .font(.system(size: 48, weight: .light))
                            .foregroundColor(.lumeMuted)
                        Text("No notes yet")
                            .font(.lumeDisplaySmall)
                            .foregroundColor(.lumeNavy)
                        Text("Tap + to jot down thoughts,\nreminders, or questions.")
                            .font(.lumeCaptionLight)
                            .foregroundColor(.lumeMuted)
                            .multilineTextAlignment(.center)
                    }
                } else {
                    ScrollView {
                        VStack(spacing: 0) {
                            // Navy color-blocked header
                            ZStack {
                                Color.lumeNavy

                                VStack(spacing: 10) {
                                    Image(systemName: "note.text")
                                        .font(.system(size: 28))
                                        .foregroundColor(.lumeGold)

                                    Text("Your Notes")
                                        .font(.lumeDisplayMedium)
                                        .foregroundColor(.white)

                                    Text("\(notes.count) note\(notes.count == 1 ? "" : "s")")
                                        .font(.lumeCaption)
                                        .foregroundColor(.white.opacity(0.6))
                                }
                                .padding(.top, 60)
                                .padding(.bottom, 28)
                            }
                            .overlay(alignment: .topLeading) {
                                if isEmbedded {
                                    EmbeddedBackButton()
                                        .padding(.leading, 16)
                                        .padding(.top, 54)
                                }
                            }
                            .overlay(alignment: .topTrailing) {
                                Button {
                                    editingNote = nil
                                    editorContent = ""
                                    showEditor = true
                                } label: {
                                    Image(systemName: "plus.circle.fill")
                                        .font(.system(size: 22))
                                        .foregroundColor(.white.opacity(0.8))
                                }
                                .padding(.trailing, 16)
                                .padding(.top, 58)
                            }
                            .cornerRadius(20, corners: [.bottomLeft, .bottomRight])

                            VStack(spacing: 14) {
                                // Search bar
                                HStack(spacing: 10) {
                                    Image(systemName: "magnifyingglass")
                                        .font(.system(size: 14))
                                        .foregroundColor(.lumeMuted)
                                    TextField("Search notes...", text: $searchText)
                                        .font(.lumeBody)
                                        .foregroundColor(.lumeText)
                                }
                                .padding(12)
                                .background(Color.lumeWarmWhite)
                                .cornerRadius(12)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.lumeBorder, lineWidth: 1)
                                )

                                // Categorized collapsible sections
                                ForEach(groupedNotes, id: \.label) { group in
                                    VStack(spacing: 0) {
                                        // Section header — tap to expand/collapse
                                        Button {
                                            withAnimation(.easeInOut(duration: 0.2)) {
                                                if expandedSections.contains(group.label) {
                                                    expandedSections.remove(group.label)
                                                } else {
                                                    expandedSections.insert(group.label)
                                                }
                                            }
                                        } label: {
                                            HStack {
                                                Text(group.label)
                                                    .font(.lumeSectionTitle)
                                                    .foregroundColor(.lumeNavy)
                                                Text("\(group.notes.count)")
                                                    .font(.lumeSmall)
                                                    .foregroundColor(.lumeMuted)
                                                Spacer()
                                                Image(systemName: expandedSections.contains(group.label) ? "chevron.up" : "chevron.down")
                                                    .font(.system(size: 12, weight: .medium))
                                                    .foregroundColor(.lumeMuted)
                                            }
                                            .padding(.vertical, 10)
                                        }
                                        .buttonStyle(.plain)

                                        if expandedSections.contains(group.label) {
                                            let columns = [
                                                GridItem(.flexible(), spacing: 12),
                                                GridItem(.flexible(), spacing: 12)
                                            ]

                                            LazyVGrid(columns: columns, spacing: 12) {
                                                ForEach(group.notes) { note in
                                                    NoteCard(note: note) {
                                                        editingNote = note
                                                        editorContent = note.content
                                                        showEditor = true
                                                    }
                                                }
                                            }
                                            .padding(.bottom, 8)
                                        }
                                    }
                                }

                                if filteredNotes.isEmpty {
                                    Text("No notes match your search.")
                                        .font(.lumeBody)
                                        .foregroundColor(.lumeMuted)
                                        .padding(.top, 20)
                                }
                            }
                            .padding(20)
                        }
                    }
                    .ignoresSafeArea(edges: .top)
                }
            }
            .navigationBarHidden(!notes.isEmpty)
            .navigationTitle(notes.isEmpty ? "Notes" : "")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if notes.isEmpty {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button {
                            editingNote = nil
                            editorContent = ""
                            showEditor = true
                        } label: {
                            Image(systemName: "plus")
                                .foregroundColor(.lumeNavy)
                        }
                    }
                }
            }
            .sheet(isPresented: $showEditor) {
                NoteEditorView(
                    content: $editorContent,
                    isEditing: editingNote != nil,
                    onSave: {
                        Task { await saveNote() }
                    },
                    onDelete: editingNote != nil ? {
                        Task { await deleteNote() }
                    } : nil
                )
            }
            .task {
                await loadNotes()
                // Auto-expand sections that have notes
                for group in groupedNotes {
                    expandedSections.insert(group.label)
                }
            }
            .refreshable { await loadNotes() }
        }
    }

    private var filteredNotes: [NoteItem] {
        if searchText.isEmpty { return notes }
        return notes.filter { $0.content.localizedCaseInsensitiveContains(searchText) }
    }

    private func loadNotes() async {
        do {
            let response = try await service.getNotes()
            notes = response.notes
            isLoading = false
            // Expand all sections on first load
            if expandedSections.isEmpty {
                for group in groupedNotes {
                    expandedSections.insert(group.label)
                }
            }
        } catch {
            isLoading = false
        }
    }

    private func saveNote() async {
        let text = editorContent.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        if let existing = editingNote {
            _ = try? await service.updateNote(id: existing.id, content: text)
        } else {
            _ = try? await service.createNote(content: text)
        }
        showEditor = false
        await loadNotes()
    }

    private func deleteNote() async {
        guard let note = editingNote else { return }
        _ = try? await service.deleteNote(id: note.id)
        showEditor = false
        await loadNotes()
    }
}

// MARK: - Note Card (compact, site-style)

struct NoteCard: View {
    let note: NoteItem
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 8) {
                Text(note.content)
                    .font(.lumeBody)
                    .foregroundColor(.lumeText)
                    .lineLimit(6)
                    .multilineTextAlignment(.leading)

                if let date = note.createdAt {
                    Text(formatDate(date))
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .background(Color.lumeWarmWhite)
            .cornerRadius(14)
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(Color.lumeBorder, lineWidth: 1)
            )
        }
    }

    private func formatDate(_ isoString: String) -> String {
        let formatter = ISO8601DateFormatter()
        guard let date = formatter.date(from: isoString) else { return isoString }
        let display = DateFormatter()
        display.dateFormat = "MMM d"
        return display.string(from: date)
    }
}

// MARK: - Note Editor

struct NoteEditorView: View {
    @Binding var content: String
    let isEditing: Bool
    let onSave: () -> Void
    let onDelete: (() -> Void)?
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                VStack {
                    TextEditor(text: $content)
                        .font(.lumeBody)
                        .foregroundColor(.lumeText)
                        .scrollContentBackground(.hidden)
                        .padding(16)

                    if let onDelete = onDelete {
                        Button(role: .destructive) {
                            onDelete()
                        } label: {
                            Text("Delete note")
                                .font(.lumeCaption)
                                .foregroundColor(.lumeAccent)
                        }
                        .padding(.bottom, 24)
                    }
                }
            }
            .navigationTitle(isEditing ? "Edit Note" : "New Note")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                        .foregroundColor(.lumeMuted)
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Save") { onSave() }
                        .fontWeight(.semibold)
                        .foregroundColor(.lumeNavy)
                        .disabled(content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
    }
}
