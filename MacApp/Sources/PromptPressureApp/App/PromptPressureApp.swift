import SwiftUI
import AppKit
import PromptPressureCore

final class PromptPressureAppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }
}

@main
struct PromptPressureApp: App {
    @NSApplicationDelegateAdaptor(PromptPressureAppDelegate.self) private var appDelegate
    @StateObject private var store = AppStore()

    var body: some Scene {
        WindowGroup("PromptPressure", id: "main") {
            ContentView()
                .environmentObject(store)
                .environmentObject(store.themeStore)
                .frame(minWidth: 1100, minHeight: 720)
                .task {
                    await store.bootstrap()
                }
        }
        .commands {
            CommandGroup(after: .newItem) {
                Button("Run Evaluation") {
                    Task { await store.startRun() }
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("Cancel Run") {
                    Task { await store.cancelRun() }
                }
                .keyboardShortcut(".", modifiers: [.command])
                .disabled(!store.isRunning)
            }
        }

        Settings {
            SettingsView()
                .environmentObject(store)
                .environmentObject(store.credentialStore)
                .environmentObject(store.themeStore)
                .frame(width: 640, height: 460)
        }
    }
}
