import sys
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "python-backend"))

from brute.adapter.drill_search_adapter import DrillSearchAdapter

def demo_arbitrage_search():
    print("🕵️  Cymonides Arbitrage Discovery Demo")
    print("=======================================")
    
    adapter = DrillSearchAdapter()
    
    # The query targets the specific "Arbitrage Opportunity" text we injected
    query = "databases disclosing shareholders and subsidiaries in offshore jurisdictions"
    print(f"\n🔍 Query: '{query}'")
    
    # We filter for 'resource' class (Registries/Capabilities) and 'logic' class (Rules)
    # Actually, let's just search everything to see the cross-pollination.
    results = adapter.search_semantic(query, k=15)
    
    print(f"\n✅ Found {len(results)} potential opportunities:\n")
    
    for i, res in enumerate(results):
        score = res.get('score', 0)
        label = res.get('label', 'Unknown')
        content = res.get('content', '')
        
        # Extract the arbitrage hint if present
        hint = ""
        if "Arbitrage Opportunity:" in content:
            start = content.find("Arbitrage Opportunity:")
            hint = content[start:].split('\n')[0]
            
        print(f"{i+1}. [{score:.3f}] {label}")
        if hint:
            print(f"   💡 {hint}")
        else:
            # Print a snippet of content
            snippet = content[:150].replace('\n', ' ')
            print(f"   📄 {snippet}...")
        print()

if __name__ == "__main__":
    demo_arbitrage_search()

