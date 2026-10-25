import os


# ---------------------------------------------------------------------------
# Structure tables
#
# A project's "structure" (saved per project as the `project_structure`
# setting) picks which features, extra top-level folders and software are
# enabled. Passing structure=None anywhere means everything is enabled.
# ---------------------------------------------------------------------------

# Always created, whatever the structure.
ESSENTIAL_DIRS = ['mazehub', 'pipeline', 'pipeline/OCIO']

NEW_ASSET_CATEGORY_LIST = ['char',
                           'env',
                           'prop',
                           'misc'
                           ]

FEATURES = {
    'shots': {'label': 'Shots', 'dirs': ['sequence']},
    'assets': {'label': 'Assets',
               'dirs': ['asset'] + [f'asset/{c}' for c in NEW_ASSET_CATEGORY_LIST]},
    'lightrigs': {'label': 'Light Rigs', 'dirs': ['lightrigs']},
    'production': {'label': 'Production Tracking', 'dirs': []},
}

EXTRA_FOLDERS = {
    'onset': {'label': 'Onset', 'dirs': ['onset']},
    'development': {'label': 'Development',
                    'dirs': ['development', 'development/storyboard',
                             'development/concept', 'development/reference']},
    'rnd': {'label': 'R&D', 'dirs': ['rnd']},
    'IO': {'label': 'IO', 'dirs': ['IO', 'IO/incoming', 'IO/outgoing']},
    'MISC': {'label': 'MISC', 'dirs': ['MISC']},
    'DB': {'label': 'DB', 'dirs': ['DB', 'DB/Resolve']},
}

# Per software: shot/asset working folders, light rig folders, project
# pipeline skeleton folders, and the apps.json keys it controls.
SOFTWARE = {
    'blender': {'label': 'Blender',
                'work': ['blender', 'blender/blend', 'blender/render', 'blender/assets',
                         'blender/cache', 'blender/texture', 'blender/USD'],
                'lightrig': [], 'pipeline': ['pipeline/Blender/scripts'], 'apps': ['Blender']},
    'houdini': {'label': 'Houdini',
                'work': ['houdini', 'houdini/hip', 'houdini/geo', 'houdini/render',
                         'houdini/USD', 'houdini/tex', 'houdini/export'],
                'lightrig': ['houdini', 'houdini/hip', 'houdini/geo', 'houdini/render',
                             'houdini/USD', 'houdini/tex'],
                'pipeline': ['pipeline/Houdini', 'pipeline/Houdini/Packages'],
                'apps': ['Houdini', 'USD']},
    'mari': {'label': 'Mari', 'work': ['mari'], 'lightrig': [], 'pipeline': [], 'apps': ['Mari']},
    'maya': {'label': 'Maya',
             'work': ['maya', 'maya/scenes', 'maya/assets', 'maya/cache', 'maya/images', 'maya/USD'],
             'lightrig': [], 'pipeline': ['pipeline/Maya/scripts'], 'apps': ['Maya']},
    'nuke': {'label': 'Nuke',
             'work': ['nuke', 'nuke/script', 'nuke/render', 'nuke/geo'],
             'lightrig': ['nuke', 'nuke/script', 'nuke/render', 'nuke/geo'],
             'pipeline': ['pipeline/Nuke/plugins'], 'apps': ['NukeX']},
    'photoshop': {'label': 'Photoshop',
                  'work': ['photoshop', 'photoshop/psd', 'photoshop/import',
                           'photoshop/export', 'photoshop/brush'],
                  'lightrig': [], 'pipeline': [], 'apps': ['Photoshop']},
    'postshot': {'label': 'Postshot', 'work': ['postshot'], 'lightrig': [], 'pipeline': [], 'apps': []},
    'ptgui': {'label': 'PTGui', 'work': ['ptgui'],
              'lightrig': ['ptgui', 'ptgui/project', 'ptgui/panorama'], 'pipeline': [], 'apps': []},
    'syntheyes': {'label': 'SynthEyes', 'work': ['syntheyes'], 'lightrig': [], 'pipeline': [], 'apps': []},
    'silhouette': {'label': 'Silhouette',
                   'work': ['silhouette', 'silhouette/project', 'silhouette/annotations',
                            'silhouette/module'],
                   'lightrig': [], 'pipeline': [], 'apps': []},
    'substance': {'label': 'Substance',
                  'work': ['substance', 'substance/spp', 'substance/textures',
                           'substance/export', 'substance/USD'],
                  'lightrig': [], 'pipeline': ['pipeline/Substance'], 'apps': ['SubstancePainter']},
    'zbrush': {'label': 'ZBrush',
               'work': ['zbrush', 'zbrush/ztl', 'zbrush/export', 'zbrush/export/maps',
                        'zbrush/export/obj', 'zbrush/export/fbx'],
               'lightrig': [], 'pipeline': [], 'apps': ['Zbrush']},
}

# Working / light rig folders created regardless of software.
COMMON_WORK = ['input', 'input/plates', 'MISC', 'reference']
COMMON_LIGHT_RIG = ['hdri', 'photogrammetry', 'usd_scene', 'input']


def default_structure():
    return {
        'features': {k: True for k in FEATURES},
        'folders': {k: True for k in EXTRA_FOLDERS},
        'software': list(SOFTWARE),
    }


def normalize_structure(cfg):
    """Fill missing entries with defaults (everything enabled)."""
    result = default_structure()
    if not isinstance(cfg, dict):
        return result
    for section in ('features', 'folders'):
        values = cfg.get(section)
        if isinstance(values, dict):
            for key in result[section]:
                if key in values:
                    result[section][key] = bool(values[key])
    software = cfg.get('software')
    if isinstance(software, list):
        result['software'] = [s for s in SOFTWARE if s in software]
    return result


def _enabled_software(structure):
    return normalize_structure(structure)['software'] if structure is not None else list(SOFTWARE)


def project_directories(structure=None):
    s = normalize_structure(structure)
    dirs = list(ESSENTIAL_DIRS)
    for key, feature in FEATURES.items():
        if s['features'][key]:
            dirs += feature['dirs']
    for key, folder in EXTRA_FOLDERS.items():
        if s['folders'][key]:
            dirs += folder['dirs']
    for sw in s['software']:
        dirs += SOFTWARE[sw]['pipeline']
    return dirs


def working_directories(structure=None):
    dirs = []
    for sw in _enabled_software(structure):
        dirs += SOFTWARE[sw]['work']
    return dirs + COMMON_WORK


def light_rig_directories(structure=None):
    dirs = list(COMMON_LIGHT_RIG)
    for sw in _enabled_software(structure):
        dirs += SOFTWARE[sw]['lightrig']
    return dirs


def app_enabled(app_key, structure=None):
    """False only for apps.json keys owned by a software that is disabled."""
    enabled = _enabled_software(structure)
    for sw, info in SOFTWARE.items():
        if app_key in info['apps']:
            return sw in enabled
    return True


def feature_enabled(feature, structure=None):
    return normalize_structure(structure)['features'].get(feature, True)


# Full (everything enabled) lists, kept for existing imports.
NEW_PROJECT_DIRECTORY = project_directories()
NEW_WORKING_DIRECTORY = working_directories()
NEW_LIGHT_RIG_DIRECTORY = light_rig_directories()

NEW_SHOT_LIST = ['_empty_shot_']

NEW_SHOOT_DAY_LIST = ['_empty_shoot_yyyy-mm-dd_']

NEW_ASSET_LIST = ['_empty_asset_']

NEW_SHOOT_DAY_DIRECTORY = ['backup',
                           'asset',
                           'shot',
                           'lensgrid',
                           'grainref',
                           'reference',

                           'shot/_empty_shot_',
                           'shot/_empty_shot_/hdri',
                           'shot/_empty_shot_/footage'
                           ]


def _make_dirs(base, rel_dirs, created=None, root=None):
    for single_directory in rel_dirs:
        path = os.path.join(base, single_directory)
        if not os.path.exists(path):
            os.makedirs(path)
            if created is not None:
                created.append(os.path.relpath(path, root or base))


def initialize_project(project_path, structure=None):
    """Create the project directory structure under project_path.

    Only the folders enabled in structure are created (None = all).
    """
    if project_path:
        _make_dirs(project_path, project_directories(structure))


def make_project(project='', root_dir='', seed=True, structure=None):
    """Create a complete project with all standard directory structures.

    Args:
        project: Name of the project to create (e.g., 'MAZE').
        root_dir: Root directory where the project folder should be created.
        seed: If True, also create the empty shot/asset/shoot-day scaffolds
              for the enabled features.
        structure: Project structure dict (None = everything enabled).
    """

    if project and root_dir:
        s = normalize_structure(structure)

        # Make the main Project Directory
        project_dir = os.path.join(root_dir, project)
        if not os.path.exists(project_dir):
            os.makedirs(project_dir)

        # Make the top level directories
        _make_dirs(project_dir, project_directories(s))

        if not seed:
            return

        if s['features']['shots']:
            for single_directory in NEW_SHOT_LIST:
                construct_shot_path = os.path.join(project_dir, 'sequence', single_directory)
                make_working_directory(construct_shot_path, s)

        if s['features']['assets']:
            for single_directory in NEW_ASSET_LIST:
                construct_asset_path = os.path.join(project_dir, 'asset', single_directory)
                make_working_directory(construct_asset_path, s)

        if s['folders']['onset']:
            for single_directory in NEW_SHOOT_DAY_LIST:
                construct_shoot_day_path = os.path.join(project_dir, 'onset', single_directory)
                if not os.path.exists(construct_shoot_day_path):
                    os.makedirs(construct_shoot_day_path)
                make_shoot_directory(construct_shoot_day_path)


def make_working_directory(path, structure=None):
    """Create the working directory structure for an asset or shot.

    Args:
        path: Path to the asset or shot directory where working folders should be created.
        structure: Project structure dict; only enabled software folders are created.

    Returns Exception if the directory already exists (prints message and returns early).
    """
    if not os.path.exists(path):
        os.makedirs(path)
    else:
        print(f"Directory already exists: {path}")
        return Exception("Directory already exists")

    if path:
        _make_dirs(path, working_directories(structure))


def repair_project_structure(project_root, structure=None):
    """Create any missing folders for the enabled parts of the structure.

    Never deletes anything. Returns the created paths relative to project_root.
    """
    s = normalize_structure(structure)
    root = str(project_root)
    missing = []
    _make_dirs(root, project_directories(s), missing)
    work_dirs = working_directories(s)

    asset_root = os.path.join(root, 'asset')
    if s['features']['assets'] and os.path.isdir(asset_root):
        for category in os.listdir(asset_root):
            cat_path = os.path.join(asset_root, category)
            if os.path.isdir(cat_path):
                for name in os.listdir(cat_path):
                    asset_path = os.path.join(cat_path, name)
                    if os.path.isdir(asset_path):
                        _make_dirs(asset_path, work_dirs, missing, root)

    seq_path = os.path.join(root, 'sequence')
    if s['features']['shots'] and os.path.isdir(seq_path):
        for name in os.listdir(seq_path):
            shot_path = os.path.join(seq_path, name)
            if os.path.isdir(shot_path):
                _make_dirs(shot_path, work_dirs, missing, root)

    lightrigs_path = os.path.join(root, 'lightrigs')
    if s['features']['lightrigs'] and os.path.isdir(lightrigs_path):
        rig_dirs = light_rig_directories(s)
        for name in os.listdir(lightrigs_path):
            rig_path = os.path.join(lightrigs_path, name)
            if os.path.isdir(rig_path):
                _make_dirs(rig_path, rig_dirs, missing, root)

    return missing


def make_shoot_directory(path):
    """Create standard shoot day directory structure for onset data.

    Args:
        path: Path to the shoot day directory where shoot folders should be created.

    Creates all directories listed in NEW_SHOOT_DAY_DIRECTORY under the given path.
    """
    if path:
        _make_dirs(path, NEW_SHOOT_DAY_DIRECTORY)


def make_light_rig_directory(path, structure=None):
    """Create directory structure for a light rig.

    Args:
        path: Path to the light rig directory where subfolders should be created.
        structure: Project structure dict; only enabled software folders are created.

    Returns Exception if the directory already exists.
    """
    if not os.path.exists(path):
        os.makedirs(path)
    else:
        print(f"Directory already exists: {path}")
        return Exception("Directory already exists")

    if path:
        _make_dirs(path, light_rig_directories(structure))
