#!/bin/bash
# Lumeway iOS Project Setup
# Run this script to generate the Xcode project

set -e

echo "=== Lumeway iOS Setup ==="
echo ""

cd "$(dirname "$0")/Lumeway"

# Check for xcodegen
if ! command -v xcodegen &> /dev/null; then
    echo "Installing XcodeGen (one-time setup)..."
    brew install xcodegen
    echo ""
fi

echo "Generating Xcode project..."
xcodegen generate

echo ""
echo "Opening project in Xcode..."
open Lumeway.xcodeproj

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. In Xcode, select your Team under Signing & Capabilities"
echo "  2. Connect your iPhone via USB"
echo "  3. Select your phone as the build target"
echo "  4. Press Cmd+R to build and run"
echo ""
echo "For TestFlight:"
echo "  1. Product > Archive"
echo "  2. Distribute App > App Store Connect"
echo "  3. Go to appstoreconnect.apple.com > TestFlight"
echo "  4. Add yourself as a tester"
echo ""
