import os
from pathlib import Path


ROOT_DIR = 'C:/Users/s5720563/OneDrive - Bournemouth University/FMP - Documents/PROJECT'

NEW_PROJECT_DIRECTORY = ['asset',
                         'pipeline',
                         'onset',
                         'development',
                         'sequence',
                         'rnd',
                         'IO',
                         'MISC',

                         'pipeline/Houdini21.0',
                         'pipeline/Nuke',
                         'pipeline/Maya',
                         'pipeline/Blender',
                         'pipeline/OCIO',
                         'pipeline/Substance',
                         'pipeline/Substance/plugins',

                         'IO/incoming',
                         'IO/outgoing',

                         'development/storyboard',
                         'development/concept',
                         'development/reference',

                         'asset/char',
                         'asset/env',
                         'asset/prop',
                         'asset/misc'
                         ]
                         
NEW_SHOT_LIST = ['_empty_shot_']

NEW_SHOOT_DAY_LIST = ['_empty_shoot_yyyy-mm-dd_']

NEW_ASSET_CATEGORY_LIST = ['char',
                           'env',
                           'prop',
                           'misc'
                           ]

NEW_ASSET_LIST = ['_empty_asset_']

NEW_WORKING_DIRECTORY = ['blender',
                     'blender/blend',
                     'blender/render',
                     'blender/assets',
                     'blender/cache',
                     'blender/texture',
                     'blender/USD',
                     
                     'houdini',
                     'houdini/hip',
                     'houdini/geo',
                     'houdini/render',
                     'houdini/USD',
                     'houdini/tex',
                     
                     'mari',

                     'maya',
                     'maya/scenes',
                     'maya/assets',
                     'maya/cache',
                     'maya/images',
                     'maya/USD',

                     'MISC',

                     'nuke',
                     'nuke/script',
                     'nuke/render',
                     'nuke/geo',

                     'photoshop',
                     'photoshop/psd',
                     'photoshop/import',
                     'photoshop/export',
                     'photoshop/brush',

                     'postshot',

                     'ptgui',

                     'reference',

                     'syntheyes',

                     'silhouette',
                     'silhouette/project',
                     'silhouette/annotations',
                     'silhouette/module',

                     'substance',
                     'substance/spp',
                     'substance/textures',
                     'substance/export',
                     'substance/USD',
                    

                     'zbrush',
                     'zbrush/ztl',
                     'zbrush/export',
                     'zbrush/export/maps',
                     'zbrush/export/obj',
                     'zbrush/export/fbx'
                     ]

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


def initialize_project(project_path):
    """Create the standard project directory structure.
    
    Args:
        project_path: Root path where the project directories should be created.
                      Should be the PROJECT_DIR (e.g., /path/to/PROJECT).
                      
    Creates all directories listed in NEW_PROJECT_DIRECTORY under the given path.
    """
    if project_path:
        for single_directory in NEW_PROJECT_DIRECTORY:
            construct_subscope_path = os.path.join(project_path, single_directory)
            if not os.path.exists(construct_subscope_path):
                os.makedirs(construct_subscope_path)


def make_project(project='', root_dir=''):
    """Create a complete project with all standard directory structures.
    
    Args:
        project: Name of the project to create (e.g., 'MAZE').
        root_dir: Root directory where the project folder should be created.
        
    Creates:
        - Main project directory at root_dir/project
        - All top-level directories from NEW_PROJECT_DIRECTORY
        - Shot directories under sequence/ with working directory structure
        - Asset directories under asset/ with working directory structure
        - Onset/shoot day directories with shoot directory structure
    """

    if project and root_dir:
        
        # Make the main Project Directory
        project_dir = os.path.join(root_dir, project)
        if not os.path.exists(project_dir):
            os.makedirs(project_dir)

        # Make the top level directories
        for single_directory in NEW_PROJECT_DIRECTORY:
            construct_subscope_path = os.path.join(project_dir, single_directory)
            if not os.path.exists(construct_subscope_path):
                os.makedirs(construct_subscope_path)

        # Make the shot directories
        for single_directory in NEW_SHOT_LIST:
            construct_shot_path = os.path.join(project_dir,'sequence', single_directory)
            make_working_directory(construct_shot_path)

        # Make the asset directories
        for single_directory in NEW_ASSET_LIST:
            construct_asset_path = os.path.join(project_dir,'asset',single_directory)
            make_working_directory(construct_asset_path)

        # Make onset directories
        for single_directory in NEW_SHOOT_DAY_LIST:
            construct_shoot_day_path = os.path.join(project_dir,'onset', single_directory)
            if not os.path.exists(construct_shoot_day_path):
                os.makedirs(construct_shoot_day_path)
            make_shoot_directory(construct_shoot_day_path)


def make_working_directory(path):
    """Create standard working directory structure for an asset or shot.
    
    Args:
        path: Path to the asset or shot directory where working folders should be created.
        
    Creates all directories listed in NEW_WORKING_DIRECTORY under the given path.
    Returns Exception if the directory already exists (prints message and returns early).
    """
    if not os.path.exists(path):
        os.makedirs(path)
    else:
        print(f"Directory already exists: {path}")
        return Exception("Directory already exists")

    if path:
        for single_directory in NEW_WORKING_DIRECTORY:
            construct_subscope_path = os.path.join(path, single_directory)
            if not os.path.exists(construct_subscope_path):
                os.makedirs(construct_subscope_path)


def repair_project_structure(project_root):
    missing = []
    root = str(project_root)
    for single_directory in NEW_PROJECT_DIRECTORY:
        path = os.path.join(root, single_directory)
        if not os.path.exists(path):
            os.makedirs(path)
            missing.append(single_directory)

    for category in os.listdir(os.path.join(root, 'asset')):
        cat_path = os.path.join(root, 'asset', category)
        if os.path.isdir(cat_path):
            for name in os.listdir(cat_path):
                asset_path = os.path.join(cat_path, name)
                if os.path.isdir(asset_path):
                    for subdir in NEW_WORKING_DIRECTORY:
                        sub_path = os.path.join(asset_path, subdir)
                        if not os.path.exists(sub_path):
                            os.makedirs(sub_path)
                            missing.append(os.path.relpath(sub_path, root))

    seq_path = os.path.join(root, 'sequence')
    if os.path.exists(seq_path):
        for name in os.listdir(seq_path):
            shot_path = os.path.join(seq_path, name)
            if os.path.isdir(shot_path):
                for subdir in NEW_WORKING_DIRECTORY:
                    sub_path = os.path.join(shot_path, subdir)
                    if not os.path.exists(sub_path):
                        os.makedirs(sub_path)
                        missing.append(os.path.relpath(sub_path, root))

    return missing


def make_shoot_directory(path):
    """Create standard shoot day directory structure for onset data.
    
    Args:
        path: Path to the shoot day directory where shoot folders should be created.
        
    Creates all directories listed in NEW_SHOOT_DAY_DIRECTORY under the given path.
    """
    if path:
        for single_directory in NEW_SHOOT_DAY_DIRECTORY:
            construct_subscope_path = os.path.join(path, single_directory)
            if not os.path.exists(construct_subscope_path):
                os.makedirs(construct_subscope_path)


# make_project('MAZE', ROOT_DIR)
