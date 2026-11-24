#!/usr/bin/env bash
# Boots a full XFCE Linux desktop reachable from the browser via noVNC on port 6080.
# Usage: bash scripts/desktop.sh   (then open the forwarded port 6080 and click vnc.html)
set -e
export DEBIAN_FRONTEND=noninteractive

echo "[*] Installing desktop stack (first run takes a few minutes)..."
apt-get update
apt-get install -y --no-install-recommends xfce4 xfce4-terminal tigervnc-standalone-server novnc websockify chromium

mkdir -p ~/.vnc
echo -n "${VNC_PASSWORD:-hacktheplanet}" | vncpasswd -f > ~/.vnc/passwd
chmod 600 ~/.vnc/passwd

cat > ~/.vnc/xstartup <<'EOF'
#!/bin/sh
unset SESSION_MANAGER
exec startxfce4
EOF
chmod +x ~/.vnc/xstartup

vncserver :1 -geometry 1600x900 -localhost yes
pkill websockify 2>/dev/null || true
websockify -D --web=/usr/share/novnc/ 6080 localhost:5901

echo
echo "[OK] Desktop is live. Open forwarded port 6080 and append /vnc.html"
echo "     Password: ${VNC_PASSWORD:-hacktheplanet} (override with the VNC_PASSWORD env var)"
