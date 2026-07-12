#!/bin/bash

# Rewards Optimization Analysis - Startup Script

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🎯 Rewards Optimization Analysis${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install -q yfinance pandas numpy

# Run analysis
echo -e "${GREEN}✓ Running 5-year rewards analysis...${NC}"
echo ""

python rewards_optimization.py --output rewards_analysis.json --report REWARDS_ANALYSIS_REPORT.txt

# Display results
echo ""
echo -e "${GREEN}✓ Analysis complete!${NC}"
echo ""
echo -e "${YELLOW}📊 Results Generated:${NC}"
echo "  • rewards_analysis.json        (Full analysis in JSON)"
echo "  • REWARDS_ANALYSIS_REPORT.txt  (Detailed report)"
echo ""
echo -e "${YELLOW}📈 Dashboard:${NC}"
echo "  Open: file://$(pwd)/rewards_dashboard.html"
echo ""
echo -e "${YELLOW}📚 Documentation:${NC}"
echo "  See: REWARDS_OPTIMIZATION_GUIDE.md"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
