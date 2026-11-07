#!/bin/bash
# ─────────────────────────────────────────────────────
# 📦 Build Ableton Batch - Collect All and Save as macOS .app + .dmg
# ─────────────────────────────────────────────────────
# No dependencies needed — uses system tools only.
#
# Usage:
#   bash build_dmg.sh
#
# Output:
#   dist/Ableton Batch - Collect All and Save.dmg
# ─────────────────────────────────────────────────────

set -e

APP_NAME="Ableton Batch - Collect All and Save"
BUNDLE_ID="com.vlooper.ableton-batch-collector"
VERSION="1.2.0"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"
APP_DIR="$DIST_DIR/$APP_NAME.app"
DMG_NAME="$APP_NAME.dmg"

echo ""
echo "  📦 Building $APP_NAME v$VERSION"
echo "  ─────────────────────────────────────"
echo ""

# ── Clean ──
rm -rf "$DIST_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# ── Copy the Python script ──
echo "  [1/5] Copying app script..."
cp "$SCRIPT_DIR/ableton_batch_collector.py" "$APP_DIR/Contents/Resources/app.py"

# ── Create the launcher ──
echo "  [2/5] Creating launcher..."
cat > "$APP_DIR/Contents/MacOS/launcher" << 'LAUNCHER'
#!/bin/bash
DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
# Use system Python 3
exec /usr/bin/python3 "$DIR/app.py"
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/launcher"

# ── Create Info.plist ──
echo "  [3/5] Creating Info.plist..."
cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>$BUNDLE_ID</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

# ── Create app icon ──
echo "  [4/5] Converting app icon..."

# Use the app_icon.png from the repo
if [ -f "$SCRIPT_DIR/app_icon.png" ]; then
    mkdir -p "$DIST_DIR/icon.iconset"
    # Use sips to resize for each icon size
    for size in 16 32 64 128 256 512; do
        sips -z $size $size "$SCRIPT_DIR/app_icon.png" --out "$DIST_DIR/icon.iconset/icon_${size}x${size}.png" > /dev/null 2>&1
    done
    for size in 16 32 64 128 256; do
        s2=$((size * 2))
        sips -z $s2 $s2 "$SCRIPT_DIR/app_icon.png" --out "$DIST_DIR/icon.iconset/icon_${size}x${size}@2x.png" > /dev/null 2>&1
    done
    echo "  Icon PNGs generated from app_icon.png"
else
    echo "  Warning: app_icon.png not found, using default"
fi

# Convert iconset to icns
if [ -d "$DIST_DIR/icon.iconset" ]; then
    iconutil -c icns "$DIST_DIR/icon.iconset" -o "$APP_DIR/Contents/Resources/AppIcon.icns" 2>/dev/null && \
        echo "  Icon created." || echo "  (Icon generation skipped, using default)"
    rm -rf "$DIST_DIR/icon.iconset"
fi

# ── Create DMG ──
echo "  [5/5] Creating DMG..."

# Create a temporary DMG directory with the app and an alias to Applications
DMG_TEMP="$DIST_DIR/dmg_temp"
rm -rf "$DMG_TEMP"
mkdir -p "$DMG_TEMP"
cp -R "$APP_DIR" "$DMG_TEMP/"
ln -s /Applications "$DMG_TEMP/Applications"

# Create DMG
rm -f "$DIST_DIR/$DMG_NAME"
hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$DMG_TEMP" \
    -ov \
    -format UDZO \
    "$DIST_DIR/$DMG_NAME" \
    > /dev/null 2>&1

rm -rf "$DMG_TEMP"

echo ""
if [ -f "$DIST_DIR/$DMG_NAME" ]; then
    SIZE=$(du -h "$DIST_DIR/$DMG_NAME" | cut -f1 | tr -d ' ')
    echo "  ✅ Done!"
    echo ""
    echo "  📦 DMG:  dist/$DMG_NAME ($SIZE)"
    echo "  📱 App:  dist/$APP_NAME.app"
    echo ""
    echo "  To install:"
    echo "    1. Open the DMG"
    echo "    2. Drag the app to Applications"
    echo "    3. Done!"
    echo ""
    echo "  ⚠️  First launch: Right-click → Open (macOS Gatekeeper)"
    echo ""
    
    # Open the dist folder
    open "$DIST_DIR"
else
    echo "  ❌ DMG creation failed. But your .app is at:"
    echo "     dist/$APP_NAME.app"
fi
