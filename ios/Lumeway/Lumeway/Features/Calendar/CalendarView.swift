import SwiftUI

struct CalendarView: View {
    @EnvironmentObject var appState: AppState
    @State private var deadlines: [DeadlineItem] = []
    @State private var isLoading = true
    @State private var showAddSheet = false
    @State private var selectedMonth = Date()
    @State private var selectedDate: Date? = nil

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

                        // Calendar grid with clickable days
                        InteractiveCalendarGrid(
                            selectedMonth: selectedMonth,
                            deadlines: deadlines,
                            selectedDate: $selectedDate
                        )
                        .padding(.horizontal, 20)

                        // Selected day event popup
                        if let date = selectedDate {
                            let eventsForDay = deadlinesForDate(date)
                            if !eventsForDay.isEmpty {
                                VStack(alignment: .leading, spacing: 10) {
                                    HStack {
                                        Text(formatFullDate(date))
                                            .font(.lumeHeadingSmall)
                                            .foregroundColor(.lumeNavy)
                                        Spacer()
                                        Button {
                                            withAnimation { selectedDate = nil }
                                        } label: {
                                            Image(systemName: "xmark.circle.fill")
                                                .font(.system(size: 18))
                                                .foregroundColor(.lumeMuted)
                                        }
                                    }

                                    ForEach(eventsForDay) { deadline in
                                        HStack(spacing: 12) {
                                            RoundedRectangle(cornerRadius: 2)
                                                .fill(urgencyColor(deadline))
                                                .frame(width: 4, height: 36)

                                            VStack(alignment: .leading, spacing: 3) {
                                                Text(deadline.title ?? "Deadline")
                                                    .font(.lumeBodyMedium)
                                                    .foregroundColor(.lumeNavy)
                                                if let notes = deadline.notes, !notes.isEmpty {
                                                    Text(notes)
                                                        .font(.lumeSmall)
                                                        .foregroundColor(.lumeMuted)
                                                        .lineLimit(2)
                                                }
                                            }

                                            Spacer()

                                            Button {
                                                toggleDeadline(deadline)
                                            } label: {
                                                ZStack {
                                                    Circle()
                                                        .stroke(deadline.completed ?? false ? Color.lumeGreen : urgencyColor(deadline), lineWidth: 2)
                                                        .frame(width: 24, height: 24)
                                                    if deadline.completed ?? false {
                                                        Image(systemName: "checkmark")
                                                            .font(.system(size: 11, weight: .bold))
                                                            .foregroundColor(.lumeGreen)
                                                    }
                                                }
                                            }
                                        }
                                        .padding(14)
                                        .background(Color.lumeWarmWhite)
                                        .cornerRadius(12)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 12)
                                                .stroke(Color.lumeBorder, lineWidth: 1)
                                        )
                                    }
                                }
                                .padding(16)
                                .background(Color.lumeAccent.opacity(0.04))
                                .cornerRadius(16)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 16)
                                        .stroke(Color.lumeAccent.opacity(0.12), lineWidth: 1)
                                )
                                .padding(.horizontal, 20)
                                .transition(.opacity.combined(with: .move(edge: .top)))
                            }
                        }

                        // Key deadlines — simplified, just title + date
                        if !majorDeadlines.isEmpty {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Key Deadlines")
                                    .font(.lumeSectionTitle)
                                    .foregroundColor(.lumeNavy)
                                    .padding(.horizontal, 24)

                                ForEach(majorDeadlines) { deadline in
                                    HStack(spacing: 14) {
                                        RoundedRectangle(cornerRadius: 2)
                                            .fill(urgencyColor(deadline))
                                            .frame(width: 4, height: 32)

                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(deadline.title ?? "Deadline")
                                                .font(.lumeBodyMedium)
                                                .foregroundColor(deadline.completed ?? false ? .lumeMuted : .lumeNavy)
                                                .strikethrough(deadline.completed ?? false)

                                            if let dueDate = deadline.dueDate {
                                                HStack(spacing: 6) {
                                                    Text(formatDateShort(dueDate))
                                                        .font(.lumeSmall)
                                                        .foregroundColor(.lumeMuted)
                                                    if let days = deadline.daysRemaining, !(deadline.completed ?? false) {
                                                        Text(daysText(days))
                                                            .font(.lumeSmall)
                                                            .foregroundColor(days <= 3 ? .lumeAccent : .lumeMuted)
                                                    }
                                                }
                                            }
                                        }

                                        Spacer()
                                    }
                                    .padding(.horizontal, 20)
                                }
                            }
                        }

                        if majorDeadlines.isEmpty && !isLoading {
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

    // Only show active (not completed) deadlines in the key list
    private var majorDeadlines: [DeadlineItem] {
        deadlines.filter { !($0.completed ?? false) }
            .sorted { ($0.daysRemaining ?? 999) < ($1.daysRemaining ?? 999) }
    }

    private func deadlinesForDate(_ date: Date) -> [DeadlineItem] {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        let dateStr = formatter.string(from: date)
        return deadlines.filter { $0.dueDate?.prefix(10) == dateStr }
    }

    private func urgencyColor(_ deadline: DeadlineItem) -> Color {
        guard let days = deadline.daysRemaining, !(deadline.completed ?? false) else { return .lumeMuted }
        if days < 0 { return .lumeAccent }
        if days <= 3 { return .lumeAccent }
        if days <= 14 { return .lumeGold }
        return .lumeGreen
    }

    private func daysText(_ days: Int) -> String {
        if days < 0 { return "Overdue" }
        if days == 0 { return "Due today" }
        if days == 1 { return "Due tomorrow" }
        return "in \(days) days"
    }

    private func formatDateShort(_ dateStr: String) -> String {
        let input = DateFormatter()
        input.dateFormat = "yyyy-MM-dd"
        guard let date = input.date(from: String(dateStr.prefix(10))) else { return dateStr }
        let output = DateFormatter()
        output.dateFormat = "MMM d, yyyy"
        return output.string(from: date)
    }

    private func formatFullDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "EEEE, MMMM d"
        return formatter.string(from: date)
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

// MARK: - Interactive Calendar Grid (clickable days)

struct InteractiveCalendarGrid: View {
    let selectedMonth: Date
    let deadlines: [DeadlineItem]
    @Binding var selectedDate: Date?

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

    private var deadlineDateSet: Set<String> {
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
                        let hasDeadline = deadlineDateSet.contains(dateStr)
                        let isToday = calendar.isDateInToday(date)
                        let isSelected = selectedDate.map { calendar.isDate($0, inSameDayAs: date) } ?? false

                        Button {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                if isSelected {
                                    selectedDate = nil
                                } else if hasDeadline {
                                    selectedDate = date
                                }
                            }
                        } label: {
                            ZStack {
                                if isSelected {
                                    Circle()
                                        .fill(Color.lumeAccent)
                                        .frame(width: 34, height: 34)
                                } else if isToday {
                                    Circle()
                                        .fill(Color.lumeNavy)
                                        .frame(width: 34, height: 34)
                                }

                                Text("\(dayNum)")
                                    .font(.lumeCaption)
                                    .foregroundColor(isSelected || isToday ? .white : .lumeText)

                                if hasDeadline && !isSelected {
                                    Circle()
                                        .fill(Color.lumeAccent)
                                        .frame(width: 6, height: 6)
                                        .offset(y: 15)
                                }
                            }
                            .frame(height: 38)
                        }
                        .buttonStyle(.plain)
                    } else {
                        Text("")
                            .frame(height: 38)
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
