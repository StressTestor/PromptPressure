import SwiftUI
import PromptPressureCore

struct OutputDocumentView: View {
    @Environment(\.dismiss) private var dismiss
    let document: OutputDocument

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
                .padding(20)
                .background(.bar)

            Divider()

            ScrollView {
                documentBody
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(24)
            }
            .background(.regularMaterial)
        }
        .frame(minWidth: 780, minHeight: 620)
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text(document.title)
                    .font(.title3.weight(.semibold))
                Text(document.subtitle)
                    .foregroundStyle(.secondary)
                Text(document.sourcePath)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .textSelection(.enabled)
            }

            Spacer()

            Button {
                dismiss()
            } label: {
                Label("Close", systemImage: "xmark")
            }
            .keyboardShortcut(.cancelAction)
        }
    }

    @ViewBuilder
    private var documentBody: some View {
        if let attributed = try? AttributedString(markdown: document.content) {
            Text(attributed)
                .font(.system(.body, design: .default))
                .textSelection(.enabled)
                .lineSpacing(4)
        } else {
            Text(document.content)
                .font(.system(.body, design: document.format == .plainText ? .monospaced : .default))
                .textSelection(.enabled)
                .lineSpacing(4)
        }
    }
}
