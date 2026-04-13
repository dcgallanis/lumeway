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
// Cormorant Garamond — ALL headers, titles, display text
// Montserrat — ALL body, UI, captions, labels

extension Font {
    // Cormorant Garamond — large display headings
    static let lumeDisplayLarge = Font.custom("CormorantGaramond-Bold", size: 36, relativeTo: .largeTitle)
    static let lumeDisplayMedium = Font.custom("CormorantGaramond-SemiBold", size: 28, relativeTo: .title2)
    static let lumeDisplaySmall = Font.custom("CormorantGaramond-SemiBold", size: 22, relativeTo: .headline)
    static let lumeDisplayItalic = Font.custom("CormorantGaramond-Italic", size: 28, relativeTo: .title2)

    // Montserrat — section headings & subheadings
    static let lumeHeadingLarge = Font.custom("CormorantGaramond-SemiBold", size: 30, relativeTo: .largeTitle)
    static let lumeHeadingMedium = Font.custom("Montserrat-SemiBold", size: 20, relativeTo: .title2)
    static let lumeHeadingSmall = Font.custom("Montserrat-Medium", size: 17, relativeTo: .headline)
    static let lumeHeadingItalic = Font.custom("Montserrat-Medium", size: 20, relativeTo: .title2)

    // Montserrat — section labels
    static let lumeSectionTitle = Font.custom("Montserrat-SemiBold", size: 14, relativeTo: .subheadline)
    static let lumeSectionTitleBold = Font.custom("Montserrat-Bold", size: 14, relativeTo: .subheadline)

    // Montserrat — body text
    static let lumeBody = Font.custom("Montserrat-Regular", size: 15, relativeTo: .body)
    static let lumeBodyLight = Font.custom("Montserrat-Light", size: 15, relativeTo: .body)
    static let lumeBodyMedium = Font.custom("Montserrat-Medium", size: 15, relativeTo: .body)
    static let lumeBodySemibold = Font.custom("Montserrat-SemiBold", size: 15, relativeTo: .body)
    static let lumeCaption = Font.custom("Montserrat-Regular", size: 13, relativeTo: .caption)
    static let lumeCaptionLight = Font.custom("Montserrat-Light", size: 13, relativeTo: .caption)
    static let lumeSmall = Font.custom("Montserrat-Regular", size: 11, relativeTo: .caption2)
    static let lumeLogoText = Font.custom("CormorantGaramond-SemiBold", size: 18, relativeTo: .headline)

    // Cormorant Garamond — accent display for emphasis
    static let lumeAccentSerif = Font.custom("CormorantGaramond-Regular", size: 18, relativeTo: .subheadline)
}

// Debug: print all available custom fonts — call once to verify font names
func debugPrintFonts() {
    for family in UIFont.familyNames.sorted() {
        let names = UIFont.fontNames(forFamilyName: family)
        if !names.isEmpty && (family.contains("Libre") || family.contains("Montserrat") || family.contains("Cormorant")) {
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

// MARK: - Conditional NavigationStack

/// Wraps content in a NavigationStack only when NOT embedded in a parent NavigationStack.
/// Use `isEmbedded: true` when the view is pushed via NavigationLink from Hub or Dashboard.
struct OptionalNavigationStack<Content: View>: View {
    let isEmbedded: Bool
    @ViewBuilder let content: () -> Content

    var body: some View {
        if isEmbedded {
            content()
        } else {
            NavigationStack {
                content()
            }
        }
    }
}

// MARK: - Embedded Back Button (for views with custom color-block headers)

/// A circular back button for views that hide the system navigation bar.
/// Place this in the top-left of the custom header ZStack.
struct EmbeddedBackButton: View {
    @Environment(\.dismiss) var dismiss
    var tint: Color = .white

    var body: some View {
        Button { dismiss() } label: {
            Image(systemName: "chevron.left")
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(tint)
                .padding(9)
                .background(Color.black.opacity(0.18))
                .clipShape(Circle())
        }
    }
}
