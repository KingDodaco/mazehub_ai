#------------------------------------------------------------------------------------------------------------------
# Dodaco Auto spine tool v001
#------------------------------------------------------------------------------------------------------------------

import maya.cmds as cmds

def arrow2(name):
    cmds.curve(n=name, d=1,
    p=[(-2, 0, -1),
       (2, 0, -1),
       (2, 0, -2),
       (4, 0, 0),
       (2, 0, 2),
       (2, 0, 1),
       (-2, 0, 1),
       (-2, 0, 2),
       (-4, 0, 0),
       (-2, 0, -2),
       (-2, 0, -1)],
    k=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

    cmds.xform(name, r=1, ro=(90,0,0))
    
    cmds.makeIdentity(name, a=1, r=1)

def Fk_IK_Switch(name):

    arrow2(name)

    fk_grp = cmds.textCurves(n=name + "_fkText",f="Arial|h-400|w-1600", t="FK")
    ik_grp = cmds.textCurves(n=name + "_ikText",f="Arial|h-400|w-1600", t="IK")

    groups = [fk_grp,ik_grp]

    for mainGroup in groups:
        childGroups = cmds.listRelatives(mainGroup)
        for group in childGroups:
            curve = cmds.listRelatives(group)
            cmds.parent(cmds.listRelatives(curve,s=1), mainGroup, s=1, r=0)
            cmds.delete(group)

        cmds.scale(3, 3, 3, mainGroup)
        cmds.xform(mainGroup, piv=cmds.xform(cmds.listRelatives(mainGroup)[1],ws=1,t=1, q=1))

        cmds.makeIdentity(mainGroup, a=1)
        
        cmds.matchTransform(mainGroup, name)

        cmds.xform(mainGroup,t=(0,2,0),r=1)

        

    cmds.group(name, fk_grp, ik_grp, n=name + "_grp")

    cmds.delete(fk_grp, constructionHistory = True)
    cmds.delete(ik_grp, constructionHistory = True)