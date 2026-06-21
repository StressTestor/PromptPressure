import Foundation
import AppKit
import PromptPressureCore

@MainActor
final class AppStore: ObservableObject {
    @Published var selectedSection: AppSection = .run
    @Published var providers: [Provider] = []
    @Published var evalSets: [EvalSet] = []
    @Published var models: [String] = []
    @Published var selectedProviderID = "mock"
    @Published var selectedModel = "mock-model"
    @Published var selectedEvalSetIDs: Set<String> = []
    @Published var statusMessage = "Ready"
    @Published var runID: String?
    @Published var isRunning = false
    @Published var logEvents: [RunLogEvent] = []
    @Published var outputs: [OutputItem] = []
    @Published var history: [RunHistoryItem] = []
    @Published var jobs: [AppJob] = []
    @Published var activeJob: AppJob?
    @Published var providerCatalog: ProviderCatalogResponse?
    @Published var diagnostics: DiagnosticsResponse?
    @Published var plugins: [JSONValue] = []
    @Published var ollamaHealth: [String: JSONValue] = [:]
    @Published var ollamaModels: [JSONValue] = []
    @Published var metadata: AppMetadata?
    @Published var selectedDocument: OutputDocument?

    let paths: ApplicationSupportPaths
    let apiClient: PromptPressureAPIClient
    let sidecar: SidecarProcess
    let credentialStore: CredentialStore
    let themeStore: ThemeStore

    private var streamTask: Task<Void, Never>?
    private var streamingJobID: String?
    private let outputLoader = OutputDocumentLoader()

    init(
        paths: ApplicationSupportPaths,
        apiClient: PromptPressureAPIClient,
        sidecar: SidecarProcess,
        credentialStore: CredentialStore,
        themeStore: ThemeStore
    ) {
        self.paths = paths
        self.apiClient = apiClient
        self.sidecar = sidecar
        self.credentialStore = credentialStore
        self.themeStore = themeStore
    }

    convenience init() {
        let paths = (try? ApplicationSupportPaths.promptPressure()) ?? ApplicationSupportPaths(
            root: URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("PromptPressure"),
            data: URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("PromptPressure/data"),
            outputs: URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("PromptPressure/outputs"),
            themes: URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("PromptPressure/themes")
        )
        let apiClient = PromptPressureAPIClient()
        let sidecar = SidecarProcess(paths: paths, apiClient: apiClient)
        let credentials = CredentialStore()
        let themes = ThemeStore(paths: paths)
        self.init(paths: paths, apiClient: apiClient, sidecar: sidecar, credentialStore: credentials, themeStore: themes)
    }

    func bootstrap() async {
        do {
            _ = try await sidecar.startIfNeeded(extraEnvironment: credentialStore.sidecarEnvironment())
            try await refreshAll()
            append("Sidecar ready", kind: "complete")
        } catch {
            statusMessage = error.localizedDescription
            append(error.localizedDescription, kind: "error")
        }
    }

    func refreshAll() async throws {
        async let metadataTask = apiClient.health()
        async let providersTask = apiClient.providers()
        async let setsTask = apiClient.evalSets()
        async let outputsTask = apiClient.outputs()
        async let jobsTask = apiClient.jobs()
        async let providerCatalogTask = apiClient.providerCatalog()

        metadata = try await metadataTask
        providers = try await providersTask
        evalSets = try await setsTask
        let outputResponse = try await outputsTask
        outputs = outputResponse.outputs
        jobs = try await jobsTask.jobs
        providerCatalog = try await providerCatalogTask

        if let first = providers.first(where: { $0.available }) {
            selectedProviderID = first.id
        }
        if let firstSet = evalSets.first, selectedEvalSetIDs.isEmpty {
            selectedEvalSetIDs = [firstSet.id]
        }
        await loadModels()
        await refreshHistory()
        await refreshWorkbenchSurfaces()
        themeStore.loadLocalThemes()
        recoverActiveJobFromLoadedJobs(reason: "startup")
        if activeJob == nil {
            statusMessage = "Ready"
        }
    }

    func loadModels() async {
        do {
            let list = try await apiClient.models(provider: selectedProviderID)
            models = list.models
            if let first = list.models.first {
                selectedModel = first
            } else if selectedModel.isEmpty {
                selectedModel = selectedProviderID == "mock" ? "mock-model" : ""
            }
        } catch {
            models = []
            append("model load failed: \(error.localizedDescription)", kind: "error")
        }
    }

    func startRun() async {
        guard !isRunning else { return }
        let evalIDs = Array(selectedEvalSetIDs).sorted()
        guard !selectedModel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            append("Pick or type a model.", kind: "error")
            return
        }
        guard !evalIDs.isEmpty else {
            append("Pick at least one eval set.", kind: "error")
            return
        }

        do {
            _ = try await sidecar.startIfNeeded(extraEnvironment: credentialStore.sidecarEnvironment())
            isRunning = true
            logEvents.removeAll()
            append("POST /app/jobs/evaluations provider=\(selectedProviderID) model=\(selectedModel) eval_sets=\(evalIDs.joined(separator: ","))")
            let job = try await apiClient.startEvaluationJob(
                provider: selectedProviderID,
                model: selectedModel,
                evalSetIDs: evalIDs
            )
            activeJob = job
            upsertJob(job)
            runID = job.id
            isRunning = !job.status.isTerminal
            statusMessage = job.status.displayName
            append("job_id=\(job.id) streaming...")
            beginJobStream(jobID: job.id)
        } catch {
            isRunning = false
            statusMessage = error.localizedDescription
            append("evaluate failed: \(error.localizedDescription)", kind: "error")
        }
    }

    func cancelRun() async {
        guard let runID else { return }
        do {
            let job = try await apiClient.cancelJob(id: runID)
            activeJob = job
            upsertJob(job)
            append("cancellation requested", kind: "cancelled")
        } catch {
            append("cancel failed: \(error.localizedDescription)", kind: "error")
        }
    }

    func retryRun() async {
        await startRun()
    }

    func startDriftRun() async {
        do {
            _ = try await sidecar.startIfNeeded(extraEnvironment: credentialStore.sidecarEnvironment())
            let job = try await apiClient.startDriftRunJob(provider: selectedProviderID, model: selectedModel)
            activeJob = job
            upsertJob(job)
            runID = job.id
            isRunning = !job.status.isTerminal
            statusMessage = job.status.displayName
            append("drift job_id=\(job.id) streaming...")
            beginJobStream(jobID: job.id)
        } catch {
            append("drift run failed: \(error.localizedDescription)", kind: "error")
            statusMessage = error.localizedDescription
        }
    }

    func refreshHistory() async {
        do {
            history = try await apiClient.evaluations()
        } catch {
            history = []
        }
    }

    func refreshJobs() async {
        do {
            let response = try await apiClient.jobs()
            jobs = response.jobs
            recoverActiveJobFromLoadedJobs(reason: "refresh")
        } catch {
            append("job refresh failed: \(error.localizedDescription)", kind: "error")
        }
    }

    func refreshOutputs() async {
        do {
            let response = try await apiClient.outputs()
            outputs = response.outputs
        } catch {
            append("output refresh failed: \(error.localizedDescription)", kind: "error")
        }
    }

    func refreshWorkbenchSurfaces() async {
        await refreshDiagnostics()
        await refreshPlugins()
        await refreshOllama()
    }

    func refreshDiagnostics() async {
        do {
            diagnostics = try await apiClient.diagnostics()
        } catch {
            append("diagnostics failed: \(error.localizedDescription)", kind: "error")
        }
    }

    func refreshPlugins() async {
        do {
            plugins = try await apiClient.plugins()
        } catch {
            plugins = []
        }
    }

    func installPlugin(name: String, confirm: Bool) async {
        do {
            _ = try await apiClient.installPlugin(name: name, confirm: confirm)
            append("plugin installed: \(name)", kind: "complete")
            await refreshPlugins()
        } catch {
            append("plugin install failed: \(error.localizedDescription)", kind: "error")
        }
    }

    func refreshOllama() async {
        do {
            ollamaHealth = try await apiClient.ollamaHealth()
        } catch {
            ollamaHealth = ["status": .string("unavailable")]
        }
        do {
            let response = try await apiClient.ollamaModels()
            if case .array(let models)? = response["models"] {
                ollamaModels = models
            } else {
                ollamaModels = []
            }
        } catch {
            ollamaModels = []
        }
    }

    func pullOllamaModel(name: String, confirm: Bool) async {
        do {
            _ = try await apiClient.pullOllamaModel(name: name, confirm: confirm)
            append("ollama pull started: \(name)")
            await refreshOllama()
        } catch {
            append("ollama pull failed: \(error.localizedDescription)", kind: "error")
        }
    }

    func deleteOllamaModel(name: String, confirm: Bool) async {
        do {
            _ = try await apiClient.deleteOllamaModel(name: name, confirm: confirm)
            append("ollama model deleted: \(name)", kind: "complete")
            await refreshOllama()
        } catch {
            append("ollama delete failed: \(error.localizedDescription)", kind: "error")
        }
    }

    func revealOutputsFolder() {
        NSWorkspace.shared.activateFileViewerSelecting([paths.outputs])
    }

    func openOutput(_ item: OutputItem) {
        do {
            selectedDocument = try outputLoader.load(item)
        } catch {
            append("open output failed: \(error.localizedDescription)", kind: "error")
            statusMessage = error.localizedDescription
        }
    }

    func openEvaluation(_ item: RunHistoryItem) async {
        do {
            let detail = try await apiClient.evaluation(id: item.id)
            selectedDocument = outputLoader.makeDocument(from: detail)
        } catch {
            append("open evaluation failed: \(error.localizedDescription)", kind: "error")
            statusMessage = error.localizedDescription
        }
    }

    private func beginJobStream(jobID: String) {
        guard streamingJobID != jobID else { return }
        streamTask?.cancel()
        streamingJobID = jobID
        streamTask = Task { [weak self] in
            guard let self else { return }
            do {
                for try await event in apiClient.stream(path: "/app/jobs/\(jobID)/events") {
                    await MainActor.run {
                        self.handleStream(event)
                    }
                }
                await self.reconcileJob(id: jobID, reason: "stream ended")
            } catch is CancellationError {
                self.clearStream(jobID: jobID)
                return
            } catch {
                await MainActor.run {
                    self.append("connection lost: \(error.localizedDescription)", kind: "error")
                }
                await self.reconcileJob(id: jobID, reason: "stream lost")
            }
            self.clearStream(jobID: jobID)
        }
    }

    private func handleStream(_ event: SSEMessage) {
        switch event.event {
        case "completed", "complete":
            append("complete: \(event.data)", kind: "complete")
            Task { if let runID { await reconcileJob(id: runID, reason: "terminal event") } }
        case "cancelled":
            append("cancelled: \(event.data)", kind: "cancelled")
            Task { if let runID { await reconcileJob(id: runID, reason: "cancelled event") } }
        case "failed", "error":
            append("error: \(event.data)", kind: "error")
            Task { if let runID { await reconcileJob(id: runID, reason: "failed event") } }
        case "start_prompt":
            append("start: \(event.data)")
        case "end_prompt":
            append("end:   \(event.data)")
        default:
            append(event.data)
        }
    }

    private func reconcileJob(id: String, reason: String) async {
        do {
            let job = try await apiClient.job(id: id)
            let previous = activeJob
            apply(job)
            if previous?.status != job.status || previous?.phase != job.phase || previous?.updatedAt != job.updatedAt {
                append("reconciled job after \(reason): \(job.status.displayName)", kind: job.status == .completed ? "complete" : "status")
            }
            if job.status.isTerminal && (previous?.status != job.status || previous?.outputs != job.outputs) {
                await refreshOutputs()
                await refreshHistory()
                await refreshJobs()
            }
        } catch {
            append("job reconcile failed: \(error.localizedDescription)", kind: "error")
            isRunning = false
            statusMessage = "Unknown"
        }
    }

    private func recoverActiveJobFromLoadedJobs(reason: String) {
        guard let job = JobRecoveryPolicy.preferredJob(from: jobs, currentID: runID ?? activeJob?.id) else {
            if activeJob == nil {
                isRunning = false
            }
            return
        }

        let previousID = activeJob?.id
        apply(job)
        runID = job.id

        if previousID != job.id {
            append("attached to job after \(reason): \(job.id) \(job.status.displayName)")
        }

        if JobRecoveryPolicy.shouldStream(job: job, streamingJobID: streamingJobID) {
            append("streaming recovered job: \(job.id)")
            beginJobStream(jobID: job.id)
        }
    }

    private func clearStream(jobID: String) {
        if streamingJobID == jobID {
            streamingJobID = nil
        }
    }

    private func apply(_ job: AppJob) {
        activeJob = job
        upsertJob(job)
        isRunning = !job.status.isTerminal
        statusMessage = job.status.displayName
    }

    private func upsertJob(_ job: AppJob) {
        if let index = jobs.firstIndex(where: { $0.id == job.id }) {
            jobs[index] = job
        } else {
            jobs.insert(job, at: 0)
        }
        jobs.sort { $0.updatedAt > $1.updatedAt }
    }

    private func append(_ message: String, kind: String = "status") {
        logEvents.append(RunLogEvent.status(message, kind: kind))
        if logEvents.count > 500 {
            logEvents.removeFirst(logEvents.count - 500)
        }
    }
}
