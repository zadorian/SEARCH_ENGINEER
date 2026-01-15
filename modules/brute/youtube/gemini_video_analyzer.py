import os
import argparse
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_client():
    """Initialize and return the GenAI client."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set.")
    return genai.Client(api_key=api_key)

def analyze_youtube_url(url, prompt, model_id="gemini-2.0-flash"):
    """
    Analyzes a YouTube video by passing the URL directly to Gemini.
    Note: This is a preview feature.
    """
    client = get_client()
    print(f"--- Analyzing YouTube URL: {url} ---")
    print(f"Model: {model_id}")
    print(f"Prompt: {prompt}")

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=types.Content(
                parts=[
                    types.Part(
                        file_data=types.FileData(
                            file_uri=url
                        )
                    ),
                    types.Part(text=prompt)
                ]
            )
        )
        return response.text
    except Exception as e:
        return f"Error processing YouTube URL: {e}"

def analyze_local_video(file_path, prompt, model_id="gemini-2.0-flash"):
    """
    Uploads a local video file using the Files API and analyzes it.
    """
    client = get_client()
    print(f"--- Analyzing Local Video: {file_path} ---")
    print(f"Model: {model_id}")
    print("Uploading file...")

    try:
        # Upload the file
        video_file = client.files.upload(file=file_path)
        print(f"File uploaded: {video_file.name}")

        # Wait for processing to complete
        while video_file.state.name == "PROCESSING":
            print("Processing video...", end="\r")
            time.sleep(2)
            video_file = client.files.get(name=video_file.name)

        if video_file.state.name == "FAILED":
            raise ValueError("Video processing failed.")

        print("Video processing complete. Generating content...")

        # Generate content
        response = client.models.generate_content(
            model=model_id,
            contents=[video_file, prompt]
        )
        
        # Cleanup (optional, but good practice if not reusing)
        # client.files.delete(name=video_file.name) 
        
        return response.text

    except Exception as e:
        return f"Error processing local video: {e}"

def main():
    parser = argparse.ArgumentParser(description="Gemini Video Analyzer (YouTube & Local)")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="YouTube Video URL")
    group.add_argument("--file", help="Path to local video file")
    
    parser.add_argument("--prompt", help="Prompt for the model", default="Summarize this video in detail.")
    parser.add_argument("--model", help="Gemini model to use", default="gemini-2.0-flash")

    args = parser.parse_args()

    result = None
    if args.url:
        result = analyze_youtube_url(args.url, args.prompt, args.model)
    elif args.file:
        result = analyze_local_video(args.file, args.prompt, args.model)

    print("\n--- Result ---\n")
    print(result)

if __name__ == "__main__":
    main()
