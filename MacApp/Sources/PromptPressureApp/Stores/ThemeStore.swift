import Foundation
import SwiftUI
import AppKit
import PromptPressureCore

@MainActor
final class ThemeStore: ObservableObject {
    @Published var selectedThemeID = "signal-dark"
    @Published var accentHex = "#5269FF"
    @Published var density: ThemeDensity = .comfortable
    @Published var chartIntensity: ChartIntensity = .standard
    @Published private(set) var builtIn: [ThemePreset] = ThemeStore.defaultThemes
    @Published private(set) var custom: [ThemePreset] = []
    @Published private(set) var invalid: [InvalidTheme] = []

    private let paths: ApplicationSupportPaths
    private let loader = ThemeFileLoader()

    init(paths: ApplicationSupportPaths) {
        self.paths = paths
        loadLocalThemes()
    }

    static let defaultThemes: [ThemePreset] = [
        ThemePreset(schemaVersion: 1, id: "signal-dark", name: "Signal Dark", base: .dark, accent: "#5269FF", density: .comfortable, chartIntensity: .standard, surfaces: nil, text: nil, source: "built-in", path: nil),
        ThemePreset(schemaVersion: 1, id: "ember", name: "Ember", base: .dark, accent: "#F05D7F", density: .comfortable, chartIntensity: .high, surfaces: nil, text: nil, source: "built-in", path: nil),
        ThemePreset(schemaVersion: 1, id: "paper-lab", name: "Paper Lab", base: .light, accent: "#1F7A5C", density: .comfortable, chartIntensity: .standard, surfaces: nil, text: nil, source: "built-in", path: nil),
        ThemePreset(schemaVersion: 1, id: "mono-console", name: "Mono Console", base: .dark, accent: "#D1D5DB", density: .compact, chartIntensity: .muted, surfaces: nil, text: nil, source: "built-in", path: nil)
    ]

    var allThemes: [ThemePreset] {
        builtIn + custom
    }

    var selectedTheme: ThemePreset {
        allThemes.first { $0.id == selectedThemeID } ?? builtIn[0]
    }

    var accentColor: Color {
        Color(hex: accentHex) ?? Color(hex: selectedTheme.accent) ?? .blue
    }

    var panelSpacing: CGFloat {
        switch density {
        case .comfortable: 14
        case .compact: 10
        case .dense: 7
        }
    }

    func select(_ theme: ThemePreset) {
        selectedThemeID = theme.id
        accentHex = theme.accent
        density = theme.density
        chartIntensity = theme.chartIntensity
    }

    func loadLocalThemes() {
        let result = loader.loadThemes(from: paths.themes)
        custom = result.themes
        invalid = result.invalid
    }

    func revealThemesFolder() {
        NSWorkspace.shared.activateFileViewerSelecting([paths.themes])
    }
}
