# PromptPressure Eval Suite Roadmap

## 1.x Series – Core Diagnostics & Observability

### v1.0–1.2 (Completed)
- ✅ Initial project setup, structured prompt dataset
- ✅ Basic evaluation logic: refusal detection, prompt compliance, tone consistency

### v1.3 (Completed)
- ✅ CLI Runner with YAML configuration support
- ✅ Pluggable adapter framework preparation (Groq, OpenAI, Mock adapters)

### v1.4 (Completed)
- ✅ Full modular adapter architecture deployed
- ✅ Expanded adapter system for easy backend swaps
- ✅ Robust schema validation

### v1.5 (Completed)
- ✅ LM Studio Adapter for local model integration
- ✅ Dataset validator tool (detecting duplicates and errors)
- ✅ Progress bars and enhanced runtime logging
- ✅ Timestamped evaluation outputs to avoid overwrites
- ✅ Runtime registration helper for custom adapters
- ✅ CI/CD Pipeline with GitHub Actions
- ✅ Automated visualization and monitoring
- ✅ Dynamic adapter selection
- ✅ Comprehensive error handling and retries
- ✅ Development tooling and type hints
- ✅ OpenRouter Adapter for unified access to 100+ models
- ✅ Enhanced adapter framework with improved configuration management

### v1.6 (Completed - Observability Focus)
- ✅ Enhanced metrics collection and analysis
- ✅ Integration with monitoring services (Prometheus/Grafana)
- ✅ Automated report generation with customizable templates (HTML/Markdown)
- ✅ Extended test coverage for all adapters
- ✅ Performance optimizations for large-scale evaluations
- ✅ Advanced configuration validation and error reporting
- ✅ Improved documentation and usage examples

### v1.7 (Completed - Scalability & Hardening)
- ✅ AsyncIO Refactor: Migrate core loop to fully asynchronous execution for massive parallelism.
- ✅ Database Integration: Reliable state storage (PostgreSQL/SQLite) instead of just file-based logging.
- ✅ Advanced Rate Limiting: Smart, adaptive throttling for diverse API providers.

### v1.8 (Completed - Advanced Tooling)
- ✅ Plugin System V0: Experimental hooks for third-party scorers.
- ✅ Comparison API: Native tools for side-by-side model diffing.
- ✅ Advanced Rate Limits: Granular control over API consumption.

### v1.9 (Completed - Pre-Platform Integration)
- ✅ Headless Mode: REST API wrapper (FastAPI) to run evals programmatically.
- ✅ JSON Schema Export: Auto-generate schemas for v2 UI form builders.
- ✅ Event Streaming: WebSocket/SSE support for real-time dashboard updates.
- ✅ LTS Hardening: Security audit fixes and dependency locking.

---

## 2.x Series – The Platform Era

### v2.0 (Completed - The Dashboard Release)
- ✅ **Interactive GUI**: A locally hosted React/Next.js dashboard to configure and run evals.
- ✅ **Visual Grid**: Real-time view of prompts vs models with diff highlighting.
- ✅ **Project Management**: Group evaluations into "Projects" with shared configurations.

### v2.1 (Completed - Plugins & Marketplace)
- ✅ **Plugin Registry**: Official support for installing community measurement tools.
- ✅ **Scorer Marketplace**: Download custom "judge" personas (e.g., "Legal Compliance Judge").
- ✅ **Custom Adapters**: Low-code UI for defining new API adapters without restarting.

### v2.2 (Completed - UI Overhaul & Advanced Analytics)
- ✅ **Design System**: Comprehensive UI refresh with proper App Shell, Sidebar, and dark mode polish.
- ✅ **Trend Analysis**: Historical plotting of model performance over time.
- ✅ **Regression Detection**: Automated alerts when a new model version fails previously passed tests.
- ✅ **Heatmaps**: Visual correlation between specific prompt categories and failure modes.

### v2.3 (Completed - Collaboration & Data Portability)
- ✅ **Team Workspaces**: Role-based access control for shared evaluation servers.
- ✅ **Comment/Annotation**: Allow human reviewers to manually override or annotate automated scores.
- ✅ **Data Portability**: Full CSV/JSON export/import for results and manual backup/restore.
- ✅ **Unified Settings Hub**: Central UI for API key management, theme customization, and global defaults.

### v2.4 (Completed - Enterprise Connectivity & Scale)
- ✅ **SSO Integration**: SAML/OIDC scaffolding.
- ✅ **Audit Logs**: Immutable logs of who ran what eval and when.

### v2.5 (LTS - User Experience & Stability)
- ✅ **Interactive Onboarding**: In-app guided tours and helper tooltips.
- ✅ **Validation Suite**: Built-in self-diagnostic tool to verify installation integrity.
- ✅ **LTS Release**: Feature freeze for long-term support maintenance.

> **Note**: v2.5 remains the LTS branch receiving security updates and critical fixes while v2.6+ development continues.

---

### v2.6 (In Progress - Desktop Studio & Offline Core)
- ✅ **Native Desktop App**: Tauri 2.0 wrapper for macOS (`.app`/`.dmg` built).
- ✅ **Bundled Runtime**: PyInstaller sidecar (Python backend bundled, no pip install needed).
- ✅ **Next.js Frontend Integration**: Full dashboard bundled as static export.
- 🔄 **Offline-First Mode**: Ollama adapter created, local model runner integration in progress.
- [ ] **Local Model Manager**: UI to download/manage local LLM weights directly.
- [ ] **Windows/Linux Builds**: Cross-platform packaging pending.

### v2.7 (External Integrations)
- [ ] **Slack/Discord Bot**: Run evals directly from chat ops.
- [ ] **Jira Sync**: Automatically create tickets for failed regression tests.
- [ ] **CI/CD Native Steps**: Official GitHub Actions and GitLab CI runners.
- [ ] **Webhook Debugger**: Log and replay failed integration events.

### v2.8 (Marketplace Expansion & Pre-Cloud)
- [ ] **Community Hub**: In-app browser for downloading community adapters/scorers.
- [ ] **Cloud Sync Preview**: Optional backup of local config/results to v3 Cloud backend.
- [ ] **Hybrid Mode**: Offload heavy processing to cloud workers while keeping local control.
- [ ] **Plugin Sandbox**: Safe execution mode for verifying untrusted community plugins.

### v2.9 (LTS Final & Polish)
- [ ] **Stability Pass**: Final bug fixes and performance tuning.
- [ ] **Documentation Overhaul**: Complete user guides and API docs.
- [ ] **Community Templates**: Curated starter configs for common use cases.
- [ ] **v2.x LTS**: Long-term support release; security updates only after this.

---

## Future Considerations (3.x+ SaaS Era)

> **Status**: The following features are deferred indefinitely. PromptPressure will remain a local-first, self-hosted tool. SaaS deployment may be revisited in the future based on demand.
>
> **Current Focus**: v2.x series (Desktop, Integrations, Marketplace)

### v3.0 (Cloud & SaaS Launch) – *Deferred*
- [ ] **SaaS Deployment**: One-click deploy to AWS/GCP/Azure.
- [ ] **Multi-Tenant Architecture**: Isolate data between different teams/organizations completely.
- [ ] **API First**: Expose 100% of functionality via a REST/gRPC API for CI pipelines.
- [ ] **Cost Center**: Detailed billing dashboard and utilization tracking per-tenant.

### v3.1 (Automated Red Teaming) – *Deferred*
- [ ] **Attack Simulation**: Built-in library of jailbreaks and prompt injections.
- [ ] **Adaptive Adversaries**: Specialized agents that evolve prompts to find weaknesses.
- [ ] **Safety Scores**: Standardized safety certification reports (e.g., NIST/ISO alignment).
- [ ] **Executive Summary**: One-click PDF report generation for non-technical stakeholders.

### v3.2 (Multi-Modal Expansion) – *Deferred*
- [ ] **Image Evaluation**: Support for text-to-image and image-to-text models.
- [ ] **Audio/Video Support**: Latency and quality metrics for A/V models.
- [ ] **Component Analysis**: Evaluating RAG pipelines (Retrieval vs Generation quality).

### v3.3 (Autonomous Optimization) – *Deferred*
- [ ] **Self-Healing Prompts**: The system suggests prompt improvements based on failure patterns.
- [ ] **Hyperparameter Tuning**: Auto-sweep temperature, top_p, and penalties to maximize scores.
- [ ] **Model Routing**: Generate logic rules for which model to use for which prompt type.
- [ ] **Approval Workflows**: Human-in-the-loop gates for applying major optimizations.

### v3.4 (Global Compliance) – *Deferred*
- [ ] **GDPR/CCPA Checks**: Automated PII scanning in prompt/response logs.
- [ ] **EU AI Act**: Built-in templates for regulatory compliance reporting.
- [ ] **Data Sovereignty**: Geofencing rules for where data is processed.

### v3.5 (Federated Evaluation) – *Deferred*
- [ ] **Private Evals**: Run evals on sensitive local data without uploading to cloud.
- [ ] **Blind Aggregation**: Share performance metrics with community benchmarks without revealing prompts.
- [ ] **Edge Runners**: Lightweight runners for edge devices/on-prem servers.
- [ ] **Fleet Health**: Centralized status dashboard for all remote runners.

### v3.6 (Agentic Benchmarks) – *Deferred*
- [ ] **Environment Sandbox**: Safe execution environments for testing agent code generation.
- [ ] **Multi-Turn Goals**: Evaluate agents on achieving complex, multi-step objectives.
- [ ] **Tool Use Evals**: Metrics for accurate API calling and tool selection.
- [ ] **Time-Travel Debugger**: Step-by-step replay of agent execution traces.

### v3.7 (Hardware Verification) – *Deferred*
- [ ] **Hardware-in-the-Loop**: Test model performance on specific hardware (TPU/GPU/NPU).
- [ ] **Energy Metrics**: Track power consumption per token/query.
- [ ] **Latency Profiling**: Detailed flame graphs of model inference stacks.

### v3.8 (Enterprise Scale) – *Deferred*
- [ ] **Global Mesh**: Multi-region active-active deployment support.
- [ ] **Disaster Recovery**: Automated failover for critical evaluation pipelines.
- [ ] **HSM Support**: Hardware Security Module integration for key management.

### v3.9 (Autonomous Era Prelude) – *Deferred*
- [ ] **Recursive Self-Improvement**: Models automatically generating better test cases for themselves.
- [ ] **Unsupervised Judging**: AI judges that learn new criteria without human labeling.
- [ ] **v4 Transition**: Bridges to the fully autonomous 4.x architecture.

---

## 4.x Series – The Autonomous Era – *Deferred*

> **Note**: Speculative future vision. Not actively planned.

### v4.0 (The Sentient Suite)
- [ ] **Self-Managed**: System defines its own roadmap and features based on usage.
- [ ] **Universal Interface**: Natural language voice/video interface for all control.
- [ ] **Emergency Kill Switch**: Hard-stop logical interrupt for autonomous operations.

---

## Mobile Companion (Parallel Track)

> **Note**: Mobile apps depend on v3.0 SaaS backend and develop in parallel with 3.x series.

### Mobile v1.0
- [ ] **iOS/Android App**: Monitor running evaluations on the go.
- [ ] **Push Notifications**: Alerts for critical failures or completion.
- [ ] **Offline Review**: Cache reports for offline analysis.
- [ ] **Biometric Login**: FaceID/TouchID support for secure mobile access.

---

## Deferred Features

The following features were considered but deferred for future evaluation:

| Feature | Original Version | Reason |
|---------|------------------|--------|
| Git Integration (UI sync) | v2.3 | Complexity; users can manually sync with git |
| VPC Peering Support | v2.4 | Enterprise-specific; low demand |
| Frontend Virtualization (10k+ rows) | v2.4 | Deferred to v3.x with new architecture |
| Distributed Workers (multi-node) | v1.7 | Requires v3.x cloud infrastructure |

---

*Last Updated: January 2026*  
*For the latest updates, check our [GitHub repository](https://github.com/StressTestor/PromptPressure)*
