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
    dependencies: [
        .package(url: "https://github.com/phosphor-icons/swift", from: "2.1.0"),
    ],
    targets: [
        .target(name: "PiaMobileClient"),
        .executableTarget(name: "PiaApp", dependencies: [
            "PiaMobileClient",
            .product(name: "PhosphorSwift", package: "swift"),
        ]),
        .testTarget(name: "PiaMobileClientTests", dependencies: ["PiaMobileClient"]),
    ]
)
