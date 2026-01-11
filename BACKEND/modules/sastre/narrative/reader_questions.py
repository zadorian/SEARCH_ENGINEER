"""
SASTRE Reader Questions Generator - Anticipate audience questions.

"What would a reader ask at this point?"

The reader is the quality control mechanism:
- They don't have your context
- They will question claims without evidence
- They will wonder about gaps you've normalized
- They expect certain standard information

This generates the questions a reader WOULD ask, which become
investigation priorities.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


# =============================================================================
# READER QUESTION TYPES
# =============================================================================

class QuestionType(Enum):
    """Types of reader questions."""
    SOURCING = "sourcing"            # "How do you know this?"
    COMPLETENESS = "completeness"    # "What about X?"
    VERIFICATION = "verification"    # "Is this confirmed?"
    CONTEXT = "context"              # "Why does this matter?"
    TIMELINE = "timeline"            # "When did this happen?"
    QUANTIFICATION = "quantification"  # "How much/many?"
    COMPARISON = "comparison"        # "How does this compare to...?"
    IMPLICATION = "implication"      # "What does this mean?"
    CONTRADICTION = "contradiction"  # "But didn't you say...?"
    ALTERNATIVE = "alternative"      # "What about other explanations?"


class QuestionPriority(Enum):
    """Priority levels for reader questions."""
    BLOCKING = "blocking"    # Report cannot publish without answer
    HIGH = "high"            # Report is incomplete without answer
    MEDIUM = "medium"        # Answer would strengthen report
    LOW = "low"              # Nice to have


# =============================================================================
# READER QUESTION
# =============================================================================

@dataclass
class ReaderQuestion:
    """A question a reader would ask."""
    question: str
    question_type: QuestionType
    priority: QuestionPriority
    trigger: str                     # What in the narrative triggered this
    trigger_location: str            # Section/paragraph reference
    suggested_sources: List[str] = field(default_factory=list)
    suggested_query: Optional[str] = None
    answerable_from_corpus: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# EXPECTED INFORMATION BY ENTITY TYPE
# =============================================================================

# What readers expect to know about different entity types
EXPECTED_INFO = {
    'person': {
        'blocking': ['full_name', 'role_in_investigation'],
        'high': ['nationality', 'dob', 'current_location', 'occupation'],
        'medium': ['education', 'career_history', 'family_status'],
        'low': ['photos', 'social_media', 'hobbies'],
    },
    'company': {
        'blocking': ['legal_name', 'jurisdiction', 'role_in_investigation'],
        'high': ['incorporation_date', 'status', 'registered_address', 'officers'],
        'medium': ['shareholders', 'financials', 'business_activity'],
        'low': ['history', 'subsidiaries', 'competitors'],
    },
    'transaction': {
        'blocking': ['amount', 'parties', 'date'],
        'high': ['purpose', 'source_of_funds', 'destination'],
        'medium': ['intermediaries', 'related_transactions'],
        'low': ['regulatory_filings', 'bank_details'],
    },
    'event': {
        'blocking': ['what_happened', 'when', 'who_involved'],
        'high': ['where', 'why', 'consequences'],
        'medium': ['witnesses', 'documentation'],
        'low': ['media_coverage', 'reactions'],
    },
}

# Standard questions readers ask about claims
STANDARD_QUESTIONS = {
    'sourcing': [
        "How do you know this?",
        "Who said this?",
        "Is there documentation?",
        "Can this be independently verified?",
    ],
    'completeness': [
        "What else is relevant here?",
        "Are there other parties involved?",
        "What happened before/after?",
        "What's the full picture?",
    ],
    'verification': [
        "Has this been confirmed?",
        "Are there multiple sources?",
        "Could this be wrong?",
        "What's the confidence level?",
    ],
    'context': [
        "Why does this matter?",
        "What's the significance?",
        "How does this fit the larger story?",
        "What are the implications?",
    ],
}


# =============================================================================
# READER QUESTION GENERATOR
# =============================================================================

class ReaderQuestionGenerator:
    """
    Generates questions a reader would ask about a narrative.

    Operates at multiple levels:
    1. Entity level - What's missing about each entity?
    2. Section level - What's unsupported in each section?
    3. Narrative level - What's the overall story missing?
    """

    def __init__(self):
        self.expected_info = EXPECTED_INFO
        self.standard_questions = STANDARD_QUESTIONS

    def generate(
        self,
        narrative_content: str,
        entities: List[Dict[str, Any]] = None,
        sections: List[Dict[str, Any]] = None
    ) -> List[ReaderQuestion]:
        """
        Generate reader questions for a narrative.
        """
        questions = []

        # 1. Entity-level questions
        if entities:
            for entity in entities:
                entity_questions = self._generate_entity_questions(entity)
                questions.extend(entity_questions)

        # 2. Section-level questions
        if sections:
            for section in sections:
                section_questions = self._generate_section_questions(section)
                questions.extend(section_questions)
        elif narrative_content:
            # Parse sections from content
            parsed_sections = self._parse_sections(narrative_content)
            for section in parsed_sections:
                section_questions = self._generate_section_questions(section)
                questions.extend(section_questions)

        # 3. Narrative-level questions
        narrative_questions = self._generate_narrative_questions(
            narrative_content, entities or []
        )
        questions.extend(narrative_questions)

        # 4. Claim-level questions (sourcing)
        claim_questions = self._generate_claim_questions(narrative_content)
        questions.extend(claim_questions)

        # Sort by priority
        priority_order = {
            QuestionPriority.BLOCKING: 0,
            QuestionPriority.HIGH: 1,
            QuestionPriority.MEDIUM: 2,
            QuestionPriority.LOW: 3,
        }
        questions.sort(key=lambda q: priority_order[q.priority])

        return questions

    def _generate_entity_questions(
        self,
        entity: Dict[str, Any]
    ) -> List[ReaderQuestion]:
        """Generate questions about what's missing for an entity."""
        questions = []

        entity_type = entity.get('type', 'person')
        entity_name = entity.get('name', entity.get('display_name', 'Unknown'))
        entity_data = entity.get('data', entity)

        expected = self.expected_info.get(entity_type, self.expected_info['person'])

        # Check blocking information
        for field in expected.get('blocking', []):
            if not entity_data.get(field):
                questions.append(ReaderQuestion(
                    question=f"What is the {field.replace('_', ' ')} of {entity_name}?",
                    question_type=QuestionType.COMPLETENESS,
                    priority=QuestionPriority.BLOCKING,
                    trigger=f"Entity '{entity_name}' mentioned",
                    trigger_location=f"entity:{entity.get('id', entity_name)}",
                    suggested_query=f'"{entity_name}" {field.replace("_", " ")}',
                ))

        # Check high-priority information
        for field in expected.get('high', []):
            if not entity_data.get(field):
                questions.append(ReaderQuestion(
                    question=f"What is the {field.replace('_', ' ')} of {entity_name}?",
                    question_type=QuestionType.COMPLETENESS,
                    priority=QuestionPriority.HIGH,
                    trigger=f"Entity '{entity_name}' mentioned",
                    trigger_location=f"entity:{entity.get('id', entity_name)}",
                    suggested_query=f'"{entity_name}" {field.replace("_", " ")}',
                ))

        return questions

    def _generate_section_questions(
        self,
        section: Dict[str, Any]
    ) -> List[ReaderQuestion]:
        """Generate questions about a section's completeness."""
        questions = []

        section_title = section.get('title', '')
        section_content = section.get('content', '')

        # Check if section is empty
        if not section_content or len(section_content.strip()) < 50:
            questions.append(ReaderQuestion(
                question=f"What should go in the '{section_title}' section?",
                question_type=QuestionType.COMPLETENESS,
                priority=QuestionPriority.BLOCKING,
                trigger=f"Empty section: {section_title}",
                trigger_location=f"section:{section_title}",
            ))
            return questions

        # Check for unsourced claims
        claims = self._extract_claims(section_content)
        for claim in claims:
            if not claim.get('sourced'):
                questions.append(ReaderQuestion(
                    question=f"What is the source for: \"{claim['text'][:100]}...\"?",
                    question_type=QuestionType.SOURCING,
                    priority=QuestionPriority.HIGH,
                    trigger=claim['text'][:100],
                    trigger_location=f"section:{section_title}",
                ))

        # Check for vague quantifications
        vague_terms = ['several', 'many', 'some', 'numerous', 'various', 'significant']
        for term in vague_terms:
            if term in section_content.lower():
                questions.append(ReaderQuestion(
                    question=f"Can you quantify '{term}' more precisely?",
                    question_type=QuestionType.QUANTIFICATION,
                    priority=QuestionPriority.MEDIUM,
                    trigger=f"Vague term: {term}",
                    trigger_location=f"section:{section_title}",
                ))

        return questions

    def _generate_narrative_questions(
        self,
        content: str,
        entities: List[Dict[str, Any]]
    ) -> List[ReaderQuestion]:
        """Generate questions about the overall narrative."""
        questions = []

        # Check for timeline gaps
        if 'timeline' not in content.lower() and len(entities) > 0:
            questions.append(ReaderQuestion(
                question="What is the chronological timeline of events?",
                question_type=QuestionType.TIMELINE,
                priority=QuestionPriority.MEDIUM,
                trigger="No explicit timeline found",
                trigger_location="narrative",
            ))

        # Check for relationship clarity
        if len(entities) > 1:
            questions.append(ReaderQuestion(
                question="How are all the mentioned parties connected?",
                question_type=QuestionType.CONTEXT,
                priority=QuestionPriority.HIGH,
                trigger="Multiple entities without clear relationship map",
                trigger_location="narrative",
            ))

        # Check for conclusion/implications
        if not any(word in content.lower() for word in ['therefore', 'conclusion', 'implication', 'significance']):
            questions.append(ReaderQuestion(
                question="What are the key conclusions and implications?",
                question_type=QuestionType.IMPLICATION,
                priority=QuestionPriority.MEDIUM,
                trigger="No explicit conclusions",
                trigger_location="narrative",
            ))

        return questions

    def _generate_claim_questions(self, content: str) -> List[ReaderQuestion]:
        """Generate sourcing questions for specific claims."""
        questions = []

        # Look for strong claims without citations
        strong_claim_patterns = [
            'is known to',
            'allegedly',
            'reportedly',
            'according to',
            'is believed to',
            'is suspected of',
            'was involved in',
            'controlled by',
            'owned by',
        ]

        for pattern in strong_claim_patterns:
            if pattern in content.lower():
                # Find the sentence containing this
                sentences = content.split('.')
                for sentence in sentences:
                    if pattern in sentence.lower():
                        # Check if it has a citation marker
                        if '[' not in sentence and '(' not in sentence:
                            questions.append(ReaderQuestion(
                                question=f"What is the source for: \"{sentence.strip()[:100]}\"?",
                                question_type=QuestionType.SOURCING,
                                priority=QuestionPriority.HIGH,
                                trigger=pattern,
                                trigger_location="narrative",
                            ))
                        break

        return questions

    def _parse_sections(self, content: str) -> List[Dict[str, Any]]:
        """Parse sections from markdown content."""
        sections = []
        current_section = None
        current_content = []

        for line in content.split('\n'):
            if line.startswith('#'):
                # Save previous section
                if current_section:
                    sections.append({
                        'title': current_section,
                        'content': '\n'.join(current_content),
                    })
                # Start new section
                current_section = line.lstrip('#').strip()
                current_content = []
            else:
                current_content.append(line)

        # Save last section
        if current_section:
            sections.append({
                'title': current_section,
                'content': '\n'.join(current_content),
            })

        return sections

    def _extract_claims(self, content: str) -> List[Dict[str, Any]]:
        """Extract factual claims from content."""
        claims = []

        # Simple heuristic: sentences with "is", "was", "has", "have" are claims
        sentences = content.replace('\n', ' ').split('.')

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20:  # Skip short sentences
                # Check if it's a factual claim
                claim_words = ['is', 'was', 'are', 'were', 'has', 'have', 'had', 'owns', 'owned']
                if any(f' {w} ' in f' {sentence.lower()} ' for w in claim_words):
                    # Check if sourced (has citation marker)
                    sourced = '[' in sentence or '(' in sentence or 'according to' in sentence.lower()
                    claims.append({
                        'text': sentence,
                        'sourced': sourced,
                    })

        return claims


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def generate_reader_questions(
    narrative_content: str,
    entities: List[Dict[str, Any]] = None,
    sections: List[Dict[str, Any]] = None
) -> List[ReaderQuestion]:
    """Generate reader questions for a narrative."""
    return ReaderQuestionGenerator().generate(narrative_content, entities, sections)
