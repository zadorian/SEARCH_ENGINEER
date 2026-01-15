# Node <-> Note Interoperability Specification

## Architecture: One Data, Two Interfaces

CYMONIDES NODES (Model) = Single Source of Truth
  |
  +-- GRID/GRAPH VIEW (visual nodes, middle column = comment)
  |
  +-- MONACO EDITOR VIEW (headers, body text, footnotes)

## Field Mappings

### NARRATIVE.CITATION

| Field   | Grid Display      | Note Display                    |
|---------|-------------------|---------------------------------|
| label   | LEFT column       | Quoted text under header        |
| comment | MIDDLE column     | Parent header (## Litigation)   |
| edges   | Connection lines  | Footnotes [^n]: url             |

### Translation Rules

Note -> Node:
- Header created -> Upsert watcher node
- Content under header -> Node value field  
- Footnote -> URL node + cited_in edge

Node -> Note:
- Citation created -> Inject under matching header
- Add footnote for cited_in URL edge

### Edge Relations (DETERMINISTIC)
- extracted_by -> watcher node
- cited_in -> url node (NO source_url field!)
