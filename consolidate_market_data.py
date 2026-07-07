"""
Consolidate market data files from scattered locations
Creates unified index for PostgreSQL loading
"""

import os
import shutil
from pathlib import Path
from typing import Dict, List
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class DataConsolidator:
    """Find and consolidate market data from all locations"""

    DATA_LOCATIONS = [
        "/Users/umashankar/data",
        "/Users/umashankar/Downloads/data",
        "/Users/umashankar/herrrickshaw/data",
        "/Users/umashankar/global_stock_analysis_optimized/parquet",
        "/Users/umashankar/german_market_data",
        "/Users/umashankar/Downloads/code/python_files",
    ]

    MARKET_PATTERNS = {
        'india': ['india', 'nse', 'bse'],
        'usa': ['usa', 'nasdaq', 'nyse', 'sp500'],
        'uk': ['uk', 'ftse', 'london', 'lse'],
        'germany': ['germany', 'dax', 'mdax', 'sdax', 'deutsche', 'frankfurt'],
        'europe': ['europe', 'stoxx', 'euronext', 'paris', 'amsterdam'],
        'japan': ['japan', 'jse', 'tse', 'nikkei'],
        'korea': ['korea', 'kospi', 'kosdaq', 'krx'],
        'china': ['china', 'ashare', 'csi', 'shanghai', 'szse'],
    }

    def __init__(self, target_dir="/Users/umashankar/market_data_consolidated"):
        self.target_dir = Path(target_dir)
        self.target_dir.mkdir(parents=True, exist_ok=True)
        self.data_index = {}

    def scan_locations(self) -> Dict[str, List[str]]:
        """Scan all data locations for market files"""
        found_files = {}

        for location in self.DATA_LOCATIONS:
            loc_path = Path(location)
            if not loc_path.exists():
                continue

            logger.info(f"📁 Scanning {location}...")

            for root, dirs, files in os.walk(loc_path):
                for file in files:
                    if file.endswith(('.csv', '.db', '.parquet')):
                        filepath = Path(root) / file
                        market = self._identify_market(file)

                        if market:
                            if market not in found_files:
                                found_files[market] = []
                            found_files[market].append(str(filepath))
                            logger.info(f"  ✓ {market}: {file} ({filepath.stat().st_size / 1024 / 1024:.1f} MB)")

        return found_files

    def _identify_market(self, filename: str) -> str:
        """Identify market from filename"""
        filename_lower = filename.lower()

        for market, patterns in self.MARKET_PATTERNS.items():
            if any(pattern in filename_lower for pattern in patterns):
                # Skip non-data files
                if any(skip in filename_lower for skip in ['readme', 'summary', 'report', 'config', 'log']):
                    continue
                return market

        return None

    def copy_files(self, found_files: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """Copy files to consolidated directory"""
        copied = {}

        for market, files in found_files.items():
            market_dir = self.target_dir / market
            market_dir.mkdir(parents=True, exist_ok=True)
            copied[market] = []

            for filepath in files:
                src = Path(filepath)
                filename = src.name
                dest = market_dir / filename

                # Avoid duplicates
                if dest.exists():
                    if src.stat().st_size == dest.stat().st_size:
                        logger.info(f"  ⊘ {market}/{filename} (already exists)")
                        continue

                try:
                    shutil.copy2(src, dest)
                    logger.info(f"  ✓ Copied {market}/{filename} ({src.stat().st_size / 1024 / 1024:.1f} MB)")
                    copied[market].append(str(dest))
                except Exception as e:
                    logger.error(f"  ✗ Error copying {filename}: {e}")

        return copied

    def generate_summary(self, copied: Dict[str, List[str]]):
        """Generate consolidation summary"""
        print("\n" + "="*70)
        print("📊 DATA CONSOLIDATION SUMMARY")
        print("="*70)
        print(f"Consolidated directory: {self.target_dir}")
        print()

        total_files = 0
        total_size = 0

        for market in sorted(copied.keys()):
            files = copied[market]
            if files:
                size = sum(Path(f).stat().st_size for f in files)
                size_mb = size / 1024 / 1024
                total_size += size
                total_files += len(files)

                print(f"🌍 {market.upper()}: {len(files)} files ({size_mb:.1f} MB)")
                for f in files[:3]:
                    print(f"     - {Path(f).name}")
                if len(files) > 3:
                    print(f"     ... and {len(files)-3} more")

        print()
        print(f"Total: {total_files} files ({total_size / 1024 / 1024:.1f} MB)")
        print("="*70)
        print("\n✅ Ready for PostgreSQL loading!")
        print(f"   Run: python3 load_market_data_to_postgres.py")


def main():
    consolidator = DataConsolidator()

    logger.info("🔍 Scanning all data locations...\n")
    found_files = consolidator.scan_locations()

    if not found_files:
        logger.error("❌ No data files found in any location!")
        return

    logger.info("\n📋 Copying files to consolidated directory...\n")
    copied = consolidator.copy_files(found_files)

    consolidator.generate_summary(copied)


if __name__ == "__main__":
    main()
