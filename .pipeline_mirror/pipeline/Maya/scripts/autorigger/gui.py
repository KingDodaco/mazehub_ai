import maya.cmds as cmds
from . import autorigger
import importlib
import sys

WINDOW_NAME = "MAZE_Autorigger_UI"

rig = autorigger.Rig()

def show():
	"""Create and show the autorigger window."""
	if cmds.window(WINDOW_NAME, exists=True):
		cmds.deleteUI(WINDOW_NAME)
	win = cmds.window(WINDOW_NAME, title="MAZE Autorigger (from existing skeleton)", widthHeight=(480, 560))
	col = cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAlign="left")

	# side prefixes
	cmds.text(label="Side prefixes:")
	cmds.rowLayout(numberOfColumns=6, columnWidth6=(60,80,60,80,60,80))
	cmds.text(label="Center:")
	cmds.textField('maze_center_prefix', text='c_')
	cmds.text(label="Left:")
	cmds.textField('maze_left_prefix', text='l_')
	cmds.text(label="Right:")
	cmds.textField('maze_right_prefix', text='r_')
	cmds.setParent('..')

	# Spine joint names
	cmds.separator(height=6)
	cmds.text(label="Spine:")
	cmds.rowLayout(numberOfColumns=2)
	cmds.text(label="Pelvis:")
	cmds.textField('maze_pelvis', text='pelvis')
	cmds.setParent('..')

	cmds.rowLayout(numberOfColumns=2)
	cmds.text(label="Chest:")
	cmds.textField('maze_chest', text='chest')
	cmds.setParent('..')

	cmds.rowLayout(numberOfColumns=5, columnWidth3=(80,220,60))
	cmds.text(label="Spine:")
	cmds.textField('maze_spine', text='spine')
	cmds.setParent('..')

	# forelimb
	cmds.separator(height=6)

	cmds.text(label="Forelimb:")
	for name, default in (('scapula','scapula'), ('shoulder','humerus'), ('elbow','radius'), ('wrist','wrist')):
		cmds.rowLayout(numberOfColumns=2)
		cmds.text(label=name.capitalize() + ":")
		cmds.textField('maze_' + name, text=default)
		cmds.setParent('..')
		
	cmds.separator(height=6)
	cmds.text(label="Hindlimb:")
	for name, default in (('femur','femur'), ('tibia','tibia'), ('metatarsus','metatarsus'), ('foot','foot'), ('ankle','ankle')):
		cmds.rowLayout(numberOfColumns=2)
		cmds.text(label=name.capitalize() + ":")
		cmds.textField('maze_' + name, text=default)
		cmds.setParent('..')

	# tail
	cmds.separator(height=6)
	cmds.rowLayout(numberOfColumns=2)
	cmds.text(label="Tail base:")
	cmds.textField('maze_tail', text='tail')
	cmds.setParent('..')

    # head
	cmds.rowLayout(numberOfColumns=2)
	cmds.text(label="Head:")
	cmds.textField('maze_head', text='head')
	cmds.setParent('..')

	# neck
	cmds.rowLayout(numberOfColumns=2)
	cmds.text(label="Neck:")
	cmds.textField('maze_neck', text='neck')
	cmds.setParent('..')

	cmds.separator(height=8)
	# Initialize / Find / Clear mapping
	cmds.rowLayout(numberOfColumns=3, columnWidth3=(160,160,160))
	cmds.button(label='Initialize rig', height=30, command=lambda *args: _initialize_rig_groups())
	cmds.setParent('..')

	cmds.rowLayout(numberOfColumns=3, columnWidth3=(160,160,160))
	cmds.button(label='Orient joints', height=30, command=lambda *args: _orient_joints())
	cmds.setParent('..')
	
	#set skeleton rest position
	cmds.rowLayout(numberOfColumns=3, columnWidth3=(160,160,160))
	cmds.button(label='Set skeleton rest', height=30, command=lambda *args: _set_skeleton_rest())
	cmds.setParent('..')

	cmds.separator(height=6)
	# Create Rig button
	cmds.rowLayout(numberOfColumns=2, columnWidth2=(240,240))
	cmds.button(label='Create Rig', height=36, command=lambda *args: _create_rig())
	cmds.setParent('..')

	cmds.separator(height=8)
	# delete and reload
	cmds.rowLayout(numberOfColumns=3, columnWidth2=(240,240))
	cmds.button(label='Delete Rig', command=lambda *args: _delete_rig())
	cmds.button(label='Reset Skeleton rest', command=lambda *args: _reset_skeleton_rest())
	cmds.button(label='Reload modules (hot-reload)', command=lambda *args: reload_and_refresh())
	cmds.setParent('..')

	cmds.showWindow(win)

# small helpers to read fields
def _collect_joint_names_from_ui():
	return {
		'pelvis': cmds.textField('maze_pelvis', q=True, text=True),
		'chest': cmds.textField('maze_chest', q=True, text=True),
		'spine': cmds.textField('maze_spine', q=True, text=True),
		'scapula': cmds.textField('maze_scapula', q=True, text=True),
		'shoulder': cmds.textField('maze_shoulder', q=True, text=True),
		'elbow': cmds.textField('maze_elbow', q=True, text=True),
		'wrist': cmds.textField('maze_wrist', q=True, text=True),
		'femur': cmds.textField('maze_femur', q=True, text=True),
		'tibia': cmds.textField('maze_tibia', q=True, text=True),
		'metatarsus': cmds.textField('maze_metatarsus', q=True, text=True),
		'ankle': cmds.textField('maze_ankle', q=True, text=True),
		'foot': cmds.textField('maze_foot', q=True, text=True),
		'tail': cmds.textField('maze_tail', q=True, text=True),
		'head': cmds.textField('maze_head', q=True, text=True),
		'neck': cmds.textField('maze_neck', q=True, text=True),
	}

def _collect_side_prefixes_from_ui():
	return {
		'center': cmds.textField('maze_center_prefix', q=True, text=True),
		'left': cmds.textField('maze_left_prefix', q=True, text=True),
		'right': cmds.textField('maze_right_prefix', q=True, text=True),
	}

def _initialize_rig_groups():
	try:
		rig.initialize_rig_folders()
		cmds.inViewMessage(amg='Initialized rig groups: <hl>%s</hl>' % rig.main_group, pos='midCenter', fade=True)
	except Exception as e:
		cmds.warning(str(e))

def _set_skeleton_rest():
	try:
		rig.set_skeleton_rest()
	except Exception as e:
		cmds.warning(str(e))

def _orient_joints():
	try:
		rig.orient_joints()
	except Exception as e:
		cmds.warning(str(e))

def _reset_skeleton_rest():
	try:
		rig.reset_skeleton_rest()
	except Exception as e:
		cmds.warning(str(e))

def _create_rig():
	joint_map = _collect_joint_names_from_ui()
	side_prefixes = _collect_side_prefixes_from_ui()

	rig.create_rig(joint_map, side_prefixes)
	cmds.inViewMessage(amg='MAZE rig created (if skeleton was found)', pos='midCenter', fade=True)

def _delete_rig():
	rig.delete_rig()
	cmds.inViewMessage(amg='MAZE rig controls deleted', pos='midCenter', fade=True)

def reload_and_refresh():
	"""Hot-reload autorigger + gui modules and re-open the refreshed UI."""
	try:
		parts = __name__.split('.')
		pkg = parts[0] if parts else None

		if pkg:
			autorigger_name = f"{pkg}.autorigger"
			gui_name = f"{pkg}.gui"
			shapes_name = f"{pkg}.Dodaco_AutoShapeTool"
		else:
			autorigger_name = 'autorigger'
			gui_name = 'gui'
			shapes_name = "Dodaco_AutoShapeTool"

		if autorigger_name in sys.modules:
			importlib.reload(sys.modules[autorigger_name])

		if shapes_name in sys.modules:
			importlib.reload(sys.modules[shapes_name])

		if gui_name in sys.modules:
			new_gui = importlib.reload(sys.modules[gui_name])
			if hasattr(new_gui, 'show'):
				new_gui.show()
		else:
			show()
	except Exception as e:
		cmds.warning("MAZE hot-reload failed: %s" % e)

	
	"""Hot-reload autorigger + gui modules and re-open the refreshed UI.
	try:
		parts = __name__.split('.')
		pkg = parts[0] if parts else None

		if pkg:
			autorigger_name = f"{pkg}.autorigger"
			gui_name = f"{pkg}.gui"
		else:
			autorigger_name = 'autorigger'
			gui_name = 'gui'

		if autorigger_name in sys.modules:
			importlib.reload(sys.modules[autorigger_name])

		if gui_name in sys.modules:
			new_gui = importlib.reload(sys.modules[gui_name])
			if hasattr(new_gui, 'show'):
				new_gui.show()
		else:
			show()
	except Exception as e:
		cmds.warning("MAZE hot-reload failed: %s" % e)"""
