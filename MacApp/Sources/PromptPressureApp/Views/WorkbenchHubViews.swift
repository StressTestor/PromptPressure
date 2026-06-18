import SwiftUI
import PromptPressureCore

struct DriftStudioView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        WorkbenchPage(title: "Drift Studio", subtitle: "Run drift-v0.1 transcripts and calibration jobs from the native sidecar.") {
            HStack {
                VStack(alignment: .leading, spacing: 6) {
                    Text("suite")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("drift-v0.1")
                        .font(.headline)
                }
                Spacer()
                Button {
                    Task { await store.startDriftRun() }
                } label: {
                    Label("Run Drift", systemImage: "waveform.path.ecg")
                }
                .buttonStyle(.borderedProminent)
                .disabled(store.isRunning)
            }
            JobList(title: "drift jobs", jobs: store.jobs.filter { $0.type.hasPrefix("drift") })
        }
    }
}

struct ProvidersWorkbenchView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        WorkbenchPage(title: "Providers", subtitle: "Built-in providers, Keychain status, and injected custom provider files.") {
            if let providerPath = store.metadata?.paths.providers {
                Label {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("custom provider folder")
                            .font(.headline)
                        Text(providerPath)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                        Text("Drop files ending in \(providerSuffix) here, then refresh.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } icon: {
                    Image(systemName: "folder")
                }
                Divider()
            }

            ForEach(store.providers) { provider in
                HStack {
                    Image(systemName: provider.available ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                        .foregroundStyle(provider.available ? .green : .orange)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(provider.label)
                            .font(.headline)
                        Text(provider.available ? "available" : (provider.reason ?? provider.remediationHint))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                Divider()
            }

            if let catalog = store.providerCatalog {
                CatalogBlock(
                    title: "custom providers",
                    empty: "No custom provider files loaded.",
                    rows: catalog.custom.map { "\($0.name) - \($0.apiStyle.rawValue) - \($0.baseURL)" }
                )
                if catalog.invalid.isEmpty {
                    Label("No invalid provider files.", systemImage: "checkmark.circle")
                        .foregroundStyle(.secondary)
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        Label("invalid provider files", systemImage: "exclamationmark.triangle.fill")
                            .font(.headline)
                            .foregroundStyle(.orange)
                        ForEach(catalog.invalid) { invalid in
                            VStack(alignment: .leading, spacing: 3) {
                                Text(invalid.name)
                                    .font(.system(.caption, design: .monospaced))
                                Text(invalid.error)
                                    .font(.caption)
                                    .foregroundStyle(.orange)
                                    .textSelection(.enabled)
                            }
                        }
                    }
                }
            }
        }
    }

    private var providerSuffix: String {
        store.providerCatalog?.providerSuffix ?? "*.pp-provider.json"
    }
}

struct ModelsWorkbenchView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        WorkbenchPage(title: "Models", subtitle: "Refresh model suggestions under the selected provider.") {
            HStack {
                Picker("Provider", selection: $store.selectedProviderID) {
                    ForEach(store.providers) { provider in
                        Text(provider.label).tag(provider.id)
                    }
                }
                Button {
                    Task { await store.loadModels() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }

            if store.models.isEmpty {
                Text("No suggestions. Type any model id the provider accepts in the Run dashboard.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(store.models, id: \.self) { model in
                    HStack {
                        Image(systemName: "cpu")
                            .foregroundStyle(.secondary)
                        Text(model)
                        Spacer()
                        if model == store.selectedModel {
                            Image(systemName: "checkmark")
                                .foregroundStyle(.green)
                        }
                    }
                    .contentShape(Rectangle())
                    .onTapGesture {
                        store.selectedModel = model
                    }
                    Divider()
                }
            }
        }
    }
}

struct SuitesWorkbenchView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        WorkbenchPage(title: "Suites", subtitle: "Pick one or more eval sets. Native jobs preserve the full selection.") {
            ForEach(store.evalSets) { set in
                Toggle(isOn: Binding(
                    get: { store.selectedEvalSetIDs.contains(set.id) },
                    set: { isOn in
                        if isOn {
                            store.selectedEvalSetIDs.insert(set.id)
                        } else {
                            store.selectedEvalSetIDs.remove(set.id)
                        }
                    }
                )) {
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(set.label)
                                .font(.headline)
                            Text(set.id)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text("\(set.count)")
                            .foregroundStyle(.secondary)
                    }
                }
                Divider()
            }
        }
    }
}

struct ReportsWorkbenchView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        WorkbenchPage(title: "Reports", subtitle: "Open generated reports and result artifacts inside the app.") {
            HStack {
                Spacer()
                Button {
                    Task { await store.refreshOutputs() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }
            if store.outputs.isEmpty {
                ContentUnavailableView("No Reports", systemImage: "doc.text.magnifyingglass", description: Text("Run an eval and generated outputs will appear here."))
                    .frame(maxWidth: .infinity, minHeight: 180)
            } else {
                ForEach(store.outputs) { output in
                    Button {
                        store.openOutput(output)
                    } label: {
                        HStack {
                            Image(systemName: "doc.text.magnifyingglass")
                            VStack(alignment: .leading, spacing: 3) {
                                Text(output.name)
                                Text(output.path)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                Text(output.files.isEmpty ? "no indexed files" : "\(output.files.count) indexed files")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                        }
                    }
                    .buttonStyle(.plain)
                    Divider()
                }
            }
        }
    }
}

struct PluginsWorkbenchView: View {
    @EnvironmentObject private var store: AppStore
    @State private var pluginName = ""
    @State private var pendingInstall: String?

    var body: some View {
        WorkbenchPage(title: "Plugins", subtitle: "List and install scorer plugins with confirmation gates.") {
            HStack {
                TextField("plugin name from registry", text: $pluginName)
                    .textFieldStyle(.roundedBorder)
                Button {
                    pendingInstall = pluginName
                } label: {
                    Label("Install", systemImage: "square.and.arrow.down")
                }
                .disabled(pluginName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            if store.plugins.isEmpty {
                Text("No registry plugins found.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(store.plugins.enumerated()), id: \.offset) { _, plugin in
                    Text(plugin.description)
                        .font(.system(.body, design: .monospaced))
                    Divider()
                }
            }
        }
        .confirmationDialog("Install plugin?", isPresented: Binding(
            get: { pendingInstall != nil },
            set: { if !$0 { pendingInstall = nil } }
        )) {
            Button("Install", role: .destructive) {
                if let pendingInstall {
                    Task { await store.installPlugin(name: pendingInstall, confirm: true) }
                }
                pendingInstall = nil
            }
            Button("Cancel", role: .cancel) {
                pendingInstall = nil
            }
        }
    }
}

struct OllamaWorkbenchView: View {
    @EnvironmentObject private var store: AppStore
    @State private var modelName = ""
    @State private var pendingDelete: String?
    @State private var pendingPull: String?

    var body: some View {
        WorkbenchPage(title: "Ollama", subtitle: "Health, local models, pull, and delete controls.") {
            HStack {
                Text("status")
                    .foregroundStyle(.secondary)
                Text(store.ollamaHealth["status"]?.description ?? "unknown")
                    .font(.headline)
                Spacer()
                Button {
                    Task { await store.refreshOllama() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }

            HStack {
                TextField("model name", text: $modelName)
                    .textFieldStyle(.roundedBorder)
                Button {
                    pendingPull = modelName
                } label: {
                    Label("Pull", systemImage: "arrow.down.circle")
                }
                .disabled(modelName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            ForEach(Array(store.ollamaModels.enumerated()), id: \.offset) { _, model in
                let name = ollamaModelName(model)
                HStack {
                    Text(name)
                        .font(.system(.body, design: .monospaced))
                        .lineLimit(1)
                    Spacer()
                    Button {
                        pendingDelete = name
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                }
                Divider()
            }
        }
        .confirmationDialog("Confirm Ollama action", isPresented: Binding(
            get: { pendingDelete != nil || pendingPull != nil },
            set: { if !$0 { pendingDelete = nil; pendingPull = nil } }
        )) {
            if let pendingPull {
                Button("Pull \(pendingPull)", role: .destructive) {
                    Task { await store.pullOllamaModel(name: pendingPull, confirm: true) }
                    self.pendingPull = nil
                }
            }
            if let pendingDelete {
                Button("Delete \(pendingDelete)", role: .destructive) {
                    Task { await store.deleteOllamaModel(name: pendingDelete, confirm: true) }
                    self.pendingDelete = nil
                }
            }
            Button("Cancel", role: .cancel) {
                pendingDelete = nil
                pendingPull = nil
            }
        }
    }

    private func ollamaModelName(_ value: JSONValue) -> String {
        if case .object(let object) = value,
           let name = object["name"]?.description,
           !name.isEmpty {
            return name
        }
        return value.description
    }
}

struct DiagnosticsWorkbenchView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        WorkbenchPage(title: "Diagnostics", subtitle: "Sidecar, database, disk, provider, and app health.") {
            HStack {
                Text("status")
                    .foregroundStyle(.secondary)
                Text(store.diagnostics?.status ?? "unknown")
                    .font(.headline)
                    .foregroundStyle(statusColor(store.diagnostics?.status))
                Spacer()
                Button {
                    Task { await store.refreshDiagnostics() }
                } label: {
                    Label("Run Checks", systemImage: "stethoscope")
                }
            }
            ForEach((store.diagnostics?.checks.keys.sorted() ?? []), id: \.self) { key in
                HStack(alignment: .top) {
                    Image(systemName: checkIcon(store.diagnostics?.checks[key]))
                        .foregroundStyle(checkColor(store.diagnostics?.checks[key]))
                    Text(key)
                        .font(.headline)
                        .frame(width: 150, alignment: .leading)
                    Text(store.diagnostics?.checks[key]?.description ?? "")
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                    Spacer()
                }
                Divider()
            }
            if let paths = store.metadata?.paths {
                VStack(alignment: .leading, spacing: 6) {
                    Text("app paths")
                        .font(.headline)
                    Text("data: \(paths.data)")
                    Text("outputs: \(paths.outputs)")
                    Text("themes: \(paths.themes)")
                    if let providers = paths.providers {
                        Text("providers: \(providers)")
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
            }
        }
    }

    private func statusColor(_ status: String?) -> Color {
        switch status?.lowercased() {
        case "ok", "healthy", "ready":
            .green
        case "warn", "warning":
            .orange
        case "error", "failed":
            .red
        default:
            .secondary
        }
    }

    private func checkIcon(_ value: JSONValue?) -> String {
        switch checkState(value) {
        case "ok", "healthy", "ready":
            "checkmark.circle.fill"
        case "warn", "warning":
            "exclamationmark.triangle.fill"
        case "error", "failed":
            "xmark.octagon.fill"
        default:
            "info.circle"
        }
    }

    private func checkColor(_ value: JSONValue?) -> Color {
        switch checkState(value) {
        case "ok", "healthy", "ready":
            .green
        case "warn", "warning":
            .orange
        case "error", "failed":
            .red
        default:
            .secondary
        }
    }

    private func checkState(_ value: JSONValue?) -> String {
        if case .object(let object) = value,
           let status = object["status"]?.description.lowercased(),
           !status.isEmpty {
            return status
        }
        return value?.description.lowercased() ?? ""
    }
}

struct JobsWorkbenchView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        WorkbenchPage(title: "Jobs", subtitle: "Authoritative sidecar job lifecycle state.") {
            HStack {
                Spacer()
                Button {
                    Task { await store.refreshJobs() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }
            JobList(title: "all jobs", jobs: store.jobs)
        }
    }
}

private struct WorkbenchPage<Content: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder let content: Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.title2.weight(.semibold))
                    Text(subtitle)
                        .foregroundStyle(.secondary)
                }
                VStack(alignment: .leading, spacing: 12) {
                    content
                }
                .padding(16)
                .background(.thinMaterial)
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .padding(22)
        }
        .navigationTitle(title)
    }
}

private struct CatalogBlock: View {
    let title: String
    let empty: String
    let rows: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
            if rows.isEmpty {
                Text(empty)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(rows, id: \.self) { row in
                    Text(row)
                        .font(.system(.caption, design: .monospaced))
                        .textSelection(.enabled)
                }
            }
        }
    }
}

private struct JobList: View {
    @EnvironmentObject private var store: AppStore
    @State private var expandedJobID: String?

    let title: String
    let jobs: [AppJob]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)
            if jobs.isEmpty {
                Text("No jobs yet.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(jobs) { job in
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Image(systemName: expandedJobID == job.id ? "chevron.down" : "chevron.right")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .frame(width: 12)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(job.id)
                                    .font(.system(.caption, design: .monospaced))
                                    .textSelection(.enabled)
                                Text("\(job.type) - \(job.phase)")
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 4) {
                                JobStatusChip(status: job.status)
                                Text(progressLabel(job.progress))
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                        }
                        .contentShape(Rectangle())
                        .onTapGesture {
                            expandedJobID = expandedJobID == job.id ? nil : job.id
                        }

                        if expandedJobID == job.id {
                            JobProgressLine(progress: job.progress)
                            JobSummaryRows(summary: job.summary)
                            if let error = job.error, !error.isEmpty {
                                Label(error, systemImage: "exclamationmark.triangle.fill")
                                    .font(.caption)
                                    .foregroundStyle(.red)
                                    .textSelection(.enabled)
                            }
                            if job.outputs.isEmpty {
                                Text(job.status.isTerminal ? "No outputs reported." : "Outputs pending.")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            } else {
                                ForEach(job.outputs) { output in
                                    Button {
                                        store.openOutput(output)
                                    } label: {
                                        HStack {
                                            Image(systemName: "doc.text.magnifyingglass")
                                                .foregroundStyle(.secondary)
                                            Text(output.name)
                                            Spacer()
                                            Image(systemName: "chevron.right")
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }
                    Divider()
                }
            }
        }
    }

    private func progressLabel(_ progress: AppJobProgress) -> String {
        if progress.total > 0 {
            return "\(progress.completed)/\(progress.total) prompts"
        }
        if let current = progress.current, !current.isEmpty {
            return current
        }
        return "waiting"
    }
}
