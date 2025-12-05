# TaskCanvas

A visual dependency **canvas** and command generator for Taskwarrior.

TaskCanvas loads your pending Taskwarrior tasks, builds a dependency graph, and opens a single HTML file where you can drag tasks around, wire dependencies, and stage changes. Every action becomes plain task commands that you copy-paste back into your terminal  -  the HTML never touches your Taskwarrior data directly.

---

## What it does

TaskCanvas is a single-file Python 3 script that:

- Calls task status:pending export (or a custom filter) to fetch your tasks.

- Builds a JSON payload with tasks (uuid, short id, description, project, tags, dependencies, due) and a dependency edge list.

- Injects that payload into a self-contained HTML/JS UI (TaskCanvas.html) in the current working directory.

- Opens the HTML in your default browser (Termux, Linux, macOS, Windows are handled).

Inside the browser you get an interactive canvas where you can:

- Drag projects, tags, and tasks around.

- Draw or remove dependency lines.

- Stage Done/Delete/Modify actions via hover buttons.

- Add new tasks and projects.

- Copy all staged changes as Taskwarrior commands.

---

## Features

Visual canvas for Taskwarrior

- All pending tasks are loaded into a searchable drawer and a canvas.

- Tasks are displayed as draggable cards with a short ID, description, project and tags.

- Dependencies are visualised as SVG lines with animated “energy” pulses flowing along the chain.

Builder & Viewer tabs

- **Builder**: full editing canvas where you place tasks, project/tag “bubbles”, and wire dependencies.

- **Viewer**: a compact read-only overview of dependency chains (grouped by project) for quick inspection. (Feature is not complete.)

Command console (copy-only)

- Every change you stage becomes a task command (modify/add/done/delete/depends +/-) in a console area.

- Commands are de-duplicated and normalised so each final line is safe to paste.

- A dedicated **dependency console overlay** is available, with a keyboard shortcut wired via Ctrl+Shift+D.

Hover actions & staging

- Hovering a task card reveals small buttons (e.g. mark Done / Delete / Modify), implemented via a nodeActions overlay.

- Staged tasks are visually highlighted (green for Done, red for Delete) with line-through titles.

Dependencies that _feel_ alive

- Existing dependency edges are rendered as smooth cubic curves with arrowheads; staged ones use animated dashed strokes.

- Pulses running along the edges help you see direction and chain flow.

- Staged vs existing edges are colour-split (blue vs pink/red) so it’s obvious what’s already in Taskwarrior vs what you’re planning.

- A robust “follow edges on move” patch keeps lines glued to tasks while you drag them around.

Actionable beacons & due badges

- Tasks that participate in dependency chains but have no remaining prerequisites get a subtle “actionable” beacon, helping you see where you can actually start.

- Due dates (when present) are shown as a small badge with visual states for overdue / soon / future.

Multiline add & project creation

- Floating “plus” menu (FAB) for adding new tasks.

- Multiline add mode lets you paste several new tasks at once; each line becomes a separate task add.

- The FAB menu is patched so you can also create **new projects** from the UI (“Add new project” button / modal).

Project selector (terminal) & auto-placement

- Optional curses-based project selector (--selector) with filtering, select all/none, paging, and a fallback text prompt if curses fails.

- Initial placement can be driven by positional project arguments and/or a Taskwarrior filter (-f/--filter).

- Filtered tasks (e.g. project:Work +P1) are automatically dropped onto the canvas while all other tasks remain available in the drawer.

Custom background

- You can give TaskCanvas a custom background image via --bg and --bg-opacity.

- If no flag is provided, it auto-searches for files like taskcanvas-bg.jpg/png/webp in the script directory or current working directory and uses them as a body overlay.

Termux & desktop friendly

- Output HTML is always TaskCanvas.html in the current directory.

- It is opened via termux-open on Termux, xdg-open on Linux, open on macOS, and os.startfile on Windows.

---

## Requirements

- Python **3.10+** (uses modern type-hint syntax like str | None).

- Taskwarrior installed and on your $PATH so the task command works.

- A reasonably modern browser (the UI is vanilla HTML/JS/SVG, no external JS dependencies). Chrome is recommended.

---

## Installation

Clone this repository somewhere convenient and make sure TaskCanvas.py is executable.

chmod +x TaskCanvas.py # or simply call it with python3

Optionally, add a small helper in your shell config:

alias twcanvas='python3 /path/to/TaskCanvas.py'

---

## Usage

### Basic

Generate and open a canvas of all **pending** tasks:
```
python3 TaskCanvas.py
```

This will:

1. Run a Taskwarrior export for status:pending.

2. Create TaskCanvas.html in the current directory.

3. Open that file in your browser.

### Auto-placing tasks by project

You can pass project names as positional arguments; tasks from those projects will be initially placed on the canvas:

```
python3 TaskCanvas.py Work Home side.hustle
```

The rest of your pending tasks remain available in the left-hand drawer for drag-and-drop.

### Auto-placing tasks via Taskwarrior filters

Use -f / --filter to provide any Taskwarrior filter expression; matching tasks will be auto-placed:

```
python3 TaskCanvas.py -f 'project:Work +P1' python3 TaskCanvas.py --filter 'due.before:2026-01-01 status:pending'
```

The filter is only used to choose which tasks to pre-place; **all** pending tasks still go into the drawer/search payload.

You can combine projects and a filter:

```
python3 TaskCanvas.py -f 'project:Work +P1' Home 'life.admin'
```

### Interactive project selector

If you don’t feel like typing project names, use the selector:

```
python3 TaskCanvas.py --selector
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
python3 TaskCanvas.py --bg /path/to/image.jpg python3 TaskCanvas.py --bg=mywall.png --bg-opacity=0.12
```

TaskCanvas will copy the image next to TaskCanvas.html (same directory) and inject a body::before overlay with the given opacity (default ≈ 0.18).

Without --bg, it tries to locate a file named like taskcanvas-bg.*, canvas-bg.*, background.* or bg.* in either the script directory or current working directory.

---

## UI overview

### Builder tab

- **Left drawer**
    Search/filter tasks, drag them into the canvas by dropping onto project/tag areas or directly into space.

- **Canvas**

    - Drag tasks, projects, and tags around freely.

    - Draw dependencies by starting from a handle on one task and dragging to another.

    - Use “remove mode” to easily click edges and remove/stage dependency removals.

    - Animated pulses and coloured lines distinguish existing vs staged dependency relationships.

- **Hover actions**

    - Hover over a task to reveal a small action bar: Done / Delete / Modify etc.

    - Toggling these stages corresponding commands and visually marks the task.

- **FAB (floating button)**

    - Add new tasks (single or multiline).

    - Add new projects via a modal, wired in through a small patch that repurposes/extends the FAB menu.

- **Console(s)**

    - Primary console at the bottom collects all staged commands.

    - A dependency-focused overlay console can be toggled via Ctrl+Shift+D.

### Viewer tab (not fully baked functionality)

- Read-only view of dependency chains:

    - Tasks grouped by project.

    - Only tasks that participate in dependencies are shown.

    - Helps you reason about chains without the clutter of the full canvas.

---

## Workflow: from canvas back to Taskwarrior

1. Run TaskCanvas.py to generate/open the HTML.

2. Use the Builder tab to:

    - Drop tasks into the right project/tag buckets.

    - Draw or remove dependency edges.

    - Mark tasks done / deleted.

    - Add any new tasks you want to create.

3. Inspect the command console and copy the lines into your terminal.

4. Run those task commands in your usual environment.

TaskCanvas is deliberately **copy-only**: it never executes task mutations on your behalf; it only exports plus generates suggestions.

---

## Notes & limitations

- Layout is not persisted. Each run builds a fresh canvas from current Taskwarrior state; you can keep the HTML open as long as you like, but there is no save/load of positions yet.

- The curses selector does not work well on some Windows terminals; in that case the fallback prompt is used.

- The UI relies on modern browser features (MutationObserver, SVG path length, etc.); very old browsers may not render animations correctly.

- If you want to share this project with some other user, share the .py project not the html file because it has embeded your pending tasks.

## Support

If you find this tool helpful, any support will be greatly apreciated.

You can do so [here](https://buymeacoffee.com/catanadj). Thank you.
