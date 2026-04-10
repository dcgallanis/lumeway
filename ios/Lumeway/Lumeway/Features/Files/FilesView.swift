import SwiftUI

struct FilesView: View {
    @EnvironmentObject var appState: AppState
    @State private var selectedTab: FileTab = .documents

    enum FileTab: String, CaseIterable {
        case documents = "Documents"
        case uploads = "Uploads"
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Segmented control
                    Picker("", selection: $selectedTab) {
                        ForEach(FileTab.allCases, id: \.self) { tab in
                            Text(tab.rawValue).tag(tab)
                        }
                    }
                    .pickerStyle(.segmented)
                    .padding(.horizontal, 24)
                    .padding(.top, 8)

                    switch selectedTab {
                    case .documents:
                        DocumentsNeededList()
                    case .uploads:
                        UploadedFilesList()
                    }
                }
            }
            .navigationTitle("Files")
            .navigationBarTitleDisplayMode(.large)
        }
    }
}

// MARK: - Documents Needed

struct DocumentsNeededList: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        if let docs = appState.dashboardData?.documentsNeeded, !docs.isEmpty {
            ScrollView {
                VStack(spacing: 12) {
                    ForEach(docs, id: \.id) { doc in
                        HStack(spacing: 12) {
                            Image(systemName: doc.obtained == true ? "checkmark.circle.fill" : "doc")
                                .font(.system(size: 20))
                                .foregroundColor(doc.obtained == true ? .lumeGreen : .lumeNavy)

                            VStack(alignment: .leading, spacing: 2) {
                                Text(doc.name ?? "")
                                    .font(.lumeCaption)
                                    .foregroundColor(.lumeText)
                                if let note = doc.note, !note.isEmpty {
                                    Text(note)
                                        .font(.lumeSmall)
                                        .foregroundColor(.lumeMuted)
                                }
                            }
                            Spacer()
                        }
                        .padding(16)
                        .background(Color.lumeWarmWhite)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(Color.lumeBorder, lineWidth: 1)
                        )
                    }
                }
                .padding(24)
            }
        } else {
            VStack(spacing: 16) {
                Spacer()
                Image(systemName: "doc.text")
                    .font(.system(size: 48, weight: .light))
                    .foregroundColor(.lumeMuted)
                Text("No documents needed yet")
                    .font(.lumeBody)
                    .foregroundColor(.lumeMuted)
                Spacer()
            }
        }
    }
}

// MARK: - Uploaded Files

struct UploadedFilesList: View {
    var body: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "folder")
                .font(.system(size: 48, weight: .light))
                .foregroundColor(.lumeMuted)
            Text("Your uploaded files will appear here")
                .font(.lumeBody)
                .foregroundColor(.lumeMuted)
            Text("Use the + button to upload documents\nlike IDs, forms, or receipts.")
                .font(.lumeCaptionLight)
                .foregroundColor(.lumeMuted)
                .multilineTextAlignment(.center)
            Spacer()
        }
    }
}
