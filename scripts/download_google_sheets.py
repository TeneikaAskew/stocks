#!/usr/bin/env python3
"""
Download Google Sheets as CSV files
Requires Google Sheets API credentials
"""
import os
import sys
import json
import argparse
from pathlib import Path

# Try importing Google API libraries
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("ERROR: Google API libraries not installed")
    print("Install with: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    sys.exit(1)

# Configuration
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# Strategy sheet names (must match your Google Sheets tabs)
STRATEGY_SHEETS = [
    'Long Calls',
    'Bull Spreads',
    'Covered Calls',
    'Long Puts',
    'Bear Spreads',
    'Short Calls',
    'Strangles',
    'Straddles',
    'Short Puts'
]


def get_credentials(credentials_path):
    """
    Load Google API credentials from service account file

    Args:
        credentials_path: Path to service account JSON file

    Returns:
        credentials object
    """
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(f"Credentials file not found: {credentials_path}")

    credentials = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=SCOPES
    )
    return credentials


def get_sheet_as_csv(service, spreadsheet_id, sheet_name):
    """
    Download a single sheet as CSV data

    Args:
        service: Google Sheets API service object
        spreadsheet_id: ID of the spreadsheet
        sheet_name: Name of the sheet to download

    Returns:
        CSV string data
    """
    try:
        # Get the sheet data
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A:ZZ"  # Get all columns
        ).execute()

        values = result.get('values', [])

        if not values:
            print(f"  ⚠️  Sheet '{sheet_name}' is empty")
            return None

        # Convert to CSV format
        csv_lines = []
        for row in values:
            # Escape fields that contain commas or quotes
            escaped_row = []
            for field in row:
                field_str = str(field)
                if ',' in field_str or '"' in field_str or '\n' in field_str:
                    # Escape quotes and wrap in quotes
                    field_str = '"' + field_str.replace('"', '""') + '"'
                escaped_row.append(field_str)
            csv_lines.append(','.join(escaped_row))

        return '\n'.join(csv_lines)

    except HttpError as e:
        print(f"  ✗ Error downloading sheet '{sheet_name}': {e}")
        return None


def download_all_sheets(spreadsheet_id, credentials_path, output_dir, sheets=None):
    """
    Download all strategy sheets from Google Sheets

    Args:
        spreadsheet_id: ID of the Google Spreadsheet
        credentials_path: Path to service account credentials JSON
        output_dir: Directory to save CSV files
        sheets: List of sheet names to download (default: all strategy sheets)
    """
    # Create output directory if needed
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Get credentials and build service
    print("Authenticating with Google Sheets API...")
    credentials = get_credentials(credentials_path)
    service = build('sheets', 'v4', credentials=credentials)

    # Use provided sheets or default strategy sheets
    sheets_to_download = sheets or STRATEGY_SHEETS

    print(f"\nDownloading {len(sheets_to_download)} sheets from spreadsheet {spreadsheet_id}...")
    print(f"Output directory: {output_path.absolute()}\n")

    success_count = 0
    failed_count = 0

    for sheet_name in sheets_to_download:
        print(f"📥 Downloading '{sheet_name}'...")

        csv_data = get_sheet_as_csv(service, spreadsheet_id, sheet_name)

        if csv_data:
            # Save to file
            filename = f"{sheet_name.replace(' ', '')}.csv"
            output_file = output_path / filename

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(csv_data)

            # Count rows (subtract header)
            row_count = len(csv_data.split('\n')) - 1
            print(f"  ✓ Saved to {filename} ({row_count} rows)")
            success_count += 1
        else:
            failed_count += 1

    print(f"\n{'='*60}")
    print(f"✓ Successfully downloaded: {success_count} sheets")
    if failed_count > 0:
        print(f"✗ Failed: {failed_count} sheets")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description='Download Google Sheets as CSV files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Download all strategy sheets
  python download_google_sheets.py --spreadsheet-id YOUR_SHEET_ID

  # Download specific sheets
  python download_google_sheets.py --spreadsheet-id YOUR_SHEET_ID --sheets "Long Calls" "Bull Spreads"

  # Use custom credentials file
  python download_google_sheets.py --spreadsheet-id YOUR_SHEET_ID --credentials path/to/creds.json

Setup:
  1. Create a Google Cloud project at https://console.cloud.google.com
  2. Enable the Google Sheets API
  3. Create a service account and download the JSON key
  4. Share your Google Sheet with the service account email
  5. Set GOOGLE_SHEETS_CREDENTIALS secret in GitHub with the JSON content
        '''
    )

    parser.add_argument(
        '--spreadsheet-id',
        required=True,
        help='Google Spreadsheet ID (from the URL)'
    )

    parser.add_argument(
        '--credentials',
        default='credentials/google-sheets-credentials.json',
        help='Path to Google service account credentials JSON file'
    )

    parser.add_argument(
        '--output-dir',
        default='google-apps-script/data',
        help='Directory to save CSV files (default: google-apps-script/data)'
    )

    parser.add_argument(
        '--sheets',
        nargs='+',
        help='Specific sheet names to download (default: all strategy sheets)'
    )

    parser.add_argument(
        '--format',
        choices=['csv', 'json', 'both'],
        default='csv',
        help='Output format (default: csv)'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Force re-download even if files exist'
    )

    args = parser.parse_args()

    try:
        download_all_sheets(
            spreadsheet_id=args.spreadsheet_id,
            credentials_path=args.credentials,
            output_dir=args.output_dir,
            sheets=args.sheets
        )
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
