import SwiftUI
import PromptPressureCore

struct RunHistoryView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("History")
                        .font(.title2.weight(.semibold))
                    Text("The analysis-first workbench grows from this run list.")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    Task { await store.refreshHistory() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }

            if store.history.isEmpty {
                ContentUnavailableView(
                    "No stored evaluations",
                    systemImage: "clock.arrow.circlepath",
                    description: Text("Run a mock eval from the dashboard to populate history.")
                )
            } else {
                ScrollView {
                    LazyVStack(spacing: 10) {
                        ForEach(store.history) { item in
                            Button {
                                Task { await store.openEvaluation(item) }
                            } label: {
                                HStack(spacing: 14) {
                                    Image(systemName: "doc.text.magnifyingglass")
                                        .foregroundStyle(statusColor(item.status))
                                        .frame(width: 20)

                                    VStack(alignment: .leading, spacing: 5) {
                                        Text(item.id)
                                            .font(.system(.body, design: .monospaced).weight(.semibold))
                                        Text(item.timestamp)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }

                                    Spacer()

                                    Text(item.status)
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(statusColor(item.status))
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(statusColor(item.status).opacity(0.14))
                                        .clipShape(RoundedRectangle(cornerRadius: 6))

                                    Image(systemName: "chevron.right")
                                        .foregroundStyle(.secondary)
                                }
                                .padding(12)
                                .background(.thinMaterial)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
        .padding(22)
        .navigationTitle("History")
    }

    private func statusColor(_ status: String) -> Color {
        switch status.lowercased() {
        case "completed", "complete", "success":
            return .green
        case "cancelled", "canceled":
            return .orange
        case "failed", "error":
            return .red
        case "running", "started":
            return .blue
        default:
            return .secondary
        }
    }
}
