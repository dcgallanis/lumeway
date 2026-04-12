import SwiftUI

struct NotesView: View {
    @State private var notes: [NoteItem] = []
    @State private var isLoading = true
    @State private var showEditor = false
    @State private var editingNote: NoteItem?
    @State private var editorContent = ""
    @State private var searchText = ""

    private let service = NotesService()

    var body: some View {
        NavigationStack {
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

                            // Notes grid — two-column masonry-style like site
                            let columns = [
                                GridItem(.flexible(), spacing: 12),
                                GridItem(.flexible(), spacing: 12)
                            ]

                            LazyVGrid(columns: columns, spacing: 12) {
                                ForEach(filteredNotes) { note in
                                    NoteCard(note: note) {
                                        editingNote = note
                                        editorContent = note.content
                                        showEditor = true
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
            }
            .navigationTitle("Notes")
            .navigationBarTitleDisplayMode(.large)
            .toolbarBackground(Color.lumeCream, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbar {
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
            .task { await loadNotes() }
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
