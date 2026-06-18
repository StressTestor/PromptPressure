import Foundation

public enum OutputDocumentError: Error, LocalizedError {
    case noReadableOutput(String)

    public var errorDescription: String? {
        switch self {
        case .noReadableOutput(let path):
            return "No readable eval output found at \(path)"
        }
    }
}

public final class OutputDocumentLoader {
    private let fileManager: FileManager

    public init(fileManager: FileManager = .default) {
        self.fileManager = fileManager
    }

    public func load(_ item: OutputItem) throws -> OutputDocument {
        var lastError: Error?
        for url in candidateURLs(for: item) {
            guard fileManager.fileExists(atPath: url.path), !isDirectory(url) else {
                continue
            }
            do {
                return try loadFile(at: url, title: item.name)
            } catch {
                lastError = error
            }
        }

        if let lastError {
            throw lastError
        }
        throw OutputDocumentError.noReadableOutput(item.path)
    }

    public func makeDocument(from detail: EvaluationDetail) -> OutputDocument {
        let passed = detail.results.filter(\.success).count
        let failed = detail.results.count - passed
        let models = Dictionary(grouping: detail.results.map(\.model), by: { $0 })
            .mapValues(\.count)
            .sorted { $0.key < $1.key }
            .map { "\($0.key) (\($0.value))" }
            .joined(separator: ", ")

        var lines: [String] = [
            "# evaluation \(detail.id)",
            "",
            "## summary",
            "- status: \(detail.status)",
            "- timestamp: \(detail.timestamp)",
            "- total prompts: \(detail.results.count)",
            "- passed: \(passed)",
            "- failed: \(failed)"
        ]

        if !models.isEmpty {
            lines.append("- models: \(models)")
        }

        lines.append("")
        lines.append("## results")

        for result in detail.results {
            lines.append("")
            lines.append("### \(result.id) - \(result.success ? "passed" : "failed")")
            lines.append("- model: \(result.model)")
            if let latencyMS = result.latencyMS {
                lines.append("- latency: \(Int(latencyMS)) ms")
            }
            lines.append("")
            lines.append("**prompt**")
            lines.append("")
            lines.append(clip(result.promptText, limit: 1_200))
            lines.append("")
            lines.append("**response**")
            lines.append("")
            lines.append(clip(result.responseText, limit: 2_000))
        }

        return OutputDocument(
            title: "evaluation \(detail.id)",
            subtitle: detail.status,
            sourcePath: "database:/evaluations/\(detail.id)",
            content: lines.joined(separator: "\n"),
            format: .markdown
        )
    }

    private func loadFile(at url: URL, title: String) throws -> OutputDocument {
        let ext = url.pathExtension.lowercased()
        switch ext {
        case "md", "markdown":
            let content = try String(contentsOf: url, encoding: .utf8)
            return OutputDocument(
                title: title,
                subtitle: "Markdown report",
                sourcePath: url.path,
                content: content,
                format: .markdown
            )
        case "json":
            let data = try Data(contentsOf: url)
            let object = try JSONSerialization.jsonObject(with: data)
            return OutputDocument(
                title: title,
                subtitle: "JSON results summary",
                sourcePath: url.path,
                content: summarizeJSON(object, title: title),
                format: .jsonSummary
            )
        case "html", "htm":
            let content = try String(contentsOf: url, encoding: .utf8)
            return OutputDocument(
                title: title,
                subtitle: "HTML report text",
                sourcePath: url.path,
                content: htmlToReadableText(content, title: title),
                format: .plainText
            )
        default:
            let content = try String(contentsOf: url, encoding: .utf8)
            return OutputDocument(
                title: title,
                subtitle: "\(ext.uppercased()) output",
                sourcePath: url.path,
                content: content,
                format: .plainText
            )
        }
    }

    private func candidateURLs(for item: OutputItem) -> [URL] {
        var urls: [URL] = []
        var seen: Set<String> = []
        let root = URL(fileURLWithPath: item.path)

        func add(_ path: String?) {
            guard let path, !path.isEmpty else { return }
            let url = URL(fileURLWithPath: path)
            guard !seen.contains(url.path) else { return }
            seen.insert(url.path)
            urls.append(url)
        }

        func addChild(_ name: String) {
            let url = root.appendingPathComponent(name)
            guard !seen.contains(url.path) else { return }
            seen.insert(url.path)
            urls.append(url)
        }

        if item.kind != "directory" {
            add(item.path)
        }

        add(item.reportMarkdown)
        addChild("report.md")

        if item.files.contains("report.md") {
            addChild("report.md")
        }
        for file in item.files where file.lowercased().hasSuffix(".md") {
            addChild(file)
        }

        addChild("results.json")
        add(item.metricsJSON)
        addChild("metrics.json")
        for file in item.files where file.lowercased().hasSuffix(".json") {
            addChild(file)
        }

        add(item.reportHTML)
        addChild("report.html")
        for file in item.files where file.lowercased().hasSuffix(".html") || file.lowercased().hasSuffix(".htm") {
            addChild(file)
        }

        for file in item.files where file.lowercased().hasSuffix(".txt") || file.lowercased().hasSuffix(".csv") {
            addChild(file)
        }

        return urls
    }

    private func summarizeJSON(_ object: Any, title: String) -> String {
        if let results = object as? [[String: Any]] {
            return summarizeResults(results, title: title)
        }
        if let dictionary = object as? [String: Any] {
            if let results = dictionary["results"] as? [[String: Any]] {
                return summarizeResults(results, title: title)
            }
            if let rows = dictionary["rows"] as? [[String: Any]] {
                return summarizeResults(rows, title: title)
            }
        }
        return prettyPrintedJSON(object, title: title)
    }

    private func summarizeResults(_ results: [[String: Any]], title: String) -> String {
        let passed = results.filter { boolValue($0["success"]) == true }.count
        let failed = results.filter { boolValue($0["success"]) == false }.count
        let unknown = max(results.count - passed - failed, 0)
        let modelCounts = Dictionary(grouping: results.compactMap { stringValue($0["model"]) }, by: { $0 })
            .mapValues(\.count)
            .sorted { $0.key < $1.key }
            .map { "\($0.key) (\($0.value))" }
            .joined(separator: ", ")

        var lines: [String] = [
            "# \(title)",
            "",
            "## summary",
            "- total prompts: \(results.count)",
            "- passed: \(passed)",
            "- failed: \(failed)"
        ]
        if unknown > 0 {
            lines.append("- unknown: \(unknown)")
        }
        if !modelCounts.isEmpty {
            lines.append("- models: \(modelCounts)")
        }

        lines.append("")
        lines.append("## results")

        for (index, result) in results.enumerated() {
            let identifier = stringValue(result["id"]) ?? "result \(index + 1)"
            let success = boolValue(result["success"])
            let status = success.map { $0 ? "passed" : "failed" } ?? "unknown"
            let prompt = stringValue(result["prompt"]) ?? stringValue(result["prompt_text"]) ?? ""
            let response = stringValue(result["response"]) ?? stringValue(result["response_text"]) ?? ""

            lines.append("")
            lines.append("### \(identifier) - \(status)")
            if let model = stringValue(result["model"]) {
                lines.append("- model: \(model)")
            }
            if let latency = latencyText(result["latency_ms"]) ?? latencyText(result["latency"]) {
                lines.append("- latency: \(latency)")
            }
            if let error = stringValue(result["error"]), !error.isEmpty {
                lines.append("- error: \(error)")
            }
            if let scores = result["plugin_scores"] as? [String: Any], !scores.isEmpty {
                lines.append("- scores: \(compactDictionary(scores))")
            }
            lines.append("")
            lines.append("**prompt**")
            lines.append("")
            lines.append(prompt.isEmpty ? "(empty)" : clip(prompt, limit: 1_200))
            lines.append("")
            lines.append("**response**")
            lines.append("")
            lines.append(response.isEmpty ? "(empty)" : clip(response, limit: 2_000))
        }

        return lines.joined(separator: "\n")
    }

    private func prettyPrintedJSON(_ object: Any, title: String) -> String {
        guard JSONSerialization.isValidJSONObject(object),
              let data = try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys]),
              let text = String(data: data, encoding: .utf8) else {
            return "# \(title)\n\nUnable to render JSON output."
        }
        return "# \(title)\n\n```json\n\(text)\n```"
    }

    private func htmlToReadableText(_ html: String, title: String) -> String {
        var text = html
        text = text.replacingOccurrences(of: "(?i)<br\\s*/?>", with: "\n", options: .regularExpression)
        text = text.replacingOccurrences(of: "(?i)</p>", with: "\n\n", options: .regularExpression)
        text = text.replacingOccurrences(of: "(?i)</h[1-6]>", with: "\n\n", options: .regularExpression)
        text = text.replacingOccurrences(of: "<[^>]+>", with: " ", options: .regularExpression)
        text = text.replacingOccurrences(of: "&nbsp;", with: " ")
        text = text.replacingOccurrences(of: "&amp;", with: "&")
        text = text.replacingOccurrences(of: "&lt;", with: "<")
        text = text.replacingOccurrences(of: "&gt;", with: ">")
        text = text.replacingOccurrences(of: "&quot;", with: "\"")
        text = text.replacingOccurrences(of: "&#39;", with: "'")
        text = text.replacingOccurrences(of: "[ \\t]{2,}", with: " ", options: .regularExpression)
        text = text.replacingOccurrences(of: "\\n[ \\t]+", with: "\n", options: .regularExpression)
        text = text.replacingOccurrences(of: "\\n{3,}", with: "\n\n", options: .regularExpression)
        return "# \(title)\n\n\(text.trimmingCharacters(in: .whitespacesAndNewlines))"
    }

    private func isDirectory(_ url: URL) -> Bool {
        var isDirectory: ObjCBool = false
        return fileManager.fileExists(atPath: url.path, isDirectory: &isDirectory) && isDirectory.boolValue
    }

    private func boolValue(_ value: Any?) -> Bool? {
        if let value = value as? Bool {
            return value
        }
        if let value = value as? NSNumber {
            return value.boolValue
        }
        if let value = value as? String {
            switch value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
            case "true", "yes", "1", "passed", "pass":
                return true
            case "false", "no", "0", "failed", "fail":
                return false
            default:
                return nil
            }
        }
        return nil
    }

    private func stringValue(_ value: Any?) -> String? {
        switch value {
        case let value as String:
            return value
        case let value as NSNumber:
            return value.stringValue
        case let value as Bool:
            return value ? "true" : "false"
        case .some(let value):
            return String(describing: value)
        case .none:
            return nil
        }
    }

    private func latencyText(_ value: Any?) -> String? {
        guard let value = value else { return nil }
        if let number = value as? NSNumber {
            return "\(Int(number.doubleValue)) ms"
        }
        if let string = value as? String, !string.isEmpty {
            return string
        }
        return nil
    }

    private func compactDictionary(_ dictionary: [String: Any]) -> String {
        dictionary
            .sorted { $0.key < $1.key }
            .map { "\($0.key)=\(stringValue($0.value) ?? "?")" }
            .joined(separator: ", ")
    }

    private func clip(_ text: String, limit: Int) -> String {
        guard text.count > limit else { return text }
        let end = text.index(text.startIndex, offsetBy: limit)
        return "\(text[..<end])\n\n[truncated]"
    }
}
