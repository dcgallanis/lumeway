import SwiftUI

struct CalendarView: View {
    @EnvironmentObject var appState: AppState
    @State private var deadlines: [DeadlineItem] = []
    @State private var isLoading = true
    @State private var showAddSheet = false
    @State private var selectedMonth = Date()

    private let service = CalendarService()
    private let calendar = Calendar.current

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        // Month header
                        MonthHeader(date: $selectedMonth)
                            .padding(.horizontal, 20)
                            .padding(.top, 12)

                        // Mini calendar grid
                        MiniCalendarGrid(
                            selectedMonth: selectedMonth,
                            deadlines: deadlines
                        )
                        .padding(.horizontal, 20)

                        // Grouped deadline sections
                        VStack(alignment: .leading, spacing: 14) {
                            if activeDeadlines.isEmpty && !isLoading {
                                VStack(spacing: 12) {
                                    Image(systemName: "calendar.badge.plus")
                                        .font(.system(size: 36))
                                        .foregroundColor(.lumeBorder)
                                    Text("No upcoming deadlines")
                                        .font(.lumeBody)
                                        .foregroundColor(.lumeMuted)
                                    Text("Add important dates to keep track of filing deadlines, court dates, and more.")
                                        .font(.lumeCaption)
                                        .foregroundColor(.lumeMuted)
                                        .multilineTextAlignment(.center)
                                        .padding(.horizontal, 40)
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 32)
                            }

                            // Overdue
                            if !overdueDeadlines.isEmpty {
                                DeadlineGroup(title: "OVERDUE", deadlines: overdueDeadlines,
                                              onToggle: toggleDeadline, onDelete: deleteDeadline)
                            }

                            // Today
                            if !todayDeadlines.isEmpty {
                                DeadlineGroup(title: "TODAY", deadlines: todayDeadlines,
                                              onToggle: toggleDeadline, onDelete: deleteDeadline)
                            }

                            // Tomorrow
                            if !tomorrowDeadlines.isEmpty {
                                DeadlineGroup(title: "TOMORROW", deadlines: tomorrowDeadlines,
                                              onToggle: toggleDeadline, onDelete: deleteDeadline)
                            }

                            // This week
                            if !thisWeekDeadlines.isEmpty {
                                DeadlineGroup(title: "THIS WEEK", deadlines: thisWeekDeadlines,
                                              onToggle: toggleDeadline, onDelete: deleteDeadline)
                            }

                            // Later
                            if !laterDeadlines.isEmpty {
                                DeadlineGroup(title: "LATER", deadlines: laterDeadlines,
                                              onToggle: toggleDeadline, onDelete: deleteDeadline)
                            }

                            // Completed section
                            if !completedDeadlines.isEmpty {
                                DeadlineGroup(title: "COMPLETED", deadlines: completedDeadlines,
                                              onToggle: toggleDeadline, onDelete: deleteDeadline, dimmed: true)
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
            .navigationTitle("Calendar")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.lumeCream, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
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
                await loadDeadlines()
            }
            .task {
                await loadDeadlines()
            }
            .sheet(isPresented: $showAddSheet) {
                AddDeadlineSheet(onSave: { title, date, notes in
                    Task { await addDeadline(title: title, date: date, notes: notes) }
                })
                .presentationDetents([.medium])
            }
        }
    }

    private var activeDeadlines: [DeadlineItem] {
        deadlines.filter { !($0.completed ?? false) }
            .sorted { ($0.daysRemaining ?? 999) < ($1.daysRemaining ?? 999) }
    }

    private var completedDeadlines: [DeadlineItem] {
        deadlines.filter { $0.completed ?? false }
    }

    private var overdueDeadlines: [DeadlineItem] {
        activeDeadlines.filter { ($0.daysRemaining ?? 0) < 0 }
    }

    private var todayDeadlines: [DeadlineItem] {
        activeDeadlines.filter { $0.daysRemaining == 0 }
    }

    private var tomorrowDeadlines: [DeadlineItem] {
        activeDeadlines.filter { $0.daysRemaining == 1 }
    }

    private var thisWeekDeadlines: [DeadlineItem] {
        activeDeadlines.filter { ($0.daysRemaining ?? 999) >= 2 && ($0.daysRemaining ?? 999) <= 7 }
    }

    private var laterDeadlines: [DeadlineItem] {
        activeDeadlines.filter { ($0.daysRemaining ?? 999) > 7 }
    }

    private func loadDeadlines() async {
        do {
            let response = try await service.getDeadlines()
            deadlines = response.deadlines
            isLoading = false
        } catch {
            isLoading = false
        }
        // Fallback: sync from dashboard data if calendar API returned empty
        if deadlines.isEmpty, let dashDeadlines = appState.dashboardData?.deadlines, !dashDeadlines.isEmpty {
            deadlines = dashDeadlines.map { d in
                DeadlineItem(id: d.id, title: d.title, dueDate: d.dueDate, completed: d.completed,
                             category: d.category, notes: d.notes, daysRemaining: d.daysRemaining)
            }
        }
    }

    private func toggleDeadline(_ deadline: DeadlineItem) {
        Task {
            do {
                _ = try await service.toggleDeadline(id: deadline.id)
                await loadDeadlines()
            } catch {}
        }
    }

    private func deleteDeadline(_ deadline: DeadlineItem) {
        Task {
            do {
                _ = try await service.deleteDeadline(id: deadline.id)
                await loadDeadlines()
            } catch {}
        }
    }

    private func addDeadline(title: String, date: String, notes: String?) async {
        do {
            _ = try await service.addDeadline(title: title, dueDate: date, notes: notes)
            await loadDeadlines()
        } catch {}
    }
}

// MARK: - Month Header

struct MonthHeader: View {
    @Binding var date: Date
    private let calendar = Calendar.current

    private var monthYear: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMMM yyyy"
        return formatter.string(from: date)
    }

    var body: some View {
        HStack {
            Button {
                date = calendar.date(byAdding: .month, value: -1, to: date) ?? date
            } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(.lumeNavy)
                    .padding(8)
            }

            Spacer()

            Text(monthYear)
                .font(.lumeHeadingSmall)
                .foregroundColor(.lumeNavy)

            Spacer()

            Button {
                date = calendar.date(byAdding: .month, value: 1, to: date) ?? date
            } label: {
                Image(systemName: "chevron.right")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(.lumeNavy)
                    .padding(8)
            }
        }
    }
}

// MARK: - Mini Calendar Grid

struct MiniCalendarGrid: View {
    let selectedMonth: Date
    let deadlines: [DeadlineItem]

    private let calendar = Calendar.current
    private let dayLabels = ["S", "M", "T", "W", "T", "F", "S"]

    private var daysInMonth: [Date?] {
        guard let range = calendar.range(of: .day, in: .month, for: selectedMonth),
              let firstOfMonth = calendar.date(from: calendar.dateComponents([.year, .month], from: selectedMonth))
        else { return [] }

        let firstWeekday = calendar.component(.weekday, from: firstOfMonth) - 1
        var days: [Date?] = Array(repeating: nil, count: firstWeekday)
        for day in range {
            if let date = calendar.date(byAdding: .day, value: day - 1, to: firstOfMonth) {
                days.append(date)
            }
        }
        return days
    }

    private var deadlineDates: Set<String> {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return Set(deadlines.compactMap { $0.dueDate?.prefix(10).description })
    }

    var body: some View {
        VStack(spacing: 8) {
            // Day of week headers
            HStack(spacing: 0) {
                ForEach(dayLabels, id: \.self) { label in
                    Text(label)
                        .font(.lumeSmall)
                        .fontWeight(.medium)
                        .foregroundColor(.lumeMuted)
                        .frame(maxWidth: .infinity)
                }
            }

            // Calendar grid
            let columns = Array(repeating: GridItem(.flexible(), spacing: 0), count: 7)
            LazyVGrid(columns: columns, spacing: 6) {
                ForEach(Array(daysInMonth.enumerated()), id: \.offset) { _, date in
                    if let date = date {
                        let dayNum = calendar.component(.day, from: date)
                        let formatter = DateFormatter()
                        let _ = formatter.dateFormat = "yyyy-MM-dd"
                        let dateStr = formatter.string(from: date)
                        let hasDeadline = deadlineDates.contains(dateStr)
                        let isToday = calendar.isDateInToday(date)

                        ZStack {
                            if isToday {
                                Circle()
                                    .fill(Color.lumeNavy)
                                    .frame(width: 32, height: 32)
                            }

                            Text("\(dayNum)")
                                .font(.lumeCaption)
                                .foregroundColor(isToday ? .white : .lumeText)

                            if hasDeadline {
                                Circle()
                                    .fill(Color.lumeAccent)
                                    .frame(width: 5, height: 5)
                                    .offset(y: 14)
                            }
                        }
                        .frame(height: 36)
                    } else {
                        Text("")
                            .frame(height: 36)
                    }
                }
            }
        }
        .padding(16)
        .background(Color.lumeWarmWhite)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Color.lumeBorder, lineWidth: 1)
        )
    }
}

// MARK: - Deadline Row

struct DeadlineRow: View {
    let deadline: DeadlineItem
    let onToggle: () -> Void
    let onDelete: () -> Void

    @State private var showDelete = false

    private var daysText: String {
        guard let days = deadline.daysRemaining else { return "" }
        if deadline.completed ?? false { return "Done" }
        if days < 0 { return "Overdue by \(abs(days))d" }
        if days == 0 { return "Due today" }
        if days <= 7 { return "Due in \(days) day\(days == 1 ? "" : "s")" }
        return "You have \(days) days"
    }

    private var urgencyColor: Color {
        guard let days = deadline.daysRemaining, !(deadline.completed ?? false) else { return .lumeMuted }
        if days <= 3 { return .lumeAccent }
        if days <= 14 { return .lumeGold }
        return .lumeGreen
    }

    var body: some View {
        HStack(spacing: 14) {
            // Toggle button
            Button(action: onToggle) {
                ZStack {
                    Circle()
                        .stroke(deadline.completed ?? false ? Color.lumeGreen : urgencyColor, lineWidth: 2)
                        .frame(width: 24, height: 24)
                    if deadline.completed ?? false {
                        Image(systemName: "checkmark")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundColor(.lumeGreen)
                    }
                }
            }

            VStack(alignment: .leading, spacing: 3) {
                Text(deadline.title ?? "Deadline")
                    .font(.lumeBodyMedium)
                    .foregroundColor(.lumeNavy)
                    .strikethrough(deadline.completed ?? false)

                HStack(spacing: 8) {
                    if let dueDate = deadline.dueDate {
                        Text(formatDate(dueDate))
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }
                    Text(daysText)
                        .font(.lumeSmall)
                        .foregroundColor(urgencyColor)
                }
            }

            Spacer()

            // Urgency bar
            if !(deadline.completed ?? false) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(urgencyColor)
                    .frame(width: 4, height: 28)
            }
        }
        .padding(16)
        .background(Color.lumeWarmWhite)
        .cornerRadius(14)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.lumeBorder, lineWidth: 1)
        )
        .swipeActions(edge: .trailing) {
            Button(role: .destructive) {
                onDelete()
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
    }

    private func formatDate(_ dateStr: String) -> String {
        let input = DateFormatter()
        input.dateFormat = "yyyy-MM-dd"
        guard let date = input.date(from: String(dateStr.prefix(10))) else { return dateStr }
        let output = DateFormatter()
        output.dateFormat = "MMM d"
        return output.string(from: date)
    }
}

// MARK: - Deadline Group (Today/Tomorrow/This Week/Later)

struct DeadlineGroup: View {
    let title: String
    let deadlines: [DeadlineItem]
    let onToggle: (DeadlineItem) -> Void
    let onDelete: (DeadlineItem) -> Void
    var dimmed: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(title)
                    .font(.lumeSmall)
                    .fontWeight(.semibold)
                    .foregroundColor(title == "OVERDUE" ? .lumeAccent : .lumeMuted)
                    .tracking(1)
                Spacer()
                Text("\(deadlines.count)")
                    .font(.lumeSmall)
                    .foregroundColor(.lumeMuted)
            }
            .padding(.horizontal, 24)

            ForEach(deadlines) { deadline in
                DeadlineRow(
                    deadline: deadline,
                    onToggle: { onToggle(deadline) },
                    onDelete: { onDelete(deadline) }
                )
                .padding(.horizontal, 20)
                .opacity(dimmed ? 0.6 : 1)
            }
        }
    }
}

// MARK: - Add Deadline Sheet

struct AddDeadlineSheet: View {
    let onSave: (String, String, String?) -> Void
    @Environment(\.dismiss) var dismiss

    @State private var title = ""
    @State private var dueDate = Date()
    @State private var notes = ""

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 18) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("What's the deadline?")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)
                            TextField("e.g., File divorce papers", text: $title)
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

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Due date")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)
                            DatePicker("", selection: $dueDate, displayedComponents: .date)
                                .datePickerStyle(.graphical)
                                .tint(.lumeAccent)
                        }

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Notes (optional)")
                                .font(.lumeCaption)
                                .fontWeight(.medium)
                                .foregroundColor(.lumeNavy)
                            TextField("Any extra details", text: $notes)
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
                            onSave(title, formatter.string(from: dueDate), notes.isEmpty ? nil : notes)
                            dismiss()
                        } label: {
                            Text("Add Deadline")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(LumePrimaryButtonStyle())
                        .disabled(title.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                    .padding(24)
                }
            }
            .navigationTitle("New Deadline")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                        .foregroundColor(.lumeMuted)
                }
            }
        }
    }
}
