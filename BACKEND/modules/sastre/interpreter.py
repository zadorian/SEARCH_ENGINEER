#!/usr/bin/env python3
"""
SASTRE Script Interpreter
=========================
Executes multi-step automation chains defined in Sastre Operator Syntax.
Handles variables, conditional logic, and narrative generation.

Usage:
    interpreter = ScriptInterpreter(executor, reporter)
    results = await interpreter.run_script(script_text)
"""

import logging
import re
import asyncio
from typing import Dict, Any, List, Optional

# Set up logging
logger = logging.getLogger("SastreInterpreter")

class ScriptInterpreter:
    def __init__(self, io_executor, edith_writer):
        self.executor = io_executor
        self.writer = edith_writer # EDITh is the writer subagent
        self.variables: Dict[str, Any] = {}
        self.context: Dict[str, List[Any]] = {}  # For narrative context

    async def run_script(self, script_text: str) -> Dict[str, Any]:
        """
        Parses and executes a full Sastre script.
        """
        lines = [line.strip() for line in script_text.split('\n') if line.strip()]
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Skip comments
            if line.startswith("//") or line.startswith("#"):
                i += 1
                continue

            # Handle Logic: IF / ELSE / END
            if line.startswith("IF "):
                condition = line[3:].replace(" THEN", "").strip()
                if self.evaluate_condition(condition):
                    # Continue executing normally inside the block
                    i += 1
                    continue
                else:
                    # Skip to ELSE or END
                    i = self._skip_to_block(lines, i, ["ELSE", "END"])
                    if lines[i].startswith("ELSE"):
                        i += 1 # Enter ELSE block
                    continue
            
            elif line.startswith("ELSE"):
                # If we hit ELSE naturally, it means we just finished the IF block.
                # Skip to END.
                i = self._skip_to_block(lines, i, ["END"])
                continue

            elif line.startswith("END"):
                # End of a block, continue
                i += 1
                continue

            # Handle Execution
            await self.execute_line(line)
            i += 1

        return self.variables

    def _skip_to_block(self, lines, current_index, targets):
        """Skips lines until one of the targets is found at the start."""
        nesting = 0
        for j in range(current_index + 1, len(lines)):
            line = lines[j]
            if line.startswith("IF "):
                nesting += 1
            elif line.startswith("END"):
                if nesting == 0:
                    if "END" in targets: return j
                else:
                    nesting -= 1
            elif line.startswith("ELSE"):
                if nesting == 0 and "ELSE" in targets:
                    return j
        return len(lines) # End of script

    async def execute_line(self, line: str):
        """Executes a single logical line."""
        
        # 1. Variable Assignment: SET $var = "val" OR $var = op
        if line.startswith("SET "):
            # Explicit SET
            parts = line[4:].split("=", 1)
            var_name = parts[0].strip()
            value = self._resolve_value(parts[1].strip())
            self.variables[var_name] = value
            logger.info(f"SET {var_name} = {value}")
            return

        # Implicit Assignment: $var = ...
        if line.startswith("$") and "=" in line and not line.startswith("IF"):
            parts = line.split("=", 1)
            var_name = parts[0].strip()
            rhs = parts[1].strip()
            
            # Execute RHS
            result = await self._execute_expression(rhs)
            self.variables[var_name] = result
            logger.info(f"Computed {var_name} via expression")
            return

        # 2. Narrative: WRITE template ...
        if line.startswith("WRITE "):
            await self._handle_write(line)
            return

        # 3. Logging
        if line.startswith("LOG "):
            msg = line[4:].strip().strip('"')
            logger.info(f"[SCRIPT LOG] {msg}")
            return

        # 4. Standalone Expression (side effects)
        await self._execute_expression(line)

    async def _execute_expression(self, expr: str) -> Any:
        """
        Executes a chain expression (e.g. "cuk: $subject :cuk! => @company?")
        """
        # Resolve variables in input
        # Naive split by '=>'
        steps = [s.strip() for s in expr.split("=>")]
        
        current_value = None
        
        for step in steps:
            # Resolve vars ($var) in step string
            resolved_step = self._resolve_vars_in_string(step)
            
            # Handle Tagging (+#tag) - special case, usually handled by executor but let's be explicit
            if resolved_step.startswith("+#"):
                # This would ideally modify the metadata of current_value
                logger.info(f"Tagging current result with {resolved_step}")
                continue

            # Execute via IOExecutor
            # We assume IOExecutor has a method execute_operator(op_string, input_context)
            # Since we don't have that unified method yet, we simulate:
            try:
                # If first step and looks like a value string, just set it
                if current_value is None and (resolved_step.startswith('"') or ":" not in resolved_step):
                    current_value = self._resolve_value(resolved_step)
                else:
                    # It's an operator query.
                    # If we have a current_value (e.g. a Node ID or Object), pass it as context
                    # The IOExecutor usually takes (query).
                    # If we are chaining, we might construct a query like "operator: <id_of_previous>"
                    
                    if current_value:
                        # Auto-pipe logic: if current is a Node, append ID?
                        # For now, simplistic: if resolved_step doesn't have an input, prepend current_value?
                        # Actually, Sastre syntax "Input => Op" implies Op takes Input.
                        pass

                    # For this stub, we simulate execution
                    logger.info(f"Executing: {resolved_step} on {current_value}")
                    # In real impl: current_value = await self.executor.execute(resolved_step, input=current_value)
                    # Simulate finding something for the "IF $node.exists" check
                    current_value = {"id": "node_123", "exists": True, "data": "Sample Data"}
            
            except Exception as e:
                logger.error(f"Error executing step '{resolved_step}': {e}")
                return None

        return current_value

    def _resolve_vars_in_string(self, text: str) -> str:
        """Replaces $var with its value in a string."""
        for var_name, val in self.variables.items():
            if f"{var_name}" in text:
                # Simple string replacement for now. 
                # Complex objects might need special handling (e.g. extracting ID)
                str_val = str(val)
                if isinstance(val, dict) and "id" in val:
                    str_val = val["id"]
                text = text.replace(f"{var_name}", str_val)
        return text

    def _resolve_value(self, val_str: str) -> Any:
        """Resolves a literal or variable."""
        val_str = val_str.strip()
        if val_str.startswith('"') and val_str.endswith('"'):
            return val_str[1:-1]
        if val_str.startswith("$"):
            return self.variables.get(val_str, None)
        return val_str

    def evaluate_condition(self, condition: str) -> bool:
        """Evaluates IF conditions."""
        # IF $var.exists
        if ".exists" in condition:
            var_name = condition.split(".")[0]
            val = self.variables.get(var_name)
            return val is not None and (not isinstance(val, dict) or val.get("exists", True))
        return False

    async def _handle_write(self, line: str):
        """Handles WRITE template ... WITH context(...)"""
        # Parse: WRITE template "name" WITH context($a, $b) => OUT section "Title"
        
        # Extract template
        match = re.search(r'WRITE template "([^"].*[^\"])"', line)
        if not match: return
        template_name = match.group(1)
        
        # Extract context
        context_vars = []
        ctx_match = re.search(r'WITH context\(([^)]+)\)', line)
        if ctx_match:
            vars_str = ctx_match.group(1)
            context_vars = [v.strip() for v in vars_str.split(",")]
        
        # Build context object
        context_data = {}
        for var in context_vars:
            context_data[var] = self.variables.get(var)
            
        logger.info(f"Generating narrative '{template_name}' with context keys: {list(context_data.keys())}")
        
        # Invoke EDITh (Writer)
        # self.writer.generate_section(template_name, context_data)
        logger.info(f"EDITh: Generating narrative '{template_name}' with context keys: {list(context_data.keys())}")
        pass
