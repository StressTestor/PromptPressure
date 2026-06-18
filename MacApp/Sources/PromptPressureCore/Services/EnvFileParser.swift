import Foundation

public struct EnvFileParser {
    public init() {}

    public func parse(_ text: String) -> [String: String] {
        var output: [String: String] = [:]

        for rawLine in text.components(separatedBy: .newlines) {
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !line.isEmpty, !line.hasPrefix("#") else { continue }

            let normalized = line.hasPrefix("export ") ? String(line.dropFirst(7)) : line
            guard let equals = normalized.firstIndex(of: "=") else { continue }

            let key = normalized[..<equals].trimmingCharacters(in: .whitespacesAndNewlines)
            guard !key.isEmpty else { continue }

            var value = normalized[normalized.index(after: equals)...]
                .trimmingCharacters(in: .whitespacesAndNewlines)

            if (value.hasPrefix("\"") && value.hasSuffix("\"")) ||
                (value.hasPrefix("'") && value.hasSuffix("'")) {
                value.removeFirst()
                value.removeLast()
            }

            output[key] = value
        }

        return output
    }

    public func parseFile(at url: URL) throws -> [String: String] {
        let text = try String(contentsOf: url, encoding: .utf8)
        return parse(text)
    }
}
