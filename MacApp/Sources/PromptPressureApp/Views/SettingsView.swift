import SwiftUI
import UniformTypeIdentifiers
import PromptPressureCore

struct SettingsView: View {
    @EnvironmentObject private var store: AppStore
    @EnvironmentObject private var credentials: CredentialStore
    @EnvironmentObject private var themeStore: ThemeStore
    @State private var selectedKey = CredentialStore.providerEnvKeys[0]
    @State private var secretValue = ""
    @State private var showingEnvImporter = false

    var body: some View {
        TabView {
            credentialsTab
                .tabItem {
                    Label("Providers", systemImage: "key")
                }

            pathsTab
                .tabItem {
                    Label("Paths", systemImage: "folder")
                }

            themeTab
                .tabItem {
                    Label("Theme", systemImage: "paintpalette")
                }
        }
        .padding(20)
    }

    private var credentialsTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("provider credentials")
                .font(.headline)
            Text("Secrets are stored in Keychain and injected only into the sidecar environment when it starts.")
                .foregroundStyle(.secondary)

            Picker("Key", selection: $selectedKey) {
                ForEach(CredentialStore.providerEnvKeys, id: \.self) { key in
                    Text(key).tag(key)
                }
            }

            SecureField("value", text: $secretValue)
                .textFieldStyle(.roundedBorder)

            HStack {
                Button("Save") {
                    credentials.set(secretValue, for: selectedKey)
                    secretValue = ""
                }
                .buttonStyle(.borderedProminent)

                Button("Import .env") {
                    showingEnvImporter = true
                }
            }

            if !credentials.knownKeys.isEmpty {
                Text("stored: \(credentials.knownKeys.joined(separator: ", "))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let error = credentials.lastError {
                Text(error)
                    .foregroundStyle(.red)
            }

            Spacer()
        }
        .fileImporter(
            isPresented: $showingEnvImporter,
            allowedContentTypes: [.plainText, .data],
            allowsMultipleSelection: false
        ) { result in
            if case .success(let urls) = result, let url = urls.first {
                credentials.importEnvFile(at: url)
            }
        }
    }

    private var pathsTab: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("application support")
                .font(.headline)
            PathRow(label: "root", url: store.paths.root)
            PathRow(label: "data", url: store.paths.data)
            PathRow(label: "outputs", url: store.paths.outputs)
            PathRow(label: "themes", url: store.paths.themes)
            HStack {
                Button("Reveal Outputs") {
                    store.revealOutputsFolder()
                }
                Button("Reveal Themes") {
                    themeStore.revealThemesFolder()
                }
            }
            Spacer()
        }
    }

    private var themeTab: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("theme defaults")
                .font(.headline)
            Picker("Theme", selection: $themeStore.selectedThemeID) {
                ForEach(themeStore.allThemes) { theme in
                    Text(theme.name).tag(theme.id)
                }
            }
            Picker("Density", selection: $themeStore.density) {
                ForEach(ThemeDensity.allCases, id: \.self) { density in
                    Text(density.rawValue.capitalized).tag(density)
                }
            }
            Picker("Chart intensity", selection: $themeStore.chartIntensity) {
                ForEach(ChartIntensity.allCases, id: \.self) { intensity in
                    Text(intensity.rawValue.capitalized).tag(intensity)
                }
            }
            Spacer()
        }
    }
}

private struct PathRow: View {
    let label: String
    let url: URL

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(url.path)
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .lineLimit(2)
        }
    }
}
