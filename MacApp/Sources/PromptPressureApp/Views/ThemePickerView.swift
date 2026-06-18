import SwiftUI
import PromptPressureCore

struct ThemePickerView: View {
    @EnvironmentObject private var themeStore: ThemeStore
    private let driftColors = DriftColors()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Themes")
                            .font(.title2.weight(.semibold))
                        Text("Presets plus accent controls. Drift semantics stay locked.")
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button {
                        themeStore.revealThemesFolder()
                    } label: {
                        Label("Themes Folder", systemImage: "folder")
                    }
                    Button {
                        themeStore.loadLocalThemes()
                    } label: {
                        Label("Reload", systemImage: "arrow.clockwise")
                    }
                }

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 14)], spacing: 14) {
                    ForEach(themeStore.allThemes) { theme in
                        ThemeCard(theme: theme, selected: theme.id == themeStore.selectedThemeID)
                            .onTapGesture {
                                themeStore.select(theme)
                            }
                    }
                }

                controls

                if !themeStore.invalid.isEmpty {
                    invalidThemes
                }
            }
            .padding(22)
        }
        .navigationTitle("Themes")
    }

    private var controls: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("customization")
                .font(.headline)
            HStack {
                ColorSwatch(color: themeStore.accentColor)
                TextField("Accent #RRGGBB", text: $themeStore.accentHex)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 140)
                Picker("Density", selection: $themeStore.density) {
                    ForEach(ThemeDensity.allCases, id: \.self) { density in
                        Text(density.rawValue.capitalized).tag(density)
                    }
                }
                Picker("Charts", selection: $themeStore.chartIntensity) {
                    ForEach(ChartIntensity.allCases, id: \.self) { intensity in
                        Text(intensity.rawValue.capitalized).tag(intensity)
                    }
                }
            }

            HStack(spacing: 10) {
                SemanticChip(label: "hold", color: driftColors.hold)
                SemanticChip(label: "partial", color: driftColors.partial)
                SemanticChip(label: "drift", color: driftColors.drift)
            }
        }
        .padding(16)
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private var invalidThemes: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("invalid custom themes")
                .font(.headline)
            ForEach(themeStore.invalid) { item in
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.name)
                        .font(.subheadline.weight(.semibold))
                    Text(item.error)
                        .foregroundStyle(.red)
                        .font(.caption)
                }
                Divider()
            }
        }
        .padding(16)
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

private struct ThemeCard: View {
    let theme: ThemePreset
    let selected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ZStack(alignment: .bottomLeading) {
                RoundedRectangle(cornerRadius: 8)
                    .fill(background)
                    .frame(height: 96)
                HStack(spacing: 6) {
                    Rectangle().fill(Color(hex: theme.accent) ?? .blue).frame(width: 50, height: 22)
                    Rectangle().fill(Color(hex: "#20B7A8") ?? .mint).frame(width: 34, height: 22)
                    Rectangle().fill(Color(hex: "#F0B24A") ?? .orange).frame(width: 34, height: 22)
                    Rectangle().fill(Color(hex: "#F05D7F") ?? .pink).frame(width: 34, height: 22)
                }
                .padding(10)
            }

            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(theme.name)
                        .font(.headline)
                    Text("\(theme.base.rawValue) · \(theme.density.rawValue)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if selected {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                }
            }
        }
        .padding(12)
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay {
            RoundedRectangle(cornerRadius: 8)
                .stroke(selected ? (Color(hex: theme.accent) ?? .blue) : .clear, lineWidth: 2)
        }
    }

    private var background: Color {
        switch theme.base {
        case .dark: Color(hex: "#222631") ?? .black
        case .light: Color(hex: "#F5F1EA") ?? .white
        case .system: .secondary.opacity(0.2)
        }
    }
}

private struct ColorSwatch: View {
    let color: Color

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 24, height: 24)
            .overlay(Circle().stroke(.white.opacity(0.5), lineWidth: 1))
    }
}

private struct SemanticChip: View {
    let label: String
    let color: Color

    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 10, height: 10)
            Text(label)
                .font(.caption.weight(.medium))
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(.thinMaterial)
        .clipShape(Capsule())
    }
}
