// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PromptPressureMac",
    defaultLocalization: "en",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .library(name: "PromptPressureCore", targets: ["PromptPressureCore"]),
        .executable(name: "PromptPressure", targets: ["PromptPressureApp"]),
        .executable(name: "PromptPressureChecks", targets: ["PromptPressureChecks"])
    ],
    targets: [
        .target(
            name: "PromptPressureCore",
            path: "MacApp/Sources/PromptPressureCore",
            linkerSettings: [
                .linkedFramework("AppKit"),
                .linkedFramework("Security")
            ]
        ),
        .executableTarget(
            name: "PromptPressureApp",
            dependencies: ["PromptPressureCore"],
            path: "MacApp/Sources/PromptPressureApp",
            linkerSettings: [
                .linkedFramework("AppKit")
            ]
        ),
        .executableTarget(
            name: "PromptPressureChecks",
            dependencies: ["PromptPressureCore"],
            path: "MacApp/Checks"
        )
    ]
)
