#!/usr/bin/env python3
"""
Google Drive API interaction script
Requirements: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""

import os
import io
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive']

class GoogleDriveAPI:
    def __init__(self, credentials_file='credentials.json', token_file='token.json'):
        """Initialize Google Drive API client"""
        self.creds = None
        self.token_file = token_file
        self.credentials_file = credentials_file
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate and create service object"""
        # Token file stores the user's access and refresh tokens
        if os.path.exists(self.token_file):
            self.creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)

        # If there are no (valid) credentials available, let the user log in
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES)
                self.creds = flow.run_local_server(port=0)

            # Save credentials for next run
            with open(self.token_file, 'w') as token:
                token.write(self.creds.to_json())

        self.service = build('drive', 'v3', credentials=self.creds)

    def list_files(self, query=None, page_size=10):
        """
        List files in Google Drive

        Args:
            query: Optional query string (e.g., "name contains 'document'")
            page_size: Number of files to return

        Returns:
            List of file dictionaries
        """
        try:
            results = self.service.files().list(
                pageSize=page_size,
                q=query,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)"
            ).execute()

            files = results.get('files', [])

            if not files:
                print('No files found.')
                return []

            print('Files:')
            for file in files:
                print(f"- {file['name']} ({file['id']}) - {file.get('mimeType', 'N/A')}")

            return files

        except HttpError as error:
            print(f'An error occurred: {error}')
            return []

    def upload_file(self, file_path, folder_id=None):
        """
        Upload a file to Google Drive

        Args:
            file_path: Path to local file
            folder_id: Optional folder ID to upload to

        Returns:
            File ID of uploaded file
        """
        try:
            file_metadata = {'name': os.path.basename(file_path)}
            if folder_id:
                file_metadata['parents'] = [folder_id]

            media = MediaFileUpload(file_path, resumable=True)

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name'
            ).execute()

            print(f"File uploaded: {file.get('name')} (ID: {file.get('id')})")
            return file.get('id')

        except HttpError as error:
            print(f'An error occurred: {error}')
            return None

    def download_file(self, file_id, destination_path):
        """
        Download a file from Google Drive

        Args:
            file_id: Google Drive file ID
            destination_path: Local path to save file

        Returns:
            Boolean indicating success
        """
        try:
            request = self.service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                print(f"Download {int(status.progress() * 100)}%")

            # Write to file
            fh.seek(0)
            with open(destination_path, 'wb') as f:
                f.write(fh.read())

            print(f"File downloaded to: {destination_path}")
            return True

        except HttpError as error:
            print(f'An error occurred: {error}')
            return False

    def create_folder(self, folder_name, parent_folder_id=None):
        """
        Create a folder in Google Drive

        Args:
            folder_name: Name of folder to create
            parent_folder_id: Optional parent folder ID

        Returns:
            Folder ID of created folder
        """
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]

            folder = self.service.files().create(
                body=file_metadata,
                fields='id, name'
            ).execute()

            print(f"Folder created: {folder.get('name')} (ID: {folder.get('id')})")
            return folder.get('id')

        except HttpError as error:
            print(f'An error occurred: {error}')
            return None

    def delete_file(self, file_id):
        """
        Delete a file or folder from Google Drive

        Args:
            file_id: File or folder ID to delete

        Returns:
            Boolean indicating success
        """
        try:
            self.service.files().delete(fileId=file_id).execute()
            print(f"File/Folder deleted: {file_id}")
            return True

        except HttpError as error:
            print(f'An error occurred: {error}')
            return False

    def search_files(self, search_term):
        """
        Search for files by name

        Args:
            search_term: Term to search for in file names

        Returns:
            List of matching files
        """
        query = f"name contains '{search_term}'"
        return self.list_files(query=query)

    def get_file_metadata(self, file_id):
        """
        Get detailed metadata for a file

        Args:
            file_id: File ID

        Returns:
            File metadata dictionary
        """
        try:
            file = self.service.files().get(
                fileId=file_id,
                fields='*'
            ).execute()

            print(f"File: {file.get('name')}")
            print(f"  ID: {file.get('id')}")
            print(f"  Type: {file.get('mimeType')}")
            print(f"  Size: {file.get('size', 'N/A')} bytes")
            print(f"  Modified: {file.get('modifiedTime')}")
            print(f"  Owners: {[o.get('displayName') for o in file.get('owners', [])]}")

            return file

        except HttpError as error:
            print(f'An error occurred: {error}')
            return None


def main():
    """Example usage of Google Drive API"""

    # Initialize API client
    # You need to download credentials.json from Google Cloud Console first
    drive = GoogleDriveAPI()

    # Example operations
    print("\n=== Listing files ===")
    drive.list_files(page_size=5)

    print("\n=== Searching for files ===")
    drive.search_files("document")

    # Example: Upload a file
    # file_id = drive.upload_file("/path/to/local/file.txt")

    # Example: Download a file
    # drive.download_file("file_id_here", "/path/to/save/file.txt")

    # Example: Create a folder
    # folder_id = drive.create_folder("My New Folder")

    # Example: Delete a file
    # drive.delete_file("file_id_here")


if __name__ == "__main__":
    main()