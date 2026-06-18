import Foundation
import Darwin

public enum SidecarError: Error, LocalizedError {
    case missingEngineRoot
    case launchFailed(String)
    case timedOut

    public var errorDescription: String? {
        switch self {
        case .missingEngineRoot:
            return "Could not find the bundled PromptPressure engine"
        case .launchFailed(let message):
            return message
        case .timedOut:
            return "PromptPressure sidecar did not become healthy in time"
        }
    }
}

public struct SidecarConfiguration: Codable {
    public let engineRoot: String
    public let pythonExecutable: String

    public init(engineRoot: String, pythonExecutable: String) {
        self.engineRoot = engineRoot
        self.pythonExecutable = pythonExecutable
    }
}

@MainActor
public final class SidecarProcess: ObservableObject {
    @Published public private(set) var baseURL: URL?
    @Published public private(set) var statusText = "Not Connected"
    @Published public private(set) var isRunning = false
    @Published public private(set) var isConnected = false

    private var process: Process?
    private let paths: ApplicationSupportPaths
    private let apiClient: PromptPressureAPIClient

    public init(paths: ApplicationSupportPaths, apiClient: PromptPressureAPIClient) {
        self.paths = paths
        self.apiClient = apiClient
    }

    public func startIfNeeded(extraEnvironment: [String: String] = [:]) async throws -> URL {
        if let baseURL, isRunning {
            return baseURL
        }

        let port = try findFreePort()
        let url = URL(string: "http://127.0.0.1:\(port)")!
        let config = try resolveConfiguration()
        let process = Process()
        process.executableURL = URL(fileURLWithPath: config.pythonExecutable)
        process.currentDirectoryURL = URL(fileURLWithPath: config.engineRoot, isDirectory: true)
        process.arguments = [
            "-m", "uvicorn", "promptpressure.api:app",
            "--host", "127.0.0.1",
            "--port", "\(port)"
        ]

        var environment = ProcessInfo.processInfo.environment
        environment["PROMPTPRESSURE_DEV_NO_AUTH"] = "1"
        environment["PROMPTPRESSURE_LAUNCHER"] = "1"
        environment["PROMPTPRESSURE_APP_SUPPORT_DIR"] = paths.root.path
        environment["PROMPTPRESSURE_OUTPUT_DIR"] = paths.outputs.path
        environment["PROMPTPRESSURE_THEMES_DIR"] = paths.themes.path
        environment["DATABASE_URL"] = "sqlite+aiosqlite:///\(paths.data.appendingPathComponent("promptpressure.db").path)"
        environment.merge(extraEnvironment) { _, new in new }
        process.environment = environment

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        statusText = "Not Connected"
        isConnected = false
        do {
            try process.run()
        } catch {
            throw SidecarError.launchFailed(error.localizedDescription)
        }

        self.process = process
        self.baseURL = url
        self.apiClient.baseURL = url
        self.isRunning = true

        try await waitForHealth()
        isConnected = true
        statusText = "Connected"
        return url
    }

    public func stop() {
        process?.terminate()
        process = nil
        isRunning = false
        isConnected = false
        statusText = "Not Connected"
    }

    private func waitForHealth() async throws {
        let deadline = Date().addingTimeInterval(12)
        while Date() < deadline {
            if let metadata = try? await apiClient.health(), metadata.sidecar {
                return
            }
            try await Task.sleep(nanoseconds: 250_000_000)
        }
        stop()
        throw SidecarError.timedOut
    }

    private func resolveConfiguration() throws -> SidecarConfiguration {
        if let resource = Bundle.main.resourceURL?.appendingPathComponent("sidecar-dev.json"),
           let data = try? Data(contentsOf: resource),
           let config = try? JSONDecoder().decode(SidecarConfiguration.self, from: data) {
            return config
        }

        if let engineRoot = ProcessInfo.processInfo.environment["PROMPTPRESSURE_ENGINE_ROOT"] {
            return SidecarConfiguration(
                engineRoot: engineRoot,
                pythonExecutable: ProcessInfo.processInfo.environment["PROMPTPRESSURE_PYTHON"] ?? "/usr/bin/python3"
            )
        }

        if let resourceEngine = Bundle.main.resourceURL?.appendingPathComponent("engine"),
           FileManager.default.fileExists(atPath: resourceEngine.appendingPathComponent("promptpressure").path) {
            return SidecarConfiguration(engineRoot: resourceEngine.path, pythonExecutable: "/usr/bin/python3")
        }

        let cwd = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        if FileManager.default.fileExists(atPath: cwd.appendingPathComponent("promptpressure").path) {
            return SidecarConfiguration(engineRoot: cwd.path, pythonExecutable: "/usr/bin/python3")
        }

        throw SidecarError.missingEngineRoot
    }

    private func findFreePort() throws -> Int {
        for port in 8020...8050 {
            let socketFD = socket(AF_INET, SOCK_STREAM, 0)
            if socketFD < 0 { continue }
            defer { close(socketFD) }

            var addr = sockaddr_in()
            addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
            addr.sin_family = sa_family_t(AF_INET)
            addr.sin_port = in_port_t(port).bigEndian
            addr.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))

            let result = withUnsafePointer(to: &addr) { pointer in
                pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    Darwin.bind(socketFD, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
                }
            }
            if result == 0 {
                return port
            }
        }
        throw SidecarError.launchFailed("No free sidecar port in 8020-8050")
    }
}
