# Bloodplague-main Knowledge Graph

Generated from GitNexus index data on 2026-04-22T18:18:23.224Z.

## Artifacts
- `reports/knowledge-graph/Bloodplague-main.graphml` — full GraphML export for Gephi, Cytoscape, yEd, or Neo4j-adjacent tooling
- `reports/knowledge-graph/Bloodplague-main-overview.mmd` — reduced architecture view in Mermaid
- `reports/knowledge-graph/Bloodplague-main-summary.json` — machine-readable summary of this export

## Snapshot
- Nodes: 52,818
- Relationships: 84,037
- Indexed files: 2,749
- Indexed processes: 300

## Node Labels
- Section: 33,722
- Function: 9,058
- Property: 2,955
- File: 2,749
- Community: 940
- Folder: 887
- Class: 817
- Method: 786
- Interface: 502
- Process: 300
- Route: 84
- Tool: 16
- CodeElement: 2

## Relationship Types
- CONTAINS: 37,301
- CALLS: 15,064
- DEFINES: 14,118
- MEMBER_OF: 5,449
- HAS_METHOD: 3,906
- HAS_PROPERTY: 2,592
- ENTRY_POINT_OF: 2,288
- STEP_IN_PROCESS: 1,426
- IMPORTS: 1,234
- ACCESSES: 517
- HANDLES_ROUTE: 84
- EXTENDS: 20
- HANDLES_TOOL: 16
- FETCHES: 11
- METHOD_IMPLEMENTS: 6
- IMPLEMENTS: 3
- QUERIES: 2

## Largest Code Areas
- claude-skills: 7,187 indexed symbols with file ownership
- agents: 3,628 indexed symbols with file ownership
- orchestrator: 1,241 indexed symbols with file ownership
- tmp_beacon_bundle: 945 indexed symbols with file ownership
- frontend: 633 indexed symbols with file ownership
- tests: 314 indexed symbols with file ownership
- scripts: 130 indexed symbols with file ownership
- epidemic_cli: 124 indexed symbols with file ownership
- (root): 8 indexed symbols with file ownership
- dashboard: 8 indexed symbols with file ownership

## Strongest Cross-Area Dependencies
- tests -> orchestrator: 376 edges (CALLS, IMPORTS)
- claude-skills -> agents: 305 edges (CALLS, IMPORTS)
- claude-skills -> tmp_beacon_bundle: 240 edges (CALLS)
- tests -> agents: 174 edges (CALLS, IMPORTS, ACCESSES)
- orchestrator -> agents: 89 edges (CALLS, IMPORTS)
- agents -> tmp_beacon_bundle: 85 edges (CALLS)
- orchestrator -> tmp_beacon_bundle: 38 edges (CALLS)
- frontend -> agents: 30 edges (CALLS)
- tmp_beacon_bundle -> agents: 26 edges (CALLS)
- agents -> claude-skills: 16 edges (CALLS, EXTENDS, IMPORTS)
- orchestrator -> claude-skills: 16 edges (CALLS)
- tests -> epidemic_cli: 16 edges (CALLS, IMPORTS)

## Largest Communities
- Orchestrator: 165 symbols, cohesion 0.958
- Type-extractors: 83 symbols, cohesion 0.929
- Orchestrator: 54 symbols, cohesion 0.789
- Tmp_beacon_bundle: 35 symbols, cohesion 0.705
- Scripts: 33 symbols, cohesion 0.240
- Guardian: 32 symbols, cohesion 0.831
- Scripts: 31 symbols, cohesion 0.550
- Tmp_beacon_bundle: 28 symbols, cohesion 0.645
- Wiki: 26 symbols, cohesion 0.840
- Database-designer: 25 symbols, cohesion 0.989
- Tmp_beacon_bundle: 25 symbols, cohesion 0.587
- Orchestrator: 23 symbols, cohesion 0.792
- Scripts: 23 symbols, cohesion 0.209
- Pixel: 22 symbols, cohesion 0.862
- Scripts: 21 symbols, cohesion 0.973

## Longest Execution Flows
- Live → Add: 9 steps (cross_community)
- Live → LookupExactAll: 9 steps (cross_community)
- CreateServer → ResolveRepoFromCache: 8 steps (cross_community)
- Live → _is_float: 8 steps (cross_community)
- Main → Merge: 8 steps (cross_community)
- Main → Merge: 8 steps (cross_community)
- Cmd_contract → _is_float: 7 steps (cross_community)
- CreateServer → CheckStaleness: 7 steps (cross_community)
- CreateServer → GetContext: 7 steps (cross_community)
- CreateServer → PhaseTimer: 7 steps (cross_community)
- Live → _analyze_images: 7 steps (cross_community)
- Live → _find_images: 7 steps (cross_community)
- Start → Add: 7 steps (cross_community)
- Start → GetFiles: 7 steps (cross_community)
- Start → LookupExactAll: 7 steps (cross_community)
