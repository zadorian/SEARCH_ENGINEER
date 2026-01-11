from anthropic import Anthropic
from docx2pdf import convert
from pathlib import Path
import os

DOCX_PATH = "/Users/brain/Report_Library/consolidated_docx/Consolidated/1..docx"
PDF_PATH = DOCX_PATH.replace('.docx', '.pdf')

print("Converting DOCX to PDF...")
convert(DOCX_PATH, PDF_PATH)
print(f"Created: {PDF_PATH}")

print("\nSending PDF to Claude...")
client = Anthropic(
    api_key="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",
    default_headers={"anthropic-beta": "pdfs-2024-09-25"}
)

with open(PDF_PATH, "rb") as f:
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Extract all footnotes and their URLs from this document. Also note where each footnote appears in the text."
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": f.read().encode('base64').decode()
                    }
                }
            ]
        }]
    )

print("\nResponse:", response.content)

# Clean up
os.remove(PDF_PATH)
print("\nCleaned up temporary PDF")