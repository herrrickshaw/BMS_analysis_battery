#!/bin/bash

# Interactive storage management menu

show_menu() {
    clear
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "           STORAGE ANALYZER & CLEANUP MENU"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "1. 📊 Analyze disk usage (by directory)"
    echo "2. 📁 Find largest files"
    echo "3. 💾 Show cache sizes"
    echo "4. 🔍 Find duplicate files"
    echo "5. 🧹 Clean caches & temp files"
    echo "6. ⚡ Quick cleanup (no prompts)"
    echo "7. 📈 Full analysis (all options)"
    echo "8. 🚪 Exit"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

analyze_disk() {
    echo ""
    echo "📊 DISK USAGE BY DIRECTORY"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    du -sh ~/* 2>/dev/null | sort -hr | head -20
    echo ""
    read -p "Press Enter to continue..."
}

largest_files() {
    echo ""
    echo "📁 TOP 30 LARGEST FILES"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    find ~ -type f -size +100M 2>/dev/null | xargs ls -lhS 2>/dev/null | awk '{print $5"\t"$9}' | head -30
    echo ""
    read -p "Press Enter to continue..."
}

cache_sizes() {
    echo ""
    echo "💾 CACHE SIZES"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "🌐 Browser Caches:"
    du -sh ~/Library/Caches/Google/Chrome 2>/dev/null || echo "  Chrome: N/A"
    du -sh ~/Library/Caches/Firefox 2>/dev/null || echo "  Firefox: N/A"
    du -sh ~/Library/Safari 2>/dev/null || echo "  Safari: N/A"

    echo ""
    echo "📦 Package Manager Caches:"
    du -sh ~/Library/Caches/pip 2>/dev/null || echo "  pip: N/A"
    du -sh ~/.npm 2>/dev/null || echo "  npm: N/A"
    du -sh ~/Library/Caches/Homebrew 2>/dev/null || echo "  Homebrew: N/A"

    echo ""
    echo "📁 Other Caches:"
    du -sh ~/Library/Caches 2>/dev/null | awk '{print "  Total ~/Library/Caches: "$1}'
    du -sh ~/Downloads 2>/dev/null | awk '{print "  Downloads: "$1}'
    du -sh ~/Library/Developer/Xcode/DerivedData 2>/dev/null || echo "  Xcode DerivedData: N/A"

    echo ""
    echo "🗑️  Trash Size:"
    du -sh ~/.Trash 2>/dev/null | awk '{print "  "$1}' || echo "  Empty"

    echo ""
    read -p "Press Enter to continue..."
}

find_duplicates() {
    echo ""
    echo "🔍 SCANNING FOR DUPLICATES"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Checking Downloads folder for large duplicates..."
    echo "(This may take a minute...)"
    echo ""

    if [ -d ~/Downloads ]; then
        find ~/Downloads -type f -size +10M 2>/dev/null | \
        awk '{print $0}' | while read file; do
            md5="$(md5 -q "$file" 2>/dev/null)"
            echo "$md5 $file"
        done | sort | awk '
            NR==1 { current=$1; count=1; file=$2; next }
            $1==current { count++; if (count==2) print file; print $2 }
            $1!=current { current=$1; file=$2; count=1 }
        ' | head -20
    fi

    echo ""
    read -p "Press Enter to continue..."
}

cleanup_interactive() {
    echo ""
    echo "🧹 CACHE CLEANUP"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    read -p "Clear browser caches? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf ~/Library/Caches/Google/Chrome/* 2>/dev/null
        rm -rf ~/Library/Caches/Firefox/* 2>/dev/null
        echo "✅ Browser caches cleared"
    fi

    read -p "Clear npm cache? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        npm cache clean --force 2>/dev/null
        echo "✅ npm cache cleared"
    fi

    read -p "Clear pip cache? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pip cache purge 2>/dev/null
        echo "✅ pip cache cleared"
    fi

    read -p "Clear Xcode DerivedData? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf ~/Library/Developer/Xcode/DerivedData/* 2>/dev/null
        echo "✅ Xcode DerivedData cleared"
    fi

    read -p "Empty trash? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf ~/.Trash/* 2>/dev/null
        echo "✅ Trash emptied"
    fi

    echo ""
    echo "✨ Cleanup complete!"
    echo ""
    read -p "Press Enter to continue..."
}

cleanup_quick() {
    echo ""
    echo "⚡ QUICK CLEANUP"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    echo "Clearing browser caches..."
    rm -rf ~/Library/Caches/Google/Chrome/* 2>/dev/null
    rm -rf ~/Library/Caches/Firefox/* 2>/dev/null

    echo "Clearing package manager caches..."
    npm cache clean --force 2>/dev/null
    pip cache purge 2>/dev/null
    brew cleanup 2>/dev/null

    echo "Clearing temp files..."
    rm -rf /tmp/* 2>/dev/null
    rm -rf /var/tmp/* 2>/dev/null

    echo "Emptying trash..."
    rm -rf ~/.Trash/* 2>/dev/null

    echo ""
    echo "✅ Quick cleanup complete!"
    echo ""
    du -sh ~/Library/Caches 2>/dev/null | awk '{print "Remaining cache: "$1}'
    echo ""
    read -p "Press Enter to continue..."
}

full_analysis() {
    echo ""
    echo "📈 FULL STORAGE ANALYSIS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    analyze_disk
    largest_files
    cache_sizes
    find_duplicates
}

# Main loop
while true; do
    show_menu
    read -p "Select option (1-8): " choice

    case $choice in
        1) analyze_disk ;;
        2) largest_files ;;
        3) cache_sizes ;;
        4) find_duplicates ;;
        5) cleanup_interactive ;;
        6) cleanup_quick ;;
        7) full_analysis ;;
        8) echo "Goodbye!"; exit 0 ;;
        *) echo "Invalid option. Press Enter..."; read ;;
    esac
done
