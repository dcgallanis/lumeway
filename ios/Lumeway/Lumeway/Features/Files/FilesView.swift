import SwiftUI
import PhotosUI
import UIKit

struct FilesView: View {
    @EnvironmentObject var appState: AppState
    @State private var selectedTab: FileTab = .documents
    @State private var uploads: [UploadedFile] = []
    @State private var isLoadingUploads = true
    @State private var showUploadSheet = false
    @State private var showCamera = false
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var isUploading = false
    @State private var uploadToast: String?

    private let api = APIClient.shared

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
                        UploadedFilesList(
                            files: uploads,
                            isLoading: isLoadingUploads,
                            onDelete: { file in
                                Task { await deleteUpload(file) }
                            }
                        )
                    }
                }

                // Upload progress overlay
                if isUploading {
                    Color.black.opacity(0.3)
                        .ignoresSafeArea()
                        .overlay(
                            VStack(spacing: 16) {
                                ProgressView()
                                    .tint(.white)
                                    .scaleEffect(1.2)
                                Text("Uploading...")
                                    .font(.lumeBodyMedium)
                                    .foregroundColor(.white)
                            }
                            .padding(32)
                            .background(Color.lumeNavy.opacity(0.9))
                            .cornerRadius(16)
                        )
                        .zIndex(5)
                }

                // Toast overlay
                if let toast = uploadToast {
                    VStack {
                        Spacer()
                        Text(toast)
                            .font(.lumeBody)
                            .foregroundColor(.lumeText)
                            .padding(.horizontal, 24)
                            .padding(.vertical, 14)
                            .background(Color.lumeWarmWhite)
                            .cornerRadius(24)
                            .shadow(color: .black.opacity(0.1), radius: 12, y: 4)
                            .padding(.bottom, 32)
                    }
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .zIndex(10)
                }
            }
            .navigationTitle("Files")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                if selectedTab == .uploads {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Menu {
                            PhotosPicker(
                                selection: $selectedPhoto,
                                matching: .any(of: [.images, .screenshots])
                            ) {
                                Label("Choose from Photos", systemImage: "photo.on.rectangle")
                            }

                            Button {
                                showCamera = true
                            } label: {
                                Label("Take Photo", systemImage: "camera")
                            }

                            Button {
                                showUploadSheet = true
                            } label: {
                                Label("Browse Files", systemImage: "folder")
                            }
                        } label: {
                            Image(systemName: "plus")
                                .foregroundColor(.lumeNavy)
                        }
                    }
                }
            }
            .onChange(of: selectedPhoto) { _, newItem in
                if let newItem {
                    Task { await handlePhotoPick(newItem) }
                }
            }
            .sheet(isPresented: $showCamera) {
                CameraPickerView { image in
                    Task { await uploadImage(image, filename: "photo_\(Date().timeIntervalSince1970).jpg") }
                }
            }
            .fileImporter(
                isPresented: $showUploadSheet,
                allowedContentTypes: [.pdf, .image, .plainText],
                allowsMultipleSelection: false
            ) { result in
                switch result {
                case .success(let urls):
                    if let url = urls.first {
                        Task { await uploadFromFile(url) }
                    }
                case .failure(let error):
                    print("File picker error: \(error)")
                }
            }
            .task { await loadUploads() }
        }
    }

    // MARK: - Upload Handlers

    private func handlePhotoPick(_ item: PhotosPickerItem) async {
        guard let data = try? await item.loadTransferable(type: Data.self) else { return }
        let filename = "photo_\(Int(Date().timeIntervalSince1970)).jpg"
        await uploadData(data, filename: filename, mimeType: "image/jpeg")
    }

    private func uploadImage(_ image: UIImage, filename: String) async {
        guard let data = image.jpegData(compressionQuality: 0.8) else { return }
        await uploadData(data, filename: filename, mimeType: "image/jpeg")
    }

    private func uploadFromFile(_ url: URL) async {
        guard url.startAccessingSecurityScopedResource() else { return }
        defer { url.stopAccessingSecurityScopedResource() }

        guard let data = try? Data(contentsOf: url) else { return }
        let filename = url.lastPathComponent
        let mimeType = mimeTypeForExtension(url.pathExtension)
        await uploadData(data, filename: filename, mimeType: mimeType)
    }

    private func uploadData(_ data: Data, filename: String, mimeType: String) async {
        isUploading = true
        do {
            let result = try await api.upload(
                path: "/api/files/upload",
                fileData: data,
                filename: filename,
                mimeType: mimeType
            )
            let generator = UINotificationFeedbackGenerator()
            generator.notificationOccurred(.success)
            showUploadToast("File uploaded successfully.")
            await loadUploads()
            _ = result
        } catch {
            let generator = UINotificationFeedbackGenerator()
            generator.notificationOccurred(.error)
            showUploadToast("Upload failed. Please try again.")
        }
        isUploading = false
        selectedPhoto = nil
    }

    private func loadUploads() async {
        do {
            let response: UploadListResponse = try await api.get("/api/files")
            uploads = response.files
            isLoadingUploads = false
        } catch {
            isLoadingUploads = false
        }
    }

    private func deleteUpload(_ file: UploadedFile) async {
        do {
            try await api.delete("/api/files/\(file.id)") as EmptyResponse
            let generator = UIImpactFeedbackGenerator(style: .medium)
            generator.impactOccurred()
            await loadUploads()
        } catch {
            print("Delete error: \(error)")
        }
    }

    private func showUploadToast(_ message: String) {
        withAnimation(.easeInOut(duration: 0.3)) {
            uploadToast = message
        }
        Task {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            withAnimation(.easeInOut(duration: 0.3)) {
                uploadToast = nil
            }
        }
    }

    private func mimeTypeForExtension(_ ext: String) -> String {
        switch ext.lowercased() {
        case "pdf": return "application/pdf"
        case "jpg", "jpeg": return "image/jpeg"
        case "png": return "image/png"
        case "heic": return "image/heic"
        case "txt": return "text/plain"
        default: return "application/octet-stream"
        }
    }
}

// MARK: - Upload Response Models

struct UploadedFile: Codable, Identifiable {
    let id: Int
    let filename: String
    let originalName: String?
    let mimeType: String?
    let size: Int?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, filename, mimeType, size
        case originalName = "original_name"
        case createdAt = "created_at"
    }

    var displayName: String {
        originalName ?? filename
    }

    var formattedSize: String {
        guard let size = size else { return "" }
        if size < 1024 { return "\(size) B" }
        if size < 1024 * 1024 { return "\(size / 1024) KB" }
        return String(format: "%.1f MB", Double(size) / (1024 * 1024))
    }

    var iconName: String {
        guard let mime = mimeType else { return "doc" }
        if mime.contains("pdf") { return "doc.richtext" }
        if mime.contains("image") { return "photo" }
        if mime.contains("text") { return "doc.plaintext" }
        return "doc"
    }
}

struct UploadListResponse: Codable {
    let files: [UploadedFile]
}

struct EmptyResponse: Codable {}

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

// MARK: - Uploaded Files List

struct UploadedFilesList: View {
    let files: [UploadedFile]
    let isLoading: Bool
    let onDelete: (UploadedFile) -> Void

    var body: some View {
        if isLoading {
            VStack {
                Spacer()
                ProgressView().tint(.lumeAccent)
                Spacer()
            }
        } else if files.isEmpty {
            VStack(spacing: 16) {
                Spacer()
                Image(systemName: "folder")
                    .font(.system(size: 48, weight: .light))
                    .foregroundColor(.lumeMuted)
                Text("No uploads yet")
                    .font(.lumeBody)
                    .foregroundColor(.lumeMuted)
                Text("Use the + button to upload documents\nlike IDs, forms, or receipts.")
                    .font(.lumeCaptionLight)
                    .foregroundColor(.lumeMuted)
                    .multilineTextAlignment(.center)
                Spacer()
            }
        } else {
            ScrollView {
                VStack(spacing: 12) {
                    ForEach(files) { file in
                        HStack(spacing: 12) {
                            Image(systemName: file.iconName)
                                .font(.system(size: 20))
                                .foregroundColor(.lumeNavy)
                                .frame(width: 28)

                            VStack(alignment: .leading, spacing: 2) {
                                Text(file.displayName)
                                    .font(.lumeCaption)
                                    .foregroundColor(.lumeText)
                                    .lineLimit(1)

                                HStack(spacing: 8) {
                                    if !file.formattedSize.isEmpty {
                                        Text(file.formattedSize)
                                            .font(.lumeSmall)
                                            .foregroundColor(.lumeMuted)
                                    }
                                    if let date = file.createdAt {
                                        Text(formatDate(date))
                                            .font(.lumeSmall)
                                            .foregroundColor(.lumeMuted)
                                    }
                                }
                            }

                            Spacer()

                            Button {
                                onDelete(file)
                            } label: {
                                Image(systemName: "trash")
                                    .font(.system(size: 14))
                                    .foregroundColor(.lumeMuted)
                            }
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
        }
    }

    private func formatDate(_ isoString: String) -> String {
        let formatter = ISO8601DateFormatter()
        guard let date = formatter.date(from: isoString) else { return "" }
        let display = DateFormatter()
        display.dateStyle = .medium
        return display.string(from: date)
    }
}

// MARK: - Camera Picker

struct CameraPickerView: UIViewControllerRepresentable {
    let onCapture: (UIImage) -> Void
    @Environment(\.dismiss) var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onCapture: onCapture, dismiss: dismiss)
    }

    class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let onCapture: (UIImage) -> Void
        let dismiss: DismissAction

        init(onCapture: @escaping (UIImage) -> Void, dismiss: DismissAction) {
            self.onCapture = onCapture
            self.dismiss = dismiss
        }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage {
                onCapture(image)
            }
            dismiss()
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            dismiss()
        }
    }
}
