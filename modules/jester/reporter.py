import logging
import os
from elastic_manager import ElasticManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Reporter")

class Reporter:
    def __init__(self, topics, index_name="jester_atoms"):
        self.elastic = ElasticManager(index_name=index_name)
        self.topics = topics

    def generate_section(self, output_file="section.md"):
        """
        Generates a clean section fragment for Smart Fill / Narrative Editor.
        Only includes the relevant content for the primary topic(s), no TOC or Unassigned.
        """
        report_lines = []
        
        # Should only be one topic in fill_section mode, but handle list
        for topic in self.topics:
            atoms = self.elastic.get_atoms_by_topic(topic)
            
            if not atoms:
                continue
                
            for atom in atoms:
                # Clean content
                content = atom['content'].replace("\n", " ").strip()
                
                # Metadata for citation
                source_title = atom.get('source_file', 'Unknown')
                source_url = atom.get('metadata', {}).get('url') or atom.get('source_location')
                
                # Format: Content [source_title](url)
                citation = ""
                if source_url and source_url.startswith('http'):
                    citation = f" [[{source_title}]({source_url})]"
                elif source_title and source_title != 'Unknown':
                    citation = f" [{source_title}]"
                    
                report_lines.append(f"{content}{citation}\n")

        with open(output_file, "w") as f:
            f.write("\n".join(report_lines))
        
        logger.info(f"Section fragment written to {output_file}")

    def generate_report(self, output_file="report.md"):
        report_lines = ["# JESTER SORTED REPORT\n"]
        
        # Aggregate Entities
        all_entities = {}
        
        # 1. Sorted Topics
        for topic in self.topics:
            atoms = self.elastic.get_atoms_by_topic(topic)
            report_lines.append(f"## 📂 {topic} ({len(atoms)} items)\n")
            
            if not atoms:
                report_lines.append("*No information found.*\n")
                continue
                
            for atom in atoms:
                source = f"{atom.get('source_file', 'unknown')}:{atom.get('source_location', '?')}"
                content = atom['content'].replace("\n", " ")
                
                # Collect entities
                for ent in atom.get("entities", []):
                    key = f"{ent['text']} ({ent['label']})"
                    all_entities[key] = all_entities.get(key, 0) + 1
                
                report_lines.append(f"- {content} *[{source}]*")
            report_lines.append("\n")

        # 2. Unassigned (The "Audit" Section)
        unassigned = self.elastic.get_unassigned_atoms()
        report_lines.append(f"## ⚠️ UNASSIGNED / CONTEXT ({len(unassigned)} items)\n")
        if unassigned:
            report_lines.append("> The following information did not strictly fit your topics but was preserved for review.\n")
            for atom in unassigned:
                source = f"{atom.get('source_file', 'unknown')}:{atom.get('source_location', '?')}"
                content = atom['content'].replace("\n", " ")
                
                # Collect entities
                for ent in atom.get("entities", []):
                    key = f"{ent['text']} ({ent['label']})"
                    all_entities[key] = all_entities.get(key, 0) + 1

                report_lines.append(f"- {content} *[{source}]*")
        else:
            report_lines.append("No unassigned items found. 100% coverage.")

        # 3. Entity Summary
        report_lines.append("\n## 🧠 ENTITIES DETECTED\n")
        if all_entities:
            sorted_entities = sorted(all_entities.items(), key=lambda x: x[1], reverse=True)
            for entity, count in sorted_entities:
                report_lines.append(f"- **{entity}**: {count} occurrences")
        else:
            report_lines.append("No entities extracted.")

        with open(output_file, "w") as f:
            f.write("\n".join(report_lines))
        
        logger.info(f"Report written to {output_file}")

    def generate_template_report(self, output_file="template_report.md"):
        """
        Generates a clean, strict report following the provided topics as headers.
        Omits Jester metadata, unassigned sections, and summaries.
        """
        report_lines = []
        
        for topic in self.topics:
            atoms = self.elastic.get_atoms_by_topic(topic)
            
            # Always write header, even if empty (to preserve template structure)
            report_lines.append(f"## {topic}\n")
            
            if not atoms:
                report_lines.append("*No information available for this section.*\n")
                continue
                
            for atom in atoms:
                # Source citation
                source_file = atom.get('source_file', 'Unknown')
                source_loc = atom.get('source_location', '?')
                source = f"{source_file}"
                if source_loc != '?':
                    source += f":{source_loc}"
                    
                content = atom['content'].replace("\n", " ").strip()
                
                # Check if URL exists
                url = atom.get('metadata', {}).get('url')
                citation = f"[{source}]"
                if url:
                    citation = f"[{source}]({url})"
                
                report_lines.append(f"- {content} *{citation}*")
            report_lines.append("\n")

        with open(output_file, "w") as f:
            f.write("\n".join(report_lines))
        
        logger.info(f"Template report written to {output_file}")

    def generate_entity_report(self, output_file="entity_report.md"):
        report_lines = ["# JESTER ENTITY REPORT\n"]
        
        # 1. Fetch all atoms and aggregate unique entities
        all_atoms = self.elastic.get_all_atoms() 
        
        unique_entities = {} 
        for atom in all_atoms:
            for entity in atom.get("entities", []):
                key = (entity["text"], entity["label"])
                unique_entities[key] = unique_entities.get(key, 0) + 1
        
        if not unique_entities:
            report_lines.append("No entities found to report on.")
            with open(output_file, "w") as f:
                f.write("\n".join(report_lines))
            logger.info(f"Entity report written to {output_file}")
            return

        # Sort entities by count
        sorted_entities = sorted(unique_entities.items(), key=lambda item: item[1], reverse=True)

        report_lines.append("---")
        report_lines.append("\n## INDEX OF ENTITIES\n")
        for (text, label), count in sorted_entities:
            report_lines.append(f"- **{text}** ({label}) - {count} mentions")
        report_lines.append("---\n")

        # 2. For each unique entity, find all its mentions
        for (entity_text, entity_label), count in sorted_entities:
            report_lines.append(f"## 👤 {entity_text} ({entity_label}) - {count} mentions\n")
            
            # Query Elastic
            mentions = self.elastic.get_atoms_by_entity(entity_text, entity_label)
            
            if not mentions:
                report_lines.append("*No direct mentions found in processed atoms.*\n")
                continue
            
            for atom in mentions:
                source = f"{atom.get('source_file', 'unknown')}:{atom.get('source_location', '?')}"
                content = atom['content'].replace("\n", " ")
                report_lines.append(f"- {content} *[{source}]*")
            report_lines.append("\n")

        with open(output_file, "w") as f:
            f.write("\n".join(report_lines))
        
        logger.info(f"Entity report written to {output_file}")

if __name__ == "__main__":
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    topics = ["Financial Crimes", "Personal Life"]
    r = Reporter(topics)
    r.generate_report()