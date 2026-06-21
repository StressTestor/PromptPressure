import Foundation

public enum APIClientError: Error, LocalizedError {
    case invalidURL(String)
    case badStatus(Int, String)
    case emptyBaseURL

    public var errorDescription: String? {
        switch self {
        case .invalidURL(let path):
            return "Invalid API path: \(path)"
        case .badStatus(let status, let body):
            return "HTTP \(status): \(body)"
        case .emptyBaseURL:
            return "Sidecar URL is not set"
        }
    }
}

public struct SSEMessage: Equatable {
    public let event: String
    public let data: String
}

public final class PromptPressureAPIClient {
    public var baseURL: URL?
    private let session: URLSession
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    public init(baseURL: URL? = nil, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    public func health() async throws -> AppMetadata? {
        try await getOptional("/app/metadata")
    }

    public func providers() async throws -> [Provider] {
        try await get("/providers")
    }

    public func models(provider: String) async throws -> ModelList {
        try await get("/models?provider=\(provider.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? provider)")
    }

    public func evalSets() async throws -> [EvalSet] {
        try await get("/eval-sets")
    }

    public func outputs() async throws -> AppOutputsResponse {
        try await get("/app/outputs")
    }

    public func themes() async throws -> ThemeCatalogResponse {
        try await get("/app/themes")
    }

    public func providerCatalog() async throws -> ProviderCatalogResponse {
        try await get("/app/providers")
    }

    public func jobs() async throws -> AppJobsResponse {
        try await get("/app/jobs")
    }

    public func job(id: String) async throws -> AppJob {
        let escapedID = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
        return try await get("/app/jobs/\(escapedID)")
    }

    public func diagnostics() async throws -> DiagnosticsResponse {
        try await get("/diagnostics")
    }

    public func plugins() async throws -> [JSONValue] {
        try await get("/plugins")
    }

    public func installPlugin(name: String, confirm: Bool) async throws -> [String: JSONValue] {
        try await post("/plugins/install", body: PluginInstallRequest(name: name, confirm: confirm))
    }

    public func ollamaHealth() async throws -> [String: JSONValue] {
        try await get("/ollama/health")
    }

    public func ollamaModels() async throws -> [String: JSONValue] {
        try await get("/ollama/models")
    }

    public func pullOllamaModel(name: String, confirm: Bool) async throws -> [String: JSONValue] {
        try await post("/ollama/models/pull", body: OllamaModelRequest(name: name, confirm: confirm))
    }

    public func deleteOllamaModel(name: String, confirm: Bool) async throws -> [String: JSONValue] {
        let escapedName = name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? name
        return try await delete("/ollama/models/\(escapedName)?confirm=\(confirm)")
    }

    public func evaluations() async throws -> [RunHistoryItem] {
        try await get("/evaluations")
    }

    public func evaluation(id: String) async throws -> EvaluationDetail {
        let escapedID = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
        return try await get("/evaluations/\(escapedID)")
    }

    public func startEvaluation(provider: String, model: String, evalSetIDs: [String]) async throws -> EvaluationStartResponse {
        let payload = LauncherRequestEnvelope(
            launcherRequest: LauncherPayload(provider: provider, model: model, evalSetIDs: evalSetIDs)
        )
        return try await post("/evaluate", body: payload)
    }

    public func startEvaluationJob(provider: String, model: String, evalSetIDs: [String]) async throws -> AppJob {
        let payload = AppEvaluationJobRequest(provider: provider, model: model, evalSetIDs: evalSetIDs)
        return try await post("/app/jobs/evaluations", body: payload)
    }

    public func startDriftRunJob(provider: String, model: String, suite: String = "drift-v0.1") async throws -> AppJob {
        let payload = DriftRunJobRequest(suite: suite, provider: provider, model: model)
        return try await post("/app/jobs/drift/run", body: payload)
    }

    public func cancel(runID: String) async throws {
        let _: EmptyResponse = try await post("/evaluations/\(runID)/cancel", body: EmptyBody())
    }

    public func cancelJob(id: String) async throws -> AppJob {
        let escapedID = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
        return try await post("/app/jobs/\(escapedID)/cancel", body: EmptyBody())
    }

    public func stream(path: String) -> AsyncThrowingStream<SSEMessage, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    let request = try makeRequest(path)
                    let (bytes, response) = try await session.bytes(for: request)
                    try validate(response: response, body: "")

                    var event = "message"
                    var dataLines: [String] = []

                    for try await rawLine in bytes.lines {
                        let line = rawLine.trimmingCharacters(in: CharacterSet(charactersIn: "\r"))
                        if line.isEmpty {
                            if !dataLines.isEmpty {
                                continuation.yield(SSEMessage(event: event, data: dataLines.joined(separator: "\n")))
                            }
                            event = "message"
                            dataLines = []
                            continue
                        }
                        if line.hasPrefix("event:") {
                            event = String(line.dropFirst(6)).trimmingCharacters(in: .whitespaces)
                        } else if line.hasPrefix("data:") {
                            dataLines.append(String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces))
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        let request = try makeRequest(path)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, body: String(data: data, encoding: .utf8) ?? "")
        return try decoder.decode(T.self, from: data)
    }

    private func getOptional<T: Decodable>(_ path: String) async throws -> T? {
        do {
            return try await get(path)
        } catch {
            return nil
        }
    }

    private func post<T: Decodable, Body: Encodable>(_ path: String, body: Body) async throws -> T {
        var request = try makeRequest(path)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)
        let (data, response) = try await session.data(for: request)
        try validate(response: response, body: String(data: data, encoding: .utf8) ?? "")
        if data.isEmpty {
            return EmptyResponse() as! T
        }
        return try decoder.decode(T.self, from: data)
    }

    private func delete<T: Decodable>(_ path: String) async throws -> T {
        var request = try makeRequest(path)
        request.httpMethod = "DELETE"
        let (data, response) = try await session.data(for: request)
        try validate(response: response, body: String(data: data, encoding: .utf8) ?? "")
        return try decoder.decode(T.self, from: data)
    }

    private func makeRequest(_ path: String) throws -> URLRequest {
        guard let baseURL else { throw APIClientError.emptyBaseURL }
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw APIClientError.invalidURL(path)
        }
        return URLRequest(url: url)
    }

    private func validate(response: URLResponse, body: String) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200..<300).contains(http.statusCode) else {
            throw APIClientError.badStatus(http.statusCode, body)
        }
    }
}

private struct EmptyBody: Encodable {}

private struct EmptyResponse: Decodable {}
