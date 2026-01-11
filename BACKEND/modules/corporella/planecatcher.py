import os
import csv
import json

# Directory containing unzipped data
data_dir = "/Users/attic/Downloads/acas/"

# Mode-S code to search for
mode_s_code = "43EAA1".lower()  # Ensure lowercase for comparison

def search_csv(file_path, mode_s_code):
    """Search for the Mode-S code in a CSV file."""
    with open(file_path, 'r', encoding='utf-8') as file:
        csv_reader = csv.reader(file)
        for row in csv_reader:
            if mode_s_code in [cell.strip().lower() for cell in row]:
                print(f"Match found in {file_path}: {row}")
                return True
    return False

def search_json(file_path, mode_s_code):
    """Search for the Mode-S code in a JSON file."""
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
        if mode_s_code in json.dumps(data).lower():
            print(f"Match found in {file_path}")
            return True
    return False

def search_files(data_dir, mode_s_code):
    """Search for the Mode-S code in all files."""
    for root, _, files in os.walk(data_dir):
        for file in files:
            file_path = os.path.join(root, file)
            if file.endswith(".csv"):
                if search_csv(file_path, mode_s_code):
                    return
            elif file.endswith(".json"):
                if search_json(file_path, mode_s_code):
                    return
    print(f"No data found for Mode-S code: {mode_s_code}")

# Run the search
search_files(data_dir, mode_s_code)