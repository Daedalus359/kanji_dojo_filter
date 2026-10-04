# Kanji Dojo Deck Analysis and Removal Workflow

## Overview

This workflow analyzes your Kanji Dojo vocabulary deck to identify low-frequency, ambiguous, or poorly-supported entries, then safely removes them after your explicit approval.

**Safety guarantee**: Your original database is never modified. All changes are made to a copy, and you control every step.

---

## Input Data Sources

All scripts require:

- **Kanji Dojo database**: `user_data.sqlite` (typically in your Kanji Dojo app directory)
- **JMdict data**: `data/JMDict/term_bank_*.json` (relative to this repo)
- **JPDBv2 frequency data**: `../frequency_data/term_meta_bank_1.json` (relative to this repo)

---

## Step 1: Analyze Your Deck

**Purpose**: Identify entries with scores > 0 (candidates for removal or review).

**Command**:
```bash
python3 analyze_deck.py \
  --database user_data.sqlite \
  --source-table vocab_deck_entry \
  --jmdict-directory data/JMDict \
  --frequency-data ../frequency_data/term_meta_bank_1.json \
  --threshold 11000 \
  --output analysis_report.txt \
  --verbose
```

**Inputs**:
- `user_data.sqlite`: Your Kanji Dojo database (read-only)
- `data/JMDict/term_bank_*.json`: JMdict vocabulary data (read-only)
- `../frequency_data/term_meta_bank_1.json`: JPDBv2 top-11000 frequency rankings (read-only)

**Output**:
- `analysis_report.txt`: Human-readable list of all entries with nonzero scores

**Key options**:
- `--threshold 11000`: Words ranked in JPDBv2's top 8,000 get zero frequency penalty
- `--verbose`: Show detailed reasoning (component scores, reasons)

---

## Step 2: Interactive Review (Multi-Session)

**Purpose**: Manually review flagged entries and decide keep/remove per deck.

**Command** (same command for all sessions):
```bash
python3 interactive_reviewer.py \
  --database user_data.sqlite \
  --source-table vocab_deck_entry \
  --decision-log decisions.json \
  --jmdict-directory data/JMDict \
  --frequency-data ../frequency_data/term_meta_bank_1.json
```

**Inputs**:
- `user_data.sqlite`: Your Kanji Dojo database (read-only)
- `data/JMDict/term_bank_*.json`: JMdict vocabulary data (read-only)
- `../frequency_data/term_meta_bank_1.json`: JPDBv2 frequency rankings (read-only)
- `decisions.json`: Your saved decisions from previous sessions (if exists)

**Output**:
- `decisions.json`: Serialized decision log (JSON format, human-editable)
  - Tracks which decks you've reviewed
  - Records your keep/remove/undecided choices
  - Stores your notes for each entry
  - Timestamps each decision

**Workflow**:
1. Script loads `decisions.json` (or creates empty log if first run)
2. Shows completed decks, prompts you to review remaining decks
3. For each deck, displays entries with nonzero scores
4. You decide: `[k]eep`, `[r]emove`, `[n]otes only`, `[s]kip`, `[q]uit`
5. When done (or quit), script saves progress to `decisions.json`
6. Next session, run same command—picks up where you left off

---

## Step 3: Export Decisions (Optional)

**Purpose**: Generate human-readable removal list for manual review/editing.

**Command**:
```bash
python3 -c "
from decision_persistence import load_decision_log, export_removal_list
from database_loader import load_deck_mapping

log = load_decision_log('decisions.json')
deck_map = load_deck_mapping('user_data.sqlite')
export_removal_list(log, 'removal_list.txt', deck_map)
"
```

**Inputs**:
- `decisions.json`: Your saved decision log (from Step 2)
- `user_data.sqlite`: Used only to fetch deck names (read-only)

**Output**:
- `removal_list.txt`: Human-readable summary grouped by decision status:
  - **MARKED FOR REMOVAL**: Entries you decided to remove
  - **UNDECIDED**: Entries you skipped
  - **MARKED TO KEEP**: Entries you decided to keep

**Can hand-edit this file** to change decisions before Step 4 if needed.

---

## Step 4: Apply Removals

**Purpose**: Review approved removals deck-by-deck, then delete from a copy of your database.

**Command**:
```bash
python3 apply_removals_main.py decisions.json \
  --database user_data.sqlite \
  --source-table vocab_deck_entry
```

**Inputs**:
- `decisions.json`: Your saved decision log (from Step 2)
- `user_data.sqlite`: Your original Kanji Dojo database (read-only during this step)

**Outputs**:
- `user_data_backup_YYYYMMDD_HHMMSS.sqlite`: Timestamped backup of original (in same directory as input)
- `user_data_approved_removals.sqlite`: New database with approved removals applied (in same directory as input)

**Workflow**:
1. Script loads `decisions.json` and groups removals by deck
2. For each deck, prompts final approval: `[y]es`, `[n]o`, `[q]uit`
3. Creates timestamped backup of original
4. Copies original to `user_data_approved_removals.sqlite`
5. Applies only approved removals to the copy
6. Original `user_data.sqlite` remains unchanged

**Important**: The original database is NOT modified. You get a new file.

---

## Step 5: Verification & Deployment

**Verify removals were applied**:
```bash
# Count removed entries (should be 0)
sqlite3 user_data_approved_removals.sqlite \
  "SELECT COUNT(*) FROM vocab_deck_entry WHERE kanji_reading = '楽む' AND kana_reading = 'たのしむ';"
```

**Deploy the cleaned database**:
```bash
# Backup the original (safe, but Step 4 already did this)
mv user_data.sqlite user_data_original_handoff.sqlite

# Use the cleaned version
mv user_data_approved_removals.sqlite user_data.sqlite
```

---

## File Locations Summary

### Read-Only Inputs
```
user_data.sqlite                              Kanji Dojo vocabulary database
data/JMDict/term_bank_1.json                 JMdict entry 1
data/JMDict/term_bank_2.json                 JMdict entry 2
... (more term_bank_*.json files)
../frequency_data/term_meta_bank_1.json      JPDBv2 frequency rankings
```

### Generated During Workflow
```
analysis_report.txt                          Step 1: Human-readable analysis (optional)
decisions.json                               Step 2: Your decisions (resumable across sessions)
removal_list.txt                             Step 3: Human-readable removal list (optional)
user_data_backup_YYYYMMDD_HHMMSS.sqlite     Step 4: Automatic backup before changes
user_data_approved_removals.sqlite           Step 4: New database with removals applied
```

---

## Safety Guarantees

✅ **Original database never modified** during review or removal phase  
✅ **Automatic backup created** with timestamp before any deletions  
✅ **Per-deck approval** – you must approve each deck's removals separately  
✅ **Resumable sessions** – quit and resume review across multiple sessions  
✅ **Scoped deletions** – removals affect only the specific deck and (expression, reading) pair  
✅ **Human-readable decisions** – export and hand-edit before applying if needed  
✅ **Easy recovery** – use the timestamped backup if anything goes wrong  

---

## Example: Full Workflow in One Session

```bash
# 1. Analyze
python3 analyze_deck.py --database user_data.sqlite --verbose --output report.txt

# 2. Review (you make decisions interactively; saves to decisions.json)
python3 interactive_reviewer.py --database user_data.sqlite --decision-log decisions.json

# 3. Export for review (optional)
python3 -c "
from decision_persistence import load_decision_log, export_removal_list
from database_loader import load_deck_mapping
log = load_decision_log('decisions.json')
deck_map = load_deck_mapping('user_data.sqlite')
export_removal_list(log, 'removal_list.txt', deck_map)
"
cat removal_list.txt  # Review before proceeding

# 4. Apply removals (interactive final approval per deck)
python3 apply_removals_main.py decisions.json --database user_data.sqlite

# 5. Verify and deploy
sqlite3 user_data_approved_removals.sqlite "SELECT COUNT(*) FROM vocab_deck_entry;"
# ... inspect and verify ...
mv user_data.sqlite user_data_backup_manual.sqlite
mv user_data_approved_removals.sqlite user_data.sqlite
```

---

## Troubleshooting

**"FileNotFoundError: SQLite database not found"**
- Check that `user_data.sqlite` exists in your working directory
- Provide `--database /full/path/to/user_data.sqlite` if in a different location

**"Could not find table vocab_deck_entry"**
- Your database may use a different table name
- Check: `sqlite3 user_data.sqlite ".tables"`
- Use `--source-table <your_table_name>` to specify

**"Frequency dataset not found"**
- Ensure `../frequency_data/term_meta_bank_1.json` exists relative to the script
- Provide `--frequency-data /full/path/to/term_meta_bank_1.json` if in a different location

**"Refusing to overwrite the original database"**
- Step 4 will not apply removals directly to the original
- The script creates a new file by default
- If you want a different output path, use `--output /path/to/new_database.sqlite`

---

## Reverting Changes

If you deploy the cleaned database and later regret, simply restore from the timestamped backup:

```bash
# List backups
ls -la user_data_backup_*.sqlite

# Restore from a specific backup
mv user_data.sqlite user_data_removed.sqlite  # Keep the modified version if needed
mv user_data_backup_20261004_143215.sqlite user_data.sqlite
```

---

## Notes

- **Frequency threshold**: Default is 8,000 (JPDBv2's top 8,000 most frequent words)
  - Words at/above rank 8,000 get zero frequency penalty in the score
  - Adjust with `--threshold` if you want a different cutoff

- **Decision log format**: `decisions.json` is plain JSON; you can edit it by hand if needed

- **Scoring model**: Composite score includes:
  - JPDBv2 frequency ranking (above threshold = higher risk)
  - JMdict match quality
  - Forms table priority
  - Expression/reading ambiguity
  - See `quality_scorer.py` for weights and details

- **Multi-session workflow**: Safe to interrupt at any point
  - Step 2 (review) saves progress to `decisions.json` whenever you quit
  - Run same command to resume where you left off
