#!/bin/bash

echo "🧹 Starting cache cleanup..."

# System caches
echo "Clearing system caches..."
rm -rf ~/Library/Caches/*
rm -rf ~/Library/Saved Application State/*

# Browser caches
echo "Clearing browser caches..."
rm -rf ~/Library/Caches/Google/Chrome/*
rm -rf ~/Library/Caches/Firefox/*
rm -rf ~/Library/Safari/History.db-wal
rm -rf ~/Library/Safari/TopSites.plist

# Package manager caches
echo "Clearing package manager caches..."
npm cache clean --force 2>/dev/null
pip cache purge 2>/dev/null
brew cleanup 2>/dev/null
gem cleanup 2>/dev/null

# Temporary files
echo "Clearing temporary files..."
rm -rf /var/tmp/*
rm -rf /tmp/*

# Application caches
echo "Clearing application caches..."
rm -rf ~/Library/Application Support/CrashReporter/*

# Empty trash
echo "Emptying trash..."
rm -rf ~/.Trash/*

echo "✅ Cache cleanup complete!"
echo "📊 Freed up space. Current disk usage:"
du -sh ~/Library/Caches
