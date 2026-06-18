import SwiftUI
import PromptPressureCore

extension AppJobStatus {
    var workbenchColor: Color {
        switch self {
        case .completed:
            Color.green
        case .failed:
            Color.red
        case .cancelled:
            Color.orange
        case .queued:
            Color.secondary
        case .running, .finalizing:
            Color.blue
        }
    }

    var workbenchIcon: String {
        switch self {
        case .queued:
            "clock"
        case .running:
            "play.fill"
        case .finalizing:
            "hourglass"
        case .completed:
            "checkmark.circle.fill"
        case .failed:
            "xmark.octagon.fill"
        case .cancelled:
            "stop.circle.fill"
        }
    }
}

struct JobStatusChip: View {
    let status: AppJobStatus

    var body: some View {
        Label(status.displayName, systemImage: status.workbenchIcon)
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(status.workbenchColor.opacity(0.16))
            .foregroundStyle(status.workbenchColor)
            .clipShape(RoundedRectangle(cornerRadius: 7))
    }
}

struct JobProgressLine: View {
    let progress: AppJobProgress

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            if progress.total > 0 {
                ProgressView(value: Double(progress.completed), total: Double(progress.total))
                HStack {
                    Text("\(progress.completed) of \(progress.total)")
                    Spacer()
                    Text(percentText)
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            } else if let current = progress.current, !current.isEmpty {
                Text(current)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            } else {
                Text("No progress reported yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var percentText: String {
        guard progress.total > 0 else { return "0%" }
        let ratio = min(max(Double(progress.completed) / Double(progress.total), 0), 1)
        return "\(Int((ratio * 100).rounded()))%"
    }
}

struct JobSummaryRows: View {
    let summary: [String: JSONValue]

    var body: some View {
        if !summary.isEmpty {
            Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 6) {
                ForEach(summary.keys.sorted(), id: \.self) { key in
                    GridRow {
                        Text(key)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(summary[key]?.description ?? "")
                            .font(.caption.weight(.semibold))
                            .lineLimit(1)
                            .textSelection(.enabled)
                    }
                }
            }
        }
    }
}
