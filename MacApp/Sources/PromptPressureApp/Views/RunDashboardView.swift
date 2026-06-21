import SwiftUI
import PromptPressureCore

struct RunDashboardView: View {
    @EnvironmentObject private var store: AppStore
    @EnvironmentObject private var themeStore: ThemeStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: themeStore.panelSpacing) {
                header

                HStack(alignment: .top, spacing: themeStore.panelSpacing) {
                    RunConfigurationPanel()
                        .frame(width: 310)

                    VStack(spacing: themeStore.panelSpacing) {
                        StatusCardsView()
                        ActiveJobPanelView()
                        LogPanelView()
                    }
                }

                OutputStripView()
            }
            .padding(22)
        }
        .navigationTitle("Run")
    }

    private var header: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Drift Studio")
                    .font(.title2.weight(.semibold))
                Text(store.statusMessage)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                Text("connection")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                HStack(spacing: 6) {
                    Circle()
                        .fill(store.sidecar.isConnected ? .green : .secondary)
                        .frame(width: 8, height: 8)
                    Text(store.sidecar.statusText)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(store.sidecar.isConnected ? .green : .secondary)
                }
            }
        }
    }
}

private struct RunConfigurationPanel: View {
    @EnvironmentObject private var store: AppStore
    @EnvironmentObject private var themeStore: ThemeStore

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("new run")
                .font(.headline)

            Picker("Provider", selection: $store.selectedProviderID) {
                ForEach(store.providers) { provider in
                    Text(provider.label).tag(provider.id)
                }
            }
            .onChange(of: store.selectedProviderID) {
                Task { await store.loadModels() }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Model")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                TextField("model id", text: $store.selectedModel)
                    .textFieldStyle(.roundedBorder)
                if !store.models.isEmpty {
                    Picker("Suggestions", selection: $store.selectedModel) {
                        ForEach(store.models, id: \.self) { model in
                            Text(model).tag(model)
                        }
                    }
                    .labelsHidden()
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Eval sets")
                    .font(.caption)
                    .foregroundStyle(.secondary)
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
                            Text(set.label)
                            Spacer()
                            Text("\(set.count)")
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            HStack {
                Button {
                    Task { await store.startRun() }
                } label: {
                    Label("Run", systemImage: "play.fill")
                }
                .buttonStyle(.borderedProminent)
                .disabled(store.isRunning)

                Button {
                    Task { await store.cancelRun() }
                } label: {
                    Label("Cancel", systemImage: "stop.fill")
                }
                .disabled(!store.isRunning)
            }
        }
        .padding(16)
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay {
            RoundedRectangle(cornerRadius: 8)
                .stroke(themeStore.accentColor.opacity(0.25), lineWidth: 1)
        }
    }
}

private struct StatusCardsView: View {
    @EnvironmentObject private var store: AppStore
    private let driftColors = DriftColors()

    var body: some View {
        Grid(horizontalSpacing: 10, verticalSpacing: 10) {
            GridRow {
                StatusCard(title: "providers", value: "\(store.providers.filter(\.available).count)", color: .blue)
                StatusCard(title: "eval sets", value: "\(store.evalSets.count)", color: .purple)
                StatusCard(title: "outputs", value: "\(store.outputs.count)", color: driftColors.hold)
                StatusCard(title: "run", value: runStatus, color: runColor)
                StatusCard(title: "progress", value: progressText, color: driftColors.partial)
            }
        }
    }

    private var runStatus: String {
        store.activeJob?.status.displayName ?? (store.isRunning ? "Running" : "Idle")
    }

    private var progressText: String {
        guard let progress = store.activeJob?.progress else { return "-" }
        if progress.total > 0 {
            return "\(progress.completed)/\(progress.total)"
        }
        return progress.current ?? "-"
    }

    private var runColor: Color {
        switch store.activeJob?.status {
        case .completed:
            return driftColors.hold
        case .failed:
            return driftColors.drift
        case .cancelled:
            return .orange
        case .queued, .running, .finalizing:
            return driftColors.partial
        case .none:
            return store.isRunning ? driftColors.partial : .secondary
        }
    }
}

private struct ActiveJobPanelView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("current job")
                    .font(.headline)
                Spacer()
                if let job = store.activeJob {
                    JobStatusChip(status: job.status)
                } else {
                    Text("Idle")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
            }

            if let job = store.activeJob {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(job.type)
                            .font(.subheadline.weight(.semibold))
                        Text(job.id)
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                        Spacer()
                        Text(job.phase)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                    }

                    JobProgressLine(progress: job.progress)

                    if let current = job.progress.current, !current.isEmpty, job.progress.total > 0 {
                        Text(current)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }

                    JobSummaryRows(summary: job.summary)

                    if let error = job.error, !error.isEmpty {
                        Label(error, systemImage: "exclamationmark.triangle.fill")
                            .font(.caption)
                            .foregroundStyle(.red)
                            .textSelection(.enabled)
                    }

                    if job.outputs.isEmpty {
                        Text(job.status.isTerminal ? "No outputs were reported for this job." : "Outputs will appear here when the sidecar finalizes the job.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("outputs")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            ForEach(job.outputs.prefix(3)) { output in
                                Button {
                                    store.openOutput(output)
                                } label: {
                                    HStack {
                                        Image(systemName: "doc.text.magnifyingglass")
                                            .foregroundStyle(.secondary)
                                        Text(output.name)
                                            .lineLimit(1)
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
            } else {
                Text("Start a run to see authoritative sidecar state, progress, and outputs here.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

private struct StatusCard: View {
    let title: String
    let value: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3.weight(.semibold))
                .foregroundStyle(color)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

private struct LogPanelView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("status")
                    .font(.headline)
                Spacer()
                Button {
                    Task { await store.retryRun() }
                } label: {
                    Label("Retry", systemImage: "arrow.counterclockwise")
                }
                .disabled(store.isRunning || store.runID == nil)
            }

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 6) {
                        ForEach(store.logEvents) { event in
                            Text(event.message)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundStyle(color(for: event.kind))
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .id(event.id)
                        }
                    }
                    .padding(12)
                }
                .frame(minHeight: 300)
                .background(Color.black.opacity(0.28))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .onChange(of: store.logEvents.count) {
                    if let last = store.logEvents.last {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }
        }
        .padding(16)
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func color(for kind: String) -> Color {
        switch kind {
        case "error": .red
        case "complete": .green
        case "cancelled": .orange
        default: .primary
        }
    }
}

private struct OutputStripView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("recent evals")
                    .font(.headline)
                Spacer()
                Button {
                    Task { await store.refreshOutputs() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }

            if store.outputs.isEmpty {
                Text("No outputs yet.")
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 18)
            } else {
                ForEach(store.outputs.prefix(5)) { output in
                    Button {
                        store.openOutput(output)
                    } label: {
                        HStack {
                            Image(systemName: output.kind == "directory" ? "doc.text.magnifyingglass" : "doc.text")
                            VStack(alignment: .leading) {
                                Text(output.name)
                                Text(output.path)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .foregroundStyle(.secondary)
                        }
                    }
                    .buttonStyle(.plain)
                    Divider()
                }
            }
        }
        .padding(16)
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
