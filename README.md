# Local RPG — Windows folder-based prototype

You can play locally, manage campaigns in File Explorer, and edit rules, templates and
characters in Notepad. Campaigns use readable TXT/JSON files, not a database. GitHub is
only for developing the application. Gameplay does not contact GitHub or a hosted AI service.

This is a supervised prototype. It runs a GM, audits each narration with an Administrator,
and asks you before saving continuity additions. The AI can still make mistakes.

## Set it up on your Windows PC

You have already installed Python, Git, Ollama and Qwen. **Do not reinstall them.** Follow
these steps on your Windows PC. No Git commands, virtual environment, or Python packages
are needed. The application uses Python's built-in tools.

### 1. Download and extract the application

Open [your GitHub repository](https://github.com/kyrominecraft-ship-it/RPG-1).
Above the file list, click the green **Code** button, then **Download ZIP**.
Save **RPG-1-main.zip** in your Windows **Downloads** folder.

Open **PowerShell** from the Start menu. Run these lines:

```powershell
Unblock-File -LiteralPath "$env:USERPROFILE\Downloads\RPG-1-main.zip"
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\RPG-1-main.zip" -DestinationPath "$env:USERPROFILE"
Set-Location "$env:USERPROFILE\RPG-1-main"
py -3 --version
```

The last command should show Python **3.12 or newer**. Inside `RPG-1-main` you should see
`Start-RPG.bat`, this README, and the `rpg`, `tests`, and `examples` folders.
Do not run the application from inside the ZIP. If an installation already exists, follow
the update instructions below instead of extracting over it. Keep campaigns separate.

### Updating an existing installation

Stop the app with Ctrl+C in its terminal. Download a fresh ZIP from GitHub and extract it
into a temporary folder using File Explorer's **Extract All**. Open the extracted folder
until you see `Start-RPG.bat`. Copy its entire **rpg** folder into your existing application
folder and choose **Replace the files in the destination**. Include new files such as
`retrieval.py`; replacing only `engine.py` will not work. Copy the new README if wanted.
Then launch your existing `Start-RPG.bat` and select your campaign again.

**Do not replace, move or delete your campaign folder or its `.rpg` history.** No campaign
migration, import, extra Python package, or extra Ollama model is needed for this update.

### 2. Check the application

In the same PowerShell window, run:

```powershell
py -3 -m unittest discover -s tests -v
```

The final result should be **OK**. These tests use temporary campaign folders and controlled
AI responses. They verify the software's storage and approval behavior, not Qwen's judgment.
They do not touch your real campaigns. Windows may skip the symlink-specific check if your
account cannot create symlinks; the other tests should still pass.

### 3. Check Ollama and the model

Open **Ollama** from the Windows Start menu. Leave it running. In PowerShell, run:

```powershell
ollama list
```

The launcher uses **`qwen2.5:7b`** for both roles. If that exact name is already listed, you
have the required model. If it is missing, run this once to obtain that exact model:

```powershell
ollama pull qwen2.5:7b
```

Then check that it responds:

```powershell
ollama run qwen2.5:7b "Reply with one short greeting."
```

The GM and Administrator run sequentially with separate prompts. Sharing the same 7B model
is a practical starting point on your RTX 4070 Super with 12 GB VRAM. It conserves memory,
but the two roles can share blind spots. The model must be downloaded before offline play.
The application makes local requests only, to Ollama on your PC.

### 4. Start the application

Run:

```powershell
.\Start-RPG.bat
```

Your browser should open the application automatically. Keep the application's terminal
window open while playing. To stop it, click that terminal window and press **Ctrl+C**.
If Windows asks `Terminate batch job?`, type `Y` and press Enter.

**After this first setup, just double-click `Start-RPG.bat` in File Explorer.** Make sure
Ollama is running first. You do not need PowerShell or Git for normal play.

### 5. Create your first campaign

1. In the application, enter a name such as **My Dark Fantasy** and click **Create campaign**.
2. The app displays the campaign's full folder path. By default campaigns are created in
   `Documents\LocalRPG\Campaigns` inside your Windows user folder. Use the displayed path
   if Windows redirects your usual Documents shortcut elsewhere.
3. Open that folder in **File Explorer**. Open `Rules.txt` in Notepad and write your rules.
4. Open `Continuity\World.txt` and write your initial location, time, and situation.
5. Open `Templates\Character_Template.txt` and edit the suggested profile headings.
6. Add one to three important character profiles in `Characters`, or use the AI draft button
   described below. A separate continuity file appears automatically for each supplied profile.
7. Return to the app. It reloads files about every five seconds and before each game action
   or update approval. No import command is needed.
8. Type a small action to start playing. Allow time for the GM, audit and continuity review.

To open an existing campaign anywhere on your PC, click **Choose folder…** and select its
folder in the Windows folder picker. Campaigns in the default location also appear in the
app's selection list. You can switch between campaigns without moving their files. Select
again after restarting; a live session is not assumed to survive closing the app.

## The campaign folder

Use this layout. The names identify file roles; they do **not** prescribe character fields.

```text
My Dark Fantasy/
  Rules.txt                          Your current behavioral and adjudication rules
  Templates/
    Character_Template.txt           Editable guidance for profile structure
    Continuity_Guidance.txt           Optional extra guidance you write yourself
  Characters/
    Mira.txt                         A supplied important character profile
    Jon.txt                          Another supplied profile
  Continuity/
    World.txt                        World developments and incidental NPC events
    Characters/
      Mira.txt                       Mira's separate ongoing continuity
      Jon.txt                        Jon's separate ongoing continuity
  World/
    Locations.txt                    Additional source documents
    Factions.json                    Optional readable JSON source
  .rpg/
    events.jsonl                     Append-only, checksummed event/audit log
    history/                         Exact saved versions of observed source files
    audits/                          Readable JSON copies of completed draft audits
    lock                             Internal file-operation coordination
```

The app reads UTF-8 **TXT and JSON** source files recursively, excluding `.rpg`. JSON files
must contain valid JSON. You can use only TXT if you prefer. Keep important character profiles
as TXT files directly inside `Characters`. A JSON file or an incidental name elsewhere does
not register a character. Additional profiles work without changing Python, subject to the
small context budget described below.

In File Explorer turn on **View → Show → File name extensions**, so a profile is really
`Mira.txt` rather than `Mira.txt.txt`. Save text in **UTF-8** in Notepad. Unsupported formats
such as Word documents are not loaded. Linked/junction folders are not supported.

## Editable character templates

A template is ordinary text. These are examples of headings you might use:

```text
# Name and role
# Personality
# Motivations
# Private Interpretations
# Secrets
# Relationships
```

Add, delete, rename or rearrange headings. You can include explanations beneath them.
The AI reads the actual template text. **No NPC profile structure is hardcoded in Python.**
Extra legitimate details in an existing profile remain valid even if they do not fit a heading.
Profiles can differ from one another; they are not forced into identical personalities.

The app's **Optional template updates for existing profiles** compares headings as helpful
suggestions. It recognizes headings beginning with `#` or ending in `:`. It also flags template
text changes since a profile was first observed. This is a rough comparison, not semantic
validation. Plain text without these heading styles still loads and guides the AI.
Changing a template never automatically changes an existing profile. Review suggestions and
edit a profile yourself only if you want them. Suggestions currently compare each template
against each profile; there is no mandatory template assignment or programming language.

### Ask the AI to fill out a template

1. In the app, expand **Ask the AI to draft a new character profile**.
2. Enter the character's name, choose a template and describe the character. Include any
   established details that must remain true.
3. Click **Draft for my review**. Nothing is written to `Characters` yet.
4. Read the draft in the editable text box. Correct anything you dislike.
5. Click **Approve and create this profile**, or discard it.

An approved new profile is created as `Characters\Name.txt`. Only then is its separate blank
continuity file created. Existing profiles are never overwritten by this feature. A profile
is author-supplied campaign material after your approval; it is not a narrated gameplay event.
You can also create the TXT yourself in Notepad. To promote an incidental NPC, add their
profile this way, preserving what has already been established about them.

## Profiles, continuity, facts and beliefs

A **profile** defines established character information. A **continuity file** records
what develops in play. The application never rewrites a profile to excuse a GM response.

Only characters with explicitly supplied TXT profiles get individual continuity files.
The GM cannot create profile or continuity paths by inventing incidental NPCs. Incidental
NPC developments can be proposed for the existing world continuity file. If you remove or
rename a profile, its old continuity file is preserved but excluded from active context until
a matching profile exists; the app displays a warning. Rename/move matching files yourself
when intentionally renaming a character. Renaming is not automatically treated as identity.

After a narration passes the audit and is recorded as an approved event, the Administrator
makes a **separate** continuity call. It can propose facts, character knowledge, assumptions,
unresolved conflicts, plot beats, promises, goals, location/injuries, relationship changes,
and other labels suggested by your templates. Custom labels such as **Private Interpretations**
are supported. Proposed notes appear in the app before any existing continuity file is written.

Entries label their perspective as **objective**, **belief**, **suspicion**, or **assumption**.
Knowledge entries must state when and how the character learned the information; the model
is instructed to record an unresolved conflict instead of inventing a learning event. Every
entry includes a quotation from its approved narration and the approved turn ID. You can
approve the additions, reject them, or request fresh proposals. Approval appends readable
text to the continuity file and retains the previous bytes in version history.

The app validates paths, quotation presence, labels, field sizes, known profiles and source
versions. It cannot prove that a quotation supports an interpretation. **Review the notes.**
The JSON used between the model and application is an internal safety envelope; it does not
impose a JSON character-profile schema on your TXT files.

## Rules and the approval boundary

Both roles read current `Rules.txt`, other loaded rule documents, applicable profiles,
continuity, templates and approved story events. You can change fictional behavioral rules,
adjudication and continuity conventions in those documents. Give instructions clearly and
avoid conflicting rule files. The Administrator is instructed to state uncertainties and
interpretive conflicts rather than treat its own judgment as unquestionable fact.

The application always enforces its storage and approval boundaries. Text documents cannot
disable the audit, approve rejected drafts, bypass your continuity approval, or authorize
rewriting profiles. Objective facts and beliefs remain explicitly distinguishable.

Each player action follows this sequence:

1. GM drafts a narration.
2. Administrator approves, or rejects with source quotation and correction.
3. GM revises; at most **three drafts** are reviewed.
4. Three rejections pause the campaign and show all drafts, raw audits and corrections.
   You must acknowledge review before another action. Acknowledging does not canonize a draft.
5. An approved narration is logged as a canonical story event and shown in chat.
6. Only after that commit does the Administrator propose continuity additions for your approval.

Rejected drafts remain audit records only. They never enter later canonical story context or
write character continuity. If continuity generation fails, the approved narration remains
canon; use **Request fresh continuity proposals**. Existing continuity documents are never
updated merely because a draft was generated or an audit rejected it.

## Editing safely and keeping backups

You can leave Notepad open. Save your work and wait for the file list to refresh before
submitting an action. Added, edited and deleted sources are discovered automatically. Your
manual edits are treated as author-supplied changes, recorded as source revisions; the app
does not silently undo them or reinterpret them as unapproved AI drafts.

If a source changes while a narration is being generated, its approval is invalidated when
the changed revision is detected. If any campaign source changes after continuity proposals
are prepared, their save is refused. Request fresh proposals and review them against the new
sources. A draft profile also becomes stale when the campaign changes.

Before continuity writes, the app verifies current file hashes again and saves exact old/new
versions. On Windows it opens update targets denying concurrent writes/deletes, so a racing
editor save cannot be silently overwritten. If a file is busy, close the editor and retry.
On non-Windows systems the file lock is advisory; avoid concurrent editor saves there.

An interrupted approved write is recorded in a durable journal. On reopening, the app can
finish it if target contents still match the reviewed old/new versions. If a target instead
contains a newer external edit or an unrecognized partial write, it preserves the file,
logs a conflict, and warns you to review continuity. A multi-file write interrupted by power
loss can leave some already-approved additions applied and others pending/conflicted; it is
recoverable from saved versions, not an all-or-nothing filesystem transaction.

`.rpg\history` contains exact bytes, named by SHA-256 checksum with a `.txt` extension,
including original JSON bytes when relevant. Source-revision records in `events.jsonl` map
original relative filenames to those checksums. Only versions the app actually observes are
captured; saves made and replaced between scans cannot be recovered. `.rpg\audits` contains
readable JSON audit snapshots; the log remains authoritative for later proposals and decisions.
Do not edit files inside `.rpg`. A malformed or incomplete log blocks further loading rather
than guessing how to repair canon. Checksums detect many accidental changes, not deliberate
tampering or removal of a complete log tail.

**Make an additional backup:** stop the application, then copy the **entire campaign folder**,
including `.rpg`, to a dated backup folder or another drive. Restore a whole known-good copy
if the log is damaged. To restore one older source version, stop the app, back up the current
folder, locate its hash in a source-revision record, and copy that history TXT's contents back
to the original source path. The app will recognize it as a new external revision next time.
There is not yet a one-click history browser or restore tool.

Campaigns are local and unencrypted. Choose folders outside the application/Git checkout.
Do not place private campaign folders inside a repository you publish. Backups, not Git,
protect normal gameplay. Updating application files should not touch your campaign folders.

## First play check on your computer

Start with one to three profiled characters and short sources. Try these checks:

1. Describe an action consistent with the rules and check that only approved narration appears.
2. Attempt to use a key/ability your profile does not possess. Expect clarification or rejection,
   not an invented possession. Check that no rejected attempt appears in continuity.
3. Check that character suspicions are labeled as suspicions and that new knowledge has an
   established way of being learned. Confirm one proposed continuity addition, then open the
   TXT in Notepad and inspect it.
4. Edit a rule and save it. Check that the app reloads it without an import.
5. Add `# Private Interpretations` to a template. Existing profiles should remain unchanged;
   the optional suggestions should update. Draft a new NPC and review the result.
6. Close and reopen the app, select the same campaign, and check chat history and pending notes.

Generation can take several minutes: there is one call per draft, one per audit, then another
for continuity. The adapter waits up to five minutes per model call. Do not submit duplicate
actions while it is working. `ollama ps` in PowerShell during generation shows GPU/CPU placement.

## Limits and troubleshooting

- **Actual Windows/model testing is still needed.** Automated tests run in this Linux cloud
  environment. HTTP tests use controlled responses and a fake Ollama server. The Windows
  native folder picker, launcher, deny-write handles and your GPU were not executed here.
- **Model quality:** separate prompts are not a guarantee of independent judgment. Exact
  quotations can be misinterpreted; important changes require your review.
- **Campaign size versus request size:** larger libraries now use passage retrieval. This
  revision is tested with a synthetic library larger than 128 KB, including roughly 19 KB
  of rules and 27 KB of player profile. The per-file limit remains 200 KB. This is not a
  claim that a 1 GB library is fast or thoroughly tested; sources and indexes are currently
  held in RAM and rebuilt for a snapshot. A disk index is future work.
- **Bounded model requests:** GM evidence is budgeted at 64,000 JSON UTF-8 bytes; Administrator
  evidence can grow to 76,000 bytes through lookup. The complete request guard remains 96,000
  bytes and Ollama context 32,768 tokens. These byte limits are not exact token counts. Unusual
  text may still exceed model context. GPU use, latency and model accuracy need local testing.
- **One local player:** run one application instance per campaign. It is not a networked or
  packaged Windows product. There is no automatic off-screen simulator, dice roller,
  cancellation, deterministic RPG rules engine, or automatic recovery of an interrupted turn.
- **Old SQLite prototype:** old databases are left untouched and are not loaded. No automatic
  migration is included. If you used one, preserve it and its original files before moving on;
  do not rename a database to TXT or assume its story history has transferred.
- **Cannot contact Ollama:** open the Ollama desktop application, run `ollama list`, and verify
  `qwen2.5:7b` exists. The app uses local port 11434. No credentials are needed for local play.
- **App says port 8000 is in use:** close an earlier app terminal before launching another copy.
- **Bad JSON/UTF-8:** fix the named source file in your editor and save as UTF-8. Loading stops
  on invalid supported files, rather than silently excluding their contents.
- **Folder picker unavailable:** the browser includes an expandable field for the full folder
  path. The standard Windows Python installation includes the Tk folder picker dependency.

## Development notes

Modules: `store.py` owns readable sources/history/events and conflict handling; `files.py`
handles durable writes and platform locks; `engine.py` owns the audit gate and post-canon
proposals; `templates.py` supplies free-text template suggestions and profile drafting;
`campaigns.py` manages folder selection; `web.py` serves the local interface. The Ollama adapter
can be replaced independently. No third-party Python dependencies are needed.

Run `python3 -m unittest discover -s tests -v` from the existing `/workspace/RPG-1` checkout
for cloud development. HTTP tests require loopback socket access. Each cloud task is already
isolated; do not create another Git worktree unless requested. No application preview link
is provided for this cloud instance. It cannot install or run software on your Windows PC.

Validation for this revision: **38 tests passed, one Windows-only sharing-semantics test
was skipped on Linux**. The tests include large-campaign request envelopes through the real
Ollama adapter with controlled responses, independent lookups and corrections, exact citations,
external edits, and exclusion of rejected drafts. Actual Qwen quality and GPU usage still
require play-testing on your Windows PC.

## How retrieval works for your 128 KB campaign

The earlier 18/48 KB *whole-campaign* gate no longer blocks larger libraries. The app searches
local text without changing your source files, adding a database, training Qwen, or downloading
another model. If a small library fits, it continues to receive full-source treatment.

For larger libraries:

1. **Rules are always included in full.** Keep the main file named `Rules.txt`. Files with
   a separate `rules`/`rule` word in the name, and files under `Rules`, are also always included.
   Do not use these names for unrelated archive material.
2. **Your player profile can be included in full.** Name it `Characters/Player_Character.txt`,
   or start a differently named character profile with `This is the player-controlled character.`
   Mentioning the player in an ordinary NPC profile does not register that NPC as the player.
3. Rules and player profiles must together fit about 56,000 serialized bytes, leaving room
   for other evidence. Your reported 19 KB rules plus 27 KB profile are the intended scale.
   If the mandatory material exceeds the budget, the app stops rather than quietly dropping it.
4. Other sources and approved story history are split into overlapping passages. Local
   keyword ranking, filenames, recent scene text and topic vocabulary (combat, relationships,
   knowledge, travel and magic) select relevant passages. Custom document headings still work;
   these topic words do not impose a character schema or new game rules.
5. The Administrator performs another search using the action **and GM draft**, keeps the GM's
   evidence, and can request up to two additional lookup rounds before deciding. A retrieved
   citation used in a correction is passed back to the GM. Lookup does not consume another
   GM draft attempt. Protocol failures or exhausted lookups stop the turn without making it canon.
6. Continuity proposals and character drafting also use relevant retrieved evidence. Continuity
   proposals still require an already-approved event and your confirmation before writing.

A citation such as `document:World/Factions.txt#chars=1400:2700` identifies an exact character
range in that source version. Selected source IDs, source versions, topics and lookup requests
are recorded in the audit log. Rejected drafts are never indexed as canonical source material.
External file edits take effect on the next refreshed snapshot, and existing stale-write checks
still apply. The app shows a retrieval notice after an approved response that used passages.

**Limitations:** this is lexical retrieval with English topic vocabulary, not semantic embeddings.
It can miss paraphrases, hidden connections or relevant old events. The Administrator is instructed
to search or ask for clarification when evidence is insufficient, but an LLM can still approve a
mistake. Passing software tests does not prove narrative correctness. Review early sessions,
especially character knowledge, relationships and capability use. Older events remain intact
on disk even when they are not selected for a particular request.

### Do setting and factions need model training?

Not for this play-test. Editable source documents plus retrieval keep lore current and provide
checkable quotations. Fine-tuning does not turn a model into an exact, reliably updated database,
and it can still invent facts. It is better considered later for style or recurring behavior,
after collecting examples and evaluation cases. Continue writing faction and setting TXT files
in your campaign's `World` folder.

### If a response hits its output limit

The GM is now asked for one playable opening scene (usually 150–350 words), not a complete
adventure in one reply. Each call starts with a 2,048-token output allowance. If Ollama
explicitly reports that allowance was exhausted, the app discards the partial response and
restarts the same request once with a 4,096-token allowance and a concise-completion reminder.
The retry also preserves JSON mode for Administrator calls. Incomplete output never becomes
canon or updates continuity. An output retry is not an Administrator rejection and does not
change the three-rejected-drafts review rule. A retry can increase waiting time.

If the retry also runs out, the error identifies the role, model and output limit. Ask for
one short scene and check whether your campaign rules demand very long responses. An unfinished
response or a response with no final text stops with a separate diagnostic rather than being
accepted. This handling is tested with controlled Ollama responses; actual model performance
and the cause of an individual Windows/Ollama interruption still need local observation.
