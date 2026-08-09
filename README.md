[![CI](https://img.shields.io/github/actions/workflow/status/catanadj/kyanbasu/ci.yml?branch=main&label=CI)](https://github.com/catanadj/kyanbasu/actions/workflows/ci.yml)

![Kyanbasu branded thinking canvas](https://raw.githubusercontent.com/catanadj/kyanbasu/main/docs/assets/kyanbasu-banner.jpg)

# Kyanbasu

A visual planning workspace and command generator for Taskwarrior.

Kyanbasu brings Taskwarrior tasks and structured notes onto one spatial canvas. Organize work across multiple workbenches, build mind maps, inspect dependency chains, and stage task changes without giving the browser direct access to your Taskwarrior data.

Task changes become plain `task` commands that you can review, edit, and copy back into your terminal. The generated HTML remains local and never writes to Taskwarrior directly.

[Changelog](CHANGELOG.md)

[Decision method](docs/DECISION_METHOD.md)

---

## What it does

Kyanbasu is a Python 3 app (`kyanbasu/` plus packaged templates) that:

- Calls task status:pending export (or a custom filter) to fetch your tasks.

- Builds a local workspace payload with tasks, dependencies, and initial placement information.

- Injects that payload into a self-contained HTML/JS workspace (`Kyanbasu.html`) in the current working directory.

- Opens the HTML in your default browser (Termux, Linux, macOS, Windows are handled).

Inside the browser you get an interactive canvas where you can:

- Arrange projects, tasks, note buckets, and mind-map branches.

- Draw task dependencies and annotated relationships between notes.

- Stage, review, edit, and remove Taskwarrior commands before copying them.

- Search, focus, collapse, import, and export structured notes.

- Separate areas of work into independent workbenches.

---
## 30-second start

```bash
# 1. clone the repo
git clone https://github.com/catanadj/kyanbasu.git
cd kyanbasu
python3 -m pip install -e .

# 2. generate the board
kyanbasu                    # all pending tasks
kyanbasu project:Work       # place Work initially
kyanbasu --filter "due.before:today"  # any filter string

# 3. your browser opens; drag, connect, edit
# 4. hit “Copy commands” and paste in terminal
```

## Features

### Tasks and projects

- All pending tasks are loaded into a searchable drawer and a canvas.

- Tasks and projects are draggable, selectable, and visually distinct from planning notes.

- Static directional dependency edges show blocking relationships without continuous animation or idle CPU work.

### Thinking canvas

- Notes form editable mind maps with keyboard-first sibling and child creation.

- Buckets group related notes and can move their contents as one unit.

- Note identifiers, search, focus mode, editable outliner, colours, multi-selection, and import/export support larger maps.

- Relationship annotations add a label or question directly to a note link.

- Guided decision maps preserve factors, options, possible outcomes, branching first/second/third-order consequence analyses, inversion analyses, choice rationale, and immutable choice-time snapshots for later review.

- Multiple workbenches separate contexts while keeping them in one generated workspace.

### Builder & Viewer tabs

- **Builder**: the full spatial workspace for arranging tasks, projects, notes, buckets, and links.

- **Viewer**: a compact task overview and notes outliner, sortable by note ID or bucket.

### Command console and review

- Every change you stage becomes a task command (modify/add/done/delete/depends +/-) in a console area.

- Commands are de-duplicated and normalised so each final line is safe to paste.

- Removed commands stay removed when the remaining command set is copied.

### Hover actions and staging

- Hovering a task card reveals focused Done, Delete, and Modify actions.

- Staged tasks are visually highlighted (green for Done, red for Delete) with line-through titles.

- Undo/redo is available for staged interactions and canvas edits via `Ctrl/Cmd+Z` (undo), `Ctrl+Y` or `Ctrl/Cmd+Shift+Z` (redo).

### Clear dependency direction

- Dependency edges use smooth static curves, clear endpoint arrows, and directional markers.

- Existing and staged relationships remain visually distinguishable without animated strokes.

- Dragging tasks keeps their edges attached and updates the geometry only when needed.

- Static rendering keeps the idle canvas responsive on larger workspaces.

### Actionable beacons and due badges

- Tasks that participate in dependency chains but have no remaining prerequisites get a subtle “actionable” beacon, helping you see where you can actually start.

- Due dates (when present) are shown as a small badge with visual states for overdue / soon / future.

### Multiline add and project creation

- Floating “plus” menu (FAB) for adding new tasks.

- Multiline add mode lets you paste several new tasks at once; each line becomes a separate task add.

- The FAB menu is patched so you can also create **new projects** from the UI (“Add new project” button / modal).

### Project selector and auto-placement

- Optional curses-based project selector (--selector) with filtering, select all/none, paging, and a fallback text prompt if curses fails.

- Initial placement can be driven by positional project arguments and/or a Taskwarrior filter (-f/--filter).

- Filtered tasks (e.g. project:Work +P1) are automatically dropped onto the canvas while all other tasks remain available in the drawer.

### Custom background

- You can give Kyanbasu a custom background image via `--bg` and `--bg-opacity`.

- If no flag is provided, it auto-searches for files like `kyanbasu-bg.jpg/png/webp` in the package, current working directory, or demo directory and uses them as a body overlay.

### Termux and desktop friendly

- Output HTML is named `Kyanbasu.html` in the current directory.

- It is opened via termux-open on Termux, xdg-open on Linux, open on macOS, and os.startfile on Windows.

---

## Requirements

- Python **3.10+** (uses modern type-hint syntax like str | None).

- Taskwarrior installed and on your $PATH so the task command works.

- If running from source, install with `python3 -m pip install -e .` so the console command can find packaged templates.

- A reasonably modern browser (the UI is vanilla HTML/JS/SVG, no external JS dependencies). Chrome is recommended.

---

## Code layout (for contributors)

- `Kyanbasu.py`: preferred wrapper for direct script execution.
- `kyanbasu/`: application package and `python -m kyanbasu` entry point.
- `kyanbasu/app.py`: app orchestrator and CLI entry point.
- `kyanbasu/task_io.py`: Taskwarrior export execution and parsing.
- `kyanbasu/payload.py`: task graph payload construction.
- `kyanbasu/cli.py`: CLI argument extraction helpers (`--filter`, `--bg`, `--bg-opacity`).
- `kyanbasu/output.py`: cross-platform browser opener.
- `kyanbasu/injectors.py`: HTML/JS feature injectors and background/overlay patch helpers.
- `kyanbasu/templates/`: base HTML template, modal replacement fragment, and runtime assets.
- `CHANGELOG.md`: release history.

---

## Diagnostics

- Set `KYANBASU_LOG_LEVEL` to control runtime logs (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
- Default log level is `INFO`.

## Commands and runtime

These launch methods are equivalent:

```bash
kyanbasu              # installed command
python3 -m kyanbasu   # module entry point
python3 Kyanbasu.py   # source-tree wrapper
```

- The Python distribution and import package are both named `kyanbasu`.
- Browser state is stored under `kyanbasu:*` keys.
- Notes and workbench exports use the `kyanbasu.notes` and `kyanbasu.workbenches` kinds.
- TaskCanvas notes and workbench JSON exports remain importable; Kyanbasu normalizes
  them to its current format when they are exported again.
- Downloaded files use `kyanbasu-notes.json`, `kyanbasu-workbenches.json`, and `kyanbasu-reviewed-commands.sh`.
- Browser integrations use `window.KyanbasuNotes`, `window.KyanbasuWorkbenches`, and the other `window.Kyanbasu*` APIs.

---

## Release checks

- Unit tests:
  - `python3 -m unittest discover -s tests -v`
- Integration test (real Taskwarrior):
  - `KYANBASU_RUN_INTEGRATION=1 python3 -m unittest tests.test_task_io_integration -v`
- Combined local release check:
  - `./scripts/release_check.sh`
- Build the distributable wheel:
  - `python3 -m pip wheel --no-build-isolation --no-deps --wheel-dir dist .`
- CI integration job is optional and can be run via **Actions -> CI -> Run workflow** with `run_integration=true`.

---

### Auto-placing tasks by project

You can pass project names as positional arguments; tasks from those projects will be initially placed on the canvas:

```
kyanbasu Work Home side.hustle
```

The rest of your pending tasks remain available in the left-hand drawer for drag-and-drop.

### Auto-placing tasks via Taskwarrior filters

Use -f / --filter to provide any Taskwarrior filter expression; matching tasks will be auto-placed:

```
kyanbasu --filter 'due.before:2026-01-01 status:pending'
```

The filter is only used to choose which tasks to pre-place; **all** pending tasks still go into the drawer/search payload.

You can combine projects and a filter:

```
kyanbasu -f 'project:Work +P1' Home 'life.admin'
```

### Interactive project selector

If you don’t feel like typing project names, use the selector:

```
kyanbasu --selector
```

This starts a curses TUI listing all projects (with counts). Use:

- Arrow keys / PgUp / PgDn / Home / End to move.

- / to filter visible projects.

- Space to toggle selection.

- a / n to select/clear all visible.

- Enter to confirm, q to cancel.

If curses is not available, it falls back to a numbered prompt.

### Custom background

To use a specific background image:

```
kyanbasu --bg /path/to/image.jpg
kyanbasu --bg=mywall.png --bg-opacity=0.12
```

Kyanbasu will copy the image next to `Kyanbasu.html` in the same directory and add a background overlay with the requested opacity (default approximately 0.18).

Without `--bg`, it tries to locate a file named like `kyanbasu-bg.*`, `canvas-bg.*`, `background.*`, or `bg.*` in the package directory, current working directory, or demo directory.

---

## Notes & limitations

- Layout is auto-saved in browser `localStorage` (per task-set signature). Node positions, project/tag area placement, zoom, and drawer state are restored on next run.

- Clearing browser site data (or using private/incognito mode) resets saved layout state.

- The curses selector does not work well on some Windows terminals; in that case the fallback prompt is used.

- The UI relies on modern browser features such as `MutationObserver`, SVG, and `localStorage`; very old browsers may not render or persist the workspace correctly.

- If you want to share this project with another user, share the project folder (script + templates), not your generated HTML file, because it embeds your pending tasks.

## Support

If you find this tool helpful, any support will be greatly appreciated.

You can do so [here](https://buymeacoffee.com/catanadj). Thank you.
