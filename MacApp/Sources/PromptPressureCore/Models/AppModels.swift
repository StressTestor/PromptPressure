import Foundation
import SwiftUI

public enum AppSection: String, CaseIterable, Identifiable {
    case run
    case drift
    case providers
    case models
    case suites
    case reports
    case plugins
    case ollama
    case diagnostics
    case jobs
    case history
    case themes
    case settings

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .run: "Run"
        case .drift: "Drift Studio"
        case .providers: "Providers"
        case .models: "Models"
        case .suites: "Suites"
        case .reports: "Reports"
        case .plugins: "Plugins"
        case .ollama: "Ollama"
        case .diagnostics: "Diagnostics"
        case .jobs: "Jobs"
        case .history: "History"
        case .themes: "Themes"
        case .settings: "Settings"
        }
    }

    public var systemImage: String {
        switch self {
        case .run: "play.circle"
        case .drift: "waveform.path.ecg"
        case .providers: "key"
        case .models: "cpu"
        case .suites: "checklist"
        case .reports: "doc.text.magnifyingglass"
        case .plugins: "puzzlepiece.extension"
        case .ollama: "shippingbox"
        case .diagnostics: "stethoscope"
        case .jobs: "list.bullet.rectangle"
        case .history: "clock.arrow.circlepath"
        case .themes: "paintpalette"
        case .settings: "gearshape"
        }
    }
}

public enum JSONValue: Codable, Equatable, CustomStringConvertible {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            self = .object(try container.decode([String: JSONValue].self))
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }

    public var description: String {
        switch self {
        case .string(let value): value
        case .number(let value): String(value)
        case .bool(let value): value ? "true" : "false"
        case .object(let value): value.map { "\($0.key): \($0.value)" }.sorted().joined(separator: ", ")
        case .array(let value): value.map(\.description).joined(separator: ", ")
        case .null: ""
        }
    }
}

public struct Provider: Identifiable, Codable, Hashable {
    public let id: String
    public let label: String
    public let available: Bool
    public let reason: String?
    public let remediationHint: String

    enum CodingKeys: String, CodingKey {
        case id
        case label
        case available
        case reason
        case remediationHint = "remediation_hint"
    }
}

public struct ModelList: Codable, Equatable {
    public let models: [String]
    public let note: String?
    public let freeText: Bool

    enum CodingKeys: String, CodingKey {
        case models
        case note
        case freeText = "free_text"
    }
}

public struct EvalSet: Identifiable, Codable, Hashable {
    public let id: String
    public let label: String
    public let count: Int
}

public struct EvaluationStartResponse: Codable, Equatable {
    public let runID: String
    public let status: String
    public let streamURL: String

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
        case status
        case streamURL = "stream_url"
    }
}

public struct LauncherRequestEnvelope: Encodable {
    public let launcherRequest: LauncherPayload

    public init(launcherRequest: LauncherPayload) {
        self.launcherRequest = launcherRequest
    }

    enum CodingKeys: String, CodingKey {
        case launcherRequest = "launcher_request"
    }
}

public struct LauncherPayload: Encodable {
    public let provider: String
    public let model: String
    public let evalSetIDs: [String]

    public init(provider: String, model: String, evalSetIDs: [String]) {
        self.provider = provider
        self.model = model
        self.evalSetIDs = evalSetIDs
    }

    enum CodingKeys: String, CodingKey {
        case provider
        case model
        case evalSetIDs = "eval_set_ids"
    }
}

public struct RunLogEvent: Identifiable, Equatable {
    public let id = UUID()
    public let kind: String
    public let message: String
    public let date: Date

    public static func status(_ message: String, kind: String = "status") -> RunLogEvent {
        RunLogEvent(kind: kind, message: message, date: Date())
    }
}

public struct RunHistoryItem: Identifiable, Codable, Hashable {
    public let id: String
    public let status: String
    public let timestamp: String
}

public struct EvaluationDetail: Identifiable, Codable, Equatable {
    public let id: String
    public let status: String
    public let timestamp: String
    public let results: [EvaluationResultItem]
}

public struct EvaluationResultItem: Identifiable, Codable, Equatable {
    public let id: String
    public let promptText: String
    public let responseText: String
    public let model: String
    public let success: Bool
    public let latencyMS: Double?

    enum CodingKeys: String, CodingKey {
        case id
        case promptText = "prompt_text"
        case responseText = "response_text"
        case model
        case success
        case latencyMS = "latency_ms"
    }
}

public struct AppMetadata: Codable, Equatable {
    public let app: String
    public let version: String
    public let sidecar: Bool
    public let launcher: Bool
    public let themeSuffix: String
    public let themeSchemaVersion: Int
    public let lockedDriftColors: [String: String]
    public let paths: AppPaths

    enum CodingKeys: String, CodingKey {
        case app
        case version
        case sidecar
        case launcher
        case themeSuffix = "theme_suffix"
        case themeSchemaVersion = "theme_schema_version"
        case lockedDriftColors = "locked_drift_colors"
        case paths
    }
}

public struct AppPaths: Codable, Equatable {
    public let root: String
    public let data: String
    public let outputs: String
    public let themes: String
    public let providers: String?
}

public struct AppOutputsResponse: Codable, Equatable {
    public let outputs: [OutputItem]
}

public struct OutputItem: Identifiable, Codable, Equatable {
    public var id: String { path }
    public let name: String
    public let path: String
    public let kind: String
    public let modifiedAt: Double
    public let files: [String]
    public let reportHTML: String?
    public let reportMarkdown: String?
    public let metricsJSON: String?

    public init(
        name: String,
        path: String,
        kind: String,
        modifiedAt: Double,
        files: [String],
        reportHTML: String?,
        reportMarkdown: String?,
        metricsJSON: String?
    ) {
        self.name = name
        self.path = path
        self.kind = kind
        self.modifiedAt = modifiedAt
        self.files = files
        self.reportHTML = reportHTML
        self.reportMarkdown = reportMarkdown
        self.metricsJSON = metricsJSON
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        name = try container.decode(String.self, forKey: .name)
        path = try container.decode(String.self, forKey: .path)
        kind = try container.decode(String.self, forKey: .kind)
        modifiedAt = try container.decodeIfPresent(Double.self, forKey: .modifiedAt) ?? 0
        files = try container.decodeIfPresent([String].self, forKey: .files) ?? []
        reportHTML = try container.decodeIfPresent(String.self, forKey: .reportHTML)
        reportMarkdown = try container.decodeIfPresent(String.self, forKey: .reportMarkdown)
        metricsJSON = try container.decodeIfPresent(String.self, forKey: .metricsJSON)
    }

    enum CodingKeys: String, CodingKey {
        case name
        case path
        case kind
        case modifiedAt = "modified_at"
        case files
        case reportHTML = "report_html"
        case reportMarkdown = "report_markdown"
        case metricsJSON = "metrics_json"
    }
}

public enum OutputDocumentFormat: String, Equatable {
    case markdown
    case jsonSummary
    case plainText
}

public struct OutputDocument: Identifiable, Equatable {
    public let id: String
    public let title: String
    public let subtitle: String
    public let sourcePath: String
    public let content: String
    public let format: OutputDocumentFormat

    public init(
        id: String = UUID().uuidString,
        title: String,
        subtitle: String,
        sourcePath: String,
        content: String,
        format: OutputDocumentFormat
    ) {
        self.id = id
        self.title = title
        self.subtitle = subtitle
        self.sourcePath = sourcePath
        self.content = content
        self.format = format
    }
}

public enum AppJobStatus: String, Codable, CaseIterable {
    case queued
    case running
    case finalizing
    case completed
    case failed
    case cancelled

    public var isTerminal: Bool {
        switch self {
        case .completed, .failed, .cancelled:
            true
        case .queued, .running, .finalizing:
            false
        }
    }

    public var displayName: String {
        switch self {
        case .queued: "Queued"
        case .running: "Running"
        case .finalizing: "Finalizing"
        case .completed: "Completed"
        case .failed: "Failed"
        case .cancelled: "Cancelled"
        }
    }
}

public struct AppJobProgress: Codable, Equatable {
    public let completed: Int
    public let total: Int
    public let current: String?

    enum CodingKeys: String, CodingKey {
        case completed
        case total
        case current
    }

    public init(completed: Int, total: Int, current: String?) {
        self.completed = completed
        self.total = total
        self.current = current
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        completed = try container.decodeIfPresent(Int.self, forKey: .completed) ?? 0
        total = try container.decodeIfPresent(Int.self, forKey: .total) ?? 0
        if let text = try? container.decodeIfPresent(String.self, forKey: .current) {
            current = text
        } else if let number = try? container.decodeIfPresent(Int.self, forKey: .current) {
            current = String(number)
        } else {
            current = nil
        }
    }
}

public struct AppJob: Identifiable, Codable, Equatable {
    public let id: String
    public let type: String
    public let status: AppJobStatus
    public let phase: String
    public let createdAt: String
    public let updatedAt: String
    public let progress: AppJobProgress
    public let summary: [String: JSONValue]
    public let outputs: [OutputItem]
    public let error: String?
    public let config: [String: JSONValue]

    enum CodingKeys: String, CodingKey {
        case id
        case type
        case status
        case phase
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case progress
        case summary
        case outputs
        case error
        case config
    }
}

public struct AppJobsResponse: Codable, Equatable {
    public let jobs: [AppJob]
}

public struct AppEvaluationJobRequest: Encodable {
    public let provider: String
    public let model: String
    public let evalSetIDs: [String]
    public let tier: String
    public let batch: Bool

    public init(provider: String, model: String, evalSetIDs: [String], tier: String = "full", batch: Bool = false) {
        self.provider = provider
        self.model = model
        self.evalSetIDs = evalSetIDs
        self.tier = tier
        self.batch = batch
    }

    enum CodingKeys: String, CodingKey {
        case provider
        case model
        case evalSetIDs = "eval_set_ids"
        case tier
        case batch
    }
}

public struct DriftRunJobRequest: Encodable {
    public let suite: String
    public let provider: String
    public let model: String

    public init(suite: String = "drift-v0.1", provider: String, model: String) {
        self.suite = suite
        self.provider = provider
        self.model = model
    }
}

public struct DiagnosticsResponse: Codable, Equatable {
    public let status: String
    public let checks: [String: JSONValue]
}

public struct OllamaModelRequest: Encodable {
    public let name: String
    public let confirm: Bool

    public init(name: String, confirm: Bool) {
        self.name = name
        self.confirm = confirm
    }
}

public struct PluginInstallRequest: Encodable {
    public let name: String
    public let confirm: Bool

    public init(name: String, confirm: Bool) {
        self.name = name
        self.confirm = confirm
    }
}

public struct ProviderCatalogResponse: Codable, Equatable {
    public let providerSuffix: String
    public let schemaVersion: Int
    public let builtIn: [ProviderDefinition]
    public let custom: [CustomProviderDefinition]
    public let invalid: [InvalidProvider]

    enum CodingKeys: String, CodingKey {
        case providerSuffix = "provider_suffix"
        case schemaVersion = "schema_version"
        case builtIn = "built_in"
        case custom
        case invalid
    }
}

public struct ProviderDefinition: Identifiable, Codable, Equatable {
    public let id: String
    public let label: String?
    public let name: String?
}

public enum ProviderAPIStyle: String, Codable, Equatable, CaseIterable {
    case openaiChat = "openai_chat"
    case anthropicMessages = "anthropic_messages"
    case openaiResponses = "openai_responses"
    case geminiGenerateContent = "gemini_generate_content"
    case localOpenAIChat = "local_openai_chat"
}

public struct CustomProviderDefinition: Identifiable, Codable, Equatable {
    public let schemaVersion: Int
    public let id: String
    public let name: String
    public let apiStyle: ProviderAPIStyle
    public let baseURL: String
    public let apiKeyEnv: String
    public let models: [String]
    public let modelsEndpoint: String?
    public let headers: [String: String]?
    public let source: String?
    public let path: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion
        case id
        case name
        case apiStyle
        case baseURL
        case apiKeyEnv
        case models
        case modelsEndpoint
        case headers
        case source
        case path
    }
}

public struct InvalidProvider: Identifiable, Codable, Equatable {
    public var id: String { path }
    public let path: String
    public let name: String
    public let error: String
}

public struct ThemeCatalogResponse: Codable, Equatable {
    public let themeSuffix: String
    public let schemaVersion: Int
    public let lockedDriftColors: [String: String]
    public let builtIn: [ThemePreset]
    public let custom: [ThemePreset]
    public let invalid: [InvalidTheme]

    enum CodingKeys: String, CodingKey {
        case themeSuffix = "theme_suffix"
        case schemaVersion = "schema_version"
        case lockedDriftColors = "locked_drift_colors"
        case builtIn = "built_in"
        case custom
        case invalid
    }
}

public struct ThemePreset: Identifiable, Codable, Equatable {
    public let schemaVersion: Int
    public let id: String
    public let name: String
    public let base: ThemeBase
    public let accent: String
    public let density: ThemeDensity
    public let chartIntensity: ChartIntensity
    public let surfaces: [String: String]?
    public let text: [String: String]?
    public let source: String?
    public let path: String?

    public init(
        schemaVersion: Int,
        id: String,
        name: String,
        base: ThemeBase,
        accent: String,
        density: ThemeDensity,
        chartIntensity: ChartIntensity,
        surfaces: [String: String]?,
        text: [String: String]?,
        source: String?,
        path: String?
    ) {
        self.schemaVersion = schemaVersion
        self.id = id
        self.name = name
        self.base = base
        self.accent = accent
        self.density = density
        self.chartIntensity = chartIntensity
        self.surfaces = surfaces
        self.text = text
        self.source = source
        self.path = path
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion
        case id
        case name
        case base
        case accent
        case density
        case chartIntensity
        case surfaces
        case text
        case source
        case path
    }
}

public enum ThemeBase: String, Codable, CaseIterable {
    case dark
    case light
    case system
}

public enum ThemeDensity: String, Codable, CaseIterable {
    case comfortable
    case compact
    case dense
}

public enum ChartIntensity: String, Codable, CaseIterable {
    case muted
    case standard
    case high
}

public struct InvalidTheme: Identifiable, Codable, Equatable {
    public var id: String { path }
    public let path: String
    public let name: String
    public let error: String

    public init(path: String, name: String, error: String) {
        self.path = path
        self.name = name
        self.error = error
    }
}

public struct DriftColors: Equatable {
    public let hold = Color(hex: "#20B7A8") ?? .mint
    public let partial = Color(hex: "#F0B24A") ?? .orange
    public let drift = Color(hex: "#F05D7F") ?? .pink

    public init() {}
}
