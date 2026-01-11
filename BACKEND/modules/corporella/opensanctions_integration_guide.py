#!/usr/bin/env python3
"""
Instructions to integrate OpenSanctions into the main corporate search app
"""

print("""
OpenSanctions Integration - Upgrade Instructions
===============================================

1. The enhanced version with OpenSanctions is in: corporate_search_main_v2.py

2. To upgrade your existing app:
   - Backup your current corporate_search_main.py
   - Review the changes in corporate_search_main_v2.py
   - Key additions:
     * OpenSanctionsAPI class for API integration
     * _search_opensanctions() method in CorporateSearchSystem
     * check_sanctions() dedicated sanctions checking method
     * Updated SearchResult dataclass with sanctions_info field
     * Enhanced report generation with sanctions alerts

3. Obtain an OpenSanctions API key from https://opensanctions.org and make sure it is available to the application.

4. To test the integration:
   python3 test_opensanctions_integration.py

5. Main features added:
   - Automatic sanctions screening in "Search all sources"
   - Dedicated sanctions check option in menu
   - Sanctions alerts in reports (⚠️ symbol)
   - Support for both Person and Company entity types
   - Match scoring and dataset attribution

6. The OpenCorporates integration is already working (despite what I said earlier!)
   - It's properly integrated in the search methods
   - Just needs the right API key in environment variables

7. To use in production:
   - Set environment variables for API keys:
     export OPENSANCTIONS_API_KEY=your_key_here
     export COMPANIES_HOUSE_API_KEY=your_companies_house_key  # legacy CH_API_KEY still supported
     export OC_API_KEY=your_opencorporates_key
   
8. Menu items to update:
   - Option 5 "Check sanctions lists" now works
   - Search all sources now includes OpenSanctions by default

Would you like to:
a) Replace the main app with the v2 version?
b) Manually merge the changes?
c) Keep both versions for now?
""")
