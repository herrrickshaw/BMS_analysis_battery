#!/usr/bin/env python3
"""
Deutsche Börse Xetra Public Data Set - AWS S3
Free historical 1-minute OHLCV data
Bucket: deutsche-boerse-xetra-pds (us-east-1, requester-pays)
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
import argparse
import logging
import csv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
    logger.warning("boto3 not installed. Run: pip install boto3")

class XetraPDSClient:
    def __init__(self):
        if not HAS_BOTO3:
            logger.error("boto3 required for Xetra PDS access")
            return
        
        # S3 requires AWS credentials for requester-pays bucket
        self.bucket = "deutsche-boerse-xetra-pds"
        self.region = "us-east-1"
        
        try:
            self.s3 = boto3.client(
                's3',
                region_name=self.region,
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
            )
            logger.info("✓ Connected to AWS S3")
        except Exception as e:
            logger.error(f"S3 connection failed: {e}")
            self.s3 = None
        
        self.output_dir = Path.home() / "xetra_pds_data"
        self.output_dir.mkdir(exist_ok=True)
    
    def list_trading_dates(self, year, month):
        """List available trading dates in S3"""
        if not self.s3:
            return []
        
        prefix = f"{year:04d}/{month:02d}/"
        logger.info(f"Listing trading dates for {year}-{month:02d}...")
        
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                Delimiter='/'
            )
            
            dates = []
            if 'CommonPrefixes' in response:
                for common_prefix in response['CommonPrefixes']:
                    date_str = common_prefix['Prefix'].split('/')[-2]
                    dates.append(date_str)
            
            logger.info(f"✓ Found {len(dates)} trading dates")
            return sorted(dates)
        except Exception as e:
            logger.error(f"List failed: {e}")
            return []
    
    def download_date(self, date_str, intraday=False):
        """Download data for specific date (YYYY-MM-DD format)"""
        if not self.s3:
            return []
        
        # Parse date
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        year = date_obj.strftime("%Y")
        month = date_obj.strftime("%m")
        day = date_obj.strftime("%d")
        
        prefix = f"{year}/{month}/{day}/"
        logger.info(f"Downloading Xetra data for {date_str}...")
        
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                MaxKeys=10000
            )
            
            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    key = obj['Key']
                    if intraday and '1min' not in key:
                        continue
                    files.append(key)
            
            logger.info(f"✓ Found {len(files)} files for {date_str}")
            
            # Download sample files
            for file_key in files[:3]:  # Limit to first 3 files for demo
                self._download_file(file_key, date_str)
            
            return files
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return []
    
    def _download_file(self, s3_key, date_str):
        """Download single file from S3"""
        try:
            filename = s3_key.split('/')[-1]
            output_file = self.output_dir / f"{date_str}_{filename}"
            
            logger.info(f"  Downloading {filename}...")
            self.s3.download_file(
                self.bucket,
                s3_key,
                str(output_file),
                ExtraArgs={'RequestPayer': 'requester'}
            )
            
            logger.info(f"  ✓ Saved to {output_file}")
            return output_file
        except Exception as e:
            logger.warning(f"  Failed to download {filename}: {e}")
            return None
    
    def download_range(self, start_date, end_date):
        """Download data for date range (YYYY-MM-DD format)"""
        if not self.s3:
            return
        
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        current = start
        all_files = []
        
        while current <= end:
            # Skip weekends
            if current.weekday() < 5:  # Monday=0, Friday=4
                files = self.download_date(current.strftime("%Y-%m-%d"))
                all_files.extend(files)
            
            current += timedelta(days=1)
        
        logger.info(f"\n✓ Downloaded data for range {start_date} to {end_date}")
        logger.info(f"  Total files: {len(all_files)}")

def main():
    parser = argparse.ArgumentParser(description="Xetra PDS - Deutsche Börse S3 Data")
    parser.add_argument("--date", type=str, help="Single date (YYYY-MM-DD)")
    parser.add_argument("--start", type=str, help="Start date for range (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date for range (YYYY-MM-DD)")
    parser.add_argument("--intraday", action="store_true", help="Download 1-minute bars only")
    parser.add_argument("--list", action="store_true", help="List available dates")
    parser.add_argument("--year", type=int, help="Year for listing (YYYY)")
    parser.add_argument("--month", type=int, help="Month for listing (MM)")
    
    args = parser.parse_args()
    
    if not HAS_BOTO3:
        print("❌ boto3 not installed")
        print("   Install: pip install boto3")
        print("   Set AWS credentials:")
        print("     export AWS_ACCESS_KEY_ID='...'")
        print("     export AWS_SECRET_ACCESS_KEY='...'")
        return
    
    client = XetraPDSClient()
    
    if args.list:
        if not args.year or not args.month:
            print("✓ Xetra PDS - S3 Data Browser")
            print("  Use --list --year YYYY --month MM to list trading dates")
            print("  Example: python3 xetra_pds.py --list --year 2024 --month 1")
            return
        
        dates = client.list_trading_dates(args.year, args.month)
        print(f"\n✓ Trading dates for {args.year}-{args.month:02d}:")
        for date in dates:
            print(f"  - {date}")
    
    elif args.date:
        client.download_date(args.date, args.intraday)
    
    elif args.start and args.end:
        client.download_range(args.start, args.end)
    
    else:
        print("✓ Xetra PDS Client ready")
        print("  Usage:")
        print("    --date 2024-01-10              # Download single day")
        print("    --start 2024-01-02 --end 2024-01-31  # Download range")
        print("    --list --year 2024 --month 1   # List available dates")
        print("    --intraday                     # Download 1-minute bars only")
        print("\n  Requirements:")
        print("    pip install boto3")
        print("    export AWS_ACCESS_KEY_ID='...'")
        print("    export AWS_SECRET_ACCESS_KEY='...'")

if __name__ == "__main__":
    main()
