#!/bin/bash
# Instala un LaunchAgent para abrir Zoom French Tracker al iniciar sesión.
set -e

APP_PATH="$HOME/Applications/Zoom French Tracker.app"
PLIST="$HOME/Library/LaunchAgents/com.rochag.zoomfrenchtracker.plist"
LABEL="com.rochag.zoomfrenchtracker"

if [ ! -d "$APP_PATH" ]; then
    echo "❌ No encontré la app en: $APP_PATH"
    echo "   Copia primero: cp -r \"dist/Zoom French Tracker.app\" ~/Applications/"
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>$APP_PATH</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "✅ Auto-inicio instalado."
echo "   La app se abrirá automáticamente al iniciar sesión en la Mac."
echo "   Para quitarlo: launchctl unload $PLIST && rm $PLIST"
