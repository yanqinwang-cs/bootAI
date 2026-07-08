# Reasoning Boundaries

## Allowed LLM Reasoning

- Semantic folder naming.
- Subfolder refinement from provided metadata.
- Cautious warnings.
- Advisory notes that preserve all input paths.

## Not Allowed

- Determining exact duplicates.
- Determining path safety.
- Deciding file removal.
- Executing actions.
- Replacing deterministic `ProjectGroup` facts.

Python validation remains mandatory for every model response.
