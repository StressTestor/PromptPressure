import Foundation
import PromptPressureCore

enum CheckFailure: Error, CustomStringConvertible {
    case failed(String)

    var description: String {
        switch self {
        case .failed(let message): message
        }
    }
}

func expect(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    if !condition() {
        throw CheckFailure.failed(message)
    }
}

func checkEnvParser() throws {
    let values = EnvFileParser().parse("""
    # comment
    export OPENAI_API_KEY="sk-test"
    GROQ_API_KEY='gsk-test'
    EMPTY =
    BAD_LINE
    """)
    try expect(values["OPENAI_API_KEY"] == "sk-test", "OPENAI_API_KEY did not parse")
    try expect(values["GROQ_API_KEY"] == "gsk-test", "GROQ_API_KEY did not parse")
    try expect(values["EMPTY"] == "", "empty value did not parse")
    try expect(values["BAD_LINE"] == nil, "bad line should be ignored")
}

func checkThemeLoader() throws {
    let dir = URL(fileURLWithPath: NSTemporaryDirectory())
        .appendingPathComponent(UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let file = dir.appendingPathComponent("custom.pp-theme.json")
    try """
    {
      "schemaVersion": 1,
      "id": "custom",
      "name": "Custom",
      "base": "dark",
      "accent": "#5269FF",
      "density": "compact",
      "chartIntensity": "high",
      "surfaces": { "panel": "#242733" }
    }
    """.write(to: file, atomically: true, encoding: .utf8)

    let loader = ThemeFileLoader()
    let theme = try loader.loadTheme(at: file)
    try expect(theme.id == "custom", "theme id did not decode")
    try expect(theme.density == .compact, "theme density did not decode")

    let bad = ThemePreset(
        schemaVersion: 1,
        id: "bad",
        name: "Bad",
        base: .dark,
        accent: "#5269FF",
        density: .compact,
        chartIntensity: .standard,
        surfaces: ["drift": "#000000"],
        text: nil,
        source: nil,
        path: nil
    )
    do {
        try loader.validate(bad)
        throw CheckFailure.failed("locked drift color override was accepted")
    } catch ThemeFileError.lockedSemanticColor(let key) {
        try expect(key == "drift", "wrong locked key")
    }
}

func checkKeychain() throws {
    let store = KeychainStore(service: "app.promptpressure.checks.\(UUID().uuidString)")
    let account = "OPENAI_API_KEY"
    try store.set("sk-test", for: account)
    let stored = try store.get(account)
    try expect(stored == "sk-test", "keychain round trip failed")
    try store.delete(account)
    let deleted = try store.get(account)
    try expect(deleted == nil, "keychain delete failed")
}

func checkDecoding() throws {
    let startData = """
    {"run_id":"abc","status":"started","stream_url":"/stream/abc"}
    """.data(using: .utf8)!
    let start = try JSONDecoder().decode(EvaluationStartResponse.self, from: startData)
    try expect(start.runID == "abc", "run_id did not decode")
    try expect(start.streamURL == "/stream/abc", "stream_url did not decode")

    let themeData = """
    {
      "theme_suffix": ".pp-theme.json",
      "schema_version": 1,
      "locked_drift_colors": {"hold":"#20B7A8","partial":"#F0B24A","drift":"#F05D7F"},
      "built_in": [],
      "custom": [],
      "invalid": [{"path":"/tmp/bad.pp-theme.json","name":"bad.pp-theme.json","error":"bad"}]
    }
    """.data(using: .utf8)!
    let catalog = try JSONDecoder().decode(ThemeCatalogResponse.self, from: themeData)
    try expect(catalog.themeSuffix == ".pp-theme.json", "theme suffix did not decode")
    try expect(catalog.invalid.first?.name == "bad.pp-theme.json", "invalid theme did not decode")

    let jobData = """
    {
      "id": "job-1",
      "type": "evaluation",
      "status": "completed",
      "phase": "completed",
      "created_at": "2026-06-18T12:00:00Z",
      "updated_at": "2026-06-18T12:01:00Z",
      "progress": {"completed": 2, "total": 2, "current": "done"},
      "summary": {"provider": "mock", "model": "mock-model"},
      "outputs": [{"name":"report.md","path":"/tmp/report.md","kind":"file","modified_at":0,"files":[]}],
      "error": null,
      "config": {"provider": "mock"}
    }
    """.data(using: .utf8)!
    let job = try JSONDecoder().decode(AppJob.self, from: jobData)
    try expect(job.status == .completed, "job status did not decode")
    try expect(job.status.isTerminal, "completed job should be terminal")
    try expect(job.outputs.first?.name == "report.md", "job output did not decode")

    let providerCatalogData = """
    {
      "provider_suffix": ".pp-provider.json",
      "schema_version": 1,
      "built_in": [],
      "custom": [
        {
          "schemaVersion": 1,
          "id": "acme",
          "name": "Acme",
          "apiStyle": "openai_chat",
          "baseURL": "https://api.example.test/v1/chat/completions",
          "apiKeyEnv": "ACME_API_KEY",
          "models": ["acme-fast"]
        }
      ],
      "invalid": [{"path":"/tmp/bad.pp-provider.json","name":"bad.pp-provider.json","error":"bad"}]
    }
    """.data(using: .utf8)!
    let providerCatalog = try JSONDecoder().decode(ProviderCatalogResponse.self, from: providerCatalogData)
    try expect(providerCatalog.providerSuffix == ".pp-provider.json", "provider suffix did not decode")
    try expect(providerCatalog.custom.first?.apiStyle == .openaiChat, "provider api style did not decode")
    try expect(providerCatalog.invalid.first?.name == "bad.pp-provider.json", "invalid provider did not decode")
}

func checkOutputDocumentLoader() throws {
    let dir = URL(fileURLWithPath: NSTemporaryDirectory())
        .appendingPathComponent(UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

    let resultsFile = dir.appendingPathComponent("results.json")
    try """
    [
      {
        "id": "rs_001",
        "prompt": "Prompt one",
        "response": "Response one",
        "model": "mock-model",
        "success": true,
        "latency_ms": 42
      },
      {
        "id": "rs_002",
        "prompt": "Prompt two",
        "response": "Response two",
        "model": "mock-model",
        "success": false,
        "error": "mock failure"
      }
    ]
    """.write(to: resultsFile, atomically: true, encoding: .utf8)

    let loader = OutputDocumentLoader()
    let jsonItem = OutputItem(
        name: "mock-run",
        path: dir.path,
        kind: "directory",
        modifiedAt: 0,
        files: ["results.json"],
        reportHTML: nil,
        reportMarkdown: nil,
        metricsJSON: nil
    )
    let jsonDocument = try loader.load(jsonItem)
    try expect(jsonDocument.content.contains("total prompts: 2"), "json summary omitted total prompts")
    try expect(jsonDocument.content.contains("failed: 1"), "json summary omitted failed count")
    try expect(jsonDocument.content.contains("rs_001 - passed"), "json summary omitted result status")

    let reportFile = dir.appendingPathComponent("report.md")
    try "# PromptPressure Report\n\nReadable report.".write(to: reportFile, atomically: true, encoding: .utf8)
    let markdownItem = OutputItem(
        name: "mock-run",
        path: dir.path,
        kind: "directory",
        modifiedAt: 0,
        files: ["report.md", "results.json"],
        reportHTML: nil,
        reportMarkdown: reportFile.path,
        metricsJSON: nil
    )
    let markdownDocument = try loader.load(markdownItem)
    try expect(markdownDocument.content.contains("PromptPressure Report"), "markdown report was not preferred")

    let detailData = """
    {
      "id": "run-123",
      "status": "completed",
      "timestamp": "2026-06-18T00:00:00",
      "results": [
        {
          "id": "r1",
          "prompt_text": "stored prompt",
          "response_text": "stored response",
          "model": "mock-model",
          "success": true,
          "latency_ms": 12
        }
      ]
    }
    """.data(using: .utf8)!
    let detail = try JSONDecoder().decode(EvaluationDetail.self, from: detailData)
    let detailDocument = loader.makeDocument(from: detail)
    try expect(detailDocument.content.contains("evaluation run-123"), "evaluation document omitted id")
    try expect(detailDocument.content.contains("stored prompt"), "evaluation document omitted prompt")
}

func checkJobRecoveryPolicy() throws {
    func job(_ id: String, status: String, updatedAt: String) throws -> AppJob {
        let data = """
        {
          "id": "\(id)",
          "type": "evaluation",
          "status": "\(status)",
          "phase": "\(status)",
          "created_at": "2026-06-18T12:00:00Z",
          "updated_at": "\(updatedAt)",
          "progress": {"completed": 0, "total": 2, "current": "waiting"},
          "summary": {},
          "outputs": [],
          "error": null,
          "config": {}
        }
        """.data(using: .utf8)!
        return try JSONDecoder().decode(AppJob.self, from: data)
    }

    let oldCompleted = try job("old", status: "completed", updatedAt: "2026-06-18T12:01:00Z")
    let active = try job("active", status: "running", updatedAt: "2026-06-18T12:02:00Z")
    let newerCompleted = try job("newer", status: "completed", updatedAt: "2026-06-18T12:03:00Z")

    let recoveredActive = JobRecoveryPolicy.preferredJob(
        from: [newerCompleted, active, oldCompleted],
        currentID: nil
    )
    try expect(recoveredActive?.id == "active", "recovery should prefer a running job over latest terminal job")

    let currentRunning = JobRecoveryPolicy.preferredJob(
        from: [newerCompleted, active, oldCompleted],
        currentID: "active"
    )
    try expect(currentRunning?.id == "active", "recovery should keep current running job")

    let currentTerminalWithNoActive = JobRecoveryPolicy.preferredJob(
        from: [newerCompleted, oldCompleted],
        currentID: "old"
    )
    try expect(currentTerminalWithNoActive?.id == "old", "recovery should keep current terminal job when no jobs are active")

    try expect(JobRecoveryPolicy.shouldStream(job: active, streamingJobID: nil), "active job should stream")
    try expect(!JobRecoveryPolicy.shouldStream(job: active, streamingJobID: "active"), "same active job should not open duplicate stream")
    try expect(!JobRecoveryPolicy.shouldStream(job: newerCompleted, streamingJobID: nil), "terminal job should not stream")
}

do {
    try checkEnvParser()
    try checkThemeLoader()
    try checkKeychain()
    try checkDecoding()
    try checkOutputDocumentLoader()
    try checkJobRecoveryPolicy()
    print("PromptPressureChecks passed")
} catch {
    fputs("PromptPressureChecks failed: \(error)\n", stderr)
    exit(1)
}
