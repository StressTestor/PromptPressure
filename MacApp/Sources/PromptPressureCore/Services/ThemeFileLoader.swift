import Foundation

public enum ThemeFileError: Error, LocalizedError {
    case wrongSuffix(String)
    case invalidAccent(String)
    case lockedSemanticColor(String)

    public var errorDescription: String? {
        switch self {
        case .wrongSuffix(let name):
            return "\(name) must end with .pp-theme.json"
        case .invalidAccent(let value):
            return "Accent \(value) must be a #RRGGBB color"
        case .lockedSemanticColor(let key):
            return "\(key) cannot override hold, partial, or drift semantic colors"
        }
    }
}

public struct ThemeFileLoader {
    public static let suffix = ".pp-theme.json"
    private let decoder = JSONDecoder()

    public init() {}

    public func loadThemes(from directory: URL) -> (themes: [ThemePreset], invalid: [InvalidTheme]) {
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: nil
        ) else {
            return ([], [])
        }

        var themes: [ThemePreset] = []
        var invalid: [InvalidTheme] = []

        for file in files where file.lastPathComponent.hasSuffix(Self.suffix) {
            do {
                let theme = try loadTheme(at: file)
                themes.append(theme)
            } catch {
                invalid.append(InvalidTheme(
                    path: file.path,
                    name: file.lastPathComponent,
                    error: error.localizedDescription
                ))
            }
        }

        return (themes.sorted { $0.name < $1.name }, invalid.sorted { $0.name < $1.name })
    }

    public func loadTheme(at url: URL) throws -> ThemePreset {
        guard url.lastPathComponent.hasSuffix(Self.suffix) else {
            throw ThemeFileError.wrongSuffix(url.lastPathComponent)
        }
        let data = try Data(contentsOf: url)
        let theme = try decoder.decode(ThemePreset.self, from: data)
        try validate(theme)
        return theme
    }

    public func validate(_ theme: ThemePreset) throws {
        guard Self.isHexColor(theme.accent) else {
            throw ThemeFileError.invalidAccent(theme.accent)
        }

        for group in [theme.surfaces, theme.text] {
            for (key, value) in group ?? [:] {
                if ["hold", "partial", "drift"].contains(key) {
                    throw ThemeFileError.lockedSemanticColor(key)
                }
                guard Self.isHexColor(value) else {
                    throw ThemeFileError.invalidAccent(value)
                }
            }
        }
    }

    public static func isHexColor(_ value: String) -> Bool {
        let pattern = #"^#[0-9A-Fa-f]{6}$"#
        return value.range(of: pattern, options: .regularExpression) != nil
    }
}
