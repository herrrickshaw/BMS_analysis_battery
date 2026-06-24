#!/usr/bin/env python3
"""
Real-time Progress Bar Monitor for SSRI Extraction
Shows live updates with visual progress bar
"""

import os
import time
import re
from datetime import datetime
from pathlib import Path

class ProgressMonitor:
    def __init__(self, log_file):
        self.log_file = log_file
        self.start_time = None
        self.stages = {
            'pagination': {'weight': 40, 'completed': False, 'count': 0},
            'company': {'weight': 25, 'completed': False, 'count': 0},
            'city': {'weight': 20, 'completed': False, 'count': 0},
            'nearby': {'weight': 10, 'completed': False, 'count': 0},
            'export': {'weight': 5, 'completed': False, 'count': 0}
        }
        self.total_pumps = 0
        self.last_lines = 0

    def read_log(self):
        """Read latest log file"""
        if not os.path.exists(self.log_file):
            return ""
        try:
            with open(self.log_file, 'r') as f:
                return f.read()
        except:
            return ""

    def parse_log(self, log_content):
        """Parse log and extract progress info"""
        if not log_content:
            return

        # Check if extraction started
        if "SSRI SYSTEMATIC EXTRACTION" in log_content and not self.start_time:
            self.start_time = datetime.now()

        # Count added pumps
        pumps = re.findall(r'total unique: (\d+)', log_content)
        if pumps:
            self.total_pumps = int(pumps[-1])

        # Check stage completion
        if "Pagination complete:" in log_content:
            self.stages['pagination']['completed'] = True
            match = re.search(r'Pagination complete: (\d+)', log_content)
            if match:
                self.stages['pagination']['count'] = int(match.group(1))

        if "Company extraction complete:" in log_content:
            self.stages['company']['completed'] = True
            match = re.search(r'Company extraction complete: (\d+)', log_content)
            if match:
                self.stages['company']['count'] = int(match.group(1))

        if "City extraction complete:" in log_content:
            self.stages['city']['completed'] = True
            match = re.search(r'City extraction complete: (\d+)', log_content)
            if match:
                self.stages['city']['count'] = int(match.group(1))

        if "Nearby extraction complete:" in log_content:
            self.stages['nearby']['completed'] = True
            match = re.search(r'Nearby extraction complete: (\d+)', log_content)
            if match:
                self.stages['nearby']['count'] = int(match.group(1))

        if "Export complete" in log_content:
            self.stages['export']['completed'] = True
            self.stages['export']['count'] = 1

    def calculate_progress(self):
        """Calculate overall progress percentage"""
        total_weight = sum(s['weight'] for s in self.stages.values())
        completed_weight = sum(
            s['weight'] for s in self.stages.values() if s['completed']
        )
        return int((completed_weight / total_weight) * 100) if total_weight > 0 else 0

    def get_elapsed_time(self):
        """Get elapsed time since start"""
        if not self.start_time:
            return "00:00"
        elapsed = datetime.now() - self.start_time
        minutes = int(elapsed.total_seconds() // 60)
        seconds = int(elapsed.total_seconds() % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def draw_progress_bar(self, progress, width=40):
        """Draw visual progress bar"""
        filled = int((progress / 100) * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {progress}%"

    def get_current_stage(self):
        """Determine current stage"""
        if self.stages['pagination']['completed'] and not self.stages['company']['completed']:
            return "🏢 Fetching by Company"
        elif self.stages['company']['completed'] and not self.stages['city']['completed']:
            return "🏙️  Fetching by City"
        elif self.stages['city']['completed'] and not self.stages['nearby']['completed']:
            return "📍 Fetching Nearby Pumps"
        elif self.stages['nearby']['completed'] and not self.stages['export']['completed']:
            return "💾 Exporting Data"
        elif self.stages['pagination']['completed']:
            return "📄 Fetching by Pagination"
        else:
            return "⏳ Initializing"

    def display(self):
        """Display progress dashboard"""
        os.system('clear' if os.name == 'posix' else 'cls')

        progress = self.calculate_progress()
        elapsed = self.get_elapsed_time()
        current_stage = self.get_current_stage()

        print("\n" + "="*70)
        print("🚀 SSRI 100,000+ PUMP EXTRACTION - PROGRESS")
        print("="*70)

        print(f"\n⏱️  Elapsed Time: {elapsed}")
        print(f"📍 Current Stage: {current_stage}")

        print(f"\n{self.draw_progress_bar(progress)}")

        print(f"\n📊 STAGE PROGRESS:")
        print(f"  📄 Pagination (40%)        {'✅ DONE' if self.stages['pagination']['completed'] else '🔄 RUNNING'}")
        if self.stages['pagination']['count'] > 0:
            print(f"     ↳ Added {self.stages['pagination']['count']:,} pumps")

        print(f"  🏢 By Company (25%)       {'✅ DONE' if self.stages['company']['completed'] else '⏳ PENDING'}")
        if self.stages['company']['count'] > 0:
            print(f"     ↳ Added {self.stages['company']['count']:,} pumps")

        print(f"  🏙️  By City (20%)          {'✅ DONE' if self.stages['city']['completed'] else '⏳ PENDING'}")
        if self.stages['city']['count'] > 0:
            print(f"     ↳ Added {self.stages['city']['count']:,} pumps")

        print(f"  📍 Nearby (10%)           {'✅ DONE' if self.stages['nearby']['completed'] else '⏳ PENDING'}")
        if self.stages['nearby']['count'] > 0:
            print(f"     ↳ Added {self.stages['nearby']['count']:,} pumps")

        print(f"  💾 Export (5%)            {'✅ DONE' if self.stages['export']['completed'] else '⏳ PENDING'}")

        print(f"\n🎯 EXTRACTION METRICS:")
        print(f"  Total Unique Pumps: {self.total_pumps:,}")
        print(f"  Deduplication: ACTIVE")
        print(f"  Status: {'✅ COMPLETE' if progress == 100 else f'🔄 {progress}% Complete'}")

        if self.total_pumps > 0:
            pumps_per_minute = self.total_pumps / max(1, int(self.get_elapsed_time().split(':')[0]))
            print(f"  Rate: {pumps_per_minute:,.0f} pumps/minute")

        print("\n" + "="*70)

        if progress == 100:
            print("✅ EXTRACTION COMPLETE!")
            print("\nNext Steps:")
            print("  1. cp outlet_data_ssri_100k/ssri_pumps_100k_*.js ../fuel-pump-locations-map/locations-data.js")
            print("  2. cd ../fuel-pump-locations-map/")
            print("  3. python3 -m http.server 8000")
            print("  4. Visit http://localhost:8000")
            return True
        else:
            print("Press Ctrl+C to stop monitoring")
            return False

    def run(self, update_interval=2):
        """Run continuous monitoring"""
        print("\n🎯 Starting progress monitor...")
        time.sleep(1)

        try:
            while True:
                log_content = self.read_log()
                self.parse_log(log_content)

                complete = self.display()

                if complete:
                    break

                time.sleep(update_interval)

        except KeyboardInterrupt:
            print("\n\n⏹️  Monitoring stopped")
            print("Run 'tail -f extraction_progress.log' to continue watching")


def main():
    """Main execution"""
    log_file = "/Users/umashankar/api-data-integration/extraction_progress.log"

    monitor = ProgressMonitor(log_file)
    monitor.run(update_interval=2)


if __name__ == "__main__":
    main()
