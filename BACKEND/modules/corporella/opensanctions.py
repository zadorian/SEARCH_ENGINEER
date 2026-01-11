import requests
import json

# Function to search for a person in the OpenSanctions database
def opensanctions_search(name):
    # Replace 'YOUR_API_KEY' with your actual OpenSanctions API key
    api_key = '1d6a91c9f96eb9594a3bb81cdcc37bd7'
    base_url = 'https://api.opensanctions.org/search/default'  # Ensure the URL is correct
    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    params = {
        'q': name,  # The name of the person to search for
        'nested': 'true'
    }
    
    try:
        response = requests.get(base_url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if response.status_code == 404:
            return {"detail": "Not Found"}
        else:
            raise Exception(f'Error: {response.status_code}, {response.text}')
    except requests.exceptions.RequestException as e:
        raise Exception(f'Error: {str(e)}')

# Main function to run the script
def main():
    name = input("Enter the name of the person to search: ")
    try:
        result = opensanctions_search(name)
        if result.get("detail") == "Not Found":
            print("The person could not be found in the OpenSanctions database.")
        else:
            print(json.dumps(result, indent=2))
    except Exception as e:
        print(str(e))

if __name__ == "__main__":
    main()