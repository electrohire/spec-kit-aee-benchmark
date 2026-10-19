# Documentation style

Use normal prose spacing around measurements: **213,457 native tokens**, **0 unknowns**, and **17 misses; 3 false alarms**. Interpolated values need spaces in their templates, too. Keep exact versions, identifiers and commands in inline code when their spelling matters.

* Use `* ` for unordered Markdown lists, with a blank line before the list.
* Use numbered lists for ordered steps and `[ ]` / `[x]` for task status.
* Put a blank line between headings and paragraphs, lists, tables or code blocks.
* Keep tables readable in source, with spaces around cell contents.
* Keep commands, JSON, Mermaid and literal output inside fenced code blocks.
* Preserve measurements, links, code and evidence hashes when changing layout.

Run `python scripts/check_docs.py` before publishing documentation. It checks reader-facing guides, protocols, specifications and report summaries. Raw model outputs, frozen source archives, imported upstream prompts and byte-preserved document archives remain evidence rather than formatting targets. Generated historical README tables are checked separately by `scripts/readme_results.py`.

Formatting revisions to a hashed report summary are recorded in the [presentation revision register](markdown-presentation-revisions.json), including its original immutable Git revision/blob and old/new SHA-256 values. Update only the summary's manifest entry; never rewrite receipts, grades or other measured artifacts to accommodate a layout change.

Write each prose paragraph and each list item on one source line, letting the viewer wrap to its available width. Use an explicit Markdown hard break only when a line break is intentional. Do not insert a source newline between adjacent links just to fit an editor column width. Report exporters use `benchmark_runner.markdown_presentation.write_markdown` to apply this layout while retaining code, links, tables and explicit breaks; raw model outputs and solver prompts never use it.
