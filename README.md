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

No Python source files are included in the published bundle.

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
