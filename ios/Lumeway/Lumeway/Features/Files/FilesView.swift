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
                // Cool blue-cream gradient
                LinearGradient(
                    colors: [Color(hex: "EFF2F5"), Color(hex: "FAF7F2")],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 0) {
                        // Color-blocked header
                        ZStack {
                            Color.lumeNavy

                            VStack(spacing: 10) {
                                Image(systemName: "folder.fill")
                                    .font(.system(size: 28))
                                    .foregroundColor(.lumeGold)

                                Text("Your Files")
                                    .font(.lumeDisplayMedium)
                                    .foregroundColor(.white)

                                Text("Keep everything in one place.")
                                    .font(.lumeCaption)
                                    .foregroundColor(.white.opacity(0.6))
                            }
                            .padding(.vertical, 28)
                        }
                        .cornerRadius(20, corners: [.bottomLeft, .bottomRight])

                        // Tab picker
                        HStack(spacing: 0) {
                            ForEach(FileTab.allCases, id: \.self) { tab in
                                Button {
                                    withAnimation(.easeInOut(duration: 0.2)) {
                                        selectedTab = tab
                                    }
                                } label: {
                                    VStack(spacing: 6) {
                                        HStack(spacing: 6) {
                                            Image(systemName: tab == .documents ? "doc.text" : "arrow.up.doc")
                                                .font(.system(size: 13))
                                            Text(tab.rawValue)
                                                .font(.lumeBodyMedium)
                                        }
                                        .foregroundColor(selectedTab == tab ? .lumeNavy : .lumeMuted)

                                        Rectangle()
                                            .fill(selectedTab == tab ? Color.lumeAccent : Color.clear)
                                            .frame(height: 2)
                                    }
                                }
                                .frame(maxWidth: .infinity)
                            }
                        }
                        .padding(.horizontal, 20)
                        .padding(.top, 16)

                        // Content
                        switch selectedTab {
                        case .documents:
                            DocumentsNeededList()
                        case .uploads:
                            UploadedFilesContent(
                                files: uploads,
                                isLoading: isLoadingUploads,
                                onDelete: { file in
                                    Task { await deleteUpload(file) }
                                },
                                selectedPhoto: $selectedPhoto,
                                onAddCamera: { showCamera = true },
                                onAddFile: { showUploadSheet = true }
                            )
                        }

                        Spacer().frame(height: 100)
                    }
                }
                .ignoresSafeArea(edges: .top)

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
                        HStack(spacing: 8) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 14))
                                .foregroundColor(.lumeGreen)
                            Text(toast)
                                .font(.lumeBody)
                                .foregroundColor(.lumeText)
                        }
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
            .navigationBarHidden(true)
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
            let _: EmptyResponse = try await api.delete("/api/files/\(file.id)")
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
            let obtained = docs.filter { $0.obtained == true }.count

            VStack(spacing: 12) {
                // Progress summary
                HStack(spacing: 12) {
                    ZStack {
                        Circle()
                            .fill(Color(hex: "E8F0E4"))
                            .frame(width: 40, height: 40)
                        Image(systemName: "doc.text.fill")
                            .font(.system(size: 16))
                            .foregroundColor(Color(hex: "4A7C59"))
                    }

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Documents for your transition")
                            .font(.lumeBodyMedium)
                            .foregroundColor(.lumeNavy)
                        Text("\(obtained) of \(docs.count) gathered")
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }
                    Spacer()
                }
                .padding(16)
                .background(Color.lumeWarmWhite)
                .cornerRadius(14)
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(Color.lumeBorder, lineWidth: 1)
                )

                ForEach(docs, id: \.id) { doc in
                    HStack(spacing: 14) {
                        ZStack {
                            Circle()
                                .fill(doc.obtained == true ? Color(hex: "E8F0E4") : Color(hex: "F0EAE0"))
                                .frame(width: 36, height: 36)
                            Image(systemName: doc.obtained == true ? "checkmark.circle.fill" : "doc")
                                .font(.system(size: 15))
                                .foregroundColor(doc.obtained == true ? Color(hex: "4A7C59") : Color(hex: "C4704E"))
                        }

                        VStack(alignment: .leading, spacing: 3) {
                            Text(doc.name ?? "")
                                .font(.lumeBodyMedium)
                                .foregroundColor(doc.obtained == true ? .lumeMuted : .lumeNavy)
                                .strikethrough(doc.obtained == true)
                            if let note = doc.note, !note.isEmpty {
                                Text(note)
                                    .font(.lumeSmall)
                                    .foregroundColor(.lumeMuted)
                            }
                        }
                        Spacer()

                        if doc.obtained == true {
                            Text("Done")
                                .font(.lumeSmall)
                                .foregroundColor(Color(hex: "4A7C59"))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 4)
                                .background(Color(hex: "E8F0E4"))
                                .cornerRadius(8)
                        }
                    }
                    .padding(16)
                    .background(Color.lumeWarmWhite)
                    .cornerRadius(14)
                    .overlay(
                        RoundedRectangle(cornerRadius: 14)
                            .stroke(Color.lumeBorder, lineWidth: 1)
                    )
                }
            }
            .padding(.horizontal, 20)
            .padding(.top, 16)
        } else {
            // Empty state — warm, website-matching placeholder
            VStack(spacing: 20) {
                Spacer().frame(height: 40)

                ZStack {
                    Circle()
                        .fill(Color(hex: "F0EAE0"))
                        .frame(width: 80, height: 80)
                    Image(systemName: "doc.text.fill")
                        .font(.system(size: 32, weight: .light))
                        .foregroundColor(Color(hex: "C4704E"))
                }

                Text("No documents yet")
                    .font(.lumeDisplaySmall)
                    .foregroundColor(.lumeNavy)

                Text("Once you start your transition, we'll\nlist every document you need — all\nin one place, nothing to guess.")
                    .font(.lumeBody)
                    .foregroundColor(.lumeMuted)
                    .multilineTextAlignment(.center)
                    .lineSpacing(3)

                HStack(spacing: 16) {
                    VStack(spacing: 6) {
                        Image(systemName: "list.clipboard")
                            .font(.system(size: 18))
                            .foregroundColor(Color(hex: "4A7C59"))
                        Text("Track")
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Color(hex: "E8F0E4"))
                    .cornerRadius(12)

                    VStack(spacing: 6) {
                        Image(systemName: "checkmark.shield")
                            .font(.system(size: 18))
                            .foregroundColor(Color(hex: "2C4A5E"))
                        Text("Organize")
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Color(hex: "E4E8EE"))
                    .cornerRadius(12)

                    VStack(spacing: 6) {
                        Image(systemName: "heart.fill")
                            .font(.system(size: 18))
                            .foregroundColor(Color(hex: "C4704E"))
                        Text("Breathe")
                            .font(.lumeSmall)
                            .foregroundColor(.lumeMuted)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Color(hex: "F0EAE0"))
                    .cornerRadius(12)
                }
                .padding(.horizontal, 20)

                Spacer()
            }
        }
    }
}

// MARK: - Uploaded Files Content

struct UploadedFilesContent: View {
    let files: [UploadedFile]
    let isLoading: Bool
    let onDelete: (UploadedFile) -> Void
    @Binding var selectedPhoto: PhotosPickerItem?
    let onAddCamera: () -> Void
    let onAddFile: () -> Void

    var body: some View {
        if isLoading {
            VStack(spacing: 16) {
                Spacer().frame(height: 60)
                ProgressView().tint(.lumeAccent)
                Spacer()
            }
        } else if files.isEmpty {
            // Empty state — warm, inviting
            VStack(spacing: 20) {
                Spacer().frame(height: 40)

                ZStack {
                    Circle()
                        .fill(Color(hex: "E4E8EE"))
                        .frame(width: 80, height: 80)
                    Image(systemName: "arrow.up.doc.fill")
                        .font(.system(size: 32, weight: .light))
                        .foregroundColor(Color(hex: "2C4A5E"))
                }

                Text("Your secure file vault")
                    .font(.lumeDisplaySmall)
                    .foregroundColor(.lumeNavy)

                Text("Upload photos of documents, IDs,\nforms, or anything you need to keep\ntrack of during your transition.")
                    .font(.lumeBody)
                    .foregroundColor(.lumeMuted)
                    .multilineTextAlignment(.center)
                    .lineSpacing(3)

                // Upload action buttons
                VStack(spacing: 10) {
                    Button(action: onAddFile) {
                        HStack(spacing: 10) {
                            Image(systemName: "folder.fill")
                                .font(.system(size: 15))
                            Text("Browse Files")
                                .font(.lumeBodyMedium)
                        }
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Color.lumeNavy)
                        .cornerRadius(12)
                    }

                    HStack(spacing: 10) {
                        Button(action: onAddCamera) {
                            HStack(spacing: 8) {
                                Image(systemName: "camera.fill")
                                    .font(.system(size: 14))
                                Text("Camera")
                                    .font(.lumeBodyMedium)
                            }
                            .foregroundColor(.lumeNavy)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(Color.lumeWarmWhite)
                            .cornerRadius(12)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color.lumeBorder, lineWidth: 1)
                            )
                        }

                        PhotosPicker(
                            selection: $selectedPhoto,
                            matching: .any(of: [.images, .screenshots])
                        ) {
                            HStack(spacing: 8) {
                                Image(systemName: "photo.fill")
                                    .font(.system(size: 14))
                                Text("Photos")
                                    .font(.lumeBodyMedium)
                            }
                            .foregroundColor(.lumeNavy)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(Color.lumeWarmWhite)
                            .cornerRadius(12)
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color.lumeBorder, lineWidth: 1)
                            )
                        }
                    }
                }
                .padding(.horizontal, 20)

                Spacer()
            }
        } else {
            VStack(spacing: 12) {
                // File count header
                HStack {
                    Text("\(files.count) file\(files.count == 1 ? "" : "s") uploaded")
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)
                    Spacer()
                }
                .padding(.horizontal, 20)
                .padding(.top, 12)

                ForEach(files) { file in
                    HStack(spacing: 14) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 10)
                                .fill(Color(hex: "E4E8EE"))
                                .frame(width: 40, height: 40)
                            Image(systemName: file.iconName)
                                .font(.system(size: 16))
                                .foregroundColor(.lumeNavy)
                        }

                        VStack(alignment: .leading, spacing: 3) {
                            Text(file.displayName)
                                .font(.lumeBodyMedium)
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
                                .padding(8)
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(Color.lumeWarmWhite)
                    .cornerRadius(14)
                    .overlay(
                        RoundedRectangle(cornerRadius: 14)
                            .stroke(Color.lumeBorder, lineWidth: 1)
                    )
                }
                .padding(.horizontal, 20)
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
