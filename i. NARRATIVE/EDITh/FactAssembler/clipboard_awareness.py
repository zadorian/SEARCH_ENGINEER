import sys
import time
import click
import json
from datetime import datetime
from pathlib import Path
from PIL import ImageGrab

from tools.image_qa import ImageQA

class ClipboardImageMonitor:
    """Monitors user input and processes the current clipboard image when requested."""
    
    def __init__(self):
        self.is_running = True
        self.image_qa = ImageQA()
        self.input_dir = Path("input_documents")
        self.input_dir.mkdir(exist_ok=True)

    def log(self, message: str):
        """Log a simple timestamped message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        click.echo(f"[{timestamp}] {message}")

    def format_qa_results(self, results):
        """Format QA results in a readable way and translate to English."""
        if isinstance(results, str):
            try:
                results = json.loads(results)
            except json.JSONDecodeError:
                click.echo(results)
                click.echo("\n" + "=" * 50)
                return

        # Generate a title based on content type
        title = "Analysis Results"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if isinstance(results, dict) and 'entities' in results:
            # Look for company or person entities
            for entity in results['entities']:
                if entity['type'].lower() == 'company':
                    # Remove local language parts from company name
                    company_name = entity['text'].split('društvo')[0].strip()
                    title = f"Company Profile: {company_name}"
                    break
                elif entity['type'].lower() == 'person':
                    title = f"Person Profile: {entity['text']}"
                    break
        
        click.echo(f"\n{title}")
        click.echo(f"ID: {timestamp}")
        click.echo("=" * 50)

        if isinstance(results, dict):
            # Handle description
            if 'description' in results:
                click.echo("\nDescription:")
                click.echo(f"  {results['description']}")

            # Handle entities
            if 'entities' in results:
                click.echo("\nKey Information:")
                
                # Define the order of sections
                section_order = ['Company', 'Person', 'Location', 'Amount']
                
                # Group and translate entities
                entities_by_type = {}
                for entity in results['entities']:
                    entity_type = entity['type'].title()
                    
                    # Skip keywords that are just UI elements
                    if entity_type == 'Keyword':
                        continue
                        
                    if entity_type not in entities_by_type:
                        entities_by_type[entity_type] = []
                    
                    # Clean up and translate the context
                    context = entity['context']
                    context = context.replace('Capital in rights', 'Authorized rights')
                    context = context.replace('Capital in kind', 'Assets contributed')
                    context = context.replace('Capital in cash', 'Cash invested')
                    
                    entities_by_type[entity_type].append({
                        'text': entity['text'],
                        'context': context
                    })
                
                # Print sections in order
                for section in section_order:
                    if section in entities_by_type:
                        click.echo(f"\n  {section}:")
                        for entity in entities_by_type[section]:
                            click.echo(f"    - {entity['text']} ({entity['context']})")

            # Handle visual elements
            if 'visual_elements' in results:
                click.echo("\nDocument Structure:")
                for element in results['visual_elements']:
                    # Skip technical UI elements
                    if 'pravosudje' in element.lower() or 'navigation' in element.lower():
                        continue
                    # Translate common terms
                    element = element.replace('Registri poslovnih subjekata', 'Business Registry')
                    click.echo(f"  - {element}")

        click.echo("\n" + "=" * 50)

    def save_clipboard_image(self) -> Path:
        """Saves clipboard image to input_documents with timestamp."""
        image = ImageGrab.grabclipboard()
        if image is None:
            self.log("No image found in clipboard.")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"clipboard_{timestamp}.png"
        file_path = self.input_dir / filename
        
        image.save(file_path, "PNG")
        self.log(f"Saved clipboard image as {file_path.name}")
        return file_path

    def analyze_clipboard_image(self):
        """Captures image from clipboard, saves it, and runs Image Q&A."""
        file_path = self.save_clipboard_image()
        if file_path is None:
            return
        
        self.log("Analyzing clipboard image with ImageQA...")
        
        # Create a new instance for each analysis to ensure fresh state
        image = self.image_qa.load_image(file_path)
        if not image:
            return
        
        # Extract structured content directly instead of using interactive menu
        results = self.image_qa.extract_structured_content(image)
        
        if results:
            self.format_qa_results(results)
        else:
            click.echo("\nNo results to display.")

    def start_monitoring(self):
        """Loop that waits for user input; 'Enter' triggers analysis, 'quit' exits."""
        self.log("Clipboard monitor started.")
        self.log("Press Enter to analyze the current clipboard image, or type 'quit' to exit.")
        while self.is_running:
            user_input = input().strip().lower()
            if user_input == 'quit':
                self.is_running = False
                break
            self.analyze_clipboard_image()

def main():
    click.echo("\nClipboard Image Monitor")
    click.echo("=======================")
    click.echo("1. Copy an image into your clipboard (e.g., screenshot).")
    click.echo("2. Press Enter here to analyze it.")
    click.echo("Type 'quit' to exit.\n")
    
    monitor = ClipboardImageMonitor()
    monitor.start_monitoring()

if __name__ == "__main__":
    main() 