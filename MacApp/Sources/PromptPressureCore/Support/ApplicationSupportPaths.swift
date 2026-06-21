import Foundation

public struct ApplicationSupportPaths {
    public let root: URL
    public let data: URL
    public let outputs: URL
    public let themes: URL

    public init(root: URL, data: URL, outputs: URL, themes: URL) {
        self.root = root
        self.data = data
        self.outputs = outputs
        self.themes = themes
    }

    public static func promptPressure(fileManager: FileManager = .default) throws -> ApplicationSupportPaths {
        let base = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let root = base.appendingPathComponent("PromptPressure", isDirectory: true)
        let paths = ApplicationSupportPaths(
            root: root,
            data: root.appendingPathComponent("data", isDirectory: true),
            outputs: root.appendingPathComponent("outputs", isDirectory: true),
            themes: root.appendingPathComponent("themes", isDirectory: true)
        )
        try paths.ensureDirectories(fileManager: fileManager)
        return paths
    }

    public func ensureDirectories(fileManager: FileManager = .default) throws {
        for directory in [root, data, outputs, themes] {
            try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        }
    }
}
