---
name: check-refs
description: >-
  Verify BibTeX citations against academic databases. TRIGGER when the user
  asks to "check references", "verify citations", "validate bibtex",
  "check my bib file", "are my references correct", "find citation errors",
  "verify bibliography", or mentions .bib files in context of verification
  or correctness checking. Queries CrossRef, OpenAlex, Semantic Scholar,
  arXiv, and DBLP to verify entries are real papers with correct metadata.
allowed-tools: Bash, Read, Glob, Grep
argument-hint: <path/to/refs.bib> [--fix] [--context path/to/paper.tex]
---

# Check References — BibTeX Citation Verification

You are verifying BibTeX citations against academic databases. Your job is to run the verification script, interpret its output, and present a clear report to the user.

## Step 1: Find the .bib file

Parse `$ARGUMENTS` for the .bib file path.

- If a path is provided, use it directly.
- If no path is given, use the Glob tool to search for `**/*.bib` files in the current directory. If multiple .bib files are found, list them and ask the user which one to check.
- Verify the file exists using Read before proceeding.

Also check for flags in `$ARGUMENTS`:
- `--fix`: After reporting, generate corrected BibTeX entries for any mismatches.
- `--context <path.tex>`: Also cross-reference citation keys against the .tex file.

## Step 2: Run the verification script

Run the verification script via Bash:

```
python3 PLUGIN_DIR/scripts/verify_bib.py "<bib_file_path>" --verbose
```

Replace `PLUGIN_DIR` with the absolute path to this plugin's root directory (two levels up from this SKILL.md file — determine this by checking where this skill file is located using the Glob tool to find `**/skills/check-refs/SKILL.md` and deriving the plugin root).

For large .bib files (50+ entries), add `--batch-delay 1.0` to be conservative with rate limits.

The script outputs JSON to stdout and progress to stderr. Capture the JSON output.

## Step 3: Present the report

Parse the JSON output and present results in this format:

### Summary line
Start with a one-line summary: "Checked N entries: X verified, Y mismatches, Z not found, W skipped"

### Verified entries
List verified entries briefly — just the citation key and title. These are confirmed real papers with matching metadata. Keep this section concise.

### Entries with mismatches
For each mismatch, show:
- **Citation key** and title
- A table or list of which fields differ, showing the bib value vs. the database value
- Specific corrections the user should make
- The database source used for verification

This is the most important section — be specific about what's wrong and how to fix it.

### Entries not found
For entries not found in any database:
- Show the citation key, title, and authors
- Note that this could mean: (a) the paper doesn't exist (hallucination), (b) the title is too different from the published version, or (c) it's in a database not covered by the tool
- Suggest the user manually verify these entries

### Skipped entries
Briefly note any entries skipped (software, websites, blogs) — these are not expected to be in academic databases.

## Step 4: Fix mode (if --fix flag)

If the user passed `--fix`:
1. For each mismatch entry, generate corrected BibTeX using the database metadata
2. Show the corrected entries in a code block
3. Ask the user if they want to write the corrections to the .bib file
4. If yes, use the Edit tool to update the specific entries in the .bib file

## Step 5: Context mode (if --context flag)

If the user passed `--context path/to/paper.tex`:
1. Read the .tex file
2. Find all `\cite{...}`, `\citep{...}`, `\citet{...}` commands using Grep
3. Extract all citation keys used in the .tex
4. Compare against keys in the .bib file
5. Report:
   - Citation keys used in .tex but missing from .bib (broken references)
   - Citation keys in .bib but never used in .tex (unused entries)

## Error handling

- If the script fails to run (Python not found, missing dependencies), tell the user they need `bibtexparser` and `requests` installed: `pip install bibtexparser requests`
- If the script reports rate limiting, inform the user and suggest: "For higher rate limits with Semantic Scholar, set the `SEMANTIC_SCHOLAR_API_KEY` environment variable."
- If the .bib file has parse errors, report which entries failed to parse and continue with the rest.

## Important notes

- Do NOT hallucinate or guess whether a paper is real. Only report what the databases return.
- The verification script queries real APIs — results may take 30-60 seconds for files with 20+ entries.
- Title matching uses fuzzy comparison. A score of 0.85+ means strong match; 0.70-0.84 means possible match with differences.
- Year differences of +/- 1 are common (preprint vs. published version) and are noted but not flagged as errors.
