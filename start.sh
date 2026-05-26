#!/bin/bash
# Lagerstöðukerfi – ræsingarskript
cd "$(dirname "$0")"

echo ""
echo "  📦  Lagerstöðukerfi"
echo "  ─────────────────────────────"

# Install Flask if missing
if ! python3 -c "import flask" 2>/dev/null; then
    echo "  ⬇️   Setur upp Flask..."
    pip3 install flask --quiet
fi

echo "  ✅  Keyrir á http://localhost:5001"
echo "  📡  Aðrir á sama neti geta opnað:"
python3 -c "import socket; s=socket.socket(); s.connect(('8.8.8.8',80)); print('      http://'+s.getsockname()[0]+':5001'); s.close()" 2>/dev/null || true
echo "  ─────────────────────────────"
echo "  Ýttu á Ctrl+C til að hætta"
echo ""

python3 app.py
