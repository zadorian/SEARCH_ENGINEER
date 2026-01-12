#!/usr/bin/env python3
"""
Chain Executor - Execute multi-hop recursive investigation chains

This module executes chain rules defined in chain_rules.json, enabling:
- Recursive expansion (person -> all companies recursively)
- Cascading ownership (beneficial owner -> ownership pyramids)
- Clustering networks (address -> corporate networks)
- Hierarchical expansion (parent -> subsidiaries tree)
- Portfolio expansion (shareholder -> investment portfolio)
- Network expansion (officer -> director networks)
- Entity network extraction (company -> all connected people)

Chain rules differ from regular rules:
- chain_config.type: Strategy for multi-hop execution
- chain_config.max_depth: Recursion limit
- chain_config.steps: Ordered sequence of actions
- chain_config.deduplication_fields: Fields to deduplicate results

Architecture:
- ChainExecutor: Main executor for chain rules
- Uses RuleExecutor from io_cli.py for individual steps
- Handles deduplication, depth tracking, and result aggregation
- Supports conditions (ownership_threshold, shareholder_type, etc.)
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Callable
from collections import defaultdict
from datetime import datetime

# Matrix directory
MATRIX_DIR = Path(__file__).parent


class ChainExecutor:
    """Execute recursive multi-hop investigation chains.

    Supports multiple chain execution strategies:
    - recursive_expansion: Execute same rule on outputs recursively
    - cascading_ownership: Follow ownership chains with threshold
    - clustering_network: Build entity clusters based on shared attributes
    - hierarchical_expansion: Build tree structures (parent->children)
    - portfolio_expansion: Map investment holdings recursively
    - network_expansion: Discover networks via shared connections
    - entity_network_extraction: Extract all connected entities
    """

    def __init__(self, rule_executor):
        """Initialize ChainExecutor.

        Args:
            rule_executor: Instance of RuleExecutor from io_cli.py
        """
        self.rule_executor = rule_executor
        self.legend = self._load_legend()
        self.rules_by_id = self._load_rules()
        self.playbooks_by_id = self._load_playbooks()
        self.chain_rules = self._load_chain_rules()

    def _load_legend(self) -> Dict[int, str]:
        """Load field code legend."""
        legend_path = MATRIX_DIR / "legend.json"
        if not legend_path.exists():
            return {}
        with open(legend_path) as f:
            legend_data = json.load(f)
            # Convert string keys to int
            return {int(k): v for k, v in legend_data.items()}

    def _load_rules(self) -> Dict[str, Dict]:
        """Load all rules indexed by ID."""
        rules_path = MATRIX_DIR / "rules.json"
        if not rules_path.exists():
            return {}
        with open(rules_path) as f:
            rules_list = json.load(f)
            return {rule['id']: rule for rule in rules_list}

    def _load_playbooks(self) -> Dict[str, Dict]:
        """Load playbooks indexed by ID.

        Playbooks can be used as chain steps, executing multiple rules at once.
        Prefers validated playbooks (grounded, with routing fields).
        """
        playbooks_path = MATRIX_DIR / "playbooks_validated.json"
        if not playbooks_path.exists():
            playbooks_path = MATRIX_DIR / "playbooks.json"
        if not playbooks_path.exists():
            return {}
        with open(playbooks_path) as f:
            playbooks_list = json.load(f)
            return {pb['id']: pb for pb in playbooks_list}

    def _load_chain_rules(self) -> Dict[str, Dict]:
        """Load chain rules indexed by ID."""
        chain_rules_path = MATRIX_DIR / "chain_rules.json"
        if not chain_rules_path.exists():
            return {}
        with open(chain_rules_path) as f:
            chain_rules_list = json.load(f)
            return {rule['id']: rule for rule in chain_rules_list}

    async def execute_step(
        self,
        step_id: str,
        value: str,
        jurisdiction: Optional[str] = None
    ) -> Dict:
        """Execute a step which can be either a rule or a playbook.

        Args:
            step_id: ID of rule or playbook to execute
            value: Input value
            jurisdiction: Optional jurisdiction filter

        Returns:
            Execution result dict
        """
        # Check if it's a playbook
        if step_id in self.playbooks_by_id:
            playbook = self.playbooks_by_id[step_id]
            return await self._execute_playbook(playbook, value, jurisdiction)

        # Otherwise execute as a rule
        rule = self.rules_by_id.get(step_id)
        if rule:
            return await self.rule_executor.execute_rule(rule, value, jurisdiction)

        return {'error': f'Step not found: {step_id}', 'step_id': step_id}

    async def _execute_playbook(
        self,
        playbook: Dict,
        value: str,
        jurisdiction: Optional[str] = None
    ) -> Dict:
        """Execute a playbook (all its child rules).

        Args:
            playbook: Playbook definition
            value: Input value
            jurisdiction: Optional jurisdiction override

        Returns:
            Aggregated results from all child rules
        """
        pb_id = playbook.get('id', 'unknown')
        rule_ids = playbook.get('rules', [])
        pb_jurisdiction = jurisdiction or playbook.get('jurisdiction')

        results = []
        entities_extracted = []

        # Execute rules in parallel
        tasks = []
        for rule_id in rule_ids:
            rule = self.rules_by_id.get(rule_id)
            if rule:
                tasks.append(self.rule_executor.execute_rule(rule, value, pb_jurisdiction))

        if tasks:
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in raw_results:
                if isinstance(r, Exception):
                    results.append({'error': str(r)})
                else:
                    results.append(r)
                    # Extract entities from successful results
                    if r.get('status') == 'success' and r.get('results'):
                        for sub in r['results']:
                            if sub.get('data'):
                                entities_extracted.append(sub['data'])

        successes = sum(1 for r in results if r.get('status') == 'success')

        return {
            'playbook_id': pb_id,
            'label': playbook.get('label'),
            'status': 'success' if successes > 0 else 'failed',
            'rules_executed': len(results),
            'rules_succeeded': successes,
            'results': results,
            'entities_extracted': entities_extracted,
            'is_playbook': True
        }

    def _emit_event(
        self,
        event_callback: Optional[Callable[[str, Dict], None]],
        event_type: str,
        data: Dict
    ):
        """Emit an event via callback if provided.

        Args:
            event_callback: Optional callback function (event_type, data) -> None
            event_type: Event type string (chain:start, chain:hop, chain:complete, etc.)
            data: Event data dictionary
        """
        if event_callback:
            try:
                event_callback(event_type, data)
            except Exception as e:
                # Don't let callback errors break execution
                pass

    async def execute_chain(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        jurisdiction: Optional[str] = None,
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute a chain rule.

        Args:
            chain_rule: Chain rule definition from chain_rules.json
            initial_input: Initial input data (e.g., {'value': 'John Smith', 'type': 'person'})
            jurisdiction: Optional jurisdiction filter
            event_callback: Optional callback for streaming events (event_type, data) -> None

        Returns:
            Dict with chain execution results, including all entities discovered
        """
        chain_config = chain_rule.get('chain_config', {})
        chain_type = chain_config.get('type')
        max_depth = chain_config.get('max_depth', 3)

        # Emit chain:start event
        self._emit_event(event_callback, 'chain:start', {
            'chain_id': chain_rule.get('id'),
            'chain_type': chain_type,
            'label': chain_rule.get('label', ''),
            'initial_value': initial_input.get('value'),
            'max_depth': max_depth,
            'jurisdiction': jurisdiction
        })

        # Route to appropriate chain executor
        if chain_type == 'recursive_expansion':
            result = await self._recursive_expand(chain_rule, initial_input, max_depth, jurisdiction, event_callback)
        elif chain_type == 'cascading_ownership':
            result = await self._cascading_ownership(chain_rule, initial_input, max_depth, jurisdiction, event_callback)
        elif chain_type == 'clustering_network':
            result = await self._clustering_network(chain_rule, initial_input, max_depth, jurisdiction, event_callback)
        elif chain_type == 'hierarchical_expansion':
            result = await self._hierarchical_expand(chain_rule, initial_input, max_depth, jurisdiction, event_callback)
        elif chain_type == 'portfolio_expansion':
            result = await self._portfolio_expand(chain_rule, initial_input, max_depth, jurisdiction, event_callback)
        elif chain_type == 'network_expansion':
            result = await self._network_expand(chain_rule, initial_input, max_depth, jurisdiction, event_callback)
        elif chain_type == 'entity_network_extraction':
            result = await self._entity_network_extract(chain_rule, initial_input, max_depth, jurisdiction, event_callback)
        # Playbook-based chain types (use playbooks as macro-steps)
        elif chain_type == 'playbook_cascade':
            result = await self._playbook_cascade(chain_rule, initial_input, jurisdiction, event_callback)
        elif chain_type == 'multi_jurisdiction_sweep':
            result = await self._multi_jurisdiction_sweep(chain_rule, initial_input, jurisdiction, event_callback)
        elif chain_type == 'domain_to_corporate_pivot':
            result = await self._domain_to_corporate_pivot(chain_rule, initial_input, jurisdiction, event_callback)
        elif chain_type == 'compliance_stack':
            result = await self._compliance_stack(chain_rule, initial_input, jurisdiction, event_callback)
        elif chain_type == 'media_aggregation':
            result = await self._media_aggregation(chain_rule, initial_input, jurisdiction, event_callback)
        # OSINT-specific chain types
        elif chain_type == 'osint_cascade':
            result = await self._osint_cascade(chain_rule, initial_input, max_depth, jurisdiction, event_callback)
        elif chain_type == 'osint_breach_network':
            result = await self._osint_breach_network(chain_rule, initial_input, max_depth, jurisdiction, event_callback)
        elif chain_type == 'osint_person_web':
            result = await self._osint_person_web(chain_rule, initial_input, max_depth, jurisdiction, event_callback)
        else:
            result = {
                'error': f'Unknown chain type: {chain_type}',
                'chain_id': chain_rule.get('id'),
                'status': 'failed'
            }

        # Emit chain:complete event
        self._emit_event(event_callback, 'chain:complete', {
            'chain_id': chain_rule.get('id'),
            'chain_type': chain_type,
            'status': result.get('status', 'unknown'),
            'total_results': result.get('total_results', 0),
            'unique_entities': result.get('unique_entities', 0),
            'depth_reached': result.get('depth_reached', 0)
        })

        return result

    async def _recursive_expand(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        max_depth: int,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute recursive expansion chain.

        Example: Officer -> all companies -> for each company get officers -> repeat

        Process:
        1. Execute initial rule with input
        2. For each result entity, re-execute the same rule
        3. Deduplicate results across all iterations
        4. Repeat until max_depth or no new results
        """
        chain_config = chain_rule.get('chain_config', {})
        steps = chain_config.get('steps', [])
        dedup_fields = chain_config.get('deduplication_fields', [])

        # Track all discovered entities (deduplicated)
        all_results = []
        seen_entities = set()  # For deduplication

        # Queue of entities to process: (value, depth)
        queue = [(initial_input.get('value'), 0)]
        processed = set()  # Avoid reprocessing same value

        depth = 0

        while queue and depth < max_depth:
            current_batch = []
            next_queue = []

            # Emit chain:hop event for this depth level
            self._emit_event(event_callback, 'chain:hop', {
                'chain_id': chain_rule.get('id'),
                'depth': depth,
                'max_depth': max_depth,
                'queue_size': len(queue),
                'entities_discovered': len(seen_entities)
            })

            # Process all items at current depth
            while queue and queue[0][1] == depth:
                value, _ = queue.pop(0)

                if value in processed:
                    continue
                processed.add(value)
                current_batch.append(value)

            # Execute steps for each value in batch
            for value in current_batch:
                step_results = []

                # Execute each step in the chain
                for step in steps:
                    action = step.get('action')

                    # Find the rule for this action
                    action_rule = self.rules_by_id.get(action)
                    if not action_rule:
                        continue

                    # Execute the rule
                    result = await self.rule_executor.execute_rule(
                        action_rule,
                        value,
                        jurisdiction
                    )

                    if result.get('status') == 'success':
                        step_results.append(result)

                        # Extract entities for next iteration
                        entities = self._extract_entities(result, step.get('output_fields', []))

                        # Add to next queue if not at max depth
                        if depth + 1 < max_depth:
                            for entity_value in entities:
                                # Deduplicate
                                entity_key = self._make_dedup_key(entity_value, dedup_fields)
                                if entity_key not in seen_entities:
                                    seen_entities.add(entity_key)
                                    next_queue.append((entity_value, depth + 1))

                # Collect results
                if step_results:
                    all_results.extend(step_results)

            # Move to next depth
            queue = next_queue
            depth += 1

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'recursive_expansion',
            'status': 'success',
            'depth_reached': depth,
            'max_depth': max_depth,
            'total_results': len(all_results),
            'unique_entities': len(seen_entities),
            'results': all_results,
            'jurisdiction': jurisdiction
        }

    async def _cascading_ownership(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        max_depth: int,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute cascading ownership chain.

        Example: Beneficial owner -> companies owned -> for each company get shareholders ->
                 if shareholder is company and owns >threshold%, recurse

        Process:
        1. Get initial ownership structure
        2. For each owner above threshold, recursively get their ownership
        3. Build ownership tree/pyramid
        4. Stop at max_depth
        """
        chain_config = chain_rule.get('chain_config', {})
        steps = chain_config.get('steps', [])
        ownership_threshold = chain_config.get('ownership_threshold_pct', 25.0)
        dedup_fields = chain_config.get('deduplication_fields', [])

        # Build ownership tree
        ownership_tree = {
            'root': initial_input.get('value'),
            'depth': 0,
            'children': [],
            'total_entities': 0
        }

        all_results = []
        seen_entities = set()

        # Recursive function to build ownership tree
        async def build_ownership_level(entity_value: str, current_depth: int, parent_node: Dict):
            if current_depth >= max_depth:
                return

            # Execute steps to get ownership information
            for step in steps:
                action = step.get('action')
                condition = step.get('condition', '')

                # Check if condition applies
                if 'shareholder_type' in condition and current_depth == 0:
                    # Skip shareholder type checks on initial owner
                    continue

                action_rule = self.rules_by_id.get(action)
                if not action_rule:
                    continue

                result = await self.rule_executor.execute_rule(
                    action_rule,
                    entity_value,
                    jurisdiction
                )

                if result.get('status') == 'success':
                    all_results.append(result)

                    # Extract shareholders/owners
                    shareholders = self._extract_shareholders(result)

                    for shareholder in shareholders:
                        shareholder_name = shareholder.get('name')
                        ownership_pct = shareholder.get('ownership_pct', 0)
                        shareholder_type = shareholder.get('type', 'person')

                        # Check ownership threshold
                        if ownership_pct >= ownership_threshold:
                            # Check deduplication
                            dedup_key = self._make_dedup_key(shareholder_name, dedup_fields)
                            if dedup_key in seen_entities:
                                continue
                            seen_entities.add(dedup_key)

                            # Create child node
                            child_node = {
                                'entity': shareholder_name,
                                'type': shareholder_type,
                                'ownership_pct': ownership_pct,
                                'depth': current_depth + 1,
                                'children': []
                            }
                            parent_node['children'].append(child_node)

                            # Recurse if corporate shareholder
                            if shareholder_type == 'company' and current_depth + 1 < max_depth:
                                await build_ownership_level(
                                    shareholder_name,
                                    current_depth + 1,
                                    child_node
                                )

        # Build the tree
        await build_ownership_level(initial_input.get('value'), 0, ownership_tree)
        ownership_tree['total_entities'] = len(seen_entities)

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'cascading_ownership',
            'status': 'success',
            'ownership_threshold': ownership_threshold,
            'max_depth': max_depth,
            'total_entities': len(seen_entities),
            'ownership_tree': ownership_tree,
            'results': all_results,
            'jurisdiction': jurisdiction
        }

    async def _clustering_network(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        max_depth: int,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute clustering network chain.

        Example: Address -> all companies at address -> get officers for each ->
                 find shared officers -> get their other companies

        Process:
        1. Find entities sharing initial attribute (e.g., address)
        2. For each cluster member, find related entities
        3. Build network graph showing connections
        """
        chain_config = chain_rule.get('chain_config', {})
        steps = chain_config.get('steps', [])
        cluster_threshold = chain_config.get('cluster_threshold', 2)
        dedup_fields = chain_config.get('deduplication_fields', [])

        all_results = []
        clusters = defaultdict(list)  # attribute -> [entities]
        network_graph = {
            'nodes': [],
            'edges': [],
            'clusters': []
        }
        seen_entities = set()

        # Execute clustering steps
        for i, step in enumerate(steps):
            action = step.get('action')
            condition = step.get('condition', '')

            action_rule = self.rules_by_id.get(action)
            if not action_rule:
                continue

            if i == 0:
                # First step: find all entities at location/with attribute
                result = await self.rule_executor.execute_rule(
                    action_rule,
                    initial_input.get('value'),
                    jurisdiction
                )

                if result.get('status') == 'success':
                    all_results.append(result)
                    entities = self._extract_entities(result, step.get('output_fields', []))

                    for entity in entities:
                        dedup_key = self._make_dedup_key(entity, dedup_fields)
                        if dedup_key not in seen_entities:
                            seen_entities.add(dedup_key)
                            network_graph['nodes'].append({
                                'id': entity,
                                'type': 'company',
                                'cluster': initial_input.get('value')
                            })

            elif 'cluster_analysis' in condition or 'CROSS_REFERENCE' in action:
                # Cross-reference step: find shared attributes
                # This identifies officers/owners appearing in multiple companies
                officer_to_companies = defaultdict(list)

                for node in network_graph['nodes']:
                    if node.get('type') == 'company':
                        result = await self.rule_executor.execute_rule(
                            action_rule,
                            node['id'],
                            jurisdiction
                        )

                        if result.get('status') == 'success':
                            all_results.append(result)
                            officers = self._extract_entities(result, step.get('output_fields', []))

                            for officer in officers:
                                officer_to_companies[officer].append(node['id'])

                                # Add officer as node
                                if officer not in [n['id'] for n in network_graph['nodes']]:
                                    network_graph['nodes'].append({
                                        'id': officer,
                                        'type': 'person',
                                        'role': 'officer'
                                    })

                                # Add edge
                                network_graph['edges'].append({
                                    'from': officer,
                                    'to': node['id'],
                                    'type': 'officer_of'
                                })

                # Identify shared officers (cluster threshold)
                for officer, companies in officer_to_companies.items():
                    if len(companies) >= cluster_threshold:
                        clusters['shared_officers'].append({
                            'officer': officer,
                            'companies': companies,
                            'count': len(companies)
                        })

            else:
                # Regular enrichment step
                for node in network_graph['nodes']:
                    if i < max_depth:
                        result = await self.rule_executor.execute_rule(
                            action_rule,
                            node['id'],
                            jurisdiction
                        )

                        if result.get('status') == 'success':
                            all_results.append(result)

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'clustering_network',
            'status': 'success',
            'cluster_threshold': cluster_threshold,
            'total_nodes': len(network_graph['nodes']),
            'total_edges': len(network_graph['edges']),
            'clusters_found': len(clusters),
            'network': network_graph,
            'clusters': dict(clusters),
            'results': all_results,
            'jurisdiction': jurisdiction
        }

    async def _hierarchical_expand(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        max_depth: int,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute hierarchical expansion chain.

        Example: Parent company -> find subsidiaries (ownership >50%) ->
                 for each subsidiary find its subsidiaries -> build tree

        Process:
        1. Get shareholdings/ownership structure
        2. Identify subsidiaries (ownership > threshold)
        3. Recursively expand each subsidiary
        4. Build hierarchical tree structure
        """
        chain_config = chain_rule.get('chain_config', {})
        ownership_threshold = chain_config.get('ownership_threshold_pct', 50.0)

        # Reuse cascading_ownership logic but with different threshold
        # and bottom-up tree building (parent -> children)
        return await self._cascading_ownership(
            chain_rule,
            initial_input,
            max_depth,
            jurisdiction,
            event_callback
        )

    async def _portfolio_expand(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        max_depth: int,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute portfolio expansion chain.

        Example: Shareholder -> all companies with holdings ->
                 if shareholder is company, get its holdings -> repeat

        Process:
        1. Find all shareholdings for entity
        2. If entity is corporate shareholder, recursively get its portfolio
        3. Build investment portfolio map
        """
        chain_config = chain_rule.get('chain_config', {})
        steps = chain_config.get('steps', [])
        ownership_threshold = chain_config.get('ownership_threshold_pct', 5.0)
        dedup_fields = chain_config.get('deduplication_fields', [])

        all_results = []
        portfolio = {
            'investor': initial_input.get('value'),
            'holdings': [],
            'total_holdings': 0
        }
        seen_entities = set()

        # Queue: (entity_value, depth, is_corporate)
        queue = [(initial_input.get('value'), 0, True)]
        processed = set()

        while queue:
            entity_value, depth, is_corporate = queue.pop(0)

            if depth >= max_depth or entity_value in processed:
                continue
            processed.add(entity_value)

            # Execute steps to find shareholdings
            for step in steps:
                action = step.get('action')
                condition = step.get('condition', '')

                # Check depth condition
                if 'depth < max_depth' in condition and depth >= max_depth:
                    continue

                action_rule = self.rules_by_id.get(action)
                if not action_rule:
                    continue

                result = await self.rule_executor.execute_rule(
                    action_rule,
                    entity_value,
                    jurisdiction
                )

                if result.get('status') == 'success':
                    all_results.append(result)

                    # Extract holdings
                    holdings = self._extract_holdings(result)

                    for holding in holdings:
                        company_name = holding.get('company')
                        ownership_pct = holding.get('ownership_pct', 0)

                        if ownership_pct >= ownership_threshold:
                            dedup_key = self._make_dedup_key(company_name, dedup_fields)
                            if dedup_key not in seen_entities:
                                seen_entities.add(dedup_key)

                                portfolio['holdings'].append({
                                    'company': company_name,
                                    'ownership_pct': ownership_pct,
                                    'investor': entity_value,
                                    'depth': depth
                                })

                                # If holding is corporate and we should recurse
                                if is_corporate and 'follow_corporate' in condition:
                                    queue.append((company_name, depth + 1, True))

        portfolio['total_holdings'] = len(portfolio['holdings'])

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'portfolio_expansion',
            'status': 'success',
            'ownership_threshold': ownership_threshold,
            'max_depth': max_depth,
            'total_holdings': portfolio['total_holdings'],
            'portfolio': portfolio,
            'results': all_results,
            'jurisdiction': jurisdiction
        }

    async def _network_expand(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        max_depth: int,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute network expansion chain.

        Example: Officer -> their companies -> all officers at those companies ->
                 their companies -> repeat

        Process:
        1. Get appointments for target officer
        2. For each company, get all officers
        3. For each connected officer, get their appointments
        4. Build network graph of officer connections
        """
        chain_config = chain_rule.get('chain_config', {})
        steps = chain_config.get('steps', [])
        network_threshold = chain_config.get('network_threshold', 2)
        dedup_fields = chain_config.get('deduplication_fields', [])

        all_results = []
        network = {
            'center': initial_input.get('value'),
            'officers': [],
            'companies': [],
            'connections': [],
            'metrics': {}
        }

        seen_officers = set()
        seen_companies = set()

        # Track connections: officer -> companies
        officer_to_companies = defaultdict(set)
        company_to_officers = defaultdict(set)

        # BFS expansion
        officer_queue = [(initial_input.get('value'), 0)]
        processed_officers = set()

        while officer_queue:
            officer_name, depth = officer_queue.pop(0)

            if depth >= max_depth or officer_name in processed_officers:
                continue
            processed_officers.add(officer_name)

            # Get appointments for this officer
            for step in steps:
                action = step.get('action')
                condition = step.get('condition', '')

                # Skip if condition doesn't match
                if 'depth < max_depth' in condition and depth >= max_depth:
                    continue
                if 'officer_name != target_officer' in condition and officer_name == initial_input.get('value'):
                    continue

                action_rule = self.rules_by_id.get(action)
                if not action_rule:
                    continue

                if 'OFFICER_APPOINTMENTS' in action:
                    # Get companies where officer has appointments
                    result = await self.rule_executor.execute_rule(
                        action_rule,
                        officer_name,
                        jurisdiction
                    )

                    if result.get('status') == 'success':
                        all_results.append(result)
                        companies = self._extract_entities(result, step.get('output_fields', []))

                        for company in companies:
                            if company not in seen_companies:
                                seen_companies.add(company)
                                network['companies'].append(company)

                            officer_to_companies[officer_name].add(company)
                            company_to_officers[company].add(officer_name)

                            network['connections'].append({
                                'officer': officer_name,
                                'company': company,
                                'type': 'appointment'
                            })

                elif 'COMPANY_OFFICERS' in action:
                    # Get all officers at companies
                    for company in list(officer_to_companies[officer_name]):
                        result = await self.rule_executor.execute_rule(
                            action_rule,
                            company,
                            jurisdiction
                        )

                        if result.get('status') == 'success':
                            all_results.append(result)
                            officers = self._extract_entities(result, step.get('output_fields', []))

                            for connected_officer in officers:
                                if connected_officer not in seen_officers:
                                    seen_officers.add(connected_officer)
                                    network['officers'].append(connected_officer)

                                    # Add to queue for next iteration
                                    if depth + 1 < max_depth:
                                        officer_queue.append((connected_officer, depth + 1))

        # Calculate network metrics
        network['metrics'] = {
            'total_officers': len(seen_officers),
            'total_companies': len(seen_companies),
            'total_connections': len(network['connections']),
            'avg_appointments_per_officer': len(network['connections']) / len(seen_officers) if seen_officers else 0,
            'shared_appointments': sum(1 for companies in officer_to_companies.values() if len(companies) >= network_threshold)
        }

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'network_expansion',
            'status': 'success',
            'network_threshold': network_threshold,
            'max_depth': max_depth,
            'network': network,
            'results': all_results,
            'jurisdiction': jurisdiction
        }

    async def _entity_network_extract(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        max_depth: int,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute entity network extraction chain.

        Example: Company -> get officers + beneficial owners + shareholders ->
                 for each person, get their other appointments

        Process:
        1. Extract all persons connected to company (officers, owners, shareholders)
        2. For each person, get their other appointments/holdings
        3. Build comprehensive person network around company
        """
        chain_config = chain_rule.get('chain_config', {})
        steps = chain_config.get('steps', [])
        dedup_fields = chain_config.get('deduplication_fields', [])

        all_results = []
        network = {
            'center_company': initial_input.get('value'),
            'persons': [],
            'connections': [],
            'secondary_companies': []
        }

        seen_persons = set()

        # Step 1-3: Extract all connected persons
        for step in steps[:3]:  # First 3 steps are extraction
            action = step.get('action')
            action_rule = self.rules_by_id.get(action)

            if not action_rule:
                continue

            result = await self.rule_executor.execute_rule(
                action_rule,
                initial_input.get('value'),
                jurisdiction
            )

            if result.get('status') == 'success':
                all_results.append(result)

                # Extract persons
                persons = self._extract_persons(result)

                for person in persons:
                    person_name = person.get('name')
                    role = person.get('role', 'unknown')

                    dedup_key = self._make_dedup_key(person_name, dedup_fields)
                    if dedup_key not in seen_persons:
                        seen_persons.add(dedup_key)
                        network['persons'].append({
                            'name': person_name,
                            'role': role,
                            'connection_to_company': initial_input.get('value')
                        })

                        network['connections'].append({
                            'person': person_name,
                            'company': initial_input.get('value'),
                            'type': role
                        })

        # Step 4: Get appointments for all persons (if depth allows)
        if max_depth > 1 and len(steps) > 3:
            step = steps[3]
            action = step.get('action')
            action_rule = self.rules_by_id.get(action)

            if action_rule:
                for person_data in network['persons']:
                    person_name = person_data['name']

                    result = await self.rule_executor.execute_rule(
                        action_rule,
                        person_name,
                        jurisdiction
                    )

                    if result.get('status') == 'success':
                        all_results.append(result)

                        # Extract secondary companies
                        companies = self._extract_entities(result, step.get('output_fields', []))

                        for company in companies:
                            if company != initial_input.get('value'):  # Exclude center company
                                if company not in network['secondary_companies']:
                                    network['secondary_companies'].append(company)

                                network['connections'].append({
                                    'person': person_name,
                                    'company': company,
                                    'type': 'officer'
                                })

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'entity_network_extraction',
            'status': 'success',
            'max_depth': max_depth,
            'total_persons': len(network['persons']),
            'total_connections': len(network['connections']),
            'total_secondary_companies': len(network['secondary_companies']),
            'network': network,
            'results': all_results,
            'jurisdiction': jurisdiction
        }

    # =========================================================================
    # Playbook-Based Chain Types
    # =========================================================================

    async def _playbook_cascade(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute playbook cascade - auto-select and run jurisdiction playbooks.

        Process:
        1. Use recommendation engine to find best playbooks for jurisdiction
        2. Execute playbooks in sequence (REGISTRY -> LEGAL -> COMPLIANCE)
        3. Aggregate outputs from all playbooks
        """
        chain_config = chain_rule.get('chain_config', {})
        steps = chain_config.get('steps', [])
        value = initial_input.get('value')

        all_results = []
        aggregated_data = {}

        self._emit_event(event_callback, 'playbook_cascade:start', {
            'chain_id': chain_rule.get('id'),
            'value': value,
            'jurisdiction': jurisdiction,
            'steps': len(steps)
        })

        for step in steps:
            action = step.get('action')
            action_type = step.get('action_type', 'rule')

            # Handle playbook recommendation step
            if action_type == 'playbook_recommendation':
                # Use IORouter to recommend playbooks
                from io_cli import IORouter
                router = IORouter()
                params = step.get('params', {})
                entity_type = params.get('entity_type', 'company')
                recs = router.recommend_playbooks(
                    entity_type,
                    jurisdiction=jurisdiction or params.get('jurisdiction'),
                    top_n=params.get('top_n', 1)
                )
                if recs:
                    # Store recommended playbook for next step
                    aggregated_data['selected_playbook'] = recs[0]
                    self._emit_event(event_callback, 'playbook_cascade:recommended', {
                        'playbook_id': recs[0]['id'],
                        'score': recs[0]['score']
                    })
                continue

            # Handle playbook execution
            if action_type == 'playbook':
                # Resolve dynamic playbook ID (e.g., PLY_{jurisdiction}_REGISTRY_*)
                playbook_id = self._resolve_playbook_id(action, jurisdiction)
                if not playbook_id:
                    fallback = step.get('fallback_pattern') or step.get('fallback')
                    if fallback:
                        playbook_id = self._resolve_playbook_id(fallback, jurisdiction)

                if playbook_id and playbook_id in self.playbooks_by_id:
                    playbook = self.playbooks_by_id[playbook_id]
                    result = await self._execute_playbook(playbook, value, jurisdiction)

                    if result.get('status') == 'success':
                        all_results.append(result)
                        # Merge data
                        for key, val in result.get('data', {}).items():
                            if key not in aggregated_data:
                                aggregated_data[key] = val
                            elif isinstance(val, list) and isinstance(aggregated_data[key], list):
                                aggregated_data[key].extend(val)

                        self._emit_event(event_callback, 'playbook_cascade:step_complete', {
                            'playbook_id': playbook_id,
                            'outputs': len(result.get('results', []))
                        })

            # Handle regular rule execution
            elif action_type == 'rule':
                rule = self.rules_by_id.get(action)
                if rule:
                    result = await self.rule_executor.execute_rule(rule, value, jurisdiction)
                    if result.get('status') == 'success':
                        all_results.append(result)

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'playbook_cascade',
            'status': 'success',
            'value': value,
            'jurisdiction': jurisdiction,
            'total_results': len(all_results),
            'aggregated_data': aggregated_data,
            'results': all_results
        }

    async def _multi_jurisdiction_sweep(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute playbooks across multiple jurisdictions in parallel.

        Process:
        1. Execute global playbook first
        2. Execute jurisdiction-specific playbooks in parallel
        3. Merge and deduplicate results
        """
        chain_config = chain_rule.get('chain_config', {})
        steps = chain_config.get('steps', [])
        value = initial_input.get('value')
        parallel = chain_config.get('parallel_execution', True)

        all_results = []
        aggregated_data = {}

        self._emit_event(event_callback, 'multi_jur_sweep:start', {
            'chain_id': chain_rule.get('id'),
            'value': value,
            'parallel': parallel
        })

        # Separate parallel and sequential steps
        parallel_tasks = []
        for step in steps:
            if step.get('parallel', False) and parallel:
                parallel_tasks.append(step)
            else:
                # Execute sequentially
                result = await self._execute_chain_step(step, value, jurisdiction, event_callback)
                if result:
                    all_results.append(result)
                    self._merge_chain_data(aggregated_data, result)

        # Execute parallel steps concurrently
        if parallel_tasks:
            async_results = await asyncio.gather(*[
                self._execute_chain_step(step, value, jurisdiction, event_callback)
                for step in parallel_tasks
            ], return_exceptions=True)

            for result in async_results:
                if isinstance(result, dict) and result.get('status') == 'success':
                    all_results.append(result)
                    self._merge_chain_data(aggregated_data, result)

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'multi_jurisdiction_sweep',
            'status': 'success',
            'value': value,
            'jurisdictions_covered': list(set(
                r.get('jurisdiction', 'GLOBAL') for r in all_results
            )),
            'total_results': len(all_results),
            'aggregated_data': aggregated_data,
            'results': all_results
        }

    async def _domain_to_corporate_pivot(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Pivot from domain intelligence to corporate enrichment.

        Process:
        1. Run DIGITAL playbook on domain
        2. Extract registrant companies/persons
        3. Run REGISTRY playbook on extracted companies
        4. Build domain-to-corporate network
        """
        chain_config = chain_rule.get('chain_config', {})
        steps = chain_config.get('steps', [])
        domain = initial_input.get('value')

        all_results = []
        extracted_companies = []
        extracted_persons = []

        self._emit_event(event_callback, 'domain_pivot:start', {
            'domain': domain
        })

        for step in steps:
            action = step.get('action')
            action_type = step.get('action_type', 'rule')

            if action_type == 'playbook':
                playbook_id = self._resolve_playbook_id(action, jurisdiction)
                if not playbook_id:
                    playbook_id = step.get('fallback')

                if playbook_id and playbook_id in self.playbooks_by_id:
                    playbook = self.playbooks_by_id[playbook_id]

                    # Determine input value based on step
                    input_val = domain
                    if step.get('input_fields') and 13 in step.get('input_fields', []):
                        # This step needs a company name, use extracted companies
                        if extracted_companies:
                            for company in extracted_companies:
                                result = await self._execute_playbook(playbook, company, jurisdiction)
                                if result.get('status') == 'success':
                                    all_results.append(result)
                            continue

                    result = await self._execute_playbook(playbook, input_val, jurisdiction)
                    if result.get('status') == 'success':
                        all_results.append(result)

                        # Extract entities for pivot
                        companies = self._extract_companies_from_result(result)
                        persons = self._extract_persons_from_result(result)
                        extracted_companies.extend(companies)
                        extracted_persons.extend(persons)

            elif action_type == 'rule' and action == 'EXTRACT_ENTITIES':
                # Entity extraction step - already handled above
                pass

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'domain_to_corporate_pivot',
            'status': 'success',
            'domain': domain,
            'extracted_companies': list(set(extracted_companies)),
            'extracted_persons': list(set(extracted_persons)),
            'total_results': len(all_results),
            'results': all_results
        }

    async def _compliance_stack(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute stacked compliance playbooks in sequence.

        Process:
        1. Run COMPLIANCE playbook
        2. Run LEGAL playbook
        3. Get officers and run individual sanctions checks
        """
        chain_config = chain_rule.get('chain_config', {})
        steps = chain_config.get('steps', [])
        value = initial_input.get('value')

        all_results = []
        compliance_findings = {
            'sanctions_matches': [],
            'pep_matches': [],
            'adverse_media': [],
            'litigation': [],
            'officers_screened': []
        }

        self._emit_event(event_callback, 'compliance_stack:start', {
            'entity': value,
            'jurisdiction': jurisdiction
        })

        officers = []

        for step in steps:
            action = step.get('action')
            action_type = step.get('action_type', 'rule')

            if action_type == 'playbook':
                playbook_id = self._resolve_playbook_id(action, jurisdiction)
                if playbook_id and playbook_id in self.playbooks_by_id:
                    playbook = self.playbooks_by_id[playbook_id]
                    result = await self._execute_playbook(playbook, value, jurisdiction)
                    if result.get('status') == 'success':
                        all_results.append(result)
                        # Extract compliance-specific data
                        self._extract_compliance_data(result, compliance_findings)

            elif action_type == 'rule':
                rule = self.rules_by_id.get(action)
                if rule:
                    if action == 'COMPANY_OFFICERS':
                        result = await self.rule_executor.execute_rule(rule, value, jurisdiction)
                        if result.get('status') == 'success':
                            all_results.append(result)
                            officers = self._extract_officer_names(result)
                    elif action == 'SANCTIONS_FROM_NAME' and officers:
                        # Screen each officer
                        for officer in officers:
                            result = await self.rule_executor.execute_rule(rule, officer, jurisdiction)
                            if result.get('status') == 'success':
                                all_results.append(result)
                                compliance_findings['officers_screened'].append({
                                    'name': officer,
                                    'result': result.get('data', {})
                                })
                    else:
                        result = await self.rule_executor.execute_rule(rule, value, jurisdiction)
                        if result.get('status') == 'success':
                            all_results.append(result)

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'compliance_stack',
            'status': 'success',
            'entity': value,
            'jurisdiction': jurisdiction,
            'compliance_findings': compliance_findings,
            'total_results': len(all_results),
            'officers_count': len(officers),
            'results': all_results
        }

    async def _media_aggregation(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Aggregate media intelligence from multiple MEDIA playbooks in parallel.

        Process:
        1. Execute GLOBAL media playbook
        2. Execute GB/US media playbooks in parallel
        3. Execute jurisdiction-specific media playbook if specified
        4. Aggregate and deduplicate results
        """
        chain_config = chain_rule.get('chain_config', {})
        steps = chain_config.get('steps', [])
        value = initial_input.get('value')

        all_results = []
        media_items = []

        self._emit_event(event_callback, 'media_aggregation:start', {
            'entity': value,
            'parallel': True
        })

        # Execute all media playbooks in parallel
        tasks = []
        for step in steps:
            action = step.get('action')
            action_type = step.get('action_type', 'playbook')

            if action_type == 'playbook':
                playbook_id = self._resolve_playbook_id(action, jurisdiction)
                if playbook_id and playbook_id in self.playbooks_by_id:
                    playbook = self.playbooks_by_id[playbook_id]
                    tasks.append(self._execute_playbook(playbook, value, jurisdiction))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, dict) and result.get('status') == 'success':
                    all_results.append(result)
                    # Extract media items
                    items = self._extract_media_items(result)
                    media_items.extend(items)

        # Deduplicate media items by URL or title
        seen = set()
        unique_media = []
        for item in media_items:
            key = item.get('url') or item.get('title', '')
            if key and key not in seen:
                seen.add(key)
                unique_media.append(item)

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'media_aggregation',
            'status': 'success',
            'entity': value,
            'total_sources': len(all_results),
            'total_media_items': len(unique_media),
            'media_items': unique_media[:100],  # Limit output
            'results': all_results
        }

    # =========================================================================
    # OSINT Chain Types - Recursive Entity Expansion with Relevance Scoring
    # =========================================================================

    async def _osint_cascade(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        max_depth: int,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute recursive OSINT entity cascade with relevance scoring.

        Given any OSINT entity (email, phone, username, password, LinkedIn, domain, person),
        recursively discovers related entities via breach data and OSINT sources.
        Uses relevance scoring to prevent infinite loops and irrelevant expansion.

        Process:
        1. Execute initial OSINT lookup via EYE-D
        2. Extract all related entities from results
        3. Score each entity for relevance (steps from target, name commonality, connection strength)
        4. AI filters which entities warrant further exploration
        5. Recursively expand approved entities
        6. Persist all entities to cymonides-1 in real-time
        """
        chain_config = chain_rule.get('chain_config', {})
        scoring_config = chain_config.get('scoring', {})
        stopping_conditions = chain_config.get('stopping_conditions', {})
        relevance_threshold = chain_config.get('relevance_threshold', 0.5)
        ai_filter_enabled = chain_config.get('ai_filter_enabled', False)
        persist_to_cymonides = chain_rule.get('cymonides_persistence') == 'always'

        # Initialize tracking structures
        all_results = []
        all_entities = []
        seen_entities = set()
        entity_graph = {
            'root': initial_input.get('value'),
            'root_type': initial_input.get('type', 'unknown'),
            'nodes': [],
            'edges': []
        }

        # Queue: (entity_value, entity_type, depth, relevance_score, parent_entity)
        initial_value = initial_input.get('value')
        initial_type = initial_input.get('type', 'unknown')
        if not initial_value:
            return {
                'chain_id': chain_rule.get('id'),
                'chain_type': 'osint_cascade',
                'status': 'failed',
                'error': 'No initial entity value provided'
            }

        queue = [(initial_value, initial_type, 0, 1.0, None)]
        processed = set()
        total_entities_discovered = 0

        self._emit_event(event_callback, 'osint_cascade:start', {
            'chain_id': chain_rule.get('id'),
            'initial_entity': initial_input.get('value'),
            'initial_type': initial_input.get('type'),
            'max_depth': max_depth,
            'relevance_threshold': relevance_threshold,
            'ai_filter_enabled': ai_filter_enabled
        })

        depth = 0
        while queue and depth <= max_depth:
            # Check stopping conditions
            if total_entities_discovered >= stopping_conditions.get('max_entities', 500):
                self._emit_event(event_callback, 'osint_cascade:stopped', {
                    'reason': 'max_entities_reached',
                    'total_entities': total_entities_discovered
                })
                break

            current_batch = []
            next_queue = []

            # Emit hop event
            self._emit_event(event_callback, 'osint_cascade:hop', {
                'depth': depth,
                'queue_size': len(queue),
                'entities_discovered': total_entities_discovered
            })

            # Process all items at current depth
            while queue and queue[0][2] == depth:
                entity_value, entity_type, entity_depth, relevance, parent = queue.pop(0)

                # Skip if already processed
                entity_key = f"{entity_type}:{entity_value}".lower()
                if entity_key in processed:
                    continue
                processed.add(entity_key)

                # Check minimum relevance
                if relevance < stopping_conditions.get('min_relevance', 0.3):
                    continue

                current_batch.append((entity_value, entity_type, relevance, parent))

            # Execute OSINT lookups for batch
            for entity_value, entity_type, relevance, parent in current_batch:
                # Emit entity:processing event
                self._emit_event(event_callback, 'osint_cascade:entity_processing', {
                    'entity': entity_value,
                    'type': entity_type,
                    'depth': depth,
                    'relevance': relevance
                })

                # Execute OSINT lookup
                osint_result = await self._execute_osint_lookup(entity_value, entity_type)

                if osint_result.get('status') == 'success':
                    all_results.append(osint_result)

                    # Add node to graph
                    node_data = {
                        'value': entity_value,
                        'type': entity_type,
                        'depth': depth,
                        'relevance': relevance,
                        'data': osint_result.get('data', {})
                    }
                    entity_graph['nodes'].append(node_data)
                    all_entities.append(node_data)
                    total_entities_discovered += 1

                    # Add edge if has parent
                    if parent:
                        entity_graph['edges'].append({
                            'from': parent,
                            'to': entity_value,
                            'type': 'discovered_from'
                        })

                    # Persist to cymonides-1 if enabled
                    if persist_to_cymonides:
                        await self._persist_to_cymonides(node_data, event_callback)

                    # Emit entity:discovered event
                    self._emit_event(event_callback, 'osint_cascade:entity_discovered', {
                        'entity': entity_value,
                        'type': entity_type,
                        'depth': depth,
                        'relevance': relevance,
                        'results_count': len(osint_result.get('results', []))
                    })

                    # Extract related entities for next iteration
                    if depth < max_depth:
                        extracted = self._extract_osint_entities(osint_result)

                        for ext_entity in extracted:
                            ext_value = ext_entity.get('value')
                            ext_type = ext_entity.get('type')

                            # Skip if already seen
                            ext_key = f"{ext_type}:{ext_value}".lower()
                            if ext_key in seen_entities:
                                continue
                            seen_entities.add(ext_key)

                            # Calculate relevance score
                            new_relevance = self._calculate_relevance_score(
                                ext_entity,
                                initial_input.get('value'),
                                depth + 1,
                                scoring_config
                            )

                            # AI filter decision (if enabled)
                            should_expand = new_relevance >= relevance_threshold
                            if ai_filter_enabled and should_expand:
                                should_expand = await self._ai_filter_decision(
                                    ext_entity,
                                    initial_input,
                                    depth + 1,
                                    new_relevance,
                                    stopping_conditions.get('ai_confidence_threshold', 0.6),
                                    event_callback
                                )

                            if should_expand:
                                next_queue.append((
                                    ext_value,
                                    ext_type,
                                    depth + 1,
                                    new_relevance,
                                    entity_value
                                ))

            # Move to next depth
            queue = sorted(next_queue, key=lambda x: x[3], reverse=True)  # Sort by relevance
            depth += 1

        self._emit_event(event_callback, 'osint_cascade:complete', {
            'chain_id': chain_rule.get('id'),
            'depth_reached': depth,
            'total_entities': total_entities_discovered,
            'unique_entities': len(seen_entities)
        })

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'osint_cascade',
            'status': 'success',
            'depth_reached': depth,
            'max_depth': max_depth,
            'total_results': len(all_results),
            'unique_entities': len(seen_entities),
            'total_entities_discovered': total_entities_discovered,
            'entity_graph': entity_graph,
            'all_entities': all_entities,
            'results': all_results,
            'jurisdiction': jurisdiction
        }

    async def _osint_breach_network(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        max_depth: int,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute breach-focused network mapping with credential clustering.

        Specialized chain for breach data exploration. Maps credential reuse patterns,
        shared passwords across accounts, and breach source clustering.

        Process:
        1. Execute initial breach lookup
        2. Cluster accounts by password (find password reuse)
        3. Cluster by breach source (find scope of compromise)
        4. Expand to find other accounts for same email/username
        5. Recursively expand newly discovered credentials
        """
        chain_config = chain_rule.get('chain_config', {})
        breach_clustering = chain_config.get('breach_clustering', {})
        relevance_threshold = chain_config.get('relevance_threshold', 0.6)
        persist_to_cymonides = chain_rule.get('cymonides_persistence') == 'always'

        # Validate input
        initial_value = initial_input.get('value')
        initial_type = initial_input.get('type', 'email')
        if not initial_value:
            return {
                'chain_id': chain_rule.get('id'),
                'chain_type': 'osint_breach_network',
                'status': 'failed',
                'error': 'No initial credential value provided'
            }

        all_results = []
        breach_network = {
            'root_credential': initial_value,
            'root_type': initial_type,
            'accounts': [],
            'password_clusters': [],  # Accounts sharing same password
            'breach_clusters': [],    # Accounts from same breach
            'credential_reuse': []    # Email/username appearing in multiple breaches
        }
        seen_credentials = set()
        processed = set()

        self._emit_event(event_callback, 'osint_breach:start', {
            'chain_id': chain_rule.get('id'),
            'initial_credential': initial_input.get('value'),
            'cluster_by_password': breach_clustering.get('cluster_by_password', True),
            'cluster_by_breach': breach_clustering.get('cluster_by_breach_source', True)
        })

        # Queue: (credential_value, credential_type, depth, source_breach)
        queue = [(initial_value, initial_type, 0, None)]
        password_to_accounts = defaultdict(list)
        breach_to_accounts = defaultdict(list)
        email_to_breaches = defaultdict(list)

        depth = 0
        while queue and depth <= max_depth:
            current_batch = []
            next_queue = []

            self._emit_event(event_callback, 'osint_breach:hop', {
                'depth': depth,
                'queue_size': len(queue),
                'accounts_found': len(breach_network['accounts'])
            })

            # Process current depth
            while queue and queue[0][2] == depth:
                cred_value, cred_type, cred_depth, source_breach = queue.pop(0)

                cred_key = f"{cred_type}:{cred_value}".lower()
                if cred_key in processed:
                    continue
                processed.add(cred_key)
                current_batch.append((cred_value, cred_type, source_breach))

            # Execute breach lookups
            for cred_value, cred_type, source_breach in current_batch:
                self._emit_event(event_callback, 'osint_breach:lookup', {
                    'credential': cred_value,
                    'type': cred_type,
                    'depth': depth
                })

                # Execute breach database lookup
                breach_result = await self._execute_breach_lookup(cred_value, cred_type)

                if breach_result.get('status') == 'success':
                    all_results.append(breach_result)

                    # Process breach records
                    for record in breach_result.get('results', []):
                        data = record.get('data', {})

                        # Create account entry
                        account_email = data.get('email') or ''
                        account_username = data.get('username') or ''

                        # Skip if no identifiable data
                        if not account_email and not account_username:
                            continue

                        account = {
                            'email': account_email or None,
                            'username': account_username or None,
                            'password': data.get('password'),
                            'password_hash': data.get('hashed_password'),
                            'breach_source': data.get('database_name') or data.get('source'),
                            'found_via': cred_value,
                            'depth': depth
                        }

                        # Check if account is new (case-insensitive dedup)
                        account_key = f"{account_email}:{account_username}".lower().strip(':')
                        if account_key not in seen_credentials:
                            seen_credentials.add(account_key)
                            breach_network['accounts'].append(account)

                            # Persist if enabled
                            if persist_to_cymonides:
                                await self._persist_to_cymonides({
                                    'value': account['email'] or account['username'],
                                    'type': 'breach_account',
                                    'data': account
                                }, event_callback)

                            # Cluster by password (if enabled)
                            if breach_clustering.get('cluster_by_password') and account.get('password'):
                                password_to_accounts[account['password']].append(account)

                            # Cluster by breach source
                            if breach_clustering.get('cluster_by_breach_source') and account.get('breach_source'):
                                breach_to_accounts[account['breach_source']].append(account)

                            # Track credential reuse
                            if account.get('email'):
                                email_to_breaches[account['email']].append(account.get('breach_source'))

                            # Add to next queue for expansion
                            if depth < max_depth:
                                # Expand on email
                                if account.get('email') and account['email'] != cred_value:
                                    next_queue.append((account['email'], 'email', depth + 1, account.get('breach_source')))

                                # Expand on username
                                if account.get('username') and account['username'] != cred_value:
                                    next_queue.append((account['username'], 'username', depth + 1, account.get('breach_source')))

            # Move to next depth
            queue = next_queue
            depth += 1

        # Build password clusters (accounts sharing same password)
        for password, accounts in password_to_accounts.items():
            if len(accounts) >= 2:
                breach_network['password_clusters'].append({
                    'password_preview': password[:3] + '***' if password else None,
                    'account_count': len(accounts),
                    'accounts': [a.get('email') or a.get('username') for a in accounts],
                    'risk_level': 'high' if len(accounts) >= 5 else 'medium'
                })

        # Build breach clusters
        for breach, accounts in breach_to_accounts.items():
            breach_network['breach_clusters'].append({
                'breach_source': breach,
                'account_count': len(accounts),
                'accounts': [a.get('email') or a.get('username') for a in accounts]
            })

        # Build credential reuse mapping
        for email, breaches in email_to_breaches.items():
            if len(breaches) >= 2:
                breach_network['credential_reuse'].append({
                    'email': email,
                    'breach_count': len(breaches),
                    'breaches': list(set(breaches))
                })

        self._emit_event(event_callback, 'osint_breach:complete', {
            'chain_id': chain_rule.get('id'),
            'total_accounts': len(breach_network['accounts']),
            'password_clusters': len(breach_network['password_clusters']),
            'breach_clusters': len(breach_network['breach_clusters']),
            'credential_reuse_cases': len(breach_network['credential_reuse'])
        })

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'osint_breach_network',
            'status': 'success',
            'depth_reached': depth,
            'max_depth': max_depth,
            'total_results': len(all_results),
            'total_accounts': len(breach_network['accounts']),
            'breach_network': breach_network,
            'results': all_results,
            'jurisdiction': jurisdiction
        }

    async def _osint_person_web(
        self,
        chain_rule: Dict,
        initial_input: Dict,
        max_depth: int,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Dict:
        """Execute person-centric OSINT aggregation with identity resolution.

        Comprehensive person profiling via OSINT. Builds complete digital footprint:
        social media accounts, breach exposure, corporate affiliations, domain ownership.

        Process:
        1. Initial person OSINT lookup
        2. Discover social media accounts
        3. Check breach exposure
        4. Find corporate affiliations
        5. Check domain ownership
        6. Resolve and merge fragmented identity data
        7. Recursively expand discovered accounts
        """
        chain_config = chain_rule.get('chain_config', {})
        identity_resolution = chain_config.get('identity_resolution', {})
        relevance_threshold = chain_config.get('relevance_threshold', 0.55)
        persist_to_cymonides = chain_rule.get('cymonides_persistence') == 'always'

        # Validate input
        initial_value = initial_input.get('value')
        initial_type = initial_input.get('type', 'person')
        if not initial_value:
            return {
                'chain_id': chain_rule.get('id'),
                'chain_type': 'osint_person_web',
                'status': 'failed',
                'error': 'No person identifier provided'
            }

        all_results = []
        person_profile = {
            'primary_identifier': initial_value,
            'identifier_type': initial_type,
            'names': [],
            'emails': [],
            'phones': [],
            'usernames': [],
            'social_profiles': [],
            'breach_exposure': [],
            'corporate_affiliations': [],
            'domains_owned': [],
            'addresses': [],
            'identity_confidence': 1.0
        }
        seen_identifiers = set()

        self._emit_event(event_callback, 'osint_person:start', {
            'chain_id': chain_rule.get('id'),
            'identifier': initial_value,
            'identifier_type': initial_type,
            'identity_resolution_enabled': identity_resolution.get('enabled', True)
        })

        # Step 1: Initial person OSINT lookup
        self._emit_event(event_callback, 'osint_person:step', {
            'step': 1,
            'action': 'PERSON_OSINT_LOOKUP'
        })

        person_result = await self._execute_person_lookup(initial_value, initial_type)

        if person_result.get('status') == 'success':
            all_results.append(person_result)
            self._merge_person_data(person_profile, person_result, seen_identifiers)

            if persist_to_cymonides:
                await self._persist_to_cymonides({
                    'value': initial_value,
                    'type': 'person',
                    'data': person_profile
                }, event_callback)

        # Step 2: Social media discovery
        self._emit_event(event_callback, 'osint_person:step', {
            'step': 2,
            'action': 'SOCIAL_MEDIA_DISCOVERY'
        })

        # Use name and email to find social profiles
        search_terms = [initial_value]
        search_terms.extend(person_profile.get('emails', [])[:3])
        search_terms.extend(person_profile.get('usernames', [])[:3])

        for term in search_terms[:5]:  # Limit searches
            social_result = await self._execute_social_lookup(term)
            if social_result.get('status') == 'success':
                all_results.append(social_result)
                self._extract_social_profiles(social_result, person_profile, seen_identifiers)

        # Step 3: Breach exposure check
        self._emit_event(event_callback, 'osint_person:step', {
            'step': 3,
            'action': 'BREACH_EXPOSURE_CHECK'
        })

        # Check all discovered emails for breaches
        for email in person_profile.get('emails', [])[:10]:
            breach_result = await self._execute_breach_lookup(email, 'email')
            if breach_result.get('status') == 'success':
                all_results.append(breach_result)
                self._extract_breach_exposure(breach_result, person_profile)

                if persist_to_cymonides:
                    await self._persist_to_cymonides({
                        'value': email,
                        'type': 'email_breach',
                        'data': breach_result.get('data', {})
                    }, event_callback)

        # Step 4: Corporate affiliation lookup
        self._emit_event(event_callback, 'osint_person:step', {
            'step': 4,
            'action': 'CORPORATE_AFFILIATION_LOOKUP'
        })

        # Search by person names found
        person_names = person_profile.get('names', [])
        if not person_names and initial_type in ['person', 'person_name']:
            person_names = [initial_value]

        for name in person_names[:3]:
            corp_result = await self._execute_corporate_lookup(name)
            if corp_result.get('status') == 'success':
                all_results.append(corp_result)
                self._extract_corporate_affiliations(corp_result, person_profile)

        # Step 5: Domain ownership check
        self._emit_event(event_callback, 'osint_person:step', {
            'step': 5,
            'action': 'DOMAIN_OWNERSHIP_CHECK'
        })

        # Check emails for potential domain ownership
        for email in person_profile.get('emails', [])[:5]:
            domain = email.split('@')[-1] if '@' in email else None
            if domain and domain not in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']:
                domain_result = await self._execute_domain_lookup(domain)
                if domain_result.get('status') == 'success':
                    all_results.append(domain_result)
                    self._extract_domain_ownership(domain_result, person_profile, person_names)

        # Step 6: Identity resolution (merge fragmented data)
        if identity_resolution.get('enabled', True):
            self._emit_event(event_callback, 'osint_person:step', {
                'step': 6,
                'action': 'IDENTITY_RESOLUTION'
            })

            person_profile['identity_confidence'] = self._resolve_identity(
                person_profile,
                identity_resolution.get('confidence_threshold', 0.75)
            )

        # Step 7: Recursive expansion (if depth allows)
        if max_depth > 1:
            self._emit_event(event_callback, 'osint_person:step', {
                'step': 7,
                'action': 'RECURSIVE_EXPANSION'
            })

            # Expand on discovered social profiles
            for profile in person_profile.get('social_profiles', [])[:5]:
                profile_url = profile.get('url')
                if profile_url:
                    expansion_result = await self._execute_osint_lookup(profile_url, 'url')
                    if expansion_result.get('status') == 'success':
                        all_results.append(expansion_result)
                        self._merge_person_data(person_profile, expansion_result, seen_identifiers)

        self._emit_event(event_callback, 'osint_person:complete', {
            'chain_id': chain_rule.get('id'),
            'emails_found': len(person_profile['emails']),
            'social_profiles_found': len(person_profile['social_profiles']),
            'breach_exposure_count': len(person_profile['breach_exposure']),
            'corporate_affiliations': len(person_profile['corporate_affiliations']),
            'identity_confidence': person_profile['identity_confidence']
        })

        return {
            'chain_id': chain_rule.get('id'),
            'chain_type': 'osint_person_web',
            'status': 'success',
            'max_depth': max_depth,
            'total_results': len(all_results),
            'person_profile': person_profile,
            'results': all_results,
            'jurisdiction': jurisdiction
        }

    # =========================================================================
    # OSINT Chain Helper Methods
    # =========================================================================

    async def _execute_osint_lookup(self, entity_value: str, entity_type: str) -> Dict:
        """Execute unified OSINT lookup via EYE-D or fallback to rule execution."""
        # Map entity type to appropriate rules (primary + fallbacks)
        type_to_rules = {
            'email': ['OSINT_FROM_EMAIL', 'DEHASHED_FROM_EMAIL', 'OSINT_INDUSTRIES_FROM_EMAIL'],
            'phone': ['OSINT_FROM_PHONE', 'OSINT_INDUSTRIES_FROM_PHONE'],
            'username': ['OSINT_FROM_USERNAME', 'DEHASHED_FROM_USERNAME'],
            'domain': ['WHOIS_FROM_DOMAIN', 'DOMAIN_LOOKUP'],
            'person': ['OSINT_FROM_PERSON', 'OSINT_INDUSTRIES_FROM_NAME'],
            'person_name': ['OSINT_FROM_PERSON', 'OSINT_INDUSTRIES_FROM_NAME'],
            'linkedin': ['OSINT_FROM_LINKEDIN', 'OSINT_FROM_URL'],
            'url': ['OSINT_FROM_URL', 'URL_LOOKUP']
        }

        rule_ids = type_to_rules.get(entity_type, ['OSINT_FROM_EMAIL', 'DEHASHED_FROM_EMAIL'])

        # Try each rule until one succeeds
        for rule_id in rule_ids:
            rule = self.rules_by_id.get(rule_id)
            if rule:
                try:
                    result = await self.rule_executor.execute_rule(rule, entity_value, None)
                    if result.get('status') == 'success':
                        return result
                except Exception as e:
                    continue  # Try next fallback

        return {'status': 'failed', 'error': f'No working rule for type: {entity_type}', 'entity': entity_value}

    async def _execute_breach_lookup(self, credential: str, cred_type: str) -> Dict:
        """Execute breach database lookup with fallbacks."""
        if cred_type == 'email':
            rule_ids = ['DEHASHED_FROM_EMAIL', 'LEAKCHECK_FROM_EMAIL', 'BREACH_FROM_EMAIL']
        else:
            rule_ids = ['DEHASHED_FROM_USERNAME', 'LEAKCHECK_FROM_USERNAME', 'BREACH_FROM_USERNAME']

        for rule_id in rule_ids:
            rule = self.rules_by_id.get(rule_id)
            if rule:
                try:
                    result = await self.rule_executor.execute_rule(rule, credential, None)
                    if result.get('status') == 'success':
                        return result
                except Exception:
                    continue

        return {'status': 'failed', 'error': 'No breach lookup rule available', 'credential': credential}

    async def _execute_person_lookup(self, identifier: str, id_type: str) -> Dict:
        """Execute person-centric OSINT lookup with fallbacks."""
        if id_type == 'email':
            rule_ids = ['OSINT_INDUSTRIES_FROM_EMAIL', 'OSINT_FROM_EMAIL', 'PERSON_FROM_EMAIL']
        elif id_type == 'linkedin':
            rule_ids = ['OSINT_FROM_LINKEDIN', 'LINKEDIN_LOOKUP', 'OSINT_FROM_URL']
        else:
            rule_ids = ['OSINT_FROM_PERSON', 'OSINT_INDUSTRIES_FROM_NAME', 'PERSON_LOOKUP']

        for rule_id in rule_ids:
            rule = self.rules_by_id.get(rule_id)
            if rule:
                try:
                    result = await self.rule_executor.execute_rule(rule, identifier, None)
                    if result.get('status') == 'success':
                        return result
                except Exception:
                    continue

        return {'status': 'failed', 'error': 'No person lookup rule available', 'identifier': identifier}

    async def _execute_social_lookup(self, search_term: str) -> Dict:
        """Execute social media profile lookup with fallbacks."""
        rule_ids = ['SOCIAL_FROM_NAME', 'SOCIAL_MEDIA_LOOKUP', 'USERNAME_SEARCH']

        for rule_id in rule_ids:
            rule = self.rules_by_id.get(rule_id)
            if rule:
                try:
                    result = await self.rule_executor.execute_rule(rule, search_term, None)
                    if result.get('status') == 'success':
                        return result
                except Exception:
                    continue

        return {'status': 'failed', 'error': 'No social lookup rule available', 'search_term': search_term}

    async def _execute_corporate_lookup(self, person_name: str) -> Dict:
        """Execute corporate affiliation lookup with fallbacks."""
        rule_ids = ['OFFICER_APPOINTMENTS_FROM_PERSON_NAME', 'OFFICER_SEARCH', 'CORPORATE_PERSON_LOOKUP']

        for rule_id in rule_ids:
            rule = self.rules_by_id.get(rule_id)
            if rule:
                try:
                    result = await self.rule_executor.execute_rule(rule, person_name, None)
                    if result.get('status') == 'success':
                        return result
                except Exception:
                    continue

        return {'status': 'failed', 'error': 'No corporate lookup rule available', 'person_name': person_name}

    async def _execute_domain_lookup(self, domain: str) -> Dict:
        """Execute domain WHOIS lookup with fallbacks."""
        rule_ids = ['WHOIS_FROM_DOMAIN', 'DOMAIN_WHOIS', 'DOMAIN_LOOKUP']

        for rule_id in rule_ids:
            rule = self.rules_by_id.get(rule_id)
            if rule:
                try:
                    result = await self.rule_executor.execute_rule(rule, domain, None)
                    if result.get('status') == 'success':
                        return result
                except Exception:
                    continue

        return {'status': 'failed', 'error': 'No domain lookup rule available', 'domain': domain}

    def _extract_osint_entities(self, result: Dict) -> List[Dict]:
        """Extract all OSINT entities from a result for further expansion."""
        entities = []
        entity_patterns = {
            'email': ['email', 'e-mail', 'mail'],
            'phone': ['phone', 'mobile', 'telephone', 'cell'],
            'username': ['username', 'user', 'login', 'handle'],
            'domain': ['domain', 'website', 'url'],
            'person_name': ['name', 'full_name', 'person_name']
        }

        for res in result.get('results', []):
            data = res.get('data', {})
            if isinstance(data, dict):
                for entity_type, patterns in entity_patterns.items():
                    for pattern in patterns:
                        for key, value in data.items():
                            if pattern in key.lower() and value:
                                if isinstance(value, str) and len(value) > 2:
                                    entities.append({'value': value, 'type': entity_type})
                                elif isinstance(value, list):
                                    for v in value:
                                        if isinstance(v, str) and len(v) > 2:
                                            entities.append({'value': v, 'type': entity_type})

        return entities

    # =========================================================================
    # Source Provenance Weights (from Query Lab consolidation plan)
    # =========================================================================
    # Confidence multipliers by data source type
    # Higher = more authoritative, lower = less certain

    SOURCE_PROVENANCE_WEIGHTS = {
        # Official registries (highest confidence)
        'corporate_registry': 0.99, 'companies_house': 0.99, 'government_registry': 0.98,
        'court_records': 0.95, 'land_registry': 0.95, 'fec': 0.97, 'sec': 0.97,
        # Professional databases (high confidence)
        'opencorporates': 0.90, 'orbis': 0.92, 'lexisnexis': 0.88, 'dnb': 0.90,
        # OSINT sources (medium confidence)
        'osint_industries': 0.85, 'dehashed': 0.80, 'leakcheck': 0.78, 'breach_data': 0.75,
        'whois': 0.82, 'dns': 0.85,
        # Social/public sources (lower confidence)
        'linkedin': 0.70, 'social_media': 0.65, 'news': 0.70, 'web_scrape': 0.60,
        # AI extraction (variable confidence)
        'ai_extraction': 0.75, 'entity_extraction': 0.72,
        # Default
        'unknown': 0.50,
    }

    def _get_source_provenance(self, source: str) -> float:
        """Get provenance weight for a data source."""
        if not source:
            return self.SOURCE_PROVENANCE_WEIGHTS['unknown']
        source_lower = source.lower()
        # Direct match
        if source_lower in self.SOURCE_PROVENANCE_WEIGHTS:
            return self.SOURCE_PROVENANCE_WEIGHTS[source_lower]
        # Partial match
        for key, weight in self.SOURCE_PROVENANCE_WEIGHTS.items():
            if key in source_lower or source_lower in key:
                return weight
        return self.SOURCE_PROVENANCE_WEIGHTS['unknown']

    def _calculate_chain_provenance(self, source_sequence: List[str]) -> float:
        """Calculate accumulated provenance through a chain of sources.

        From consolidation plan: (cuk: 0.99) => (p? 0.85) => (e: 0.70) = 0.99 × 0.85 × 0.70 = 0.59
        """
        if not source_sequence:
            return 1.0
        provenance = 1.0
        for source in source_sequence:
            provenance *= self._get_source_provenance(source)
        return provenance

    def _calculate_relevance_score(
        self,
        entity: Dict,
        root_value: str,
        depth: int,
        scoring_config: Dict,
        source: str = None,
        chain_provenance: float = 1.0
    ) -> float:
        """Calculate relevance score with provenance-weighted chain confidence.

        From Query Lab consolidation plan - Graph Convolution + Provenance:
        - conv(p: John Smith, n=3, decay=0.5) = 3-hop with 50% decay per hop
        - (cuk: 0.99) => (p? 0.85) => (e: 0.70) = Final: 0.99 × 0.85 × 0.70 = 0.59

        Scoring factors:
        - Graph convolution decay (exponential per hop)
        - Name commonality (common names penalized)
        - Connection strength (name similarity boost)
        - Source provenance (official registry vs breach data)
        - Chain provenance (accumulated confidence)
        """
        base_score = 1.0

        # Graph Convolution: Exponential decay per hop
        # conv(entity, n=depth, decay=decay_per_step)
        decay_per_step = scoring_config.get('decay_per_step', 0.15)
        depth_factor = (1 - decay_per_step) ** depth
        base_score *= depth_factor

        # Name commonality penalty
        name_weight = scoring_config.get('name_commonality_weight', 0.3)
        common_name_penalty = scoring_config.get('common_name_penalty', 0.7)
        entity_value = entity.get('value', '').lower()

        common_names = [
            'john', 'james', 'michael', 'david', 'robert', 'william', 'mary', 'jennifer',
            'smith', 'johnson', 'williams', 'jones', 'brown', 'davis', 'miller',
            'test', 'admin', 'user', 'info', 'contact', 'support', 'noreply', 'no-reply'
        ]
        if any(common in entity_value for common in common_names):
            base_score -= common_name_penalty * name_weight

        # Connection strength (name similarity)
        connection_weight = scoring_config.get('connection_strength_weight', 0.3)
        root_lower = (root_value or '').lower()

        if root_lower and entity_value:
            # Exact match = big boost
            if root_lower == entity_value:
                base_score += 0.3 * connection_weight
            # Partial match (substring)
            elif root_lower in entity_value or entity_value in root_lower:
                base_score += 0.2 * connection_weight
            # Same email domain
            elif '@' in root_lower and '@' in entity_value:
                if root_lower.split('@')[-1] == entity_value.split('@')[-1]:
                    base_score += 0.15 * connection_weight

        # Source Provenance Weight
        if source:
            base_score *= self._get_source_provenance(source)

        # Chain Provenance: Multiply accumulated confidence through chain
        base_score *= chain_provenance

        # Flag entities below verification threshold (from consolidation plan)
        entity['needs_verification'] = base_score < 0.5
        entity['confidence'] = base_score

        return max(0.0, min(1.0, base_score))

    # =========================================================================
    # ?age Operator - Calculate entity age
    # =========================================================================
    # Pattern: ?age extracts age from dates (person birth, company incorporation)

    def age_operator(
        self,
        entity: Dict,
        reference_date: Optional[str] = None
    ) -> Dict:
        """
        ?age operator - Calculate age of an entity.

        For persons: age from birth_date
        For companies: age from incorporation_date
        For domains: age from registration_date

        Args:
            entity: Entity dict with date fields
            reference_date: Optional reference date (defaults to today)

        Returns:
            Dict with age calculation: {years, months, days, age_string, source_date}
        """
        from datetime import datetime, date
        import re

        # Date field patterns by entity type
        date_field_patterns = {
            'person': ['birth_date', 'birthdate', 'date_of_birth', 'dob', 'born'],
            'company': ['incorporation_date', 'registered_date', 'founded', 'established',
                       'date_incorporated', 'formation_date', 'registration_date'],
            'domain': ['registration_date', 'created', 'created_date', 'registered',
                      'creation_date', 'domain_registered'],
        }

        # Determine entity type
        entity_type = entity.get('type', entity.get('entity_type', 'unknown')).lower()

        # Find relevant date field
        source_date_str = None
        source_field = None

        # Try type-specific patterns first
        patterns = date_field_patterns.get(entity_type, [])
        for pattern in patterns:
            for key, value in entity.items():
                if pattern in key.lower() and value:
                    source_date_str = str(value)
                    source_field = key
                    break
            if source_date_str:
                break

        # Fallback: try any date-like field
        if not source_date_str:
            for key, value in entity.items():
                if any(d in key.lower() for d in ['date', 'born', 'founded', 'created', 'registered']):
                    if value and isinstance(value, (str, datetime, date)):
                        source_date_str = str(value)
                        source_field = key
                        break

        if not source_date_str:
            return {
                'status': 'no_date_found',
                'entity_type': entity_type,
                'searched_patterns': patterns
            }

        # Parse date
        source_date = None
        date_formats = [
            '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d',
            '%d-%m-%Y', '%Y%m%d', '%d.%m.%Y', '%Y.%m.%d',
            '%B %d, %Y', '%d %B %Y', '%b %d, %Y', '%d %b %Y',
            '%Y', '%m/%Y', '%Y-%m'  # Partial dates
        ]

        for fmt in date_formats:
            try:
                source_date = datetime.strptime(source_date_str.strip()[:20], fmt)
                break
            except ValueError:
                continue

        # Try regex extraction for embedded dates
        if not source_date:
            date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', source_date_str)
            if date_match:
                try:
                    source_date = datetime.strptime(date_match.group(1).replace('/', '-'), '%Y-%m-%d')
                except ValueError:
                    pass

        if not source_date:
            return {
                'status': 'parse_error',
                'source_string': source_date_str,
                'source_field': source_field
            }

        # Reference date
        if reference_date:
            ref_date = datetime.strptime(reference_date, '%Y-%m-%d')
        else:
            ref_date = datetime.now()

        # Calculate age
        years = ref_date.year - source_date.year
        months = ref_date.month - source_date.month
        days = ref_date.day - source_date.day

        # Adjust for negative months/days
        if days < 0:
            months -= 1
            # Approximate days in previous month
            days += 30
        if months < 0:
            years -= 1
            months += 12

        # Generate age string
        if entity_type == 'person':
            age_string = f"{years} years old"
        elif entity_type == 'company':
            if years == 0:
                age_string = f"{months} months since incorporation"
            else:
                age_string = f"{years} years since incorporation"
        elif entity_type == 'domain':
            if years == 0:
                age_string = f"{months} months since registration"
            else:
                age_string = f"{years} years since registration"
        else:
            age_string = f"{years} years, {months} months"

        return {
            'status': 'success',
            'entity_type': entity_type,
            'source_field': source_field,
            'source_date': source_date.isoformat(),
            'reference_date': ref_date.isoformat(),
            'years': years,
            'months': months,
            'days': days,
            'total_days': (ref_date - source_date).days,
            'age_string': age_string
        }

    def apply_age_to_results(
        self,
        results: Dict,
        entity_key: str = 'entities'
    ) -> Dict:
        """
        Apply ?age operator to all entities in a result set.

        Usage in templates:
            results = await chain.execute(...)
            results = chain.apply_age_to_results(results)
        """
        entities = results.get(entity_key, [])
        if not entities and 'results' in results:
            entities = results.get('results', [])

        for entity in entities:
            age_info = self.age_operator(entity)
            if age_info.get('status') == 'success':
                entity['age'] = age_info

        return results

    async def _ai_filter_decision(
        self,
        entity: Dict,
        root_input: Dict,
        depth: int,
        relevance: float,
        confidence_threshold: float,
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> bool:
        """Use AI to decide if entity warrants further exploration.

        Returns True if AI recommends expanding this entity.
        """
        # For now, use heuristic-based filtering
        # In production, this would call GPT-4.1-nano for decision

        entity_value = entity.get('value', '')
        entity_type = entity.get('type', '')

        # Always expand emails and usernames (high value)
        if entity_type in ['email', 'username']:
            return True

        # Expand domains if not generic
        if entity_type == 'domain':
            generic_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']
            return entity_value not in generic_domains

        # For person names, require higher relevance
        if entity_type == 'person_name':
            return relevance >= 0.6

        # Default: use relevance threshold
        return relevance >= confidence_threshold

    async def _persist_to_cymonides(
        self,
        entity_data: Dict,
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> bool:
        """Persist entity to cymonides-1.

        Returns True if persistence succeeded.
        Tries multiple import paths for flexibility.
        """
        ATLASNodeCreator = None

        # Try multiple import paths
        import_paths = [
            ('CYMONIDES.atlas_node_creator', 'ATLASNodeCreator'),
            ('cymonides.atlas_node_creator', 'ATLASNodeCreator'),
            ('CYMONIDES.cymonides_unified', 'ATLASNodeCreator'),
        ]

        for module_path, class_name in import_paths:
            try:
                module = __import__(module_path, fromlist=[class_name])
                ATLASNodeCreator = getattr(module, class_name)
                break
            except (ImportError, AttributeError):
                continue

        if not ATLASNodeCreator:
            # Cymonides not available - skip persistence silently
            return False

        try:
            creator = ATLASNodeCreator()

            # Try the async create_node method first, fall back to sync
            if hasattr(creator, 'create_node'):
                create_method = creator.create_node
            elif hasattr(creator, 'process_atlas_results'):
                create_method = creator.process_atlas_results
            else:
                return False

            # Check if method is async
            import asyncio
            if asyncio.iscoroutinefunction(create_method):
                result = await create_method(
                    entity_type=entity_data.get('type'),
                    value=entity_data.get('value'),
                    data=entity_data.get('data', {}),
                    source='osint_chain'
                )
            else:
                result = create_method(
                    entity_type=entity_data.get('type'),
                    value=entity_data.get('value'),
                    data=entity_data.get('data', {}),
                    source='osint_chain'
                )

            if result:
                self._emit_event(event_callback, 'cymonides:persisted', {
                    'entity': entity_data.get('value'),
                    'type': entity_data.get('type')
                })
                return True

        except Exception as e:
            self._emit_event(event_callback, 'cymonides:error', {
                'entity': entity_data.get('value'),
                'error': str(e)
            })

        return False

    def _merge_person_data(
        self,
        profile: Dict,
        result: Dict,
        seen: set
    ):
        """Merge OSINT result data into person profile."""
        for res in result.get('results', []):
            data = res.get('data', {})
            if not isinstance(data, dict):
                continue

            # Extract and merge emails
            for key in ['email', 'emails', 'e-mail']:
                if key in data:
                    vals = data[key] if isinstance(data[key], list) else [data[key]]
                    for v in vals:
                        if v and v not in seen:
                            seen.add(v)
                            profile['emails'].append(v)

            # Extract and merge phones
            for key in ['phone', 'phones', 'mobile', 'telephone']:
                if key in data:
                    vals = data[key] if isinstance(data[key], list) else [data[key]]
                    for v in vals:
                        if v and v not in seen:
                            seen.add(v)
                            profile['phones'].append(v)

            # Extract and merge names
            for key in ['name', 'full_name', 'person_name', 'display_name']:
                if key in data:
                    v = data[key]
                    if v and v not in seen:
                        seen.add(v)
                        profile['names'].append(v)

            # Extract and merge usernames
            for key in ['username', 'handle', 'screen_name', 'user']:
                if key in data:
                    vals = data[key] if isinstance(data[key], list) else [data[key]]
                    for v in vals:
                        if v and v not in seen:
                            seen.add(v)
                            profile['usernames'].append(v)

    def _extract_social_profiles(
        self,
        result: Dict,
        profile: Dict,
        seen: set
    ):
        """Extract social media profiles from result."""
        for res in result.get('results', []):
            data = res.get('data', {})

            # Look for social profile indicators
            social_keys = ['linkedin', 'twitter', 'facebook', 'instagram', 'github', 'social_profiles']
            for key in social_keys:
                if key in data:
                    val = data[key]
                    if isinstance(val, str) and val not in seen:
                        seen.add(val)
                        profile['social_profiles'].append({
                            'platform': key,
                            'url': val
                        })
                    elif isinstance(val, list):
                        for v in val:
                            if isinstance(v, dict):
                                profile['social_profiles'].append(v)
                            elif isinstance(v, str) and v not in seen:
                                seen.add(v)
                                profile['social_profiles'].append({
                                    'platform': key,
                                    'url': v
                                })

    def _extract_breach_exposure(self, result: Dict, profile: Dict):
        """Extract breach exposure data from result."""
        for res in result.get('results', []):
            data = res.get('data', {})

            breach_info = {
                'email': data.get('email'),
                'breach_source': data.get('database_name') or data.get('source'),
                'password_exposed': bool(data.get('password')),
                'date': data.get('date') or data.get('breach_date')
            }

            if breach_info['breach_source']:
                profile['breach_exposure'].append(breach_info)

    def _extract_corporate_affiliations(self, result: Dict, profile: Dict):
        """Extract corporate affiliations from result."""
        for res in result.get('results', []):
            data = res.get('data', {})

            affiliation = {
                'company_name': data.get('company_name') or data.get('company'),
                'role': data.get('officer_role') or data.get('role') or data.get('position'),
                'status': data.get('status', 'active'),
                'jurisdiction': data.get('jurisdiction')
            }

            if affiliation['company_name']:
                profile['corporate_affiliations'].append(affiliation)

    def _extract_domain_ownership(self, result: Dict, profile: Dict, person_names: List[str]):
        """Extract domain ownership from WHOIS result if matches person."""
        for res in result.get('results', []):
            data = res.get('data', {})

            registrant = data.get('registrant_name') or data.get('registrant')
            domain = data.get('domain')

            # Check if registrant matches any person name
            if registrant and person_names:
                registrant_lower = registrant.lower()
                for name in person_names:
                    if name.lower() in registrant_lower or registrant_lower in name.lower():
                        profile['domains_owned'].append({
                            'domain': domain,
                            'registrant': registrant,
                            'created': data.get('created_date'),
                            'expires': data.get('expiry_date')
                        })
                        break

    def _resolve_identity(self, profile: Dict, confidence_threshold: float) -> float:
        """Resolve identity by analyzing consistency of profile data.

        Returns confidence score (0.0 - 1.0) that all data belongs to same person.
        """
        confidence = 1.0
        issues = []

        # Check name consistency
        names = profile.get('names', [])
        if len(names) > 3:
            # Many different names could indicate data mixing
            confidence -= 0.1 * (len(names) - 3)
            issues.append('multiple_names')

        # Check email domain consistency
        emails = profile.get('emails', [])
        if len(emails) > 1:
            domains = set(e.split('@')[-1] for e in emails if '@' in e)
            # Multiple unrelated domains is suspicious
            if len(domains) > 5:
                confidence -= 0.15
                issues.append('many_email_domains')

        # Check if social profiles are consistent
        social = profile.get('social_profiles', [])
        if len(social) > 10:
            confidence -= 0.1
            issues.append('many_social_profiles')

        # Boost confidence if data is internally consistent
        if len(names) == 1 and len(emails) <= 3:
            confidence += 0.1

        return max(0.0, min(1.0, confidence))

    # =========================================================================
    # Playbook Chain Helpers
    # =========================================================================

    def _resolve_playbook_id(self, pattern: str, jurisdiction: Optional[str]) -> Optional[str]:
        """Resolve a playbook pattern to actual playbook ID.

        Handles patterns like:
        - PLY_{jurisdiction}_REGISTRY_*
        - {selected_playbook.id}
        """
        if not pattern:
            return None

        # Replace jurisdiction placeholder
        if '{jurisdiction}' in pattern and jurisdiction:
            pattern = pattern.replace('{jurisdiction}', jurisdiction.upper())

        # Handle wildcard patterns
        if '*' in pattern:
            prefix = pattern.replace('*', '')
            for pb_id in self.playbooks_by_id.keys():
                if pb_id.startswith(prefix):
                    return pb_id
            return None

        # Handle dynamic reference
        if pattern.startswith('{'):
            return None  # Needs to be resolved from context

        # Direct ID
        if pattern in self.playbooks_by_id:
            return pattern

        return None

    async def _execute_chain_step(
        self,
        step: Dict,
        value: str,
        jurisdiction: Optional[str],
        event_callback: Optional[Callable[[str, Dict], None]] = None
    ) -> Optional[Dict]:
        """Execute a single step in a chain (rule or playbook)."""
        action = step.get('action')
        action_type = step.get('action_type', 'rule')

        if action_type == 'playbook':
            playbook_id = self._resolve_playbook_id(action, jurisdiction)
            if playbook_id and playbook_id in self.playbooks_by_id:
                playbook = self.playbooks_by_id[playbook_id]
                return await self._execute_playbook(playbook, value, jurisdiction)
        elif action_type == 'rule':
            rule = self.rules_by_id.get(action)
            if rule:
                return await self.rule_executor.execute_rule(rule, value, jurisdiction)

        return None

    def _merge_chain_data(self, aggregated: Dict, result: Dict):
        """Merge chain step result into aggregated data."""
        for key, val in result.get('data', {}).items():
            if key not in aggregated:
                aggregated[key] = val
            elif isinstance(val, list) and isinstance(aggregated[key], list):
                aggregated[key].extend(val)
            elif isinstance(val, dict) and isinstance(aggregated[key], dict):
                aggregated[key].update(val)

    def _extract_companies_from_result(self, result: Dict) -> List[str]:
        """Extract company names from a result."""
        companies = []
        for r in result.get('results', []):
            data = r.get('data', {})
            for key in ['company_name', 'registrant_company', 'company', 'organization']:
                if key in data and data[key]:
                    companies.append(data[key])
        return companies

    def _extract_persons_from_result(self, result: Dict) -> List[str]:
        """Extract person names from a result."""
        persons = []
        for r in result.get('results', []):
            data = r.get('data', {})
            for key in ['person_name', 'registrant_person', 'name', 'contact']:
                if key in data and data[key]:
                    persons.append(data[key])
        return persons

    def _extract_officer_names(self, result: Dict) -> List[str]:
        """Extract officer names from company officers result."""
        officers = []
        for r in result.get('results', []):
            data = r.get('data', {})
            if 'officers' in data and isinstance(data['officers'], list):
                for officer in data['officers']:
                    if isinstance(officer, dict):
                        name = officer.get('name') or officer.get('officer_name')
                        if name:
                            officers.append(name)
                    elif isinstance(officer, str):
                        officers.append(officer)
            if 'officer_name' in data:
                officers.append(data['officer_name'])
        return list(set(officers))

    def _extract_compliance_data(self, result: Dict, findings: Dict):
        """Extract compliance-specific data from result."""
        for r in result.get('results', []):
            data = r.get('data', {})
            if data.get('sanctions_match'):
                findings['sanctions_matches'].append(data)
            if data.get('pep_status'):
                findings['pep_matches'].append(data)
            if data.get('adverse_media'):
                findings['adverse_media'].extend(
                    data['adverse_media'] if isinstance(data['adverse_media'], list) else [data['adverse_media']]
                )
            if data.get('litigation'):
                findings['litigation'].extend(
                    data['litigation'] if isinstance(data['litigation'], list) else [data['litigation']]
                )

    def _extract_media_items(self, result: Dict) -> List[Dict]:
        """Extract media items from result."""
        items = []
        for r in result.get('results', []):
            data = r.get('data', {})
            # Handle list of articles
            if 'articles' in data and isinstance(data['articles'], list):
                items.extend(data['articles'])
            # Handle single article
            if data.get('url') or data.get('title'):
                items.append({
                    'url': data.get('url'),
                    'title': data.get('title'),
                    'source': data.get('source'),
                    'date': data.get('date') or data.get('published_date'),
                    'snippet': data.get('snippet') or data.get('description')
                })
        return items

    # =========================================================================
    # Helper Methods - Entity Extraction and Deduplication
    # =========================================================================

    def _extract_entities(self, result: Dict, output_fields: List[int]) -> List[str]:
        """Extract entity values from execution result based on output fields.

        Args:
            result: Execution result from RuleExecutor
            output_fields: List of field codes to extract

        Returns:
            List of entity values (company names, person names, etc.)
        """
        entities = []
        results_list = result.get('results', [])

        for res in results_list:
            data = res.get('data', {})

            if isinstance(data, dict):
                # Extract values for output fields
                for field_code in output_fields:
                    field_name = self.legend.get(field_code, '')

                    if field_name in data:
                        value = data[field_name]
                        if value and isinstance(value, str):
                            entities.append(value)

                    # Also check common variations
                    for key in data.keys():
                        if field_name.replace('_', '') in key.replace('_', ''):
                            value = data[key]
                            if value and isinstance(value, str):
                                entities.append(value)

            elif isinstance(data, list):
                # Data is array of records
                for record in data:
                    if isinstance(record, dict):
                        for field_code in output_fields:
                            field_name = self.legend.get(field_code, '')
                            if field_name in record:
                                value = record[field_name]
                                if value and isinstance(value, str):
                                    entities.append(value)

        # Deduplicate while preserving order
        seen = set()
        unique_entities = []
        for entity in entities:
            if entity not in seen:
                seen.add(entity)
                unique_entities.append(entity)

        return unique_entities

    def _extract_shareholders(self, result: Dict) -> List[Dict]:
        """Extract shareholder information from result.

        Returns list of dicts with: name, ownership_pct, type
        """
        shareholders = []
        results_list = result.get('results', [])

        for res in results_list:
            data = res.get('data', {})

            if isinstance(data, list):
                for record in data:
                    if isinstance(record, dict):
                        shareholder = {
                            'name': record.get('shareholder_name') or record.get('name'),
                            'ownership_pct': float(record.get('ownership_pct', 0) or record.get('shares_pct', 0)),
                            'type': record.get('shareholder_type', 'person')
                        }
                        if shareholder['name']:
                            shareholders.append(shareholder)

            elif isinstance(data, dict):
                # Single shareholder record
                if 'shareholders' in data and isinstance(data['shareholders'], list):
                    for s in data['shareholders']:
                        shareholder = {
                            'name': s.get('name'),
                            'ownership_pct': float(s.get('ownership_pct', 0)),
                            'type': s.get('type', 'person')
                        }
                        if shareholder['name']:
                            shareholders.append(shareholder)

        return shareholders

    def _extract_holdings(self, result: Dict) -> List[Dict]:
        """Extract holdings/shareholding information from result.

        Returns list of dicts with: company, ownership_pct
        """
        holdings = []
        results_list = result.get('results', [])

        for res in results_list:
            data = res.get('data', {})

            if isinstance(data, list):
                for record in data:
                    if isinstance(record, dict):
                        holding = {
                            'company': record.get('company_name') or record.get('company'),
                            'ownership_pct': float(record.get('ownership_pct', 0) or record.get('shares_pct', 0))
                        }
                        if holding['company']:
                            holdings.append(holding)

        return holdings

    def _extract_persons(self, result: Dict) -> List[Dict]:
        """Extract person information from result.

        Returns list of dicts with: name, role
        """
        persons = []
        results_list = result.get('results', [])

        for res in results_list:
            data = res.get('data', {})

            if isinstance(data, list):
                for record in data:
                    if isinstance(record, dict):
                        person = {
                            'name': (record.get('officer_name') or
                                   record.get('beneficial_owner_name') or
                                   record.get('shareholder_name') or
                                   record.get('person_name') or
                                   record.get('name')),
                            'role': (record.get('officer_role') or
                                   record.get('role') or
                                   record.get('type', 'unknown'))
                        }
                        if person['name']:
                            persons.append(person)

        return persons

    def _make_dedup_key(self, value: Any, dedup_fields: List[int]) -> str:
        """Create deduplication key from value.

        Args:
            value: Entity value (string) or dict with multiple fields
            dedup_fields: Field codes to use for deduplication

        Returns:
            String key for deduplication
        """
        if isinstance(value, str):
            # Simple string value - normalize and use as key
            return value.lower().strip()

        elif isinstance(value, dict):
            # Extract values for dedup fields
            key_parts = []
            for field_code in dedup_fields:
                field_name = self.legend.get(field_code, '')
                if field_name in value:
                    key_parts.append(str(value[field_name]).lower().strip())

            return '|'.join(key_parts) if key_parts else str(value)

        else:
            return str(value)


# =============================================================================
# Integration Functions for io_cli.py
# =============================================================================

async def execute_chain_rule(
    chain_rule_id: str,
    initial_value: str,
    jurisdiction: Optional[str] = None,
    event_callback: Optional[Callable[[str, Dict], None]] = None
) -> Dict:
    """Execute a chain rule by ID.

    This is the main entry point for chain execution from io_cli.py.

    Args:
        chain_rule_id: ID of chain rule from chain_rules.json
        initial_value: Input value (person name, company name, etc.)
        jurisdiction: Optional jurisdiction filter
        event_callback: Optional callback for streaming events (event_type, data) -> None

    Returns:
        Dict with chain execution results
    """
    # Import RuleExecutor from io_cli
    from io_cli import RuleExecutor

    # Initialize executors
    rule_executor = RuleExecutor()
    chain_executor = ChainExecutor(rule_executor)

    # Get chain rule
    chain_rule = chain_executor.chain_rules.get(chain_rule_id)
    if not chain_rule:
        return {
            'error': f'Chain rule not found: {chain_rule_id}',
            'available_chains': list(chain_executor.chain_rules.keys())
        }

    # Execute chain
    initial_input = {'value': initial_value}
    result = await chain_executor.execute_chain(chain_rule, initial_input, jurisdiction, event_callback)

    # Cleanup
    await rule_executor.close()

    return result


async def execute_playbook_chain(
    chain_id: str,
    value: str,
    jurisdiction: Optional[str] = None,
    playbook_categories: Optional[List[str]] = None,
    event_callback: Optional[Callable[[str, Dict], None]] = None
) -> Dict:
    """Execute a playbook-based chain rule.

    This is the entry point referenced by chain_rules.json for playbook chains.
    Handles auto-selection of playbooks based on jurisdiction and categories.

    Args:
        chain_id: ID of the playbook chain (e.g., CHAIN_PLAYBOOK_FULL_COMPANY_INTEL)
        value: Input value (company name, person name, domain, etc.)
        jurisdiction: Optional jurisdiction code (HU, GB, US, etc.)
        playbook_categories: Optional list of categories (REGISTRY, LEGAL, COMPLIANCE, MEDIA)
        event_callback: Optional callback for streaming events

    Returns:
        Dict with chain execution results including aggregated data from all playbooks
    """
    # Import RuleExecutor from io_cli
    from io_cli import RuleExecutor, IORouter

    # Initialize executors
    rule_executor = RuleExecutor()
    chain_executor = ChainExecutor(rule_executor)

    # Get chain rule
    chain_rule = chain_executor.chain_rules.get(chain_id)
    if not chain_rule:
        # Try to find a matching playbook chain
        playbook_chains = [
            cid for cid in chain_executor.chain_rules.keys()
            if 'PLAYBOOK' in cid
        ]
        return {
            'error': f'Playbook chain not found: {chain_id}',
            'available_playbook_chains': playbook_chains
        }

    # Verify this is a playbook-based chain
    if not chain_rule.get('uses_playbooks'):
        return {
            'error': f'{chain_id} is not a playbook-based chain',
            'suggestion': 'Use execute_chain_rule() for non-playbook chains'
        }

    # Execute chain
    initial_input = {'value': value}
    result = await chain_executor.execute_chain(chain_rule, initial_input, jurisdiction, event_callback)

    # Cleanup
    await rule_executor.close()

    return result


def recommend_playbooks_sync(
    entity_type: str,
    jurisdiction: Optional[str] = None,
    top_n: int = 5,
    min_success_rate: float = 0.0,
    prefer_friction: Optional[str] = None
) -> List[Dict]:
    """Synchronous wrapper for playbook recommendations.

    Convenience function for CLI and API use.

    Args:
        entity_type: "company", "person", "domain", "email", "phone"
        jurisdiction: Optional jurisdiction code
        top_n: Number of recommendations
        min_success_rate: Minimum success rate filter
        prefer_friction: Prefer specific friction level

    Returns:
        List of recommended playbooks with scores
    """
    from io_cli import IORouter

    router = IORouter()
    return router.recommend_playbooks(
        entity_type,
        jurisdiction=jurisdiction,
        top_n=top_n,
        min_success_rate=min_success_rate,
        prefer_friction=prefer_friction
    )


# =============================================================================
# Public Entry Point Functions for OSINT Chains
# =============================================================================

async def execute_osint_cascade(
    initial_entity: str,
    entity_type: str = 'email',
    max_depth: int = 3,
    relevance_threshold: float = 0.5,
    ai_filter: bool = True,
    persist_to_cymonides: bool = True,
    event_callback: Optional[Callable[[str, Dict], None]] = None
) -> Dict:
    """
    Public entry point for OSINT cascade chain.

    Recursively discovers related OSINT entities from an initial entity.

    Args:
        initial_entity: The entity value to start from (email, phone, username, etc.)
        entity_type: Type of entity ('email', 'phone', 'username', 'domain', 'person')
        max_depth: Maximum recursion depth (default 3)
        relevance_threshold: Minimum relevance score to continue expansion (0.0-1.0)
        ai_filter: Whether to use AI filtering between expansion stages
        persist_to_cymonides: Whether to persist entities to cymonides-1
        event_callback: Optional callback for real-time event streaming

    Returns:
        Dict containing entity_graph, all_entities, and results

    Example:
        result = await execute_osint_cascade(
            'target@example.com',
            entity_type='email',
            event_callback=lambda t, d: print(f"[{t}] {d}")
        )
    """
    from io_cli import RuleExecutor
    rule_executor = RuleExecutor()
    chain_executor = ChainExecutor(rule_executor)

    try:
        result = await chain_executor.execute_chain(
            'CHAIN_OSINT_CASCADE',
            {'value': initial_entity, 'type': entity_type},
            max_depth=max_depth,
            event_callback=event_callback
        )
        return result
    finally:
        await rule_executor.close()


async def execute_osint_breach_network(
    initial_credential: str,
    credential_type: str = 'email',
    max_depth: int = 2,
    cluster_passwords: bool = True,
    cluster_breaches: bool = True,
    persist_to_cymonides: bool = True,
    event_callback: Optional[Callable[[str, Dict], None]] = None
) -> Dict:
    """
    Public entry point for breach network mapping chain.

    Maps credential reuse patterns, password clusters, and breach exposure.

    Args:
        initial_credential: The credential to start from (email, username, phone)
        credential_type: Type of credential ('email', 'username', 'phone')
        max_depth: Maximum recursion depth (default 2)
        cluster_passwords: Whether to cluster by shared passwords
        cluster_breaches: Whether to cluster by breach source
        persist_to_cymonides: Whether to persist to cymonides-1
        event_callback: Optional callback for real-time event streaming

    Returns:
        Dict containing breach_network with accounts, password_clusters, breach_clusters

    Example:
        result = await execute_osint_breach_network(
            'user@example.com',
            credential_type='email',
            event_callback=lambda t, d: print(f"[{t}] {d}")
        )
    """
    from io_cli import RuleExecutor
    rule_executor = RuleExecutor()
    chain_executor = ChainExecutor(rule_executor)

    try:
        result = await chain_executor.execute_chain(
            'CHAIN_OSINT_BREACH_NETWORK',
            {'value': initial_credential, 'type': credential_type},
            max_depth=max_depth,
            event_callback=event_callback
        )
        return result
    finally:
        await rule_executor.close()


async def execute_osint_person_web(
    person_identifier: str,
    identifier_type: str = 'person',
    max_depth: int = 2,
    include_corporate: bool = True,
    include_domains: bool = True,
    identity_resolution: bool = True,
    persist_to_cymonides: bool = True,
    event_callback: Optional[Callable[[str, Dict], None]] = None
) -> Dict:
    """
    Public entry point for person-centric OSINT aggregation.

    Builds complete digital footprint: social media, breaches, corporate, domains.

    Args:
        person_identifier: Person name, email, or LinkedIn URL
        identifier_type: Type ('person', 'email', 'linkedin')
        max_depth: Maximum recursion depth (default 2)
        include_corporate: Whether to look up corporate affiliations
        include_domains: Whether to check domain ownership
        identity_resolution: Whether to merge fragmented identity data
        persist_to_cymonides: Whether to persist to cymonides-1
        event_callback: Optional callback for real-time event streaming

    Returns:
        Dict containing person_profile with emails, phones, social_profiles, etc.

    Example:
        result = await execute_osint_person_web(
            'John Smith',
            identifier_type='person',
            event_callback=lambda t, d: print(f"[{t}] {d}")
        )
    """
    from io_cli import RuleExecutor
    rule_executor = RuleExecutor()
    chain_executor = ChainExecutor(rule_executor)

    try:
        result = await chain_executor.execute_chain(
            'CHAIN_OSINT_PERSON_WEB',
            {'value': person_identifier, 'type': identifier_type},
            max_depth=max_depth,
            event_callback=event_callback
        )
        return result
    finally:
        await rule_executor.close()


# =============================================================================
# Investigation Templates (Macros) - Query Lab Integration
# =============================================================================
# These templates encode common investigation patterns as predefined chain sequences.
# Notation from consolidation plan:
#   p: = person, e: = email, c: = company, cdom: = company domain
#   breach? = breach lookup (optional), rep: = reputation
#   ? suffix = optional/conditional step

async def dd_person(
    person_name: str,
    jurisdiction: Optional[str] = None,
    max_depth: int = 3,
    include_breach: bool = True,
    include_corporate: bool = True,
    include_reputation: bool = True,
    event_callback: Optional[Callable[[str, Dict], None]] = None
) -> Dict:
    """
    DD_PERSON Investigation Template - Deep Due Diligence on a Person.

    Chain pattern: p: => e: => breach? => c? => cdom: => rep:

    Executes a full person investigation:
    1. Person lookup (p:) - Get basic person data
    2. Email discovery (e:) - Find associated emails
    3. Breach check (breach?) - Check emails in breach databases
    4. Corporate affiliations (c?) - Find company connections
    5. Company domains (cdom:) - Get domains for affiliated companies
    6. Reputation check (rep:) - Check person/company reputation

    Args:
        person_name: Full name of the person to investigate
        jurisdiction: Optional jurisdiction code (GB, US, HU, etc.)
        max_depth: Maximum recursion depth for each stage
        include_breach: Whether to include breach database checks
        include_corporate: Whether to include corporate affiliation lookup
        include_reputation: Whether to include reputation checks
        event_callback: Optional callback for real-time streaming

    Returns:
        Comprehensive person profile with all discovered data
    """
    from io_cli import RuleExecutor
    rule_executor = RuleExecutor()
    chain_executor = ChainExecutor(rule_executor)

    results = {
        'template': 'DD_PERSON',
        'input': person_name,
        'jurisdiction': jurisdiction,
        'stages': {},
        'entities_discovered': [],
        'risk_indicators': [],
        'chain_provenance': 1.0,
    }

    try:
        # Stage 1: Person lookup (p:)
        if event_callback:
            event_callback('stage_start', {'stage': 'person_lookup', 'input': person_name})

        person_result = await chain_executor.execute_chain(
            'CHAIN_OSINT_PERSON_WEB',
            {'value': person_name, 'type': 'person'},
            max_depth=1,
            jurisdiction=jurisdiction,
            event_callback=event_callback
        )
        results['stages']['person'] = person_result

        # Extract emails for next stage
        emails = []
        if person_result.get('status') == 'success':
            profile = person_result.get('person_profile', {})
            emails = profile.get('emails', [])
            results['entities_discovered'].extend([{'type': 'email', 'value': e} for e in emails])
            results['chain_provenance'] *= 0.95  # Person lookup confidence

        # Stage 2: Email enrichment (e:)
        email_results = []
        for email in emails[:5]:  # Limit to top 5 emails
            if event_callback:
                event_callback('stage_start', {'stage': 'email_enrichment', 'email': email})

            email_result = await chain_executor._execute_osint_lookup(email, 'email')
            email_results.append({'email': email, 'result': email_result})

        results['stages']['emails'] = email_results
        results['chain_provenance'] *= 0.90

        # Stage 3: Breach check (breach?) - Optional
        if include_breach and emails:
            if event_callback:
                event_callback('stage_start', {'stage': 'breach_check'})

            breach_result = await chain_executor.execute_chain(
                'CHAIN_OSINT_BREACH_NETWORK',
                {'value': emails[0], 'type': 'email'},
                max_depth=1,
                event_callback=event_callback
            )
            results['stages']['breach'] = breach_result
            results['chain_provenance'] *= 0.80  # Breach data lower confidence

            # Extract risk indicators from breaches
            if breach_result.get('status') == 'success':
                breach_count = len(breach_result.get('breaches', []))
                if breach_count > 0:
                    results['risk_indicators'].append({
                        'type': 'breach_exposure',
                        'severity': 'high' if breach_count > 5 else 'medium',
                        'details': f'{breach_count} breach(es) found'
                    })

        # Stage 4: Corporate affiliations (c?) - Optional
        if include_corporate:
            if event_callback:
                event_callback('stage_start', {'stage': 'corporate_affiliations'})

            # Look up person as officer
            corp_result = await chain_executor.execute_chain(
                'CHAIN_OFFICER_TO_ALL_COMPANIES',
                {'value': person_name, 'type': 'person'},
                max_depth=2,
                jurisdiction=jurisdiction,
                event_callback=event_callback
            )
            results['stages']['corporate'] = corp_result
            results['chain_provenance'] *= 0.92

            # Extract companies
            if corp_result.get('status') == 'success':
                companies = corp_result.get('companies', [])
                results['entities_discovered'].extend([
                    {'type': 'company', 'value': c.get('name', c.get('company_name', ''))}
                    for c in companies[:10]
                ])

        # Stage 5: Company domains (cdom:)
        if include_corporate and results['stages'].get('corporate', {}).get('companies'):
            companies = results['stages']['corporate'].get('companies', [])[:3]
            domain_results = []

            for company in companies:
                company_name = company.get('name', company.get('company_name', ''))
                if company_name:
                    if event_callback:
                        event_callback('stage_start', {'stage': 'company_domain', 'company': company_name})

                    domain_result = await chain_executor._execute_osint_lookup(company_name, 'domain')
                    domain_results.append({'company': company_name, 'result': domain_result})

            results['stages']['company_domains'] = domain_results

        # Stage 6: Reputation check (rep:) - Optional
        if include_reputation:
            if event_callback:
                event_callback('stage_start', {'stage': 'reputation_check'})

            # Aggregate reputation signals
            reputation = {
                'person_mentions': 0,
                'adverse_media': False,
                'pep_status': False,
                'sanctions_hit': False,
            }

            # Check for PEP/sanctions if we have rules
            if chain_executor.rules_by_id.get('PEP_CHECK'):
                pep_result = await chain_executor.rule_executor.execute_rule(
                    chain_executor.rules_by_id['PEP_CHECK'],
                    person_name,
                    jurisdiction
                )
                if pep_result.get('status') == 'success' and pep_result.get('matches'):
                    reputation['pep_status'] = True
                    results['risk_indicators'].append({
                        'type': 'pep',
                        'severity': 'high',
                        'details': 'Politically Exposed Person match'
                    })

            results['stages']['reputation'] = reputation

        results['status'] = 'success'
        results['final_provenance'] = results['chain_provenance']

        if event_callback:
            event_callback('template_complete', {'template': 'DD_PERSON', 'provenance': results['chain_provenance']})

        return results

    except Exception as e:
        results['status'] = 'error'
        results['error'] = str(e)
        return results
    finally:
        await rule_executor.close()


async def dd_corporate(
    company_name: str,
    jurisdiction: Optional[str] = None,
    company_number: Optional[str] = None,
    max_depth: int = 3,
    include_officers: bool = True,
    include_reputation: bool = True,
    event_callback: Optional[Callable[[str, Dict], None]] = None
) -> Dict:
    """
    DD_CORPORATE Investigation Template - Deep Due Diligence on a Company.

    Chain pattern: c: => cdom: => rep: => p? => e?

    Executes a full corporate investigation:
    1. Company lookup (c:) - Get company registry data
    2. Company domain (cdom:) - Discover company websites/domains
    3. Reputation (rep:) - Check company reputation signals
    4. Officers (p?) - Get company officers/directors
    5. Officer emails (e?) - Find email addresses for officers

    Args:
        company_name: Company name to investigate
        jurisdiction: Jurisdiction code (GB, US, HU, etc.)
        company_number: Optional company registration number
        max_depth: Maximum recursion depth
        include_officers: Whether to include officer lookup
        include_reputation: Whether to include reputation checks
        event_callback: Optional callback for real-time streaming

    Returns:
        Comprehensive corporate profile with officers, domains, reputation
    """
    from io_cli import RuleExecutor
    rule_executor = RuleExecutor()
    chain_executor = ChainExecutor(rule_executor)

    results = {
        'template': 'DD_CORPORATE',
        'input': company_name,
        'jurisdiction': jurisdiction,
        'stages': {},
        'entities_discovered': [],
        'risk_indicators': [],
        'chain_provenance': 1.0,
    }

    try:
        # Stage 1: Company lookup (c:)
        if event_callback:
            event_callback('stage_start', {'stage': 'company_lookup', 'input': company_name})

        company_result = await chain_executor.execute_chain(
            'CHAIN_COMPANY_FULL_PROFILE',
            {'value': company_name, 'type': 'company', 'company_number': company_number},
            max_depth=1,
            jurisdiction=jurisdiction,
            event_callback=event_callback
        )
        results['stages']['company'] = company_result

        if company_result.get('status') == 'success':
            results['chain_provenance'] *= 0.99  # Registry data high confidence

        # Stage 2: Company domain discovery (cdom:)
        if event_callback:
            event_callback('stage_start', {'stage': 'domain_discovery'})

        domain_result = await chain_executor._execute_osint_lookup(company_name, 'domain')
        results['stages']['domains'] = domain_result

        domains = []
        if domain_result.get('status') == 'success':
            domains = domain_result.get('domains', [])
            results['entities_discovered'].extend([{'type': 'domain', 'value': d} for d in domains])
        results['chain_provenance'] *= 0.85

        # Stage 3: Reputation check (rep:)
        if include_reputation:
            if event_callback:
                event_callback('stage_start', {'stage': 'reputation_check'})

            reputation = {
                'adverse_media': False,
                'sanctions_hit': False,
                'enforcement_actions': [],
            }

            # Would integrate with news/sanctions APIs here
            results['stages']['reputation'] = reputation

        # Stage 4: Officers lookup (p?)
        officers = []
        if include_officers:
            if event_callback:
                event_callback('stage_start', {'stage': 'officers_lookup'})

            # Extract officers from company result if available
            if company_result.get('status') == 'success':
                company_data = company_result.get('company', {})
                officers = company_data.get('officers', company_data.get('directors', []))

                results['stages']['officers'] = officers
                results['entities_discovered'].extend([
                    {'type': 'person', 'value': o.get('name', '')} for o in officers[:20]
                ])
            results['chain_provenance'] *= 0.95

        # Stage 5: Officer email discovery (e?)
        if include_officers and officers:
            officer_emails = []
            for officer in officers[:5]:  # Top 5 officers
                officer_name = officer.get('name', '')
                if officer_name:
                    if event_callback:
                        event_callback('stage_start', {'stage': 'officer_email', 'officer': officer_name})

                    email_result = await chain_executor._execute_osint_lookup(officer_name, 'person')
                    if email_result.get('status') == 'success':
                        found_emails = email_result.get('emails', [])
                        officer_emails.append({
                            'officer': officer_name,
                            'emails': found_emails
                        })
                        results['entities_discovered'].extend([
                            {'type': 'email', 'value': e} for e in found_emails
                        ])

            results['stages']['officer_emails'] = officer_emails
            results['chain_provenance'] *= 0.75  # Email inference lower confidence

        results['status'] = 'success'
        results['final_provenance'] = results['chain_provenance']

        if event_callback:
            event_callback('template_complete', {'template': 'DD_CORPORATE', 'provenance': results['chain_provenance']})

        return results

    except Exception as e:
        results['status'] = 'error'
        results['error'] = str(e)
        return results
    finally:
        await rule_executor.close()


async def network_map(
    seed_entity: str,
    entity_type: str = 'person',
    max_hops: int = 3,
    min_connection_strength: float = 0.5,
    include_clink: bool = True,
    event_callback: Optional[Callable[[str, Dict], None]] = None
) -> Dict:
    """
    NETWORK_MAP Investigation Template - Map Entity Relationships.

    Chain pattern: p: => c? => p? => clink

    Builds a relationship graph starting from a seed entity:
    1. Seed lookup (p: or c:) - Get initial entity
    2. Find connections (c? or p?) - Discover related entities
    3. Expand network (p?) - Find people connected to companies
    4. Clink analysis - Identify shared connections between entities

    Args:
        seed_entity: Starting entity (person name or company)
        entity_type: Type of seed ('person' or 'company')
        max_hops: Maximum relationship hops to traverse
        min_connection_strength: Minimum confidence for connections
        include_clink: Whether to perform clink (shared connection) analysis
        event_callback: Optional callback for real-time streaming

    Returns:
        Network graph with nodes, edges, and clink connections
    """
    from io_cli import RuleExecutor
    rule_executor = RuleExecutor()
    chain_executor = ChainExecutor(rule_executor)

    results = {
        'template': 'NETWORK_MAP',
        'seed': seed_entity,
        'seed_type': entity_type,
        'graph': {
            'nodes': [],
            'edges': [],
        },
        'clinks': [],
        'chain_provenance': 1.0,
    }

    # Track discovered entities for deduplication
    seen_nodes = set()
    node_id_counter = 0

    def add_node(name: str, node_type: str, metadata: Dict = None) -> int:
        nonlocal node_id_counter
        node_key = f"{node_type}:{name.lower()}"
        if node_key in seen_nodes:
            # Return existing node ID
            for node in results['graph']['nodes']:
                if node['key'] == node_key:
                    return node['id']
            return -1

        seen_nodes.add(node_key)
        node_id = node_id_counter
        node_id_counter += 1
        results['graph']['nodes'].append({
            'id': node_id,
            'key': node_key,
            'label': name,
            'type': node_type,
            'metadata': metadata or {}
        })
        return node_id

    def add_edge(from_id: int, to_id: int, relationship: str, strength: float = 1.0):
        if from_id < 0 or to_id < 0:
            return
        results['graph']['edges'].append({
            'from': from_id,
            'to': to_id,
            'relationship': relationship,
            'strength': strength
        })

    try:
        # Add seed node
        seed_node_id = add_node(seed_entity, entity_type)

        if event_callback:
            event_callback('stage_start', {'stage': 'seed_lookup', 'entity': seed_entity})

        # Stage 1: Seed lookup
        if entity_type == 'person':
            # Person => find companies
            corp_result = await chain_executor.execute_chain(
                'CHAIN_OFFICER_TO_ALL_COMPANIES',
                {'value': seed_entity, 'type': 'person'},
                max_depth=1,
                event_callback=event_callback
            )

            if corp_result.get('status') == 'success':
                companies = corp_result.get('companies', [])
                for company in companies[:10]:
                    company_name = company.get('name', company.get('company_name', ''))
                    if company_name:
                        company_node_id = add_node(company_name, 'company', company)
                        role = company.get('role', company.get('officer_role', 'associated'))
                        add_edge(seed_node_id, company_node_id, role, 0.9)

                results['chain_provenance'] *= 0.95

        else:  # company
            # Company => find officers
            company_result = await chain_executor.execute_chain(
                'CHAIN_COMPANY_FULL_PROFILE',
                {'value': seed_entity, 'type': 'company'},
                max_depth=1,
                event_callback=event_callback
            )

            if company_result.get('status') == 'success':
                company_data = company_result.get('company', {})
                officers = company_data.get('officers', company_data.get('directors', []))
                for officer in officers[:10]:
                    officer_name = officer.get('name', '')
                    if officer_name:
                        officer_node_id = add_node(officer_name, 'person', officer)
                        role = officer.get('role', 'officer')
                        add_edge(seed_node_id, officer_node_id, role, 0.95)

                results['chain_provenance'] *= 0.99

        # Stage 2: Expand network (additional hops)
        if max_hops > 1:
            if event_callback:
                event_callback('stage_start', {'stage': 'network_expansion', 'hop': 2})

            # Get nodes added in first hop
            first_hop_nodes = [n for n in results['graph']['nodes'] if n['id'] != seed_node_id]

            for node in first_hop_nodes[:5]:  # Limit expansion
                if node['type'] == 'company':
                    # Company => find more officers
                    expand_result = await chain_executor.execute_chain(
                        'CHAIN_COMPANY_FULL_PROFILE',
                        {'value': node['label'], 'type': 'company'},
                        max_depth=1,
                        event_callback=None  # Quiet for expansion
                    )

                    if expand_result.get('status') == 'success':
                        officers = expand_result.get('company', {}).get('officers', [])
                        for officer in officers[:5]:
                            officer_name = officer.get('name', '')
                            if officer_name:
                                officer_node_id = add_node(officer_name, 'person', officer)
                                add_edge(node['id'], officer_node_id, 'officer', 0.85)

                elif node['type'] == 'person':
                    # Person => find more companies
                    expand_result = await chain_executor.execute_chain(
                        'CHAIN_OFFICER_TO_ALL_COMPANIES',
                        {'value': node['label'], 'type': 'person'},
                        max_depth=1,
                        event_callback=None
                    )

                    if expand_result.get('status') == 'success':
                        companies = expand_result.get('companies', [])
                        for company in companies[:3]:
                            company_name = company.get('name', company.get('company_name', ''))
                            if company_name:
                                company_node_id = add_node(company_name, 'company', company)
                                add_edge(node['id'], company_node_id, 'director', 0.85)

            results['chain_provenance'] *= 0.80

        # Stage 3: Clink analysis (shared connections)
        if include_clink and len(results['graph']['nodes']) > 2:
            if event_callback:
                event_callback('stage_start', {'stage': 'clink_analysis'})

            # Find shared connections (nodes connected to multiple other nodes)
            node_connections = {}
            for edge in results['graph']['edges']:
                for node_id in [edge['from'], edge['to']]:
                    if node_id not in node_connections:
                        node_connections[node_id] = set()
                    node_connections[node_id].add(edge['from'] if edge['to'] == node_id else edge['to'])

            # Identify clink nodes (connected to 2+ other entities)
            for node_id, connections in node_connections.items():
                if len(connections) >= 2:
                    node = next((n for n in results['graph']['nodes'] if n['id'] == node_id), None)
                    if node:
                        connected_labels = [
                            next((n['label'] for n in results['graph']['nodes'] if n['id'] == c), '')
                            for c in connections
                        ]
                        results['clinks'].append({
                            'node': node['label'],
                            'type': node['type'],
                            'connects': connected_labels,
                            'connection_count': len(connections)
                        })

        results['status'] = 'success'
        results['final_provenance'] = results['chain_provenance']
        results['node_count'] = len(results['graph']['nodes'])
        results['edge_count'] = len(results['graph']['edges'])

        if event_callback:
            event_callback('template_complete', {
                'template': 'NETWORK_MAP',
                'nodes': results['node_count'],
                'edges': results['edge_count'],
                'clinks': len(results['clinks'])
            })

        return results

    except Exception as e:
        results['status'] = 'error'
        results['error'] = str(e)
        return results
    finally:
        await rule_executor.close()


# =============================================================================
# CLI Interface
# =============================================================================

async def main():
    """CLI interface for chain execution and playbook recommendations."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Chain Executor - Execute multi-hop investigation chains and get playbook recommendations'
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Chain execution command
    chain_parser = subparsers.add_parser('chain', help='Execute a chain rule')
    chain_parser.add_argument('chain_id', help='Chain rule ID (e.g., CHAIN_OFFICER_TO_ALL_COMPANIES)')
    chain_parser.add_argument('value', help='Initial input value (person/company name, etc.)')
    chain_parser.add_argument('--jurisdiction', '-j', help='Jurisdiction filter (e.g., GB, US)')
    chain_parser.add_argument('--output', '-o', help='Output file for results (JSON)')

    # Playbook chain command
    pb_chain_parser = subparsers.add_parser('playbook-chain', help='Execute a playbook-based chain')
    pb_chain_parser.add_argument('chain_id', help='Playbook chain ID (e.g., CHAIN_PLAYBOOK_FULL_COMPANY_INTEL)')
    pb_chain_parser.add_argument('value', help='Input value')
    pb_chain_parser.add_argument('--jurisdiction', '-j', help='Jurisdiction (HU, GB, US, etc.)')
    pb_chain_parser.add_argument('--output', '-o', help='Output file')

    # Recommend playbooks command
    rec_parser = subparsers.add_parser('recommend', help='Get playbook recommendations')
    rec_parser.add_argument('entity_type', choices=['company', 'person', 'domain', 'email', 'phone'],
                           help='Entity type to investigate')
    rec_parser.add_argument('--jurisdiction', '-j', help='Jurisdiction code (HU, GB, US, etc.)')
    rec_parser.add_argument('--top', '-n', type=int, default=5, help='Number of recommendations (default: 5)')
    rec_parser.add_argument('--friction', '-f', choices=['Open', 'Low', 'Medium', 'Restricted', 'Paywalled'],
                           help='Preferred friction level')
    rec_parser.add_argument('--min-success', type=float, default=0.0, help='Minimum success rate (0.0-1.0)')
    rec_parser.add_argument('--json', action='store_true', help='Output as JSON (for API integration)')

    # List chains command
    list_parser = subparsers.add_parser('list', help='List available chains')
    list_parser.add_argument('--playbook-only', action='store_true', help='Only show playbook-based chains')

    # Investigation Template commands (Query Lab macros)
    # DD_PERSON: p: => e: => breach? => c? => cdom: => rep:
    dd_person_parser = subparsers.add_parser('dd-person', help='DD_PERSON template - Deep due diligence on a person')
    dd_person_parser.add_argument('name', help='Person name to investigate')
    dd_person_parser.add_argument('--jurisdiction', '-j', help='Jurisdiction code (GB, US, HU, etc.)')
    dd_person_parser.add_argument('--no-breach', action='store_true', help='Skip breach database checks')
    dd_person_parser.add_argument('--no-corporate', action='store_true', help='Skip corporate affiliation lookup')
    dd_person_parser.add_argument('--no-reputation', action='store_true', help='Skip reputation checks')
    dd_person_parser.add_argument('--output', '-o', help='Output file for results (JSON)')

    # DD_CORPORATE: c: => cdom: => rep: => p? => e?
    dd_corp_parser = subparsers.add_parser('dd-corporate', help='DD_CORPORATE template - Deep due diligence on a company')
    dd_corp_parser.add_argument('name', help='Company name to investigate')
    dd_corp_parser.add_argument('--company-number', '-n', help='Company registration number')
    dd_corp_parser.add_argument('--jurisdiction', '-j', help='Jurisdiction code (GB, US, HU, etc.)')
    dd_corp_parser.add_argument('--no-officers', action='store_true', help='Skip officer lookup')
    dd_corp_parser.add_argument('--no-reputation', action='store_true', help='Skip reputation checks')
    dd_corp_parser.add_argument('--output', '-o', help='Output file for results (JSON)')

    # NETWORK_MAP: p: => c? => p? => clink
    network_parser = subparsers.add_parser('network-map', help='NETWORK_MAP template - Map entity relationships')
    network_parser.add_argument('entity', help='Seed entity (person or company name)')
    network_parser.add_argument('--type', '-t', choices=['person', 'company'], default='person', help='Entity type')
    network_parser.add_argument('--hops', type=int, default=3, help='Maximum relationship hops (default: 3)')
    network_parser.add_argument('--no-clink', action='store_true', help='Skip clink (shared connection) analysis')
    network_parser.add_argument('--output', '-o', help='Output file for results (JSON)')

    args = parser.parse_args()

    # Handle commands
    if args.command == 'chain':
        result = await execute_chain_rule(args.chain_id, args.value, args.jurisdiction)
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"Results written to: {args.output}")
        else:
            print(json.dumps(result, indent=2))

    elif args.command == 'playbook-chain':
        result = await execute_playbook_chain(args.chain_id, args.value, args.jurisdiction)
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"Results written to: {args.output}")
        else:
            print(json.dumps(result, indent=2))

    elif args.command == 'recommend':
        recs = recommend_playbooks_sync(
            args.entity_type,
            jurisdiction=args.jurisdiction,
            top_n=args.top,
            min_success_rate=args.min_success,
            prefer_friction=args.friction
        )

        # JSON output for API integration
        if args.json:
            output = {
                "recommendations": recs,
                "query": {
                    "entity_type": args.entity_type,
                    "jurisdiction": args.jurisdiction,
                    "top_n": args.top,
                    "min_success_rate": args.min_success,
                    "prefer_friction": args.friction
                },
                "count": len(recs)
            }
            print(json.dumps(output, indent=2))
        else:
            # Human-readable output
            print(f"\n{'='*60}")
            print(f"PLAYBOOK RECOMMENDATIONS: {args.entity_type.upper()}")
            if args.jurisdiction:
                print(f"Jurisdiction: {args.jurisdiction}")
            print(f"{'='*60}\n")

            for i, rec in enumerate(recs, 1):
                print(f"{i}. {rec['id']}")
                print(f"   Label: {rec['label']}")
                print(f"   Score: {rec['score']:.3f}")
                print(f"   Success Rate: {rec['success_rate']:.0%}")
                print(f"   Jurisdiction: {rec.get('jurisdiction', 'GLOBAL')}")
                print(f"   Friction: {rec['friction']}")
                print(f"   Rules: {rec['rule_count']} | Outputs: {rec['output_count']}")
                print(f"   Score Breakdown: {rec['score_breakdown']}")
                print()

    elif args.command == 'list':
        from io_cli import RuleExecutor
        rule_executor = RuleExecutor()
        chain_executor = ChainExecutor(rule_executor)

        chains = chain_executor.chain_rules
        if args.playbook_only:
            chains = {k: v for k, v in chains.items() if v.get('uses_playbooks')}

        print(f"\n{'='*60}")
        print(f"AVAILABLE CHAINS ({len(chains)} total)")
        print(f"{'='*60}\n")

        for chain_id, chain in chains.items():
            pb_tag = "[PLAYBOOK]" if chain.get('uses_playbooks') else ""
            print(f"  {chain_id} {pb_tag}")
            print(f"    {chain.get('label', '')}")
            print(f"    Type: {chain.get('chain_config', {}).get('type', 'unknown')}")
            print()

        await rule_executor.close()

    elif args.command == 'dd-person':
        # DD_PERSON Investigation Template
        def progress_callback(event_type, data):
            stage = data.get('stage', event_type)
            print(f"  [{stage}] ...", flush=True)

        print(f"\n{'='*60}")
        print(f"DD_PERSON: {args.name}")
        if args.jurisdiction:
            print(f"Jurisdiction: {args.jurisdiction}")
        print(f"{'='*60}\n")

        result = await dd_person(
            args.name,
            jurisdiction=args.jurisdiction,
            include_breach=not args.no_breach,
            include_corporate=not args.no_corporate,
            include_reputation=not args.no_reputation,
            event_callback=progress_callback
        )

        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\nResults written to: {args.output}")
        else:
            print(f"\n{'='*60}")
            print("RESULTS")
            print(f"{'='*60}")
            print(f"Status: {result.get('status', 'unknown')}")
            print(f"Chain Provenance: {result.get('final_provenance', 0):.3f}")
            print(f"Entities Discovered: {len(result.get('entities_discovered', []))}")
            print(f"Risk Indicators: {len(result.get('risk_indicators', []))}")
            for risk in result.get('risk_indicators', []):
                print(f"  - [{risk['severity'].upper()}] {risk['type']}: {risk['details']}")
            print()
            print(json.dumps(result, indent=2))

    elif args.command == 'dd-corporate':
        # DD_CORPORATE Investigation Template
        def progress_callback(event_type, data):
            stage = data.get('stage', event_type)
            print(f"  [{stage}] ...", flush=True)

        print(f"\n{'='*60}")
        print(f"DD_CORPORATE: {args.name}")
        if args.jurisdiction:
            print(f"Jurisdiction: {args.jurisdiction}")
        if args.company_number:
            print(f"Company Number: {args.company_number}")
        print(f"{'='*60}\n")

        result = await dd_corporate(
            args.name,
            jurisdiction=args.jurisdiction,
            company_number=args.company_number,
            include_officers=not args.no_officers,
            include_reputation=not args.no_reputation,
            event_callback=progress_callback
        )

        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\nResults written to: {args.output}")
        else:
            print(f"\n{'='*60}")
            print("RESULTS")
            print(f"{'='*60}")
            print(f"Status: {result.get('status', 'unknown')}")
            print(f"Chain Provenance: {result.get('final_provenance', 0):.3f}")
            print(f"Entities Discovered: {len(result.get('entities_discovered', []))}")
            print()
            print(json.dumps(result, indent=2))

    elif args.command == 'network-map':
        # NETWORK_MAP Investigation Template
        def progress_callback(event_type, data):
            stage = data.get('stage', event_type)
            print(f"  [{stage}] ...", flush=True)

        print(f"\n{'='*60}")
        print(f"NETWORK_MAP: {args.entity}")
        print(f"Entity Type: {args.type}")
        print(f"Max Hops: {args.hops}")
        print(f"{'='*60}\n")

        result = await network_map(
            args.entity,
            entity_type=args.type,
            max_hops=args.hops,
            include_clink=not args.no_clink,
            event_callback=progress_callback
        )

        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\nResults written to: {args.output}")
        else:
            print(f"\n{'='*60}")
            print("RESULTS")
            print(f"{'='*60}")
            print(f"Status: {result.get('status', 'unknown')}")
            print(f"Chain Provenance: {result.get('final_provenance', 0):.3f}")
            print(f"Nodes: {result.get('node_count', 0)}")
            print(f"Edges: {result.get('edge_count', 0)}")
            print(f"Clinks (shared connections): {len(result.get('clinks', []))}")
            for cl in result.get('clinks', []):
                print(f"  - {cl['node']} ({cl['type']}): connects {cl['connection_count']} entities")
            print()
            print(json.dumps(result, indent=2))

    else:
        parser.print_help()


if __name__ == '__main__':
    asyncio.run(main())
