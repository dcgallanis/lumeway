import SwiftUI

struct ActivityLogView: View {
    var isEmbedded: Bool = false

    @State private var entries: [ActivityEntry] = []
    @State private var isLoading = true
    @State private var showAddSheet = false
    @State private var selectedFilter: String? = nil

    private let service = ActivityLogService()

    // Match site dashboard activity types exactly
    private let actionTypes: [(id: String, label: String, icon: String, color: Color)] = [
        ("phone_call", "Phone Call", "phone.fill", .lumeGreen),
        ("email_sent", "Email Sent", "envelope.fill", Color(hex: "5E8C9A")),
        ("appointment", "Appointment", "calendar.badge.clock", .lumeNavy),
        ("form_submitted", "Form Submitted", "doc.text.fill", .lumeAccent),
        ("document_filed", "Document Filed", "folder.fill", .lumeGold),
        ("other", "Other", "ellipsis.circle.fill", Color(hex: "6B7B8D")),
    ]

    var body: some View {
        OptionalNavigationStack(isEmbedded: isEmbedded) {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 18) {
                        // Filter chips
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 10) {
                                FilterChip(label: "All", isSelected: selectedFilter == nil) {
                                    selectedFilter = nil
                                }
                                ForEach(actionTypes, id: \.id) { type in
                                    FilterChip(
                                        label: type.label,
                                        isSelected: selectedFilter == type.id
                                    ) {
                                        selectedFilter = selectedFilter == type.id ? nil : type.id
                                    }
                                }
                            }
                            .padding(.horizontal, 20)
                        }
                        .padding(.top, 8)

                        // Entries grouped by date
                        if filteredEntries.isEmpty && !isLoading {
                            VStack(spacing: 12) {
                                Image(systemName: "note.text")
                                    .font(.system(size: 36))
                                    .foregroundColor(.lumeBorder)
                                Text("No activity logged yet")
                                    .font(.lumeBody)
                                    .foregroundColor(.lumeMuted)
                                Text("Keep track of calls, emails, meetings, and filings related to your transition.")
                                    .font(.lumeCaption)
                                    .foregroundColor(.lumeMuted)
                                    .multilineTextAlignment(.center)
                                    .padding(.horizontal, 40)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 40)
                        }

                        ForEach(groupedByDate, id: \.key) { group in
                            VStack(alignment: .leading, spacing: 10) {
                                Text(group.key)
                                    .font(.lumeCaption)
                                    .fontWeight(.medium)
                                    .foregroundColor(.lumeMuted)
                                    .padding(.horizontal, 24)

                                ForEach(group.entries) { entry in
                                    ActivityEntryRow(
                                        entry: entry,
                                        typeInfo: typeFor(entry.actionType),
                                        onDelete: { deleteEntry(entry) }
                                    )
                                    .padding(.horizontal, 20)
                                }
                            }
                        }

                        Spacer().frame(height: 100)
                    }
                }

                if isLoading {
                    ProgressView()
                        .tint(.lumeAccent)
                }
            }
            .navigationTitle("Activity Log")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.lumeCream, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.light, for: .navigationBar)
            .tint(.lumeNavy)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showAddSheet = true
                    } label: {
                        Image(systemName: "plus.circle.fill")
                            .font(.system(size: 22))
                            .foregroundColor(.lumeAccent)
                    }
                }
            }
            .refreshable {
                await loadEntries()
            }
            .task {
                await loadEntries()
            }
            .sheet(isPresented: $showAddSheet) {
                AddActivitySheet(actionTypes: actionTypes, onSave: { type, desc, date, contact, org in
                    Task { await addEntry(type: type, desc: desc, date: date, contact: contact, org: org) }
                })
                .presentationDetents([.large])
            }
        }
    }

    private var filteredEntries: [ActivityEntry] {
        guard let filter = selectedFilter else { return entries }
        return entries.filter { $0.actionType == filter }
    }

    private struct DateGroup: Identifiable {
        let key: String
        let entries: [ActivityEntry]
        var id: String { key }
    }

    private var groupedByDate: [DateGroup] {
        let grouped = Dictionary(grouping: filteredEntries) { entry -> String in
            guard let dateStr = entry.date else { return "Unknown" }
            return formatGroupDate(dateStr)
        }
        return grouped.map { DateGroup(key: $0.key, entries: $0.value) }
            .sorted { $0.key > $1.key }
    }

    private func typeFor(_ actionType: String?) -> (label: String, icon: String, color: Color) {
        guard let type = actionType,
              let found = actionTypes.first(where: { $0.id == type }) else {
            return ("Other", "ellipsis.circle.fill", Color(hex: "6B7B8D"))
        }
        return (found.label, found.icon, found.color)
    }

    private func formatGroupDate(_ dateStr: String) -> String {
        let input = DateFormatter()
        input.dateFormat = "yyyy-MM-dd"
        guard let date = input.date(from: String(dateStr.prefix(10))) else { return dateStr }
        let output = DateFormatter()
        output.dateFormat = "EEEE, MMM d"
        return output.string(from: date)
    }

    private func loadEntries() async {
        do {
            let response = try await service.getEntries()
            entries = response.entries
            isLoading = false
        } catch {
            isLoading = false
        }
    }

    private func addEntry(type: String, desc: String, date: String, contact: String?, org: String?) async {
        do {
            _ = try await service.addEntry(actionType: type, description: desc, date: date, contactName: contact, organization: org)
            await loadEntries()
        } catch {}
    }

    private func deleteEntry(_ entry: ActivityEntry) {
        Task {
            do {
                _ = try await service.deleteEntry(id: entry.id)
                await loadEntries()
            } catch {}
        }
    }
}

// MARK: - Filter Chip

struct FilterChip: View {
    let label: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.lumeCaption)
                .fontWeight(isSelected ? .semibold : .regular)
                .foregroundColor(isSelected ? .white : .lumeNavy)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(isSelected ? Color.lumeNavy : Color.lumeWarmWhite)
                .cornerRadius(20)
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .stroke(isSelected ? Color.clear : Color.lumeBorder, lineWidth: 1)
                )
        }
    }
}

// MARK: - Activity Entry Row

struct ActivityEntryRow: View {
    let entry: ActivityEntry
    let typeInfo: (label: String, icon: String, color: Color)
    let onDelete: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            // Type icon
            ZStack {
                RoundedRectangle(cornerRadius: 10)
                    .fill(typeInfo.color.opacity(0.12))
                    .frame(width: 38, height: 38)
                Image(systemName: typeInfo.icon)
                    .font(.system(size: 15))
                    .foregroundColor(typeInfo.color)
            }

            VStack(alignment: .leading, spacing: 4) {
                // Description — full text, not truncated
                if let desc = entry.description, !desc.isEmpty {
                    Text(desc)
                        .font(.lumeBody)
                        .foregroundColor(.lumeNavy)
                        .fixedSize(horizontal: false, vertical: true)
                }

                // Metadata row
                HStack(spacing: 8) {
                    Text(typeInfo.label)
                        .font(.lumeSmall)
                        .foregroundColor(typeInfo.color)

                    if let contact = entry.contactName, !contact.isEmpty {
                        HStack(spacing: 3) {
                            Image(systemName: "person.fill")
                                .font(.system(size: 8))
                            Text(contact)
                        }
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)
                    }

                    if let org = entry.organization, !org.isEmpty {
                        HStack(spacing: 3) {
                            Image(systemName: "building.2.fill")
                                .font(.system(size: 8))
                            Text(org)
                        }
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)
                    }
                }

                // Date
                if let dateStr = entry.date {
                    Text(formatEntryDate(dateStr))
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)
                }
            }

            Spacer()

            // Delete button
            Button(action: onDelete) {
                Image(systemName: "trash")
                    .font(.system(size: 12))
                    .foregroundColor(.lumeMuted.opacity(0.5))
            }
        }
        .padding(14)
        .background(Color.lumeWarmWhite)
        .cornerRadius(14)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.lumeBorder, lineWidth: 1)
        )
    }

    private func formatEntryDate(_ dateStr: String) -> String {
        let input = DateFormatter()
        input.dateFormat = "yyyy-MM-dd"
        guard let date = input.date(from: String(dateStr.prefix(10))) else { return dateStr }
        let output = DateFormatter()
        output.dateFormat = "MMM d, yyyy"
        return output.string(from: date)
    }
}

// MARK: - Add Activity Sheet

struct AddActivitySheet: View {
    let actionTypes: [(id: String, label: String, icon: String, color: Color)]
    let onSave: (String, String, String, String?, String?) -> Void
    @Environment(\.dismiss) var dismiss

    @State private var selectedType = "phone_call"
    @State private var description = ""
    @State private var date = Date()
    @State private var contactName = ""
    @State private var organization = ""

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        // Type picker
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Type of activity")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)

                            LazyVGrid(columns: [
                                GridItem(.flexible()),
                                GridItem(.flexible()),
                                GridItem(.flexible())
                            ], spacing: 10) {
                                ForEach(actionTypes, id: \.id) { type in
                                    Button {
                                        selectedType = type.id
                                    } label: {
                                        VStack(spacing: 6) {
                                            Image(systemName: type.icon)
                                                .font(.system(size: 18))
                                                .foregroundColor(selectedType == type.id ? .white : type.color)
                                            Text(type.label)
                                                .font(.lumeSmall)
                                                .foregroundColor(selectedType == type.id ? .white : .lumeNavy)
                                        }
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 14)
                                        .background(selectedType == type.id ? type.color : type.color.opacity(0.08))
                                        .cornerRadius(12)
                                    }
                                }
                            }
                        }

                        // Description
                        VStack(alignment: .leading, spacing: 8) {
                            Text("What happened?")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)

                            ZStack(alignment: .topLeading) {
                                if description.isEmpty {
                                    Text("What happened...")
                                        .font(.lumeBody)
                                        .foregroundColor(.lumeMuted.opacity(0.5))
                                        .padding(.horizontal, 18)
                                        .padding(.vertical, 18)
                                        .allowsHitTesting(false)
                                }
                                TextEditor(text: $description)
                                    .font(.lumeBody)
                                    .foregroundColor(.lumeText)
                                    .scrollContentBackground(.hidden)
                                    .frame(minHeight: 80)
                                    .padding(12)
                            }
                            .background(Color.lumeWarmWhite)
                            .cornerRadius(12)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color.lumeBorder, lineWidth: 1)
                            )
                        }

                        // Date
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Date")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)
                            DatePicker("", selection: $date, in: ...Date(), displayedComponents: .date)
                                .labelsHidden()
                                .tint(.lumeAccent)
                        }

                        // Contact name
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Contact name (optional)")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)
                            TextField("Who you dealt with", text: $contactName)
                                .font(.lumeBody)
                                .foregroundColor(.lumeText)
                                .padding(14)
                                .background(Color.lumeWarmWhite)
                                .cornerRadius(12)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.lumeBorder, lineWidth: 1)
                                )
                        }

                        // Organization
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Organization (optional)")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)
                            TextField("Company/agency", text: $organization)
                                .font(.lumeBody)
                                .foregroundColor(.lumeText)
                                .padding(14)
                                .background(Color.lumeWarmWhite)
                                .cornerRadius(12)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.lumeBorder, lineWidth: 1)
                                )
                        }

                        Button {
                            let formatter = DateFormatter()
                            formatter.dateFormat = "yyyy-MM-dd"
                            onSave(
                                selectedType,
                                description,
                                formatter.string(from: date),
                                contactName.isEmpty ? nil : contactName,
                                organization.isEmpty ? nil : organization
                            )
                            dismiss()
                        } label: {
                            Text("Log Activity")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(LumePrimaryButtonStyle())
                        .disabled(description.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                    .padding(24)
                }
            }
            .navigationTitle("Log Activity")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.lumeCream, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.light, for: .navigationBar)
            .tint(.lumeNavy)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                        .foregroundColor(.lumeMuted)
                }
            }
        }
        .environment(\.colorScheme, .light)
    }
}
