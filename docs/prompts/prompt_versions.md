# Prompt Versions

## Version Table

| Version | Stage | Status |
| --- | --- | --- |
| v1 | Stage 7 | current strict JSON group refinement prompt |
| v2+ | future | placeholder |

## v1

Goals:

- Refine deterministic group folder names.
- Assign each provided file path to one allowed subfolder.
- Return compact JSON only.

Schema:

- `folder_name`
- `confidence`
- `reason`
- `subfolders`
- `warnings`

Expected strengths:

- Strong path preservation.
- Easy Python validation.
- Low prompt size.

Known limitations:

- No semantic access to file contents.
- Quality depends on filenames and deterministic metadata.
- Local model behavior can vary by model family.

Future ideas:

- Add an evaluated few-shot variant.
- Compare local models.
- Track validation failure rates by model.
