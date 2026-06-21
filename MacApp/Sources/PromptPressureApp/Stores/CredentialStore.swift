import Foundation
import PromptPressureCore

@MainActor
final class CredentialStore: ObservableObject {
    @Published private(set) var knownKeys: [String] = []
    @Published var lastError: String?

    private let keychain: KeychainStore
    private let parser = EnvFileParser()

    static let providerEnvKeys = [
        "OPENROUTER_API_KEY",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "GOOGLE_API_KEY",
        "XAI_API_KEY",
        "LITELLM_API_KEY"
    ]

    init(keychain: KeychainStore = KeychainStore()) {
        self.keychain = keychain
        refreshKnownKeys()
    }

    func refreshKnownKeys() {
        knownKeys = Self.providerEnvKeys.filter { key in
            (try? keychain.get(key)) != nil
        }
    }

    func set(_ value: String, for key: String) {
        do {
            if value.isEmpty {
                try keychain.delete(key)
            } else {
                try keychain.set(value, for: key)
            }
            lastError = nil
            refreshKnownKeys()
        } catch {
            lastError = error.localizedDescription
        }
    }

    func importEnvFile(at url: URL) {
        do {
            let values = try parser.parseFile(at: url)
            for key in Self.providerEnvKeys {
                if let value = values[key], !value.isEmpty {
                    try keychain.set(value, for: key)
                }
            }
            lastError = nil
            refreshKnownKeys()
        } catch {
            lastError = error.localizedDescription
        }
    }

    func sidecarEnvironment() -> [String: String] {
        var env: [String: String] = [:]
        for key in Self.providerEnvKeys {
            if let value = try? keychain.get(key), !value.isEmpty {
                env[key] = value
            }
        }
        return env
    }
}
