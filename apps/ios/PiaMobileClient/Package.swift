// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "PiaMobileClient",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
    ],
    products: [
        .library(name: "PiaMobileClient", targets: ["PiaMobileClient"]),
        .executable(name: "PiaApp", targets: ["PiaApp"]),
    ],
    targets: [
        .target(name: "PiaMobileClient"),
        .executableTarget(name: "PiaApp", dependencies: ["PiaMobileClient"]),
        .testTarget(name: "PiaMobileClientTests", dependencies: ["PiaMobileClient"]),
    ]
)
