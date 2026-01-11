import sys
import os
from pathlib import Path

# Add path to find sibling modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from inspector_gadget import InspectorGadget
# We need DirectConversation which is in gemini_longtext, imported by InspectorGadget
# But InspectorGadget doesn't expose it directly.
# Let's re-import from the source using the path setup in inspector_gadget logic
modules_dir = os.path.dirname(current_dir)
sys.path.append(modules_dir)

try:
    from gemini_longtext import DirectConversation
except ImportError:
    print("Warning: Could not import DirectConversation from gemini_longtext")
    DirectConversation = None

class Auditor:
    """
    The Auditor: Verifies reports against source documents using Long-Context AI.
    """
    def __init__(self):
        self.inspector = InspectorGadget()

    def verify_report(self, report_path, original_file_path):
        """
        Compares the generated report against the original text to find hallucinations or omissions.
        """
        if not self.inspector.longtext_cli or not DirectConversation:
            return "⚠️ Verification skipped: Gemini 3 Pro unavailable."
            
        print(f"⚖️ Auditor: Verifying {report_path} against {original_file_path}...")
        
        try:
            # Read Report
            with open(report_path, 'r', encoding='utf-8', errors='ignore') as f:
                report_content = f.read()
                
            # Read Original Doc
            with open(original_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                source_content = f.read()
            
            # Prompt
            prompt = f"""
            You are a rigorous Fact-Checker.
            
            TASK 1: HALLUCINATION CHECK
            Verify that every claim in the REPORT is supported by the SOURCE DOCUMENT.
            
            TASK 2: OMISSION CHECK
            Are there any CRITICAL facts in the SOURCE that are completely missing from the REPORT?
            
            REPORT TO VERIFY:
            ---
            {report_content}
            ---
            
            SOURCE DOCUMENT:
            ---
            {source_content}
            ---
            
            OUTPUT FORMAT (Markdown):
            ## ⚖️ Verification Result
            ### 🔴 Hallucinations (False Claims)
            - [List any claims not supported by source, or "None"]
            
            ### 🟠 Critical Omissions (Missing Facts)
            - [List important facts missed, or "None"]
            
            ### 🟢 Quality Score
            - **Accuracy:** [0-100]%
            - **Completeness:** [0-100]%
            """
            
            # Use Gemini 3 Pro via DirectConversation
            chat = DirectConversation(self.inspector.longtext_cli.client, self.inspector.longtext_cli.model)
            response = chat.send(prompt)
            
            return response
            
        except Exception as e:
            return f"⚠️ Verification failed: {e}"
