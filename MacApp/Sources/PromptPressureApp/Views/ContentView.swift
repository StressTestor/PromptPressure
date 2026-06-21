import SwiftUI
import PromptPressureCore

struct ContentView: View {
    @EnvironmentObject private var store: AppStore
    @EnvironmentObject private var themeStore: ThemeStore

    var body: some View {
        NavigationSplitView {
            SidebarView(selection: $store.selectedSection)
        } detail: {
            Group {
                switch store.selectedSection {
                case .run:
                    RunDashboardView()
                case .drift:
                    DriftStudioView()
                case .providers:
                    ProvidersWorkbenchView()
                case .models:
                    ModelsWorkbenchView()
                case .suites:
                    SuitesWorkbenchView()
                case .reports:
                    ReportsWorkbenchView()
                case .plugins:
                    PluginsWorkbenchView()
                case .ollama:
                    OllamaWorkbenchView()
                case .diagnostics:
                    DiagnosticsWorkbenchView()
                case .jobs:
                    JobsWorkbenchView()
                case .history:
                    RunHistoryView()
                case .themes:
                    ThemePickerView()
                case .settings:
                    SettingsView()
                }
            }
            .background(.regularMaterial)
        }
        .toolbar {
            ToolbarItemGroup {
                Button {
                    Task { try? await store.refreshAll() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }

                Button {
                    Task { await store.startRun() }
                } label: {
                    Label("Run", systemImage: "play.fill")
                }
                .disabled(store.isRunning)

                Button {
                    Task { await store.cancelRun() }
                } label: {
                    Label("Cancel", systemImage: "stop.fill")
                }
                .disabled(!store.isRunning)
            }
        }
        .sheet(item: $store.selectedDocument) { document in
            OutputDocumentView(document: document)
        }
        .tint(themeStore.accentColor)
    }
}
