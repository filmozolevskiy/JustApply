import os
import sys
import argparse
from fastmcp import FastMCP
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/drive'
]

FOLDER_ID = "11DdZR63ul4OushN3MOvNFdaQIE3y3uP-"
SPREADSHEET_NAME = "Job Tracker Sheet"

JOBS_HEADERS = [
    'Job title', 'Company + Company size', 'Posting link', 'Posting date',
    'Location + Remote type (in office, hybrid, remote)', 'Seniority type (junior, mid, senior)',
    'Salary type', 'Short description', 'match', 'no-match', 'Should proceed?'
]

APPLICATIONS_HEADERS = [
    'Job title', 'Company + Company size', 'Posting link', 'Posting date',
    'Application date', 'Location + Remote type (in office, hybrid, remote)',
    'Salary type', 'Short description', 'match', 'no-match',
    'People contacted', 'Contact message', 'Comment'
]


def get_credentials(auth_only=False):
    creds = None
    token_path = 'token.json'
    credentials_path = 'credentials.json'

    # Load from token.json if it exists
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception as e:
            print(f"Error loading token.json: {e}", file=sys.stderr)
            creds = None
    
    # If credentials are not valid (expired, or don't exist)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Token expired, refreshing...", file=sys.stderr)
            try:
                creds.refresh(Request())
                with open(token_path, 'w') as token_file:
                    token_file.write(creds.to_json())
                print("Token refreshed successfully.", file=sys.stderr)
            except Exception as e:
                print(f"Error refreshing token: {e}", file=sys.stderr)
                creds = None
        
        # If refreshing failed or token.json didn't exist
        if not creds:
            if auth_only or not os.path.exists(token_path):
                if not os.path.exists(credentials_path):
                    print("Error: credentials.json not found in root directory.", file=sys.stderr)
                    print("Please obtain credentials.json from Google Cloud Console.", file=sys.stderr)
                    sys.exit(1)
                
                print("Starting browser OAuth 2.0 flow...", file=sys.stderr)
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
                
                # Save credentials to token.json
                with open(token_path, 'w') as token_file:
                    token_file.write(creds.to_json())
                print("Authorization complete. token.json created successfully.", file=sys.stderr)
            else:
                print("Error: credentials not authorized.", file=sys.stderr)
                print("Please run this script manually with the --auth flag in your terminal to complete browser setup.", file=sys.stderr)
                print("Example: python3 scripts/google_sheets_mcp.py --auth", file=sys.stderr)
                sys.exit(1)
                
    return creds

def initialize_tabs_and_headers(sheets_service, spreadsheet_id):
    spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = spreadsheet.get('sheets', [])
    sheet_titles = [s['properties']['title'] for s in sheets]
    
    requests = []
    jobs_existed = 'Jobs' in sheet_titles
    apps_existed = 'Applications' in sheet_titles
    
    if not jobs_existed:
        requests.append({
            'addSheet': {
                'properties': {
                    'title': 'Jobs'
                }
            }
        })
    if not apps_existed:
        requests.append({
            'addSheet': {
                'properties': {
                    'title': 'Applications'
                }
            }
        })
        
    if requests:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': requests}
        ).execute()
        
        # Re-fetch sheets
        spreadsheet = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet.get('sheets', [])
        sheet_titles = [s['properties']['title'] for s in sheets]
        
    # Delete Sheet1 if it exists
    if 'Sheet1' in sheet_titles:
        sheet1_id = next(s['properties']['sheetId'] for s in sheets if s['properties']['title'] == 'Sheet1')
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': [{'deleteSheet': {'sheetId': sheet1_id}}]}
        ).execute()
        
    # Verify and write headers
    for tab_name, headers in [('Jobs', JOBS_HEADERS), ('Applications', APPLICATIONS_HEADERS)]:
        try:
            result = sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"'{tab_name}'!A1:Z1"
            ).execute()
            current_headers = result.get('values', [[]])[0]
        except Exception:
            current_headers = []
            
        if current_headers != headers:
            sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"'{tab_name}'!A1",
                valueInputOption='RAW',
                body={'values': [headers]}
            ).execute()

def get_or_create_spreadsheet(creds):
    drive_service = build('drive', 'v3', credentials=creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    
    query = f"'{FOLDER_ID}' in parents and name = '{SPREADSHEET_NAME}' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    response = drive_service.files().list(q=query, fields="files(id, name)").execute()
    files = response.get('files', [])
    
    if files:
        spreadsheet_id = files[0]['id']
    else:
        file_metadata = {
            'name': SPREADSHEET_NAME,
            'mimeType': 'application/vnd.google-apps.spreadsheet',
            'parents': [FOLDER_ID]
        }
        file = drive_service.files().create(body=file_metadata, fields='id').execute()
        spreadsheet_id = file.get('id')
        
    initialize_tabs_and_headers(sheets_service, spreadsheet_id)
    return spreadsheet_id

# Initialize FastMCP server
mcp = FastMCP("Google Sheets MCP")

@mcp.tool()
def test_connection() -> str:
    """Test that Google Sheets and Drive connection and authentication is functioning correctly."""
    try:
        creds = get_credentials()
        if creds and creds.valid:
            return "Connection successful. OAuth 2.0 credentials are valid and active."
        return "Connection failed: invalid credentials."
    except Exception as e:
        return f"Connection failed with error: {str(e)}"

@mcp.tool()
def list_jobs() -> list:
    """List all jobs currently in the Jobs tab. Returns a list of dicts with header keys."""
    creds = get_credentials()
    spreadsheet_id = get_or_create_spreadsheet(creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="'Jobs'!A:K"
    ).execute()
    
    rows = result.get('values', [])
    if not rows:
        return []
        
    headers = rows[0]
    jobs = []
    for row in rows[1:]:
        padded_row = list(row) + [''] * (len(headers) - len(row))
        jobs.append(dict(zip(headers, padded_row)))
    return jobs

@mcp.tool()
def list_applications() -> list:
    """List all applications currently in the Applications tab. Returns a list of dicts with header keys."""
    creds = get_credentials()
    spreadsheet_id = get_or_create_spreadsheet(creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="'Applications'!A:M"
    ).execute()
    
    rows = result.get('values', [])
    if not rows:
        return []
        
    headers = rows[0]
    apps = []
    for row in rows[1:]:
        padded_row = list(row) + [''] * (len(headers) - len(row))
        apps.append(dict(zip(headers, padded_row)))
    return apps


@mcp.tool()
def add_job(
    job_title: str,
    company: str,
    posting_link: str,
    posting_date: str = "",
    location: str = "",
    seniority: str = "",
    salary: str = "",
    short_description: str = "",
    match_details: str = "",
    no_match_details: str = "",
    should_proceed: str = ""
) -> str:
    """Add a new job listing to the Jobs tab."""
    creds = get_credentials()
    spreadsheet_id = get_or_create_spreadsheet(creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    
    row_values = [
        job_title, company, posting_link, posting_date,
        location, seniority, salary, short_description,
        match_details, no_match_details, should_proceed
    ]
    
    sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="'Jobs'!A:K",
        valueInputOption='RAW',
        body={'values': [row_values]}
    ).execute()
    
    return f"Job '{job_title}' at '{company}' successfully added to Jobs tab."

@mcp.tool()
def update_job_status(
    job_title: str,
    company: str,
    should_proceed: str
) -> str:
    """Update the 'Should proceed?' column of a job matching job_title and company (case-insensitive)."""
    creds = get_credentials()
    spreadsheet_id = get_or_create_spreadsheet(creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="'Jobs'!A:K"
    ).execute()
    
    rows = result.get('values', [])
    if not rows:
        return f"Job '{job_title}' at '{company}' not found: sheet is empty."
        
    found_row_idx = -1
    for i, row in enumerate(rows):
        if i == 0:
            continue
        row_title = row[0] if len(row) > 0 else ""
        row_company = row[1] if len(row) > 1 else ""
        if row_title.strip().lower() == job_title.strip().lower() and row_company.strip().lower() == company.strip().lower():
            found_row_idx = i + 1
            break
            
    if found_row_idx == -1:
        return f"Job '{job_title}' at '{company}' not found in Jobs tab."
        
    range_name = f"'Jobs'!K{found_row_idx}"
    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption='RAW',
        body={'values': [[should_proceed]]}
    ).execute()
    
    return f"Job '{job_title}' at '{company}' successfully updated with status '{should_proceed}'."

@mcp.tool()
def track_application(
    job_title: str,
    company: str,
    posting_link: str,
    posting_date: str = "",
    application_date: str = "",
    location: str = "",
    salary: str = "",
    short_description: str = "",
    match_details: str = "",
    no_match_details: str = "",
    people_contacted: str = "",
    contact_message: str = "",
    comment: str = ""
) -> str:
    """Add a new application entry to the Applications tab."""
    creds = get_credentials()
    spreadsheet_id = get_or_create_spreadsheet(creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    
    row_values = [
        job_title, company, posting_link, posting_date,
        application_date, location, salary, short_description,
        match_details, no_match_details, people_contacted,
        contact_message, comment
    ]
    
    sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="'Applications'!A:M",
        valueInputOption='RAW',
        body={'values': [row_values]}
    ).execute()
    
    return f"Application for '{job_title}' at '{company}' successfully tracked in Applications tab."

@mcp.tool()
def get_resume(filename: str) -> str:
    """Retrieve and parse the full text of a candidate's resume profile (e.g. 'qa.md') from the resumes subfolder on Google Drive.
    
    Args:
        filename: The name of the resume file (e.g. 'qa.md' or 'qa').
    """
    creds = get_credentials()
    drive_service = build('drive', 'v3', credentials=creds)
    
    # 1. Search for a subfolder containing "resume" or "cv" or "profile" (case-insensitive) under FOLDER_ID
    query = f"'{FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    response = drive_service.files().list(q=query, fields="files(id, name)").execute()
    folders = response.get('files', [])
    
    resumes_folder_id = None
    target_names = ["resumes", "resume profiles", "cv's", "cvs"]
    for folder in folders:
        name_lower = folder['name'].lower()
        if any(target in name_lower for target in target_names):
            resumes_folder_id = folder['id']
            break
            
    # Fallback to the first subfolder if no exact match, or FOLDER_ID if no subfolders exist
    if not resumes_folder_id:
        if folders:
            resumes_folder_id = folders[0]['id']
        else:
            resumes_folder_id = FOLDER_ID
            
    # 2. Search for the file in the resumes folder
    # Ensure filename has extension .md or try both with/without
    if not filename.lower().endswith('.md'):
        file_query_name = f"{filename}.md"
    else:
        file_query_name = filename
        
    query_file = f"'{resumes_folder_id}' in parents and name = '{file_query_name}' and trashed = false"
    file_response = drive_service.files().list(q=query_file, fields="files(id, name)").execute()
    files = file_response.get('files', [])
    
    # Fallback: if ends with .md, try without extension
    if not files and filename.lower().endswith('.md'):
        no_ext = filename[:-3]
        query_file = f"'{resumes_folder_id}' in parents and name = '{no_ext}' and trashed = false"
        file_response = drive_service.files().list(q=query_file, fields="files(id, name)").execute()
        files = file_response.get('files', [])
        
    if not files:
        raise ValueError(f"Resume profile '{filename}' not found in Google Drive folder.")
        
    file_id = files[0]['id']
    
    # 3. Retrieve the full text content of the file using get_media
    content_bytes = drive_service.files().get_media(fileId=file_id).execute()
    return content_bytes.decode('utf-8')

def main():
    parser = argparse.ArgumentParser(description="Google Sheets OAuth 2.0 MCP Server")
    parser.add_argument("--auth", action="store_true", help="Run the interactive OAuth 2.0 browser authorization flow")
    args, unknown = parser.parse_known_args()

    if args.auth:
        get_credentials(auth_only=True)
        sys.exit(0)

    # Otherwise, run FastMCP stdio transport
    mcp.run()

if __name__ == "__main__":
    main()
