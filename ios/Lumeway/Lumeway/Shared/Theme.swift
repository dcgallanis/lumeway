import SwiftUI
import UIKit

// MARK: - Colors (Sunrise palette)
extension Color {
    static let lumeCream = Color(hex: "FAF7F2")
    static let lumeWarmWhite = Color(hex: "FDFCFA")
    static let lumeText = Color(hex: "2C3E50")
    static let lumeMuted = Color(hex: "6B7B8D")
    static let lumeNavy = Color(hex: "2C4A5E")
    static let lumeGold = Color(hex: "B8977E")
    static let lumeAccent = Color(hex: "C4704E")
    static let lumeAccentLight = Color(hex: "D4896C")
    static let lumeBorder = Color(hex: "E8E0D6")
    static let lumeGreen = Color(hex: "4A7C59")
    static let lumeBlush = Color(hex: "E8CFC0")
    static let lumeSage = Color(hex: "8BA888")

    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let r, g, b: UInt64
        (r, g, b) = ((int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: 1
        )
    }
}

// MARK: - Typography

extension Font {
    // DM Serif Display — bold, fun heading font
    static let lumeDisplayLarge = Font.custom("DMSerifDisplay-Regular", size: 34, relativeTo: .largeTitle)
    static let lumeDisplayMedium = Font.custom("DMSerifDisplay-Regular", size: 26, relativeTo: .title2)
    static let lumeDisplaySmall = Font.custom("DMSerifDisplay-Regular", size: 20, relativeTo: .headline)
    static let lumeDisplayItalic = Font.custom("DMSerifDisplay-Italic", size: 26, relativeTo: .title2)

    // Libre Baskerville — elegant serif for subheadings
    static let lumeHeadingLarge = Font.custom("LibreBaskerville-Regular", size: 32, relativeTo: .largeTitle)
    static let lumeHeadingMedium = Font.custom("LibreBaskerville-Regular", size: 24, relativeTo: .title2)
    static let lumeHeadingSmall = Font.custom("LibreBaskerville-Regular", size: 18, relativeTo: .headline)
    static let lumeHeadingItalic = Font.custom("LibreBaskerville-Italic", size: 24, relativeTo: .title2)

    // Plus Jakarta Sans — clean sans-serif body
    static let lumeBody = Font.custom("PlusJakartaSans-Regular", size: 15, relativeTo: .body)
    static let lumeBodyLight = Font.custom("PlusJakartaSans-Light", size: 15, relativeTo: .body)
    static let lumeBodyMedium = Font.custom("PlusJakartaSans-Medium", size: 15, relativeTo: .body)
    static let lumeBodySemibold = Font.custom("PlusJakartaSans-SemiBold", size: 15, relativeTo: .body)
    static let lumeCaption = Font.custom("PlusJakartaSans-Regular", size: 13, relativeTo: .caption)
    static let lumeCaptionLight = Font.custom("PlusJakartaSans-Light", size: 13, relativeTo: .caption)
    static let lumeSmall = Font.custom("PlusJakartaSans-Regular", size: 11, relativeTo: .caption2)
    static let lumeLogoText = Font.custom("PlusJakartaSans-SemiBold", size: 16, relativeTo: .headline)
}

// Debug: print all available custom fonts — call once to verify font names
func debugPrintFonts() {
    for family in UIFont.familyNames.sorted() {
        let names = UIFont.fontNames(forFamilyName: family)
        if !names.isEmpty && (family.contains("Libre") || family.contains("Jakarta") || family.contains("DM") || family.contains("Serif")) {
            print("Font family: \(family)")
            for name in names {
                print("  - \(name)")
            }
        }
    }
}

// MARK: - Shared Component Styles
struct LumeCardStyle: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(20)
            .background(Color.lumeWarmWhite)
            .cornerRadius(16)
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(Color.lumeBorder, lineWidth: 1)
            )
    }
}

struct LumePrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.lumeBodySemibold)
            .foregroundColor(.white)
            .padding(.horizontal, 24)
            .padding(.vertical, 14)
            .background(
                RoundedRectangle(cornerRadius: 28)
                    .fill(configuration.isPressed ? Color.lumeAccentLight : Color.lumeAccent)
            )
    }
}

struct LumeSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.lumeBodyMedium)
            .foregroundColor(.lumeText)
            .padding(.horizontal, 24)
            .padding(.vertical, 14)
            .background(
                RoundedRectangle(cornerRadius: 28)
                    .stroke(Color.lumeBorder, lineWidth: 1.5)
            )
    }
}

extension View {
    func lumeCard() -> some View {
        modifier(LumeCardStyle())
    }
}
