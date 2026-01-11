from .base_variator import BaseVariator
from typing import List
import re

class CompanyVariator(BaseVariator):
    """Handles company name variations"""
    
    def __init__(self):
        super().__init__()
        self.name = "company"
        
    def get_prompt(self, name: str) -> str:
        """Generate prompt for company variations"""
        return f"""
        Generate comprehensive variations of this company name: {name}
        
        Include:
        1. Abbreviated and formal versions (Inc/Incorporated, Corp/Corporation, etc.)
        2. Common alternative spellings and acronyms
        3. Subsidiary and parent company variations where applicable
        4. Transliterations into major scripts:
           - Cyrillic (Russian): Use standard Russian transliteration
           - Arabic: Include vowel markers, transliterate business terms appropriately
           - Hebrew: Use standard Hebrew transliteration
           - Georgian: Use Georgian script
           - Chinese (Simplified): Use Mandarin phonetic transliteration, include 公司 where appropriate
           - Korean (Hangul): Use standard Korean phonetic transliteration
           - Japanese (Katakana): Use katakana for foreign company names
           - Armenian: Use Armenian script
        
        Examples for "Apple Inc":
        ["Apple Inc", "Apple Incorporated", "Apple", "Apple Computer", "Apple Corp", "Эппл Инк", "أبل إنك", "אפל אינק", "ეპლ ინკ", "苹果公司", "애플 인크", "アップル・インク", "Փքիլ Ինք"]
        
        Examples for "Microsoft Corporation":
        ["Microsoft Corporation", "Microsoft Corp", "Microsoft", "MSFT", "MS", "Майкрософт Корпорейшн", "مايكروسوفت كوربوريشن", "מיקרוסופט קורפוריישן", "მაიკროსოფტ კორპორაცია", "微软公司", "마이크로소프트 코퍼레이션", "マイクロソフト・コーポレーション", "Մայքրոսոֆթ Կորպորեյշն"]
        
        Return ONLY a JSON array of strings.
        """
        
    def generate_variations(self, name: str) -> List[str]:
        """Generate comprehensive company variations including AI transliterations"""
        # Start with fallback variations
        variations = self.fallback_variations(name)
        
        # Use the base class method which calls AI
        ai_variations = super().generate_variations(name)
        
        # Combine and deduplicate
        all_variations = variations + ai_variations
        seen = set()
        unique_variations = []
        for var in all_variations:
            if var not in seen and var.strip():
                seen.add(var)
                unique_variations.append(var)
        
        return unique_variations
        
    def fallback_variations(self, name: str) -> List[str]:
        """Generate basic company name variations as fallback"""
        variations = []
        
        # Always include the original
        variations.append(name)
        
        # Common company designators with their alternatives
        designator_mappings = {
            " Inc": [" Incorporated", " Inc.", ", Inc.", ", Incorporated"],
            " LLC": [" Limited Liability Company", ", LLC"],
            " Ltd": [" Limited", ", Ltd.", ", Limited"],
            " Corp": [" Corporation", ", Corp.", ", Corporation"],
            " Corporation": [" Corp", " Corp.", ", Corporation", ", Corp"],
            " Limited": [" Ltd", " Ltd.", ", Limited", ", Ltd"],
            " Co": [" Company", " Co.", ", Co.", ", Company"],
            " Company": [" Co", " Co.", ", Company", ", Co"],
            " GmbH": [", GmbH"],  # German
            " AG": [", AG"],      # German/Swiss
            " SA": [", SA"],      # French/Spanish
            " SAS": [", SAS"],    # French
            " SRL": [", SRL"],    # Italian/Romanian
            " BV": [", BV"],      # Dutch
            " AB": [", AB"],      # Swedish
            " AS": [", AS"],      # Norwegian/Danish
            " Oy": [", Oy"],      # Finnish
            " SpA": [", SpA"],    # Italian
            " NV": [", NV"]       # Dutch/Belgian
        }
        
        # Try removing/replacing company designators
        clean_name = name
        found_designator = None
        
        for designator, alternatives in designator_mappings.items():
            if name.endswith(designator):
                clean_name = name.replace(designator, "").strip()
                found_designator = designator
                # Add alternatives
                for alt in alternatives:
                    if alt.startswith(","):
                        variations.append(f"{clean_name}{alt}")
                    else:
                        variations.append(f"{clean_name}{alt}")
                break
        
        # Add the clean version if different from original
        if clean_name != name:
            variations.append(clean_name)
        
        # Add common acronym variations for well-known patterns
        words = clean_name.split()
        if len(words) >= 2:
            # Create acronym from first letters
            acronym = "".join(word[0].upper() for word in words if word and word[0].isalpha())
            if len(acronym) >= 2 and acronym != clean_name:
                variations.append(acronym)
        
        # Add "The" prefix variations
        if not name.lower().startswith("the "):
            variations.append(f"The {name}")
            if clean_name != name:
                variations.append(f"The {clean_name}")
        else:
            # Remove "The" prefix
            without_the = name[4:].strip()
            variations.append(without_the)
        
        return variations
