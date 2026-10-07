# MazeHub

MazeHub is a VFX pipeline management tool built with PySide6. It launches DCC applications (Maya, Houdini, Nuke, Blender, etc.) with the correct project context, environment variables, and timeline settings.

## Requirements

- Python 3.12+
- PySide6 6.6+
- PyInstaller 6.21+ (for building the exe)

## Structure

MazeHub separates the **install** (app + pipeline tools) from **projects**
(data folders). The install can live anywhere (e.g. `C:\Tools\MazeHub`);
projects can live anywhere else (OneDrive, NAS, local disk).

### Install folder

```
MazeHub/                  # wherever you extracted the release zip
  MazeHub.exe
  launch_mazehub.bat
  mazehub/                # app code + config
    apps.json             # DCC app configurations
    styles.qss            # UI stylesheet
    icon.svg              # App icon
    make_folders.py       # Folder structure creator
  Blender/                # DCC launchers and scripts
  Houdini21.0/
  Mari/
  Maya/
  Nuke/
  OCIO/
  Photoshop/
  Substance/
  Zbrush/
```

### Project folder (data only)

```
project_root/
  asset/                  # Asset directories (char/env/prop/misc)
  development/            # Storyboards, concepts, references
  IO/                     # Incoming/outgoing files
  lightrigs/
  MISC/
  mazehub/                # Per-project shared settings
    shared_settings.json
  onset/
  pipeline/               # Empty skeleton for project-specific plugins/tools
  rnd/
  sequence/               # Shot directories
```

Projects contain **data only** by default — pipeline tools always come from
the install folder. MazeHub creates an empty `pipeline/` skeleton when a
project is created or repaired; it stays empty until you add your own extras
(project wins over the install, see [Projects](#projects)), and MazeHub never
deletes it. Legacy projects that still contain a full `pipeline/` copy are
treated the same way — their stale files now shadow the install, so trim such
a folder down to the extras you actually override, or delete it.

## Installation

### From source

```bash
pip install -r requirements.txt
# or
uv sync
```

### As an installed app

1. Extract `MazeHub-pipeline.zip` (or copy the `publish/pipeline/` folder)
   anywhere, e.g. `C:\Tools\MazeHub`.
2. Create a shortcut to `MazeHub.exe` (optionally add `--project <path>`).
3. On first launch choose **Add Existing Folder…** and point MazeHub at your
   project — or create a new one in Settings → Projects.

## Projects

An install can open any number of projects. Registered projects and the
active project are stored with the install in
`<install>/mazehub/projects.json`, so every device that opens the same
install shares one project list.

- **Sidebar switcher** — the project name at the top of the sidebar switches
  projects live: all pages reload against the new project. Switching is
  blocked while an update is running or an app launch/render is in flight.
- **Settings → Projects** — list all registered projects. **Open**
  (or double-click) switches, **Add Existing…** registers a folder,
  **Create New…** builds a data-only project (optional sample shot/asset/
  shoot-day scaffolds) and opens it, **Remove** unregisters a project
  (the folder itself is never deleted).
- **CLI override** — `MazeHub.exe --project D:\work\MyProject` (or
  `python main.py --project ...`) opens that project for the session only;
  the stored active project is unchanged. The `MAZE_PROJECT_ROOT`
  environment variable has the same effect.

Resolution order: `--project` flag → `MAZE_PROJECT_ROOT` → active project
in the registry → first-launch folder picker.

### Project pipeline (optional)

A project can ship its own plugins and tools in `<project>/pipeline/`,
mirroring the install layout:

- `pipeline/Houdini/` (+ `Packages/`) — Houdini scripts and packages
- `pipeline/Maya/scripts/` (+ `123.py` entry) — Maya scripts
- `pipeline/Nuke/plugins/` — Nuke plugins
- `pipeline/Blender/scripts/` (+ `startup.py`) — Blender scripts
- `pipeline/Substance/` — Substance Painter plugins
- `pipeline/OCIO/` — `OCIO_set.bat` or `BU_nov2024_config.ocio` config override

When MazeHub launches an app, every search path lists the **project folder
first, then the install folder**, so a project file overrides the same file
in the main pipeline. A project OCIO config replaces the studio one. Only
scripts/plugins/configs are overlaid — executables, launcher scripts and
binaries always come from the install. The folder is optional; when present
`MAZE_PROJECT_PIPELINE` points at it, otherwise the variable is empty and
behaviour is identical to a plain project.

## Usage

### Running from Source

```bash
python main.py
# or
launch_mazehub.bat
```

### Building the Exe

```bash
build.bat
```

This creates `dist/MazeHub.exe`. The exe bundles Python, PySide6, and all app code. Pipeline data (DCC scripts, configs) lives on disk next to the exe.

### Publishing a Deployable Bundle

```bash
publish_pipeline.bat
# or with a target directory
python publish_pipeline.py --target /path/to/deploy
# or build release assets for GitHub
python publish_pipeline.py --zip
```

This creates a deployable bundle in `publish/pipeline/`:

```
publish/pipeline/
  MazeHub.exe
  launch_mazehub.bat
  mazehub/
    apps.json
    styles.qss
    icon.svg
    make_folders.py
  Blender/
  Houdini21.0/
  Maya/
  Nuke/
  ...
```

No Python source files are included in the published bundle. With `--zip`,
`publish/MazeHub-pipeline.zip` and `publish/manifest.json` are also produced
(release assets used by the self-updater).

`--target` syncs manifest-aware instead of overwriting the destination: local
edits and user data (see below) are preserved, only changed files are copied.

## Self-Update

MazeHub updates itself from GitHub Releases (`KingDodaco/mazehub_ai`):

1. On launch (frozen exe only) it silently checks `releases/latest`.
2. If a newer version exists you get an **Update & Restart** prompt.
3. The zip is downloaded, checksum-verified, and staged outside the install.
4. Data files are synced into place; the exe is swapped by a helper script
   that waits for MazeHub to exit, renames the old exe, moves the new one in,
   relaunches, and rolls back automatically if the new exe fails to start.

### Releases

CI creates a GitHub Release tagged `v{version}` when `pyproject.toml` /
`APP_VERSION` change (no release is created on pushes without a version
bump). Assets: `MazeHub-pipeline.zip` + `manifest.json` (file list with
SHA-256 hashes).

### What is preserved

- Files never shipped in a release are **never touched or deleted**:
  `mazehub/shared_settings.json`, and any file an artist adds to the
  install folder.
- Shipped files that were edited locally are kept, with the incoming version
  saved next to them as `<file>.new`.
- `apps.json` is three-way merged: your `versions`, `default_version`, and
  exe-path edits survive; new apps/fields from the release are added; apps
  you added are kept. Conflicts are reported (local value wins).
- Removed-from-source files are deleted on update; if locally edited first
  they are moved to `.update/trash/` instead.
- Projects are outside the install folder and are never touched by updates.
  Recent files live with the project (`<project>/mazehub/`); app versions
  and global settings live in the install folder (`<install>/mazehub/`).

### Settings

Settings → Updates: current version, auto-check toggle, manual
**Check for Updates**, and an optional `update_channel` (a folder or URL
containing `manifest.json` + `MazeHub-pipeline.zip`, for testing or an
offline channel — blank means GitHub releases).

## GUI Pages

### Home

Dashboard showing project info and quick launch buttons for each DCC application.

### Launch Apps

Launch any configured DCC application. If a shot or asset context is selected, the app opens with the correct project settings, timeline, and environment variables.

### Shot Explorer

Browse existing shots and create new ones. Each shot stores metadata (frame range, frame rate, description) in a `_metadata.json` file.

### Asset Explorer

Browse existing assets organized by category. Create new assets with automatic folder structure generation.

### Env Vars

View all environment variables set by MazeHub for the current project and context.

### Settings

Manage projects (open/add/create/remove), repair file structure, app
versions, webhook URLs, and updates.

## Environment Variables

MazeHub sets the following environment variables when launched:

| Variable | Description |
|----------|-------------|
| `MAZE_PROJECT_ROOT` | Root directory of the project |
| `MZE` | Alias for `MAZE_PROJECT_ROOT` |
| `MAZE_PROJECT` | Project folder name |
| `MAZE_PIPELINE` | Path to the install folder's pipeline tools (not inside the project) |
| `MAZE_PROJECT_PIPELINE` | Path to the project's `pipeline/` folder (empty skeleton by default), or empty if none |
| `MAZE_ASSETS` | Path to the asset directory |
| `MAZE_SEQUENCES` | Path to the sequence directory |
| `MAZE_ONSET` | Path to the onset directory |
| `MAZE_IO` | Path to the IO directory |
| `MAZE_DEVELOPMENT` | Path to the development directory |
| `MAZE_RND` | Path to the RND directory |
| `MAZE_MISC` | Path to the MISC directory |

When launching a DCC app with a context, additional variables are set:

| Variable | Description |
|----------|-------------|
| `MAZE_CONTEXT_TYPE` | `shot` or `asset` |
| `MAZE_CONTEXT_NAME` | Name of the shot or asset |
| `MAZE_CONTEXT_PATH` | Full path to the context directory |
| `START_FRAME` | Start frame (shots only) |
| `END_FRAME` | End frame (shots only) |
| `FRAME_RATE` | Frame rate (shots only) |

## DCC Application Launchers

Each DCC app has a `.bat` launcher that:

1. Sets project-specific environment variables
2. Configures OCIO color management (install config, then optional project override)
3. Opens a file if one was selected (from file browser or recent files)
4. Runs a startup script to configure the timeline

Script/plugin search paths are built project-first
(`<project>/pipeline/...` before `<install>/pipeline/...`) — see
[Projects](#projects).

### Supported Applications

| App | Launcher | Startup Script |
|-----|----------|----------------|
| Maya | `MAZE_Maya.bat` | `scripts/123.py` |
| Houdini | `MAZE_Houdini_21.0.bat` | `scripts/123.py` |
| NukeX | `MAZE_NukeX.bat` | - |
| Blender | `MAZE_Blender.bat` | `scripts/startup.py` |
| Mari | `MAZE_Mari.bat` | - |
| Substance Painter | `MAZE_SubstancePainter.bat` | - |
| Photoshop | `MAZE_Photoshop.bat` | - |
| ZBrush | `MAZE_Zbrush.bat` | - |

## File Browser

The file browser shows project files organized by shot or asset. Double-clicking a file opens it in the appropriate DCC application with the correct context.

Supported file extensions are defined in `pipeline_app.py` (`APP_FILE_EXTENSIONS`).

## Recent Files

The recent files panel tracks recently opened files with:
- File name and full path
- Context (shot or asset name)
- Application name
- Timestamp

Recent files are stored per project in
`<project>/mazehub/recent_files_<user>.json` (they follow the active
project when you switch). With no project active they fall back to
`<install>/mazehub/recent_files_<user>.json`. Files from the legacy
`<project>/pipeline/mazehub/` location and from the old
`~/.config/mazehub/recent_files.json` fallback are migrated automatically.

## Building

### Build the Exe

```bash
build.bat
```

Output: `dist/MazeHub.exe`

### Publish for Deployment

```bash
publish_pipeline.bat
```

Output: `publish/pipeline/` (ready to copy to target machines)

### Options

- `--target <path>`: Copy the published bundle to an additional location
- `--no-exe`: Publish pipeline data only (skip copying the exe)

## Cleanup

```bash
python cleanup.py
```

Removes build artifacts: `build/`, `dist/`, `*.spec`, and `__pycache__/` directories.

## Configuration

### apps.json

Configure DCC applications in `<install>/mazehub/apps.json`:

```json
{
    "AppName": {
        "display_name": "Display Name",
        "executable": "MAZE_AppName.bat",
        "subdir": "AppDir",
        "appsanywhere": true
    }
}
```

### styles.qss

Customize the UI appearance by editing `<install>/mazehub/styles.qss`. The
stylesheet uses Qt's CSS syntax.

### Shared settings

Webhook URLs, husk path, and other per-project settings shared between
machines live in `<project>/mazehub/shared_settings.json`. Projects that
still store it at `<project>/pipeline/mazehub/shared_settings.json` are
migrated automatically on first load (the legacy file is left in place).

### Install config (`<install>/mazehub/`)

Global (non-project) settings live with the install, so every device that
can see the install sees the same configuration — including on a local
network share. Files from the legacy `~/.config/mazehub/` location are
migrated on first run (the legacy copy is left in place; the first device
to run wins, so all devices converge on the install copies). Set
`MAZE_CONFIG_DIR` to redirect this folder (used by the test suites).

| File | Contents |
|------|----------|
| `projects.json` | Registered projects and the active project |
| `user_settings.json` | Global settings (update channel, husk path, toggles) |
| `app_versions_<user>.json` | Last-used app versions |
| `recent_files_<user>.json` | Recent files fallback (no active project) |
