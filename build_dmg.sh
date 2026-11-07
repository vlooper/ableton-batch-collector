#!/bin/bash
# ─────────────────────────────────────────────────────
# 📦 Build Ableton Batch Collector as macOS .app + .dmg
# ─────────────────────────────────────────────────────
# No dependencies needed — uses system tools only.
#
# Usage:
#   bash build_dmg.sh
#
# Output:
#   dist/Ableton Batch Collector.dmg
# ─────────────────────────────────────────────────────

set -e

APP_NAME="Ableton Batch Collector"
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
echo "  [4/5] Generating app icon..."

# Create a simple icon using Python (renders an emoji-style icon)
python3 - << 'ICONSCRIPT'
import struct, zlib, os, sys

# We'll create a simple 256x256 PNG icon
# Box emoji style: orange rounded square with white package lines
SIZE = 256
pixels = []

for y in range(SIZE):
    row = []
    for x in range(SIZE):
        # Normalized coords
        nx = x / SIZE
        ny = y / SIZE
        
        # Rounded rectangle check
        cx, cy = abs(nx - 0.5), abs(ny - 0.5)
        in_rect = cx < 0.38 and cy < 0.38
        
        # Round corners
        corner_r = 0.1
        if cx > 0.38 - corner_r and cy > 0.38 - corner_r:
            dx = cx - (0.38 - corner_r)
            dy = cy - (0.38 - corner_r)
            in_rect = (dx*dx + dy*dy) < corner_r * corner_r
        
        if in_rect:
            # Orange gradient background
            r = int(255 - ny * 30)
            g = int(107 - ny * 20)
            b = int(74 - ny * 15)
            
            # White cross/package lines
            is_line = False
            # Horizontal middle line
            if abs(ny - 0.5) < 0.008:
                is_line = True
            # Vertical middle line
            if abs(nx - 0.5) < 0.008:
                is_line = True
            # Top flap lines
            if ny < 0.5 and ny > 0.35:
                # Left flap
                slope_l = (ny - 0.35) / (nx - 0.25 + 0.001)
                if abs(slope_l - 0.6) < 0.08 and nx < 0.5:
                    is_line = True
                # Right flap
                slope_r = (ny - 0.35) / (0.75 - nx + 0.001)
                if abs(slope_r - 0.6) < 0.08 and nx > 0.5:
                    is_line = True
            
            if is_line:
                r, g, b = 255, 255, 255
            
            row.extend([r, g, b, 255])
        else:
            row.extend([0, 0, 0, 0])
    pixels.append(bytes(row))

# Write PNG
def write_png(filename, width, height, rows):
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    
    raw = b''
    for row in rows:
        raw += b'\x00' + row
    
    with open(filename, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)))
        f.write(chunk(b'IDAT', zlib.compress(raw)))
        f.write(chunk(b'IEND', b''))

dist = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else '.'
icon_dir = sys.argv[1] if len(sys.argv) > 1 else 'dist'
os.makedirs(f'{icon_dir}/icon.iconset', exist_ok=True)

for size in [16, 32, 64, 128, 256]:
    # Simple resize by nearest neighbor
    resized = []
    for y in range(size):
        row = bytearray()
        sy = int(y * SIZE / size)
        for x in range(size):
            sx = int(x * SIZE / size)
            offset = sx * 4
            row.extend(pixels[sy][offset:offset+4])
        resized.append(bytes(row))
    
    write_png(f'{icon_dir}/icon.iconset/icon_{size}x{size}.png', size, size, resized)
    if size <= 128:
        s2 = size * 2
        resized2 = []
        for y in range(s2):
            row = bytearray()
            sy = int(y * SIZE / s2)
            for x in range(s2):
                sx = int(x * SIZE / s2)
                offset = sx * 4
                row.extend(pixels[sy][offset:offset+4])
            resized2.append(bytes(row))
        write_png(f'{icon_dir}/icon.iconset/icon_{size}x{size}@2x.png', s2, s2, resized2)

print("  Icon PNGs generated.")
ICONSCRIPT

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
