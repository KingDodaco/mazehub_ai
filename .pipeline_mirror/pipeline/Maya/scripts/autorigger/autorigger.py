import maya.cmds as cmds
import maya.api.OpenMaya as om
from . import Dodaco_AutoShapeTool as shapes


class Rig:
    def __init__(self):
        self.main_group = None
        self.geometry_group = None
        self.deformation_skeleton_group = None
        self.rigComponents = []

        self.left_colour_index = 6
        self.right_colour_index = 13

    def create_rig(self, joint_map, side_prefixes):
        if(self.main_group is None or self.geometry_group is None or self.deformation_skeleton_group is None):
            raise RuntimeError("Rig groups not initialized. Please initialize the rig groups before creating the rig.")

        self.joint_map = joint_map
        self.side_prefixes = side_prefixes

        self.rig_root()
        self.rig_spine()
        self.rig_front_legs()
        self.rig_rear_legs()
        self.rig_tail()
        self.rig_head()
        self.rig_neck()

    def find_joints(self):
        self.joints = cmds.listRelatives(self.deformation_skeleton_group, allDescendents=True, type='joint')
        print("Found joints in deformation skeleton group: %s" % self.joints)

    def get_geo(self):

        selection = cmds.ls(selection=True)

        if(len(selection) > 0 and cmds.objectType(selection[0]) == "transform"):
            return selection
        else:
            raise RuntimeError("No Geometry selected!")

    def delete_rig(self):
        if(self.main_group is None or self.geometry_group is None or self.deformation_skeleton_group is None):
            raise RuntimeError("Rig groups not initialized. Please initialize the rig groups before creating the rig.")

        controls = cmds.listRelatives(self.controls_group, ad = True)
        cmds.delete(controls)

        drivers = cmds.listRelatives(self.driver_skeleton_group, ad = True)
        cmds.delete(drivers)

        for c in self.rigComponents:
            cmds.delete(c)

    def mirror_skeleton(self):
        pass

    def orient_joints(self):
        self.find_joints()

        primary_axis = "x"
        up_vector_axis = "y"

        for j in self.joints:
            opm = cmds.getAttr(j + ".offsetParentMatrix")
            
            cmds.xform(j, matrix=opm, relative=False)
            m = cmds.getAttr(j + ".matrix")

            identity_matrix_obj = om.MMatrix()
            default_matrix_list = list(identity_matrix_obj)
            cmds.setAttr(j+".offsetParentMatrix", default_matrix_list, type="matrix")

            cmds.makeIdentity(j, apply=True, translate=False, rotate=True, scale=False, jointOrient=False)

            cmds.joint(j, e=1, oj="xyz",  secondaryAxisOrient='yup', zeroScaleOrient=True, ch=1)

    def set_skeleton_rest(self):
        self.find_joints()
        '''
        for j in self.joints:
            cmds.makeIdentity(j, a=True)

        '''
        for j in self.joints:
            localMatrix = cmds.getAttr(j + ".xformMatrix")
            offsetMatrix = cmds.getAttr(j + ".offsetParentMatrix")

            lM = om.MMatrix(localMatrix)
            oM = om.MMatrix(offsetMatrix)

            oM= lM * oM

            cmds.setAttr(j + ".offsetParentMatrix", *oM, type="matrix")

            cmds.setAttr(j + ".translate", 0,0,0)
            cmds.setAttr(j + ".rotate", 0,0,0)
            cmds.setAttr(j + ".scale", 1,1,1)
            
            try:
                cmds.setAttr(j + ".jointOrient", 0,0,0)
            except Exception:
                pass

    def reset_skeleton_rest(self):
        if self.joints == None:
            self.find_joints()

        for j in self.joints:
            cmds.setAttr(j + ".translate", 0,0,0)
            cmds.setAttr(j + ".rotate", 0,0,0)
            cmds.setAttr(j + ".scale", 1,1,1)
        
    def initialize_rig_folders(self):

        if(cmds.objExists("main")):
            main_group = cmds.ls("main")[0]
            main_children = cmds.listRelatives(main_group)

            if("geometry" in main_children):
                geometry_group = cmds.ls("geometry")[0]
                self.geometry = cmds.listRelatives(geometry_group)
            else:
                geometry_group = cmds.group(geometry)
                cmds.parent(geometry_group, main_group)
            
            if("deformation_skeleton" in main_children):
                deformation_skeleton_group = cmds.ls("deformation_skeleton")[0]
            else:
                deformation_skeleton_group = cmds.group(empty=True, name="deformation_skeleton")
                cmds.parent(deformation_skeleton_group, main_group)

            if("controls" in main_children):
                controls_group = cmds.ls("controls")[0]
            else:
                controls_group = cmds.group(empty=True, name="controls")
                cmds.parent(controls_group, main_group)

            if("driver_skeleton" in main_children):
                driver_skeleton_group = cmds.ls("driver_skeleton")[0]
            else:
                driver_skeleton_group = cmds.group(empty=True, name="driver_skeleton")
                cmds.parent(driver_skeleton_group,main_group)
            
        else:
            main_group = cmds.group(empty= True, name="main")
            
            geometry = self.get_geo()
            self.geometry = geometry
            geometry_group = cmds.group(geometry)
            cmds.parent(geometry_group, main_group)
            deformation_skeleton_group = cmds.group(empty=True, name="deformation_skeleton")
            cmds.parent(deformation_skeleton_group, main_group)
            controls_group = cmds.group(empty=True, name="controls")
            cmds.parent(controls_group, main_group)
            driver_skeleton_group = cmds.group(empty=True, name="driver_skeleton")
            cmds.parent(driver_skeleton_group,main_group)

        self.main_group = main_group
        self.geometry_group = geometry_group
        self.deformation_skeleton_group = deformation_skeleton_group
        self.controls_group = controls_group
        self.driver_skeleton_group = driver_skeleton_group

    def find_joint(self, prefix, joint):
        joint_name = prefix + self.joint_map[joint]
        if joint_name in self.joints:
            joint = joint_name
        elif joint_name + "_0" in self.joints:
            joint = joint_name + "_0"
        else:
            raise RuntimeError(f" No scapula joint named: {joint_name} found")
        
        return joint

    # ----------------------------------------------------
    # main rigging functions
    # ----------------------------------------------------
    def rig_root(self):
        print("Rigging root controls")

        global_ctrl = "global_ctrl"
        cmds.circle(n=global_ctrl, radius=10, nr=(0,1,0))
        global_ctrl_grp = cmds.group(global_ctrl, n=global_ctrl+"_grp")

        local_ctrl = "local_ctrl"
        cmds.circle(n=local_ctrl, radius=9, nr=(0,1,0))
        local_ctrl_grp = cmds.group(local_ctrl, n=local_ctrl+"_grp")

        cmds.parent(local_ctrl_grp, global_ctrl)
        cmds.parent(global_ctrl_grp, self.controls_group)

        self.global_control = global_ctrl
        self.local_control = local_ctrl

    def rig_spine(self):
        print("Rigging spine controls")
        spine_joints = []
        for joint in self.joints:
            if self.joint_map['spine'] in joint:
                spine_joints.append(joint)
        
        spine_root_joint = spine_joints[-1]
        spine_tip_joint = spine_joints[0]

        #calculate centre position

        spine_root_pos = om.MVector(cmds.xform(spine_root_joint, query=True, translation=True, worldSpace=True))
        spine_tip_pos = om.MVector(cmds.xform(spine_tip_joint, query=True, translation=True, worldSpace=True))

        spine_middle_pos = spine_root_pos +(spine_tip_pos - spine_root_pos) * .5

        #Create controls
        #hip control
        hip_ctrl = "hip_ctrl" 
        cmds.polyCube(n=hip_ctrl,w=1, d=1, h=1)
        cmds.setAttr(hip_ctrl + ".overrideEnabled",1)
        cmds.setAttr(hip_ctrl + ".overrideShading",0)
        hip_ctrl_grp = cmds.group(hip_ctrl, n=hip_ctrl + "_grp")

        cmds.parent(hip_ctrl_grp, self.controls_group)
        cmds.matchTransform(hip_ctrl, spine_root_joint, pos=1)

        #chest control
        chest_ctrl = "chest_ctrl"
        cmds.polyCube(n=chest_ctrl,w=1, d=1, h=1)
        cmds.setAttr(chest_ctrl + ".overrideEnabled",1)
        cmds.setAttr(chest_ctrl + ".overrideShading",0)
        chest_ctrl_grp = cmds.group(chest_ctrl, n=chest_ctrl + "_grp")

        cmds.parent(chest_ctrl_grp, self.controls_group)
        cmds.matchTransform(chest_ctrl, spine_tip_joint, pos=1)

        # Add rest position offset so hip/chest can be frozen (translate zeroed at rest)
        # This allows Freeze Transform on hip_ctrl/chest_ctrl without breaking the spine
        hip_rest_add = cmds.createNode("plusMinusAverage", n="hip_ctrl_rest_add")
        cmds.setAttr(hip_rest_add + ".operation", 1)
        cmds.setAttr(hip_rest_add + ".input3D[1]", spine_root_pos.x, spine_root_pos.y, spine_root_pos.z, type="double3")
        cmds.connectAttr(hip_ctrl + ".translate", hip_rest_add + ".input3D[0]", f=1)

        chest_rest_add = cmds.createNode("plusMinusAverage", n="chest_ctrl_rest_add")
        cmds.setAttr(chest_rest_add + ".operation", 1)
        cmds.setAttr(chest_rest_add + ".input3D[1]", spine_tip_pos.x, spine_tip_pos.y, spine_tip_pos.z, type="double3")
        cmds.connectAttr(chest_ctrl + ".translate", chest_rest_add + ".input3D[0]", f=1)

        # Freeze hip/chest controls: move rest position into parent groups so translate is zero at rest
        # Node network above adds rest position back, so spine drivers see correct world position
        cmds.setAttr(hip_ctrl_grp + ".translate", spine_root_pos.x, spine_root_pos.y, spine_root_pos.z)
        cmds.setAttr(chest_ctrl_grp + ".translate", spine_tip_pos.x, spine_tip_pos.y, spine_tip_pos.z)
        cmds.setAttr(hip_ctrl + ".translate", 0, 0, 0)
        cmds.setAttr(chest_ctrl + ".translate", 0, 0, 0)
        cmds.makeIdentity(hip_ctrl, apply=True, t=1, r=1, s=1, n=0)
        cmds.makeIdentity(chest_ctrl, apply=True, t=1, r=1, s=1, n=0)

        #centre control
        centre_ctrl = "centre_ctrl"
        cmds.polyCube(n=centre_ctrl,w=1, d=1, h=1)
        cmds.move(spine_middle_pos.x,spine_middle_pos.y + 1, spine_middle_pos.z, a=1)
        cmds.setAttr(centre_ctrl + ".overrideEnabled",1)
        cmds.setAttr(centre_ctrl + ".overrideShading",0)
        centre_ctrl_grp = cmds.group(centre_ctrl, n=centre_ctrl+"_grp",)

        cmds.parent(centre_ctrl_grp, self.local_control)

        cmds.makeIdentity(centre_ctrl, apply=True, t=1, r=1, s=1, n=0)

        cmds.parentConstraint(centre_ctrl, hip_ctrl_grp, mo=1)
        cmds.parentConstraint(centre_ctrl, chest_ctrl_grp, mo=1)

        spine_mid_ctrl = "spine_mid_ctrl"
        cmds.circle(n=spine_mid_ctrl, radius=1)
        cmds.move(spine_middle_pos.x,spine_middle_pos.y, spine_middle_pos.z, a=1)
        spine_mid_ctrl_grp = cmds.group(spine_mid_ctrl, n=spine_mid_ctrl+"_grp")
        cmds.parent(spine_mid_ctrl_grp, self.controls_group)

        cmds.makeIdentity(spine_mid_ctrl, apply=True, t=1, r=1, s=1, n=0)


        #create spine drivers

        spine_driver_root = cmds.joint(name="spine_driver_root", p=spine_root_pos)
        spine_driver_root_grp = cmds.group(spine_driver_root, name = spine_driver_root + "_grp", r=1)
        spine_driver_root_helper = cmds.joint(name="spine_driver_root_helper", p=spine_middle_pos)
        cmds.parent(spine_driver_root_helper, spine_driver_root)
        cmds.parent(spine_driver_root_grp, self.driver_skeleton_group)
        cmds.joint(spine_driver_root, e=1, oj="xyz", children=1)
        cmds.setAttr(spine_driver_root+".scaleX",.9)
        self.hip_driver = spine_driver_root
        
        spine_driver_tip = cmds.joint(name="spine_driver_tip", p=spine_tip_pos)
        spine_driver_tip_grp = cmds.group(spine_driver_tip, name = spine_driver_tip + "_grp", r=1)
        spine_driver_tip_helper = cmds.joint(name="spine_driver_tip_helper", p=spine_middle_pos)
        cmds.parent(spine_driver_tip_helper, spine_driver_tip)
        cmds.parent(spine_driver_tip_grp, self.driver_skeleton_group)
        cmds.joint(spine_driver_tip, e=1, oj="xyz", children=1)
        cmds.setAttr(spine_driver_tip+".scaleX",.9)
        self.chest_driver = spine_driver_tip


        #parent the centre control to the driver joints
        cmds.pointConstraint(spine_driver_root_helper, spine_driver_tip_helper, spine_mid_ctrl_grp, w=.5, mo=1)
        cmds.orientConstraint(spine_driver_root, spine_mid_ctrl_grp, w=1, mo=1)

        #constrain spine drivers
        spine_rest_distance = (spine_tip_pos - spine_root_pos).length()

        spine_control_subtract = cmds.createNode("plusMinusAverage")
        spine_control_distance = cmds.createNode("length")
        cmds.setAttr(spine_control_subtract+".op", 2)
        cmds.connectAttr(hip_rest_add + ".output3D", spine_control_subtract+".input3D[0]",f=1)
        cmds.connectAttr(chest_rest_add + ".output3D", spine_control_subtract+".input3D[1]",f=1)
        cmds.connectAttr(spine_control_subtract+".output3D", spine_control_distance+".input",f=1)

        spine_control_divide = cmds.createNode("divide")
        cmds.setAttr(spine_control_divide+".input1", spine_rest_distance/2)
        cmds.connectAttr(spine_control_distance+".output",spine_control_divide+".input2", f=1)

        spine_control_add = cmds.createNode("sum")
        cmds.setAttr(spine_control_add +".input[0]", .5)
        cmds.connectAttr(spine_control_divide +".output", spine_control_add+".input[1]", f=1)

        spine_control_invert= cmds.createNode("subtract")
        cmds.setAttr(spine_control_invert+".input1",1)
        cmds.connectAttr(spine_control_add+".output", spine_control_invert+".input2", f=1)

        #root constraints
        root_constraint_point = "root_constraint_point"
        cmds.pointConstraint(hip_ctrl, chest_ctrl, spine_driver_root_grp, n=root_constraint_point, w=1, mo=0)
        cmds.connectAttr(spine_control_add+".output",root_constraint_point+".tg[0].tw", f=1)
        cmds.connectAttr(spine_control_invert+".output",root_constraint_point+".tg[1].tw", f=1)

        root_constraint_aim = "root_constraint_aim"
        cmds.aimConstraint(spine_driver_tip_grp, spine_driver_root, n=root_constraint_aim, w=1, mo=1)
        spine_hip_invert_x = cmds.createNode("multiplyDivide", n="spine_hip_invert_x")
        cmds.setAttr(spine_hip_invert_x + ".input2X", -1)
        cmds.connectAttr(hip_ctrl + ".rotateX", spine_hip_invert_x + ".input1X", f=True)
        cmds.connectAttr(spine_hip_invert_x + ".outputX", root_constraint_aim + ".offsetZ", f=True)
        cmds.connectAttr(hip_ctrl + ".rotateY", root_constraint_aim + ".offsetY", f=True)
        cmds.connectAttr(hip_ctrl + ".rotateZ", root_constraint_aim + ".offsetX", f=True)

        #chest constraints
        chest_constraint_point = "chest_constraint_point"
        cmds.pointConstraint(hip_ctrl, chest_ctrl, spine_driver_tip_grp, n=chest_constraint_point, w=1, mo=0)
        cmds.connectAttr(spine_control_add+".output",chest_constraint_point+".tg[1].tw", f=1)
        cmds.connectAttr(spine_control_invert+".output",chest_constraint_point+".tg[0].tw", f=1)

        chest_constraint_aim = "chest_constraint_aim"
        cmds.aimConstraint(spine_driver_root_grp, spine_driver_tip, n=chest_constraint_aim, w=1, mo=1)
        # X/Z switched, Z inverted
        cmds.connectAttr(chest_ctrl + ".rotateX", chest_constraint_aim + ".offsetZ", f=True)
        cmds.connectAttr(chest_ctrl + ".rotateY", chest_constraint_aim + ".offsetY", f=True)
        spine_chest_invert_z = cmds.createNode("multiplyDivide", n="spine_chest_invert_z")
        cmds.setAttr(spine_chest_invert_z + ".input2Z", -1)
        cmds.connectAttr(chest_ctrl + ".rotateZ", spine_chest_invert_z + ".input1Z", f=True)
        cmds.connectAttr(spine_chest_invert_z + ".outputZ", chest_constraint_aim + ".offsetX", f=True)

        #spline solver
        spine_solver = "spine_solver"
        spine_solver, effector, spline = cmds.ikHandle(n=spine_solver, sj=spine_root_joint,ee= spine_tip_joint,solver="ikSplineSolver", ns=3)
        cmds.parent(spine_solver, self.driver_skeleton_group)
        cmds.parentConstraint(spine_driver_tip, spine_solver)
        cmds.parent(spline, self.driver_skeleton_group)
        cmds.parentConstraint(spine_driver_root, spine_root_joint)

        clusters = []

        for i in range(6):
            cv = spline + f".cv[{i}]"
            cluster = cmds.cluster(cv)
            clusters.append(cluster)
            cmds.parent(cluster, self.driver_skeleton_group)

            if i < 2:
                cmds.parentConstraint(spine_driver_root, cluster, mo=1)
            elif i < 4:
                cmds.parentConstraint(spine_mid_ctrl, cluster, mo=1)
            else:
                cmds.parentConstraint(spine_driver_tip, cluster, mo=1)

        #spline stretch
        curve_info = cmds.arclen(spline, ch=1)
        restlength = cmds.getAttr(curve_info + ".arcLength")

        spline_stretch_divide = cmds.createNode("divide")
        cmds.connectAttr(curve_info + ".arcLength", spline_stretch_divide +".input1", f=1)
        cmds.setAttr(spline_stretch_divide+".input2", restlength)

        for j in spine_joints:
            cmds.connectAttr(spline_stretch_divide+".output", j +".scaleX", f=1)

        #Spine cvs

        #pelvis controls

        pelvis_name = self.side_prefixes["center"] + self.joint_map["pelvis"]
        if pelvis_name in self.joints:
            self.pelvis_joint = pelvis_name
            self.pelvis_end_joint = cmds.listRelatives(self.pelvis_joint, c=1)[0]
        else:
            raise RuntimeError(f"No pelvis joint named:{pelvis_name} found")

        cmds.pointConstraint(spine_driver_root,self.pelvis_joint, mo=True)

        pelvis_ctrl = "pelvis_ctrl"
        cmds.circle(n=pelvis_ctrl, r=1, nr=(0,1,0))
        cmds.matchTransform(pelvis_ctrl, self.pelvis_joint, pos=1)
        cmds.makeIdentity(pelvis_ctrl, apply=True, t=1, r=1, s=1, n=0)

        pelvis_ctrl_grp = cmds.group(pelvis_ctrl, n=pelvis_ctrl+"_grp")

        #cmds.parentConstraint(spine_driver_root, pelvis_ctrl_grp, mo=1)
        cmds.pointConstraint(spine_driver_root, pelvis_ctrl_grp, mo=1)
        cmds.orientConstraint(spine_driver_root, pelvis_ctrl_grp, mo=1)

        cmds.parent(pelvis_ctrl_grp, self.controls_group)

        #replace this with a dedicated pelvis control
        cmds.orientConstraint(pelvis_ctrl, self.pelvis_joint, mo=1)

    def rig_front_legs(self):
        side_prefixes = [self.side_prefixes["left"], self.side_prefixes["right"]]

        for prefix in side_prefixes:
            print(f"Rigging front legs for {prefix}")

            control_colour = self.left_colour_index

            if(prefix == self.side_prefixes["left"]):
                control_colour = self.left_colour_index
            else:
                control_colour = self.right_colour_index

            scapula_joint = self.find_joint(prefix, "scapula")
            shoulder_joint = self.find_joint(prefix, "shoulder")
            elbow_joint = self.find_joint(prefix, "elbow")
            wrist_joint = self.find_joint(prefix, "wrist")

            #controls
            scapula_ctrl = prefix + "scapula_ctrl"
            cmds.polySphere(n=scapula_ctrl, r = .1,)
            cmds.matchTransform(scapula_ctrl, scapula_joint, pos=1)
            cmds.setAttr(scapula_ctrl + ".overrideEnabled",1)
            cmds.setAttr(scapula_ctrl+ ".overrideColor", control_colour)
            cmds.setAttr(scapula_ctrl + ".overrideShading",0)
            scapula_ctrl_grp = cmds.group(scapula_ctrl, n= scapula_ctrl+"_grp")
            cmds.parent(scapula_ctrl_grp, self.chest_driver)

            cmds.makeIdentity(scapula_ctrl, apply=True, t=1, r=1, s=1, n=0)

            shoulder_ctrl = prefix + "shoulder_ctrl"
            cmds.circle(n=shoulder_ctrl, r = .5, nr = (1,0,0))
            cmds.matchTransform(shoulder_ctrl, shoulder_joint, pos=1)
            cmds.setAttr(shoulder_ctrl + ".overrideEnabled",1)
            cmds.setAttr(shoulder_ctrl+ ".overrideColor", control_colour)
            cmds.setAttr(shoulder_ctrl + ".overrideShading",0)
            shoulder_ctrl_grp = cmds.group(shoulder_ctrl, n= shoulder_ctrl+"_grp")
            cmds.parent(shoulder_ctrl_grp, self.local_control)

            cmds.makeIdentity(shoulder_ctrl, apply=True, t=1, r=1, s=1, n=0)

            #Wrist Control
            wrist_ctrl = prefix + "wrist_ctrl"
            cmds.polySphere(n=wrist_ctrl, r = .1,)
            cmds.matchTransform(wrist_ctrl, wrist_joint, pos=1)
            cmds.setAttr(wrist_ctrl + ".overrideEnabled",1)
            cmds.setAttr(wrist_ctrl+ ".overrideColor", control_colour)
            cmds.setAttr(wrist_ctrl + ".overrideShading",0)
            wrist_ctrl_grp = cmds.group(wrist_ctrl, n= wrist_ctrl+"_grp")
            cmds.parent(wrist_ctrl_grp, self.controls_group)
            cmds.select(cl=1)

            cmds.makeIdentity(wrist_ctrl, apply=True, t=1, r=1, s=1, n=0)

            #Elbow Pole Vector
            elbow_pole_vector = prefix + "elbow_pole_vector"
            cmds.polySphere(n=elbow_pole_vector, r = .1,)
            cmds.matchTransform(elbow_pole_vector, elbow_joint, pos=1)
            cmds.move(0, 0, -2, r=1)
            cmds.setAttr(elbow_pole_vector + ".overrideEnabled",1)
            cmds.setAttr(elbow_pole_vector+ ".overrideColor", control_colour)
            cmds.setAttr(elbow_pole_vector + ".overrideShading",0)
            elbow_pole_vector_grp = cmds.group(elbow_pole_vector, n= elbow_pole_vector+"_grp")
            cmds.parent(elbow_pole_vector_grp, self.controls_group)
            cmds.select(cl=1)

            cmds.makeIdentity(elbow_pole_vector, apply=True, t=1, r=1, s=1, n=0)

            cmds.parentConstraint(wrist_ctrl, shoulder_ctrl, elbow_pole_vector_grp, mo=1)

            #IK
            ikDriver_joints = []
            limb_joints = [shoulder_joint, elbow_joint, wrist_joint]
            for joint in limb_joints:
                driver_joint = joint + "_ikDriver"
                cmds.joint(n=driver_joint)
                cmds.matchTransform(driver_joint, joint)
                cmds.makeIdentity(driver_joint)
                ikDriver_joints.append(driver_joint)
                #disable the visibility of the fk driver joints
                cmds.setAttr(driver_joint + ".visibility", 0)
            cmds.select(cl=1)
            cmds.parent(ikDriver_joints[0], self.driver_skeleton_group)

            ik_solver = prefix + "_arm_IKHandle"
            cmds.ikHandle(n=ik_solver, sol = "ikRPsolver", sj=ikDriver_joints[0], ee=ikDriver_joints[2])
            cmds.poleVectorConstraint(elbow_pole_vector, ik_solver)
            cmds.parentConstraint(wrist_ctrl, ik_solver)
            cmds.parentConstraint(shoulder_ctrl,shoulder_joint+"_ikDriver")
            cmds.parent(ik_solver, self.driver_skeleton_group)
            #Hide the ik solver
            cmds.setAttr(ik_solver + ".visibility", 0)


            fkDriver_joints = []
            for joint in limb_joints:
                driver_joint = joint + "_fkDriver"
                cmds.joint(n=driver_joint)
                cmds.matchTransform(driver_joint, joint)
                cmds.makeIdentity(driver_joint)
                fkDriver_joints.append(driver_joint)
                #disable the visibility of the fk driver joints
                cmds.setAttr(driver_joint + ".visibility", 0)

            cmds.select(cl=1)
            cmds.parent(fkDriver_joints[0], self.driver_skeleton_group)
            cmds.parentConstraint(shoulder_ctrl, fkDriver_joints[0])

            #constrain to ik/fk
            ik_parentConstraints = self.fk_ik_switch(limb_joints=limb_joints, fkDriver_joints=fkDriver_joints, ikDriver_joints=ikDriver_joints, chain_length=3, limb_name="leg_front", prefix=prefix)
            

            rotate_sourceX = cmds.listConnections(shoulder_joint + ".rotateX", plugs=1, source=1, destination=0)
            cmds.disconnectAttr(rotate_sourceX[0], shoulder_joint + ".rotateX")
            rotate_sourceY = cmds.listConnections(shoulder_joint + ".rotateY", plugs=1, source=1, destination=0)
            cmds.disconnectAttr(rotate_sourceY[0], shoulder_joint + ".rotateY")
            rotate_sourceZ = cmds.listConnections(shoulder_joint + ".rotateZ", plugs=1, source=1, destination=0)
            cmds.disconnectAttr(rotate_sourceZ[0], shoulder_joint + ".rotateZ")

            #scapula aim constraint

            scapula_xform = om.MMatrix(cmds.getAttr(scapula_joint + ".offsetParentMatrix"))
            scapula_xform_tm = om.MTransformationMatrix(scapula_xform)

            
            #scapula_aim_vector = scapula_xform_tm.translation(om.MSpace.kTransform).normal()
            #cmds.aimConstraint(scapula_ctrl, shoulder_joint, mo=0, wut = "objectrotation", sk="y")

            cmds.ikHandle(n=prefix + "_scapula_ikHandle", sol = "ikSCsolver", sj=shoulder_joint, ee=scapula_joint)
            cmds.parent(prefix + "_scapula_ikHandle", self.driver_skeleton_group)
            cmds.parentConstraint(scapula_ctrl, prefix + "_scapula_ikHandle", mo=1)
            cmds.setAttr(prefix + "_scapula_ikHandle" + ".visibility", 0)

            shoulder_parentConstraint = prefix + "shoulder_parentConstraint"
            cmds.parentConstraint(wrist_ctrl, self.chest_driver, shoulder_ctrl_grp, n= shoulder_parentConstraint, mo=1)
            source_attr_0 = cmds.listConnections(shoulder_parentConstraint + ".tg[0].tw", plugs=1, source=1, destination=0)
            cmds.disconnectAttr(source_attr_0[0], shoulder_parentConstraint + ".tg[0].tw")
            source_attr_1 = cmds.listConnections(shoulder_parentConstraint + ".tg[1].tw", plugs=1, source=1, destination=0)
            cmds.disconnectAttr(source_attr_1[0], shoulder_parentConstraint + ".tg[1].tw")

            cmds.setAttr(shoulder_parentConstraint + ".tg[0].tw", .2)
            cmds.setAttr(shoulder_parentConstraint + ".tg[1].tw", .8)
            

            #reverse foot()
            cmds.select(cl=1)
            reverse_joints = self.rig_reverse_foot(ankle_joint=wrist_joint, prefix=prefix, name="hand", ankletarget=shoulder_ctrl_grp)

            cmds.pointConstraint(reverse_joints[-1], wrist_ctrl)

    def rig_rear_legs(self):

        side_prefixes = [self.side_prefixes["left"], self.side_prefixes["right"]]

        for prefix in side_prefixes:
            print(f"Rigging rear legs for {prefix}")
            
            control_colour = self.left_colour_index

            if(prefix == self.side_prefixes["left"]):
                control_colour = self.left_colour_index
            else:
                control_colour = self.right_colour_index

            femur_joint = self.find_joint(prefix, "femur")
            tibia_joint = self.find_joint(prefix, "tibia")
            metatarsus_joint = self.find_joint(prefix, "metatarsus")
            ankle_joint = self.find_joint(prefix, "ankle")

            #Controls
            ankle_ctrl = prefix + "ankle_ctrl"
            cmds.polySphere(n=ankle_ctrl, r = .1,)
            cmds.matchTransform(ankle_ctrl, ankle_joint, pos=1)
            cmds.setAttr(ankle_ctrl + ".overrideEnabled",1)
            cmds.setAttr(ankle_ctrl+ ".overrideColor", control_colour)
            cmds.setAttr(ankle_ctrl + ".overrideShading",0)
            ankle_ctrl_grp = cmds.group(ankle_ctrl, n= ankle_ctrl+"_grp")
            cmds.parent(ankle_ctrl_grp, self.controls_group)
            cmds.select(cl=1)

            #Pole Vector
            knee_pole_vector = prefix + "knee_pole_vector"
            cmds.polySphere(n=knee_pole_vector, r = .1,)
            cmds.matchTransform(knee_pole_vector, tibia_joint, pos=1)
            cmds.move(0, 0, 1, r=1)
            cmds.setAttr(knee_pole_vector + ".overrideEnabled",1)
            cmds.setAttr(knee_pole_vector+ ".overrideColor", control_colour)
            cmds.setAttr(knee_pole_vector + ".overrideShading",0)
            knee_pole_vector_grp = cmds.group(knee_pole_vector, n= knee_pole_vector+"_grp")
            cmds.parent(knee_pole_vector_grp, self.controls_group)
            cmds.select(cl=1)
            cmds.makeIdentity(knee_pole_vector, apply=True, t=1, r=1, s=1, n=0)

            cmds.parentConstraint(ankle_ctrl, knee_pole_vector_grp, mo=1)

            #IK
            ikDriver_joints = []
            limb_joints = [femur_joint, tibia_joint, metatarsus_joint, ankle_joint]
            for joint in limb_joints:
                driver_joint = joint + "_ikDriver"
                cmds.joint(n=driver_joint)
                cmds.matchTransform(driver_joint, joint)
                cmds.makeIdentity(driver_joint)
                ikDriver_joints.append(driver_joint)
                #disable the visibility of the fk driver joints
                cmds.setAttr(driver_joint + ".visibility", 0)
            cmds.select(cl=1)
            cmds.parent(ikDriver_joints[0], self.driver_skeleton_group)

            ik_solver = prefix + "_leg_IKHandle"
            cmds.ikHandle(n=ik_solver, sol = "ikRPsolver", sj=ikDriver_joints[0], ee=ikDriver_joints[3])
            cmds.poleVectorConstraint(knee_pole_vector, ik_solver)
            cmds.parentConstraint(ankle_ctrl, ik_solver)
            cmds.parentConstraint(self.pelvis_joint, femur_joint + "_ikDriver", mo=1)
            cmds.parent(ik_solver, self.driver_skeleton_group)
            #Hide the ik solver
            cmds.setAttr(ik_solver + ".visibility", 0)

            #FK
            fkDriver_joints = []
            for joint in limb_joints:
                driver_joint = joint + "_fkDriver"
                cmds.joint(n=driver_joint)
                cmds.matchTransform(driver_joint, joint)
                cmds.makeIdentity(driver_joint)
                fkDriver_joints.append(driver_joint)
                #disable the visibility of the fk driver joints
                cmds.setAttr(driver_joint + ".visibility", 0)

            cmds.select(cl=1)
            cmds.parent(fkDriver_joints[0], self.driver_skeleton_group)
            cmds.parentConstraint(self.pelvis_joint, fkDriver_joints[0], mo=1)

            #constrain to ik/fk
            ik_parentConstraints = self.fk_ik_switch(limb_joints=limb_joints, fkDriver_joints=fkDriver_joints, ikDriver_joints=ikDriver_joints, chain_length=4, limb_name="leg_rear", prefix=prefix)
            
            cmds.select(cl=1)
            reverse_joints = self.rig_reverse_foot(ankle_joint=ankle_joint, prefix=prefix, name="leg", ankletarget=self.hip_driver)

            cmds.pointConstraint(reverse_joints[-1], ankle_ctrl)

    def rig_reverse_foot(self, ankle_joint, prefix, name, ankletarget):

        print(f"Rigging reverse foot for {prefix}")
        
        ball_joint = cmds.listRelatives(ankle_joint, c=1)[0]
        toe_joint = cmds.listRelatives(ball_joint, c=1)[0]

        if prefix == self.side_prefixes["left"]:
            in_dir = -1
        else:
            in_dir = 1

        ankle_joint_pos = om.MVector(cmds.xform(ankle_joint, q=1, t=1, ws=1))
        toe_joint_pos = om.MVector(cmds.xform(toe_joint, q=1, t=1, ws=1))
        ball_joint_pos = om.MVector(cmds.xform(ball_joint, q=1, t=1, ws=1))
        root_joint_pos = om.MVector(ankle_joint_pos.x, toe_joint_pos.y, ankle_joint_pos.z)
        root_toe_length = (toe_joint_pos - root_joint_pos).length()
        bank_in_joint_pos =  (root_joint_pos.x + root_toe_length/2 * in_dir, root_joint_pos.y, root_joint_pos.z + root_toe_length/2)
        bank_out_joint_pos =  (root_joint_pos.x + root_toe_length/2 * -in_dir, root_joint_pos.y, root_joint_pos.z + root_toe_length/2)

        reverse_joint_chain = []
        reverse_root_joint = f"{prefix}_{name}_reverse_root"
        cmds.joint(n=reverse_root_joint,p=root_joint_pos)
        reverse_joint_chain.append(reverse_root_joint)
        cmds.parent(reverse_root_joint, self.driver_skeleton_group)

        reverse_bank_in_joint = f"{prefix}_{name}_reverse_bank_in"
        cmds.joint(n=reverse_bank_in_joint,p=bank_in_joint_pos)
        reverse_joint_chain.append(reverse_bank_in_joint)

        reverse_bank_out_joint = f"{prefix}_{name}_reverse_bank_out"
        cmds.joint(n=reverse_bank_out_joint,p=bank_out_joint_pos)
        reverse_joint_chain.append(reverse_bank_out_joint)

        reverse_toe_joint = f"{prefix}_{name}_reverse_toe"
        cmds.joint(n=reverse_toe_joint,p=toe_joint_pos)
        reverse_joint_chain.append(reverse_toe_joint)

        reverse_ball_joint = f"{prefix}_{name}_reverse_ball"
        cmds.joint(n=reverse_ball_joint,p=ball_joint_pos)
        reverse_joint_chain.append(reverse_ball_joint)

        reverse_ankle_joint = f"{prefix}_{name}_reverse_ankle"
        cmds.joint(n=reverse_ankle_joint,p=ankle_joint_pos)
        reverse_joint_chain.append(reverse_ankle_joint)

        for joint in reverse_joint_chain:
            cmds.joint(joint, e=1, oj="xyz",sao="yup", ch=1, zso=1)

        #controls

        control_colour = self.left_colour_index

        if(prefix == self.side_prefixes["left"]):
            control_colour = self.left_colour_index
        else:
            control_colour = self.right_colour_index

        main_ctrl = f"{prefix}_{name}_main"
        cmds.circle(n= main_ctrl, r=1, nr = (0,1,0))
        cmds.move(root_joint_pos.x, root_joint_pos.y, root_joint_pos.z + root_toe_length/2, a=1)
        cmds.setAttr(main_ctrl + ".overrideEnabled",1)
        cmds.setAttr(main_ctrl+ ".overrideColor", control_colour)
        cmds.setAttr(main_ctrl + ".overrideShading",0)
        cmds.parent(main_ctrl, self.local_control)

        cmds.makeIdentity(main_ctrl, apply=True, t=1, r=1, s=1, n=0)

        main_parent_constraint = f"{prefix}_{name}_main_parentConstraint"
        cmds.parentConstraint(main_ctrl, reverse_root_joint, mo=1, n=main_parent_constraint)
        #cmds.aimConstraint(ankletarget,reverse_ball_joint, mo=1, w=.3, wut="none")

        cmds.ikHandle(n=f"{prefix}_{name}_foot_ik", sol = "ikSCsolver", sj=ankle_joint, ee=ball_joint)
        cmds.parentConstraint(reverse_ball_joint,f"{prefix}_{name}_foot_ik", mo=1)
        cmds.parent(f"{prefix}_{name}_foot_ik", self.driver_skeleton_group)

        cmds.ikHandle(n=f"{prefix}_{name}_toe_ik", sol = "ikSCsolver", sj=ball_joint, ee=toe_joint)
        cmds.parentConstraint(reverse_toe_joint, f"{prefix}_{name}_toe_ik", mo=1)
        cmds.parent(f"{prefix}_{name}_toe_ik", self.driver_skeleton_group)

        cmds.setAttr(f"{prefix}_{name}_foot_ik" + ".visibility", 0)
        cmds.setAttr(f"{prefix}_{name}_toe_ik" + ".visibility", 0)

        cmds.addAttr(main_ctrl, ln="bank_in", defaultValue=0.0, minValue = -90, maxValue = 90, k=1, at="float")
        cmds.addAttr(main_ctrl, ln="bank_out", defaultValue=0.0, minValue = -90, maxValue = 90, k=1, at="float")
        cmds.addAttr(main_ctrl, ln="toe", defaultValue=0.0, minValue = -90, maxValue = 90, k=1, at="float")
        cmds.addAttr(main_ctrl, ln="heel", defaultValue=0.0, minValue = -90, maxValue = 90, k=1, at="float")
        cmds.addAttr(main_ctrl, ln="ball", defaultValue=0.0, minValue = -90, maxValue = 90, k=1, at="float")

        cmds.createNode("plusMinusAverage", n=f"{prefix}_{name}_add_heel_rotate", ss=1)
        cmds.connectAttr(main_ctrl + ".heel", f"{prefix}_{name}_add_heel_rotate.input1D[0]")
        cmds.connectAttr(main_parent_constraint + ".constraintRotateZ", f"{prefix}_{name}_add_heel_rotate.input1D[1]")

        cmds.connectAttr(main_ctrl + ".bank_in", reverse_bank_in_joint + ".rotateZ")
        cmds.connectAttr(main_ctrl + ".bank_out", reverse_bank_out_joint + ".rotateZ")
        cmds.connectAttr(main_ctrl + ".toe", reverse_toe_joint + ".rotateZ")
        cmds.connectAttr(main_ctrl + ".ball", reverse_ball_joint + ".rotateZ")
        cmds.connectAttr(f"{prefix}_{name}_add_heel_rotate" + ".output1D", reverse_root_joint + ".rotateZ", f=1)

        return reverse_joint_chain
    
    def fk_ik_switch(self, limb_joints, fkDriver_joints, ikDriver_joints, chain_length, limb_name, prefix):#, ik_ctrls, fk_ctrls):

        if prefix == self.side_prefixes["left"]: 
            in_dir = -1
        else:
            in_dir = 1
        
        limb_name = prefix + limb_name

        fk_ik_ctrl = limb_name + "_ctrl"

        shapes.Fk_IK_Switch(fk_ik_ctrl)

        fk_ik_ctrl_grp = fk_ik_ctrl + "_grp"

        cmds.parent(fk_ik_ctrl_grp, self.controls_group)


        ctrl_pos = cmds.xform(limb_joints[chain_length-1], q=1, ws=1, t=1)
        cmds.xform(fk_ik_ctrl_grp, ws=1, t=(ctrl_pos[0] + (2 * -in_dir),ctrl_pos[1],ctrl_pos[2]), s=(.1,.1,.1))

        cmds.addAttr(fk_ik_ctrl, ln="FK_IK_Switch", defaultValue=1.0, minValue = 0, maxValue = 1.0, k=1, at="float")
        cmds.shadingNode("reverse", au=1, n=(limb_name + "_FK_IK_reverse"))
        cmds.setAttr((limb_name + "_FK_IK_reverse.inputX"),1)
        cmds.connectAttr((fk_ik_ctrl + ".FK_IK_Switch"), (limb_name + "_FK_IK_reverse.inputX"),f=1)

        cmds.connectAttr((fk_ik_ctrl + ".FK_IK_Switch"), fk_ik_ctrl + "_ikTextShape.visibility")
        cmds.connectAttr((limb_name + "_FK_IK_reverse.outputX"), fk_ik_ctrl + "_fkTextShape.visibility")
        
        cmds.pointConstraint(limb_joints[chain_length-1], fk_ik_ctrl_grp, mo=1, w=1)

        if(prefix == self.side_prefixes["left"]):
            control_colour = self.left_colour_index
        else:
            control_colour = self.right_colour_index

        cmds.setAttr(fk_ik_ctrl + ".overrideEnabled",1)
        cmds.setAttr(fk_ik_ctrl+ ".overrideColor", control_colour)

        ik_parentConstraints = []
        for i in range(chain_length):
            constraint = cmds.parentConstraint(ikDriver_joints[i], fkDriver_joints[i], limb_joints[i], w=1, mo=1)
            ik_parentConstraints.append(constraint)

        for constraint in ik_parentConstraints:
            getWeights = cmds.parentConstraint(constraint, q=1, wal=1)

            cmds.connectAttr((fk_ik_ctrl + ".FK_IK_Switch"), (constraint[0] + "." + getWeights[0]), f=1)
            cmds.connectAttr((limb_name + "_FK_IK_reverse.outputX"), (constraint[0] + "." + getWeights[1]), f=1)

        return ik_parentConstraints
    
    def rig_tail(self):
        print("Rigging tail controls")

        prefix = self.side_prefixes["center"]

        tail_root = self.find_joint(prefix=prefix, joint=self.joint_map["tail"])

        print("the tail joint is" + tail_root)

        #cmds.parentConstraint(self.pelvis_joint, tail_root, mo=1)

        tail_joints = cmds.listRelatives(tail_root, ad=1, type="joint")

        tail_joints.append(tail_root)

        tail_joints.reverse()

        tail_ctrls = []

        for i in range(len(tail_joints)-1):
            joint = tail_joints[i]
            control_name = joint.replace("tail", "tail_ctrl")
            cmds.circle(n=control_name, r=.5, nr=(1,0,0))
            cmds.matchTransform(control_name, joint, pos=1, rot=1)
            cmds.setAttr(control_name + ".overrideEnabled",1)
            cmds.group(n = control_name + "_grp")
            tail_ctrls.append(control_name)

            cmds.makeIdentity(control_name, apply=True, t=1, r=1, s=1, n=0)

            if(i == 0):
                cmds.parentConstraint( self.pelvis_joint, control_name + "_grp", mo=1)
                cmds.parent(control_name + "_grp", self.controls_group)
            else:
                cmds.parent(control_name + "_grp", tail_ctrls[i-1])

            cmds.parentConstraint(control_name, joint, mo=1)

    def rig_head(self):
        print("Rigging head controls")

        prefix = self.side_prefixes["center"]
        head_ctrl = prefix + self.joint_map["head"] + "_ctrl"
        head_joint = self.find_joint(prefix=prefix, joint=self.joint_map["head"])

        cmds.circle(n=head_ctrl, r=1, nr=(0,0,1))
        cmds.matchTransform(head_ctrl, head_joint, pos=1)

        cmds.parentConstraint(head_ctrl, head_joint, mo=1)

        head_ctrl_grp = cmds.group(head_ctrl, n=head_ctrl + "_grp")

        cmds.makeIdentity(head_ctrl, apply=True, t=1, r=1, s=1, n=0)

        cmds.parent(head_ctrl_grp, self.controls_group)

        cmds.pointConstraint(self.chest_driver, head_ctrl_grp, mo=1)

    def rig_neck(self):
        print("Rigging neck controls")

        prefix = self.side_prefixes["center"]
        neck_ctrl = prefix + self.joint_map["neck"] + "_ctrl"
        neck_joint = self.find_joint(prefix=prefix, joint=self.joint_map["neck"])

        print("the neck joint is" + neck_joint)

        cmds.parentConstraint(self.chest_driver, neck_joint, mo=1)