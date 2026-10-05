# MazeHub

MazeHub is a VFX pipeline management tool built with PySide6. It launches DCC applications (Maya, Houdini, Nuke, Blender, etc.) with the correct project context, environment variables, and timeline settings.

## Requirements

- Python 3.12+
- PySide6 6.6+
- PyInstaller 6.21+ (for building the exe)

## Project Structure

```
project_root/
  asset/                  # Asset directories
  development/            # Storyboards, concepts, references
  IO/                     # Incoming/outgoing files
  MISC/
  onset/
  pipeline/
    mazehub/              # MazeHub app files
      apps.json           # DCC app configurations
      styles.qss          # UI stylesheet
      icon.svg            # App icon
      make_folders.py     # Folder structure creator
    Blender/              # Blender launcher and scripts
    Houdini21.0/          # Houdini launcher and scripts
    Mari/                 # Mari launcher
    Maya/                 # Maya launcher and scripts
    Nuke/                 # Nuke launcher and plugins
    OCIO/                 # OCIO color config
    Photoshop/            # Photoshop launcher
    Substance/            # Substance Painter launcher
    Zbrush/               # ZBrush launcher
  rnd/
  sequence/               # Shot directories
```

## Installation

```bash
pip install -r requirements.txt
# or
uv sync
```

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
  `shared_settings.json`, `recent_files_*.json`, `app_versions_*.json`,
  and any file an artist adds to the pipeline folder.
- Shipped files that were edited locally are kept, with the incoming version
  saved next to them as `<file>.new`.
- `apps.json` is three-way merged: your `versions`, `default_version`, and
  exe-path edits survive; new apps/fields from the release are added; apps
  you added are kept. Conflicts are reported (local value wins).
- Removed-from-source files are deleted on update; if locally edited first
  they are moved to `.update/trash/` instead.

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

Repair file structure and configure project options.

## Environment Variables

MazeHub sets the following environment variables when launched:

| Variable | Description |
|----------|-------------|
| `MAZE_PROJECT_ROOT` | Root directory of the project |
| `MZE` | Alias for `MAZE_PROJECT_ROOT` |
| `MAZE_PROJECT` | Project folder name |
| `MAZE_PIPELINE` | Path to the pipeline directory |
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
2. Configures OCIO color management
3. Opens a file if one was selected (from file browser or recent files)
4. Runs a startup script to configure the timeline

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

Recent files are stored in `~/.config/mazehub/recent_files.json`.

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

Configure DCC applications in `pipeline/mazehub/apps.json`:

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

Customize the UI appearance by editing `pipeline/mazehub/styles.qss`. The stylesheet uses Qt's CSS syntax.
