# Google Drive Programmatic Access Guide

## Method 1: Google Drive API (Python)

### Setup Instructions

1. **Enable Google Drive API:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable Google Drive API in the API Library
   - Create credentials (OAuth 2.0 Client ID)
   - Download credentials as `credentials.json`

2. **Install Required Libraries:**

   ```bash
   pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
   ```

3. **Run the Python Script:**
   ```bash
   python google_drive_api.py
   ```

### Quick Usage Examples

```python
from google_drive_api import GoogleDriveAPI

# Initialize
drive = GoogleDriveAPI()

# List files
files = drive.list_files()

# Upload a file
file_id = drive.upload_file("/path/to/file.pdf")

# Download a file
drive.download_file("file_id_here", "/path/to/save/file.pdf")

# Create folder
folder_id = drive.create_folder("New Folder")

# Search files
results = drive.search_files("report")
```

## Method 2: Terminal/CLI Tools

### 1. **rclone** (Most Popular)

#### Installation:

```bash
# macOS
brew install rclone

# Linux
curl https://rclone.org/install.sh | sudo bash

# Configure Google Drive
rclone config
# Follow prompts to add Google Drive remote
```

#### Common Commands:

```bash
# List files
rclone ls remote:
rclone ls remote:folder/

# Copy file to Google Drive
rclone copy /local/file.txt remote:
rclone copy /local/folder remote:destination/

# Sync folder (one-way)
rclone sync /local/folder remote:backup/

# Download from Google Drive
rclone copy remote:file.txt /local/destination/

# Mount Google Drive as filesystem
rclone mount remote: ~/gdrive/

# Show disk usage
rclone size remote:

# Delete files
rclone delete remote:file.txt

# Move files
rclone move /local/file.txt remote:folder/
```

### 2. **gdrive** (Simple CLI tool)

#### Installation:

```bash
# Download from GitHub releases
# https://github.com/prasmussen/gdrive

# macOS example
brew install gdrive

# Or download binary
wget -O gdrive "https://github.com/prasmussen/gdrive/releases/download/2.1.1/gdrive_2.1.1_darwin_amd64.tar.gz"
tar -xvf gdrive
chmod +x gdrive
sudo mv gdrive /usr/local/bin/
```

#### Common Commands:

```bash
# List files
gdrive list

# Upload file
gdrive upload file.txt

# Download file
gdrive download [FILE_ID]

# Create folder
gdrive mkdir "Folder Name"

# Share file
gdrive share [FILE_ID]

# Info about file
gdrive info [FILE_ID]

# Delete file
gdrive delete [FILE_ID]
```

### 3. **Google's Official gcloud CLI**

#### Installation:

```bash
# Install Google Cloud SDK
curl https://sdk.cloud.google.com | bash

# Initialize
gcloud init

# Install gsutil for storage operations
gcloud components install gsutil
```

#### Common Commands:

```bash
# Note: gsutil works with Google Cloud Storage, not Drive directly
# But you can use it for similar cloud storage needs

# List buckets
gsutil ls

# Copy file to bucket
gsutil cp file.txt gs://bucket-name/

# Download from bucket
gsutil cp gs://bucket-name/file.txt .

# Sync folders
gsutil rsync -r local-folder gs://bucket-name/folder/
```

## Method 3: Node.js Implementation

### Installation:

```bash
npm install googleapis
```

### Example Script:

```javascript
const { google } = require("googleapis");
const fs = require("fs");
const readline = require("readline");

// Setup OAuth2 client
const oauth2Client = new google.auth.OAuth2(
  CLIENT_ID,
  CLIENT_SECRET,
  REDIRECT_URL
);

// Initialize Drive API
const drive = google.drive({ version: "v3", auth: oauth2Client });

// List files
async function listFiles() {
  const res = await drive.files.list({
    pageSize: 10,
    fields: "files(id, name)",
  });
  return res.data.files;
}

// Upload file
async function uploadFile(filename) {
  const fileMetadata = { name: filename };
  const media = {
    mimeType: "text/plain",
    body: fs.createReadStream(filename),
  };

  const res = await drive.files.create({
    resource: fileMetadata,
    media: media,
    fields: "id",
  });
  return res.data.id;
}
```

## Method 4: Using curl with Google Drive API

### Direct API calls:

```bash
# Get access token first (requires OAuth setup)
ACCESS_TOKEN="your_access_token"

# List files
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://www.googleapis.com/drive/v3/files"

# Upload file (metadata)
curl -X POST -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "test.txt"}' \
  "https://www.googleapis.com/drive/v3/files"

# Download file
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://www.googleapis.com/drive/v3/files/FILE_ID?alt=media" \
  -o output.txt
```

## Quick Decision Guide

| Method         | Best For                       | Pros                              | Cons                     |
| -------------- | ------------------------------ | --------------------------------- | ------------------------ |
| **rclone**     | Regular backups, syncing       | Feature-rich, mount as filesystem | Initial setup complexity |
| **gdrive**     | Quick uploads/downloads        | Simple commands                   | Less maintained          |
| **Python API** | Automation, complex operations | Full API access                   | Requires coding          |
| **Node.js**    | Web applications               | Async operations                  | Requires coding          |
| **curl**       | Scripts, simple operations     | No dependencies                   | Manual token management  |

## Common Use Cases

### 1. Automated Backup Script (bash + rclone)

```bash
#!/bin/bash
# backup.sh
DATE=$(date +%Y%m%d)
rclone sync ~/Documents remote:backup/$DATE/ --progress
```

### 2. Watch Folder and Auto-upload (Python)

```python
import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from google_drive_api import GoogleDriveAPI

class UploadHandler(FileSystemEventHandler):
    def __init__(self):
        self.drive = GoogleDriveAPI()

    def on_created(self, event):
        if not event.is_directory:
            self.drive.upload_file(event.src_path)

if __name__ == "__main__":
    path = "/path/to/watch"
    event_handler = UploadHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
```

### 3. Sync Multiple Folders (rclone)

```bash
# Create config file: sync_folders.txt
/home/user/Documents:backup/documents
/home/user/Pictures:backup/pictures
/home/user/Projects:backup/projects

# Sync script
while IFS=: read -r local remote; do
    rclone sync "$local" "remote:$remote" --progress
done < sync_folders.txt
```

## Security Best Practices

1. **Never commit credentials.json or token.json to git**
2. **Use environment variables for sensitive data:**

   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials.json"
   ```

3. **Implement token refresh logic**
4. **Use service accounts for server applications**
5. **Limit OAuth scopes to minimum required**

## Troubleshooting

### Common Issues:

1. **"Insufficient Permission" Error:**
   - Check OAuth scopes
   - Verify file ownership

2. **"Quota Exceeded" Error:**
   - Implement exponential backoff
   - Check API quotas in Google Cloud Console

3. **Token Expired:**
   - Implement automatic token refresh
   - Re-authenticate if refresh token is invalid

4. **Large File Uploads:**
   - Use resumable uploads
   - Implement chunked upload for files > 5MB

## Additional Resources

- [Google Drive API Documentation](https://developers.google.com/drive/api/v3/about-sdk)
- [rclone Documentation](https://rclone.org/drive/)
- [Google API Python Client](https://github.com/googleapis/google-api-python-client)
- [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/)
