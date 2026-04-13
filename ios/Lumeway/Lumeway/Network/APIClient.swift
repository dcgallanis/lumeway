import Foundation

enum APIError: LocalizedError {
    case invalidURL
    case unauthorized
    case serverError(Int, String?)
    case decodingError(Error)
    case networkError(Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .unauthorized: return "Please sign in again"
        case .serverError(let code, let msg): return msg ?? "Server error (\(code))"
        case .decodingError(let err): return "Data error: \(err.localizedDescription)"
        case .networkError(let err): return err.localizedDescription
        }
    }
}

final class APIClient {
    static let shared = APIClient()

    private let baseURL = "https://lumeway.co"

    private let session: URLSession
    private let decoder: JSONDecoder

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 300
        self.session = URLSession(configuration: config)
        self.decoder = JSONDecoder()
    }

    // MARK: - Core Request Methods

    func get<T: Decodable>(_ path: String) async throws -> T {
        let request = try buildRequest(path: path, method: "GET")
        return try await execute(request)
    }

    func post<T: Decodable>(_ path: String, body: [String: Any]? = nil) async throws -> T {
        var request = try buildRequest(path: path, method: "POST")
        if let body = body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return try await execute(request)
    }

    func put<T: Decodable>(_ path: String, body: [String: Any]? = nil) async throws -> T {
        var request = try buildRequest(path: path, method: "PUT")
        if let body = body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return try await execute(request)
    }

    func delete<T: Decodable>(_ path: String) async throws -> T {
        let request = try buildRequest(path: path, method: "DELETE")
        return try await execute(request)
    }

    // Fire-and-forget POST (for toggles, etc.)
    func post(_ path: String, body: [String: Any]? = nil) async throws {
        var request = try buildRequest(path: path, method: "POST")
        if let body = body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (_, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { return }
        if http.statusCode == 401 { throw APIError.unauthorized }
        if http.statusCode >= 400 {
            throw APIError.serverError(http.statusCode, nil)
        }
    }

    // MARK: - SSE Streaming (for chat)

    func stream(_ path: String, body: [String: Any]) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    var request = try buildRequest(path: path, method: "POST")
                    request.httpBody = try JSONSerialization.data(withJSONObject: body)
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
                    request.timeoutInterval = 120

                    let (bytes, response) = try await session.bytes(for: request)
                    guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                        continuation.finish(throwing: APIError.serverError(0, "Stream failed"))
                        return
                    }

                    for try await line in bytes.lines {
                        if line.hasPrefix("data: ") {
                            let data = String(line.dropFirst(6))
                            if data.hasPrefix("[DONE]") {
                                // Extract JSON after [DONE]
                                let json = String(data.dropFirst(6))
                                continuation.yield("[DONE]\(json)")
                                continuation.finish()
                                return
                            }
                            let text = data.replacingOccurrences(of: "\\n", with: "\n")
                            continuation.yield(text)
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    // MARK: - File Upload

    func upload(path: String, fileData: Data, filename: String, mimeType: String, fields: [String: String] = [:]) async throws -> [String: Any] {
        let boundary = UUID().uuidString
        var request = try buildRequest(path: path, method: "POST")
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        for (key, value) in fields {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(key)\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(value)\r\n".data(using: .utf8)!)
        }
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.serverError(0, "No response")
        }
        if http.statusCode == 401 { throw APIError.unauthorized }
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw APIError.decodingError(NSError(domain: "", code: 0))
        }
        return json
    }

    // MARK: - Private

    private func buildRequest(path: String, method: String) throws -> URLRequest {
        guard let url = URL(string: baseURL + path) else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = method

        // Inject auth token
        if let token = KeychainHelper.getToken() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        return request
    }

    private func execute<T: Decodable>(_ request: URLRequest) async throws -> T {
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(error)
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIError.serverError(0, "Invalid response")
        }

        if http.statusCode == 401 {
            throw APIError.unauthorized
        }

        if http.statusCode >= 400 {
            let msg = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            let errorMsg = msg?["error"] as? String
            throw APIError.serverError(http.statusCode, errorMsg)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }
}
