import sys
import os
import json
from pathlib import Path

# Add parent directory to path to import utils
sys.path.append(str(Path(__file__).parent.parent.parent))

try:
    from utils.ftm_converter import FtMConverter
except ImportError:
    print("Could not import FtMConverter. Make sure followthemoney is installed.")
    sys.exit(1)

def test_conversion():
    print("Initializing FtM Converter...")
    converter = FtMConverter()
    
    # Test Data: Simulating a Drill Search "Company" node
    drill_company = {
        "name": "Drill Search Industries Ltd",
        "jurisdiction": "gb",
        "registration_number": "01234567",
        "incorporation_date": "2023-01-01",
        "status": "Active",
        "address": "123 Data Street, London"
    }
    
    print(f"\nConverting Company: {drill_company['name']}")
    ftm_company = converter.convert_drill_node("company", drill_company, drill_id="drill-comp-001")
    
    if ftm_company:
        print("✓ Success!")
        print(json.dumps(ftm_company.to_dict(), indent=2))
    else:
        print("✗ Failed to convert company")

    # Test Data: Simulating a "Person" node
    drill_person = {
        "name": "John Drill",
        "nationality": "gb",
        "birth_date": "1980-05-15"
    }
    
    print(f"\nConverting Person: {drill_person['name']}")
    ftm_person = converter.convert_drill_node("person", drill_person, drill_id="drill-person-001")
    
    if ftm_person:
        print("✓ Success!")
        print(json.dumps(ftm_person.to_dict(), indent=2))
    else:
        print("✗ Failed to convert person")

    # Test Relationship
    if ftm_company and ftm_person:
        print(f"\nConverting Relationship: Officer Of")
        rel_props = {
            "role": "Director",
            "start_date": "2023-01-01"
        }
        ftm_rel = converter.convert_relationship(
            "officer_of", 
            source_id=ftm_person.id, 
            target_id=ftm_company.id,
            properties=rel_props
        )
        
        if ftm_rel:
            print("✓ Success!")
            print(json.dumps(ftm_rel.to_dict(), indent=2))
        else:
            print("✗ Failed to convert relationship")

if __name__ == "__main__":
    test_conversion()

