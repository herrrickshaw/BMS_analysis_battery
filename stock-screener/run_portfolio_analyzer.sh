#!/bin/bash

# Portfolio Analyzer - Startup Script
# Starts both the FastAPI backend and opens the web dashboard

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}📊 Portfolio Analyzer - Startup${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate venv
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Install dependencies
echo -e "${YELLOW}Installing/updating dependencies...${NC}"
pip install -q -r portfolio_requirements.txt

# Start backend
echo -e "${GREEN}✓ Starting FastAPI backend on http://127.0.0.1:8001${NC}"
python portfolio_api.py &
BACKEND_PID=$!

# Wait for backend to start
sleep 2

# Open dashboard
echo -e "${GREEN}✓ Opening web dashboard at http://127.0.0.1:8001 in browser...${NC}"
echo ""
echo -e "${BLUE}Dashboard URL: file://$(pwd)/portfolio_dashboard.html${NC}"
echo ""
echo -e "${YELLOW}To use the dashboard:${NC}"
echo "  1. Open: file://$(pwd)/portfolio_dashboard.html in your browser"
echo "  2. Click 'Load Sample' to test with sample data"
echo "  3. Or upload your own CSV/Excel portfolio file"
echo ""
echo -e "${YELLOW}Portfolio file format (CSV/Excel):${NC}"
echo "  Columns: ticker, quantity, purchase_price, purchase_date, market, sector (optional)"
echo "  Example:"
echo "    ticker,quantity,purchase_price,purchase_date,market,sector"
echo "    HDFCBANK,10,1500,2023-01-15,india,banking"
echo "    AAPL,5,180,2023-11-10,us,tech"
echo ""
echo -e "${YELLOW}API Endpoints:${NC}"
echo "  POST   /portfolio/upload                - Upload portfolio file"
echo "  POST   /portfolio/load-sample          - Load sample portfolio"
echo "  GET    /portfolio/metrics              - Portfolio metrics"
echo "  GET    /portfolio/holdings             - Detailed holdings"
echo "  GET    /portfolio/quality              - Position quality scores"
echo "  GET    /portfolio/rebalancing          - Rebalancing opportunities"
echo "  GET    /portfolio/sectors              - Sector allocation"
echo "  GET    /portfolio/alerts               - Portfolio alerts"
echo "  GET    /portfolio/report               - Complete report (JSON)"
echo ""
echo -e "${YELLOW}Stop backend: Press Ctrl+C${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Wait for backend process
wait $BACKEND_PID
