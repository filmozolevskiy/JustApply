import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add scripts directory to path to import google_sheets_mcp
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from google_sheets_mcp import (
    get_or_create_spreadsheet,
    list_jobs,
    list_applications,
    add_job,
    update_job_status,
    track_application,
    get_resume,
    FOLDER_ID,
    SPREADSHEET_NAME,
    JOBS_HEADERS,
    APPLICATIONS_HEADERS
)

@pytest.fixture
def mock_sheets_services():
    with patch('google_sheets_mcp.get_credentials') as mock_creds, \
         patch('google_sheets_mcp.build') as mock_build:
        
        mock_drive = MagicMock()
        mock_sheets = MagicMock()
        
        def build_side_effect(serviceName, version, **kwargs):
            if serviceName == 'drive':
                return mock_drive
            elif serviceName == 'sheets':
                return mock_sheets
            return MagicMock()
            
        mock_build.side_effect = build_side_effect
        
        # Default mock implementations
        mock_list_result = MagicMock()
        mock_drive.files().list.return_value = mock_list_result
        mock_list_result.execute.return_value = {'files': [{'id': 'test_spreadsheet_123', 'name': SPREADSHEET_NAME}]}
        
        yield mock_drive, mock_sheets

def test_get_or_create_spreadsheet_creates_when_missing():
    with patch('google_sheets_mcp.build') as mock_build:
        mock_drive = MagicMock()
        mock_sheets = MagicMock()
        
        def build_side_effect(serviceName, version, **kwargs):
            if serviceName == 'drive':
                return mock_drive
            elif serviceName == 'sheets':
                return mock_sheets
            return MagicMock()
            
        mock_build.side_effect = build_side_effect
        
        # Mock Drive files list to return empty (not found)
        mock_list_result = MagicMock()
        mock_drive.files().list.return_value = mock_list_result
        mock_list_result.execute.return_value = {'files': []}
        
        # Mock Drive files create
        mock_create_result = MagicMock()
        mock_drive.files().create.return_value = mock_create_result
        mock_create_result.execute.return_value = {'id': 'new_spreadsheet_id_123'}
        
        # Mock Sheets get to return empty sheet list initially
        mock_get_result = MagicMock()
        mock_sheets.spreadsheets().get.return_value = mock_get_result
        mock_get_result.execute.return_value = {
            'sheets': [
                {'properties': {'title': 'Sheet1', 'sheetId': 0}}
            ]
        }
        
        # Call get_or_create_spreadsheet
        mock_creds = MagicMock()
        spreadsheet_id = get_or_create_spreadsheet(mock_creds)
        
        # Assertions
        assert spreadsheet_id == 'new_spreadsheet_id_123'
        mock_drive.files().create.assert_called_once_with(
            body={
                'name': SPREADSHEET_NAME,
                'mimeType': 'application/vnd.google-apps.spreadsheet',
                'parents': [FOLDER_ID]
            },
            fields='id'
        )

def test_list_jobs_empty(mock_sheets_services):
    mock_drive, mock_sheets = mock_sheets_services
    
    # Mock Sheets values get to return only headers
    mock_values_result = MagicMock()
    mock_sheets.spreadsheets().values().get.return_value = mock_values_result
    mock_values_result.execute.return_value = {'values': [JOBS_HEADERS]}
    
    jobs = list_jobs()
    assert jobs == []

def test_list_jobs_with_data(mock_sheets_services):
    mock_drive, mock_sheets = mock_sheets_services
    
    row1 = ['Software Engineer', 'Google', 'http://google.com/jobs', '2026-06-01', 'Remote', 'Senior', '$150k', 'Cool job', 'Python', 'Java', 'Yes']
    mock_values_result = MagicMock()
    mock_sheets.spreadsheets().values().get.return_value = mock_values_result
    mock_values_result.execute.return_value = {'values': [JOBS_HEADERS, row1]}
    
    jobs = list_jobs()
    assert len(jobs) == 1
    assert jobs[0]['Job title'] == 'Software Engineer'
    assert jobs[0]['Company + Company size'] == 'Google'
    assert jobs[0]['Should proceed?'] == 'Yes'

def test_list_applications_empty(mock_sheets_services):
    mock_drive, mock_sheets = mock_sheets_services
    
    # Mock Sheets values get to return only headers
    mock_values_result = MagicMock()
    mock_sheets.spreadsheets().values().get.return_value = mock_values_result
    mock_values_result.execute.return_value = {'values': [APPLICATIONS_HEADERS]}
    
    apps = list_applications()
    assert apps == []

def test_list_applications_with_data(mock_sheets_services):
    mock_drive, mock_sheets = mock_sheets_services
    
    row1 = ['Software Engineer', 'Google', 'http://google.com/jobs', '2026-06-01', '2026-06-02', 'Remote', '$150k', 'Cool job', 'Python', 'Java', 'John Doe', 'Hi John', 'Applied']
    mock_values_result = MagicMock()
    mock_sheets.spreadsheets().values().get.return_value = mock_values_result
    mock_values_result.execute.return_value = {'values': [APPLICATIONS_HEADERS, row1]}
    
    apps = list_applications()
    assert len(apps) == 1
    assert apps[0]['Job title'] == 'Software Engineer'
    assert apps[0]['Company + Company size'] == 'Google'
    assert apps[0]['People contacted'] == 'John Doe'

def test_add_job(mock_sheets_services):
    mock_drive, mock_sheets = mock_sheets_services
    
    mock_append_result = MagicMock()
    mock_sheets.spreadsheets().values().append.return_value = mock_append_result
    mock_append_result.execute.return_value = {}
    
    result = add_job(
        job_title='QA Automation',
        company='Apple',
        posting_link='http://apple.com/jobs',
        posting_date='2026-06-02',
        location='Cupertino',
        seniority='Mid',
        salary='$130k',
        short_description='Testing apps'
    )
    
    assert "successfully added" in result
    mock_sheets.spreadsheets().values().append.assert_called_once()
    
    # Verify values appended
    call_args = mock_sheets.spreadsheets().values().append.call_args[1]
    expected_values = ['QA Automation', 'Apple', 'http://apple.com/jobs', '2026-06-02', 'Cupertino', 'Mid', '$130k', 'Testing apps', '', '', '']
    assert call_args['body']['values'] == [expected_values]

def test_update_job_status_success(mock_sheets_services):
    mock_drive, mock_sheets = mock_sheets_services
    
    row1 = ['Software Engineer', 'Google', 'http://google.com/jobs', '2026-06-01', 'Remote', 'Senior', '$150k', 'Cool job', 'Python', 'Java', '']
    mock_get_values = MagicMock()
    mock_sheets.spreadsheets().values().get.return_value = mock_get_values
    mock_get_values.execute.return_value = {'values': [JOBS_HEADERS, row1]}
    
    mock_update = MagicMock()
    mock_sheets.spreadsheets().values().update.return_value = mock_update
    mock_update.execute.return_value = {}
    
    result = update_job_status(job_title='Software Engineer', company='Google', should_proceed='Yes')
    
    assert "successfully updated" in result
    mock_sheets.spreadsheets().values().update.assert_any_call(
        spreadsheetId='test_spreadsheet_123',
        range="'Jobs'!K2",
        valueInputOption='RAW',
        body={'values': [['Yes']]}
    )

def test_update_job_status_not_found(mock_sheets_services):
    mock_drive, mock_sheets = mock_sheets_services
    
    mock_get_values = MagicMock()
    mock_sheets.spreadsheets().values().get.return_value = mock_get_values
    mock_get_values.execute.return_value = {'values': [JOBS_HEADERS]}
    
    result = update_job_status(job_title='Software Engineer', company='Google', should_proceed='Yes')
    assert "not found" in result

def test_track_application(mock_sheets_services):
    mock_drive, mock_sheets = mock_sheets_services
    
    mock_append_result = MagicMock()
    mock_sheets.spreadsheets().values().append.return_value = mock_append_result
    mock_append_result.execute.return_value = {}
    
    result = track_application(
        job_title='QA Automation',
        company='Apple',
        posting_link='http://apple.com/jobs',
        posting_date='2026-06-02',
        application_date='2026-06-03',
        location='Cupertino',
        salary='$130k',
        short_description='Testing apps',
        people_contacted='John Doe',
        contact_message='Hi John',
        comment='Applied'
    )
    
    assert "successfully tracked" in result
    mock_sheets.spreadsheets().values().append.assert_called_once()
    
    # Verify values appended
    call_args = mock_sheets.spreadsheets().values().append.call_args[1]
    expected_values = ['QA Automation', 'Apple', 'http://apple.com/jobs', '2026-06-02', '2026-06-03', 'Cupertino', '$130k', 'Testing apps', '', '', 'John Doe', 'Hi John', 'Applied']
    assert call_args['body']['values'] == [expected_values]

def test_get_resume_success(mock_sheets_services):
    mock_drive, mock_sheets = mock_sheets_services
    
    # 1. Mock drive list folders inside FOLDER_ID
    mock_list_folders = MagicMock()
    mock_list_folders.execute.return_value = {
        'files': [
            {'id': 'folder_cvs_123', 'name': "CV's"}
        ]
    }
    
    # 2. Mock drive list file qa.md inside folder_cvs_123
    mock_list_files = MagicMock()
    mock_list_files.execute.return_value = {
        'files': [
            {'id': 'file_qa_456', 'name': 'qa.md'}
        ]
    }
    
    # Custom side effect for mock_drive.files().list
    def list_side_effect(q=None, fields=None):
        if 'folder_cvs_123' in q:
            return mock_list_files
        else:
            return mock_list_folders
            
    mock_drive.files().list.side_effect = list_side_effect
    
    # 3. Mock get_media().execute() to return bytes
    mock_get_media = MagicMock()
    mock_get_media.execute.return_value = b"# QA Engineer Profile"
    mock_drive.files().get_media.return_value = mock_get_media
    
    content = get_resume('qa.md')
    assert content == "# QA Engineer Profile"
    
    # Verify get_media was called with the correct file ID
    mock_drive.files().get_media.assert_called_once_with(fileId='file_qa_456')

def test_get_resume_not_found(mock_sheets_services):
    mock_drive, mock_sheets = mock_sheets_services
    
    # 1. Mock drive list folders inside FOLDER_ID
    mock_list_folders = MagicMock()
    mock_list_folders.execute.return_value = {
        'files': [
            {'id': 'folder_cvs_123', 'name': "CV's"}
        ]
    }
    
    # 2. Mock drive list file qa.md inside folder_cvs_123 to return empty
    mock_list_files = MagicMock()
    mock_list_files.execute.return_value = {
        'files': []
    }
    
    def list_side_effect(q=None, fields=None):
        if 'folder_cvs_123' in q:
            return mock_list_files
        else:
            return mock_list_folders
            
    mock_drive.files().list.side_effect = list_side_effect
    
    with pytest.raises(ValueError) as excinfo:
        get_resume('nonexistent.md')
    
    assert "not found in Google Drive folder" in str(excinfo.value)
