#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

show_usage() {
    echo "Usage: $0 [option]"
    echo "Options:"
    echo "  analyze    - Analyze disk usage by directory"
    echo "  largest    - Find largest files on disk"
    echo "  caches     - Show cache sizes"
    echo "  cleanup    - Clean caches and temp files"
    echo "  duplicate  - Find potential duplicate files"
    echo "  all        - Run all analyses"
    echo ""
}

# Analyze disk usage
analyze_disk() {
    echo -e "${BLUE}📊 DISK USAGE BY DIRECTORY${NC}\n"
    du -sh ~/* 2>/dev/null | sort -hr | head -20
    echo ""
}

# Find largest files
largest_files() {
    echo -e "${BLUE}📁 TOP 30 LARGEST FILES${NC}\n"
    find ~ -type f -size +100M 2>/dev/null | xargs ls -lhS | awk '{print $5, $9}' | head -30
    echo ""
}

# Analyze cache sizes
analyze_caches() {
    echo -e "${BLUE}💾 CACHE SIZES${NC}\n"

    echo -e "${YELLOW}Browser Caches:${NC}"
    du -sh ~/Library/Caches/Google/Chrome 2>/dev/null | awk '{print "  Chrome: " $1}'
    du -sh ~/Library/Caches/Firefox 2>/dev/null | awk '{print "  Firefox: " $1}'
    du -sh ~/Library/Safari 2>/dev/null | awk '{print "  Safari: " $1}'

    echo -e "\n${YELLOW}Application Caches:${NC}"
    du -sh ~/Library/Caches 2>/dev/null | awk '{print "  Total ~/Library/Caches: " $1}'

    echo -e "\n${YELLOW}Package Manager Caches:${NC}"
    du -sh ~/Library/Caches/pip 2>/dev/null | awk '{print "  pip: " $1}'
    du -sh ~/.npm 2>/dev/null | awk '{print "  npm: " $1}'
    du -sh ~/Library/Caches/Homebrew 2>/dev/null | awk '{print "  Homebrew: " $1}'

    echo -e "\n${YELLOW}Temporary Files:${NC}"
    du -sh /tmp 2>/dev/null | awk '{print "  /tmp: " $1}'
    du -sh /var/tmp 2>/dev/null | awk '{print "  /var/tmp: " $1}'

    echo -e "\n${YELLOW}Xcode (if installed):${NC}"
    du -sh ~/Library/Developer/Xcode/DerivedData 2>/dev/null | awk '{print "  DerivedData: " $1}'
    du -sh ~/Library/Developer/Xcode/Archives 2>/dev/null | awk '{print "  Archives: " $1}'

    echo -e "\n${YELLOW}Downloads:${NC}"
    du -sh ~/Downloads 2>/dev/null | awk '{print "  Downloads: " $1}'

    echo ""
}

# Find duplicate files
find_duplicates() {
    echo -e "${BLUE}🔍 SCANNING FOR DUPLICATE FILES${NC}\n"
    echo "This may take a while for large directories..."

    # Look for duplicates in common locations
    for dir in ~/Downloads ~/Documents ~/Desktop; do
        if [ -d "$dir" ]; then
            echo -e "\n${YELLOW}Checking $dir:${NC}"
            find "$dir" -type f -size +1M 2>/dev/null | \
            while read file; do
                md5sum "$file" 2>/dev/null
            done | sort | uniq -w32 -D --check-chars=32 | while read sum file; do
                echo "  Potential duplicate: $(basename "$file") ($(du -h "$file" | cut -f1))"
            done | head -10
        fi
    done
    echo ""
}

# Clean caches and temp files
cleanup() {
    echo -e "${YELLOW}⚠️  CACHE CLEANUP IN PROGRESS...${NC}\n"

    local freed=0

    # Browser caches
    echo "Clearing browser caches..."
    rm -rf ~/Library/Caches/Google/Chrome/* 2>/dev/null
    rm -rf ~/Library/Caches/Firefox/* 2>/dev/null

    # Package manager caches
    echo "Clearing package manager caches..."
    npm cache clean --force 2>/dev/null
    pip cache purge 2>/dev/null
    brew cleanup 2>/dev/null

    # Temporary files
    echo "Clearing temporary files..."
    rm -rf /tmp/* 2>/dev/null
    rm -rf /var/tmp/* 2>/dev/null

    # Xcode derived data (if safe)
    if [ -d ~/Library/Developer/Xcode/DerivedData ]; then
        read -p "Clear Xcode DerivedData? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf ~/Library/Developer/Xcode/DerivedData/* 2>/dev/null
        fi
    fi

    # Empty trash
    echo "Emptying trash..."
    rm -rf ~/.Trash/* 2>/dev/null

    echo -e "${GREEN}✅ Cleanup complete!${NC}\n"

    # Show freed space
    echo -e "${BLUE}Current cache sizes after cleanup:${NC}"
    du -sh ~/Library/Caches 2>/dev/null | awk '{print "~/Library/Caches: " $1}'
    du -sh /tmp 2>/dev/null | awk '{print "/tmp: " $1}'
    echo ""
}

# Run all analyses
run_all() {
    analyze_disk
    largest_files
    analyze_caches
    find_duplicates
}

# Main script
if [ $# -eq 0 ]; then
    show_usage
    exit 0
fi

case "$1" in
    analyze)
        analyze_disk
        ;;
    largest)
        largest_files
        ;;
    caches)
        analyze_caches
        ;;
    cleanup)
        cleanup
        ;;
    duplicate)
        find_duplicates
        ;;
    all)
        run_all
        ;;
    *)
        echo "Unknown option: $1"
        show_usage
        exit 1
        ;;
esac
