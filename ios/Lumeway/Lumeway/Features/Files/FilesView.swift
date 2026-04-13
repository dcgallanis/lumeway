import SwiftUI
import PhotosUI
import UIKit
import QuickLook
import WebKit

struct FilesView: View {
    @EnvironmentObject var appState: AppState
    @State private var selectedTab: FileTab = .upload
    @State private var uploads: [UploadedFile] = []
    @State private var isLoadingUploads = true
    @State private var showFileImporter = false
    @State private var showCamera = false
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var isUploading = false
    @State private var uploadToast: String?
    @State private var previewFile: UploadedFile?
    @State private var previewURL: URL?

    private let api = APIClient.shared

    enum FileTab: String, CaseIterable {
        case upload = "Upload"
        case myFiles = "My Files"
    }

    var body: some View {
        NavigationStack {
            ZStack {
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

                                if !uploads.isEmpty {
                                    Text("\(uploads.count) file\(uploads.count == 1 ? "" : "s")")
                                        .font(.lumeCaption)
                                        .foregroundColor(.white.opacity(0.6))
                                } else {
                                    Text("Keep everything in one place.")
                                        .font(.lumeCaption)
                                        .foregroundColor(.white.opacity(0.6))
                                }
                            }
                            .padding(.top, 60)
                            .padding(.bottom, 28)
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
                                            Image(systemName: tab == .upload ? "arrow.up.doc" : "folder")
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
                        case .upload:
                            UploadSection(
                                selectedPhoto: $selectedPhoto,
                                onCamera: { showCamera = true },
                                onBrowse: { showFileImporter = true }
                            )
                        case .myFiles:
                            MyFilesSection(
                                files: uploads,
                                isLoading: isLoadingUploads,
                                onDelete: { file in Task { await deleteUpload(file) } },
                                onPreview: { file in Task { await openPreview(file) } }
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
                isPresented: $showFileImporter,
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
            .sheet(item: $previewFile) { file in
                FilePreviewSheet(file: file, previewURL: previewURL)
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
            _ = try await api.upload(
                path: "/api/files/upload",
                fileData: data,
                filename: filename,
                mimeType: mimeType
            )
            let generator = UINotificationFeedbackGenerator()
            generator.notificationOccurred(.success)
            showUploadToast("File uploaded successfully.")
            await loadUploads()
            // Switch to My Files tab after upload
            withAnimation { selectedTab = .myFiles }
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

    private func openPreview(_ file: UploadedFile) async {
        // Download the file to a temp location for preview
        do {
            var request = URLRequest(url: URL(string: "https://lumeway.co/api/files/\(file.id)/preview")!)
            if let token = KeychainHelper.getToken() {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }
            let (data, _) = try await URLSession.shared.data(for: request)
            let ext = file.fileExtension
            let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("preview_\(file.id).\(ext)")
            try data.write(to: tempURL)
            previewURL = tempURL
            previewFile = file
        } catch {
            print("Preview error: \(error)")
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

// MARK: - Upload Section

struct UploadSection: View {
    @Binding var selectedPhoto: PhotosPickerItem?
    let onCamera: () -> Void
    let onBrowse: () -> Void

    var body: some View {
        VStack(spacing: 20) {
            Spacer().frame(height: 24)

            // Upload area
            VStack(spacing: 24) {
                ZStack {
                    Circle()
                        .fill(Color(hex: "E4E8EE"))
                        .frame(width: 72, height: 72)
                    Image(systemName: "arrow.up.doc.fill")
                        .font(.system(size: 28, weight: .light))
                        .foregroundColor(.lumeNavy)
                }

                VStack(spacing: 6) {
                    Text("Upload a file")
                        .font(.lumeDisplaySmall)
                        .foregroundColor(.lumeNavy)

                    Text("Photos of documents, IDs, forms,\nreceipts — anything you need to keep.")
                        .font(.lumeBody)
                        .foregroundColor(.lumeMuted)
                        .multilineTextAlignment(.center)
                        .lineSpacing(3)
                }

                // Upload buttons
                VStack(spacing: 10) {
                    // Camera button — prominent
                    Button(action: onCamera) {
                        HStack(spacing: 10) {
                            Image(systemName: "camera.fill")
                                .font(.system(size: 16))
                            Text("Take a Photo")
                                .font(.lumeBodyMedium)
                        }
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(Color.lumeAccent)
                        .cornerRadius(14)
                    }

                    HStack(spacing: 10) {
                        // Photo library
                        PhotosPicker(
                            selection: $selectedPhoto,
                            matching: .any(of: [.images, .screenshots])
                        ) {
                            HStack(spacing: 8) {
                                Image(systemName: "photo.fill")
                                    .font(.system(size: 14))
                                Text("Photo Library")
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

                        // File browser
                        Button(action: onBrowse) {
                            HStack(spacing: 8) {
                                Image(systemName: "folder.fill")
                                    .font(.system(size: 14))
                                Text("Browse Files")
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
            }
            .padding(24)
            .background(Color.lumeWarmWhite)
            .cornerRadius(20)
            .overlay(
                RoundedRectangle(cornerRadius: 20)
                    .stroke(Color.lumeBorder, lineWidth: 1)
            )
            .padding(.horizontal, 20)

            // Supported formats info
            VStack(spacing: 10) {
                HStack(spacing: 8) {
                    Image(systemName: "lock.shield.fill")
                        .font(.system(size: 13))
                        .foregroundColor(.lumeGreen)
                    Text("Files are encrypted and stored securely")
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)
                }

                HStack(spacing: 8) {
                    Image(systemName: "doc.badge.ellipsis")
                        .font(.system(size: 13))
                        .foregroundColor(.lumeMuted)
                    Text("PDF, JPG, PNG, TXT, DOC, XLSX — up to 10 MB")
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)
                }
            }
            .padding(.horizontal, 20)

            Spacer()
        }
    }
}

// MARK: - My Files Section

struct MyFilesSection: View {
    let files: [UploadedFile]
    let isLoading: Bool
    let onDelete: (UploadedFile) -> Void
    let onPreview: (UploadedFile) -> Void

    var body: some View {
        if isLoading {
            VStack(spacing: 16) {
                Spacer().frame(height: 60)
                ProgressView().tint(.lumeAccent)
                Spacer()
            }
        } else if files.isEmpty {
            VStack(spacing: 16) {
                Spacer().frame(height: 60)

                ZStack {
                    Circle()
                        .fill(Color(hex: "E4E8EE"))
                        .frame(width: 64, height: 64)
                    Image(systemName: "folder")
                        .font(.system(size: 26, weight: .light))
                        .foregroundColor(.lumeNavy)
                }

                Text("No files yet")
                    .font(.lumeDisplaySmall)
                    .foregroundColor(.lumeNavy)

                Text("Upload your first file using\nthe Upload tab.")
                    .font(.lumeBody)
                    .foregroundColor(.lumeMuted)
                    .multilineTextAlignment(.center)

                Spacer()
            }
        } else {
            VStack(spacing: 12) {
                HStack {
                    Text("\(files.count) file\(files.count == 1 ? "" : "s")")
                        .font(.lumeSmall)
                        .foregroundColor(.lumeMuted)
                    Spacer()
                }
                .padding(.horizontal, 20)
                .padding(.top, 12)

                ForEach(files) { file in
                    FileCard(
                        file: file,
                        onTap: { onPreview(file) },
                        onDelete: { onDelete(file) }
                    )
                }
                .padding(.horizontal, 20)
            }
        }
    }
}

// MARK: - File Card with Preview

struct FileCard: View {
    let file: UploadedFile
    let onTap: () -> Void
    let onDelete: () -> Void
    @State private var thumbnail: UIImage?
    @State private var isLoadingThumb = false

    var isImage: Bool {
        file.contentType?.contains("image") == true
    }

    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 0) {
                // Thumbnail area
                ZStack {
                    if isImage, let thumb = thumbnail {
                        Image(uiImage: thumb)
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                            .frame(maxWidth: .infinity)
                            .frame(height: 160)
                            .clipped()
                    } else if isImage && isLoadingThumb {
                        Rectangle()
                            .fill(Color(hex: "E4E8EE"))
                            .frame(height: 160)
                            .overlay(ProgressView().tint(.lumeMuted))
                    } else {
                        // Non-image file type icon
                        Rectangle()
                            .fill(file.bgColor)
                            .frame(height: 100)
                            .overlay(
                                VStack(spacing: 8) {
                                    Image(systemName: file.iconName)
                                        .font(.system(size: 32, weight: .light))
                                        .foregroundColor(file.accentColor)
                                    Text(file.fileExtension.uppercased())
                                        .font(.lumeSmall)
                                        .fontWeight(.bold)
                                        .foregroundColor(file.accentColor)
                                }
                            )
                    }
                }
                .cornerRadius(14, corners: [.topLeft, .topRight])

                // File info
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(file.displayName)
                            .font(.lumeBodyMedium)
                            .foregroundColor(.lumeText)
                            .lineLimit(1)

                        HStack(spacing: 6) {
                            if !file.formattedSize.isEmpty {
                                Text(file.formattedSize)
                                    .font(.lumeSmall)
                                    .foregroundColor(.lumeMuted)
                            }
                            if let date = file.uploadedAt {
                                Text("·")
                                    .font(.lumeSmall)
                                    .foregroundColor(.lumeBorder)
                                Text(formatDate(date))
                                    .font(.lumeSmall)
                                    .foregroundColor(.lumeMuted)
                            }
                        }
                    }

                    Spacer()

                    // Action buttons
                    HStack(spacing: 4) {
                        Image(systemName: "eye")
                            .font(.system(size: 13))
                            .foregroundColor(.lumeNavy)
                            .padding(8)

                        Button {
                            onDelete()
                        } label: {
                            Image(systemName: "trash")
                                .font(.system(size: 13))
                                .foregroundColor(.lumeMuted)
                                .padding(8)
                        }
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .background(Color.lumeWarmWhite)
            }
            .background(Color.lumeWarmWhite)
            .cornerRadius(14)
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(Color.lumeBorder, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .task {
            if isImage { await loadThumbnail() }
        }
    }

    private func loadThumbnail() async {
        isLoadingThumb = true
        defer { isLoadingThumb = false }
        do {
            var request = URLRequest(url: URL(string: "https://lumeway.co/api/files/\(file.id)/preview")!)
            if let token = KeychainHelper.getToken() {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }
            let (data, _) = try await URLSession.shared.data(for: request)
            if let image = UIImage(data: data) {
                thumbnail = image
            }
        } catch {
            print("Thumbnail load error: \(error)")
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

// MARK: - File Preview Sheet

struct FilePreviewSheet: View {
    let file: UploadedFile
    let previewURL: URL?
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                Color.lumeCream.ignoresSafeArea()

                if let url = previewURL {
                    if file.contentType?.contains("image") == true {
                        // Image preview — zoomable
                        ScrollView([.horizontal, .vertical]) {
                            if let data = try? Data(contentsOf: url),
                               let image = UIImage(data: data) {
                                Image(uiImage: image)
                                    .resizable()
                                    .aspectRatio(contentMode: .fit)
                                    .frame(maxWidth: .infinity)
                                    .padding(16)
                            }
                        }
                    } else if file.contentType?.contains("pdf") == true {
                        // PDF preview
                        PDFPreviewView(url: url)
                    } else if file.contentType?.contains("text") == true {
                        // Text file preview
                        if let text = try? String(contentsOf: url, encoding: .utf8) {
                            ScrollView {
                                Text(text)
                                    .font(.lumeBody)
                                    .foregroundColor(.lumeText)
                                    .padding(20)
                            }
                        }
                    } else {
                        // Generic — show file info
                        VStack(spacing: 16) {
                            Image(systemName: file.iconName)
                                .font(.system(size: 48, weight: .light))
                                .foregroundColor(.lumeNavy)
                            Text(file.displayName)
                                .font(.lumeBodyMedium)
                                .foregroundColor(.lumeText)
                            Text("Preview not available for this file type.")
                                .font(.lumeBody)
                                .foregroundColor(.lumeMuted)
                        }
                    }
                } else {
                    ProgressView()
                        .tint(.lumeAccent)
                }
            }
            .navigationTitle(file.displayName)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.lumeMuted)
                    }
                }
            }
        }
    }
}

// MARK: - PDF Preview using UIKit

struct PDFPreviewView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> UIView {
        let webView = WKWebViewWrapper.createWebView()
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateUIView(_ uiView: UIView, context: Context) {}
}

enum WKWebViewWrapper {
    static func createWebView() -> WKWebView {
        let config = WKWebViewConfiguration()
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.backgroundColor = UIColor(Color.lumeCream)
        return webView
    }
}

// MARK: - Upload Response Models

struct UploadedFile: Codable, Identifiable {
    let id: Int
    let originalName: String?
    let category: String?
    let fileSize: Int?
    let contentType: String?
    let uploadedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case originalName = "original_name"
        case category
        case fileSize = "file_size"
        case contentType = "content_type"
        case uploadedAt = "uploaded_at"
    }

    var displayName: String {
        originalName ?? "Untitled"
    }

    var formattedSize: String {
        guard let fileSize = fileSize else { return "" }
        if fileSize < 1024 { return "\(fileSize) B" }
        if fileSize < 1024 * 1024 { return "\(fileSize / 1024) KB" }
        return String(format: "%.1f MB", Double(fileSize) / (1024 * 1024))
    }

    var fileExtension: String {
        guard let name = originalName else { return "file" }
        let ext = (name as NSString).pathExtension.lowercased()
        return ext.isEmpty ? "file" : ext
    }

    var iconName: String {
        guard let mime = contentType else { return "doc" }
        if mime.contains("pdf") { return "doc.richtext" }
        if mime.contains("image") { return "photo" }
        if mime.contains("text") { return "doc.plaintext" }
        if mime.contains("spreadsheet") || mime.contains("excel") || mime.contains("xlsx") { return "tablecells" }
        if mime.contains("word") || mime.contains("doc") { return "doc.text" }
        return "doc"
    }

    var bgColor: Color {
        guard let mime = contentType else { return Color(hex: "E4E8EE") }
        if mime.contains("pdf") { return Color(hex: "F0E4E4") }
        if mime.contains("text") { return Color(hex: "E4E8EE") }
        if mime.contains("spreadsheet") || mime.contains("excel") { return Color(hex: "E8F0E4") }
        if mime.contains("word") || mime.contains("doc") { return Color(hex: "E4E8F0") }
        return Color(hex: "E4E8EE")
    }

    var accentColor: Color {
        guard let mime = contentType else { return .lumeNavy }
        if mime.contains("pdf") { return Color(hex: "C4704E") }
        if mime.contains("text") { return .lumeNavy }
        if mime.contains("spreadsheet") || mime.contains("excel") { return Color(hex: "4A7C59") }
        if mime.contains("word") || mime.contains("doc") { return Color(hex: "2C4A5E") }
        return .lumeNavy
    }
}

struct UploadListResponse: Codable {
    let files: [UploadedFile]
}

struct EmptyResponse: Codable {}

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

// RoundedCorner helper defined in ChecklistView.swift
