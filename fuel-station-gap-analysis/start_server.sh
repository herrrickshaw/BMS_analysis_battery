#!/bin/bash
# Simple server launcher for Petrol Station Gap Analysis

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║      Fuel Station Gap Analysis — Starting Local Server         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if Python is available
if command -v python3 &> /dev/null; then
    PORT=8000
    echo "✓ Starting Python HTTP server on port $PORT..."
    echo ""
    echo "📍 Open your browser and visit:"
    echo "   http://localhost:$PORT"
    echo ""
    echo "Press Ctrl+C to stop the server"
    echo ""
    python3 -m http.server $PORT
elif command -v python &> /dev/null; then
    PORT=8000
    echo "✓ Starting Python HTTP server on port $PORT..."
    echo ""
    echo "📍 Open your browser and visit:"
    echo "   http://localhost:$PORT"
    echo ""
    echo "Press Ctrl+C to stop the server"
    echo ""
    python -m SimpleHTTPServer $PORT
else
    echo "❌ Python is not installed. Please install Python to run this server."
    exit 1
fi
