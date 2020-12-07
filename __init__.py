import bpy
import os
import sys
import time
from .pypresence import pypresence as rpc

bl_info = {
    "name": "BlendPresence",
    "description": "Discord Rich Presence for Blender 2.90",
    "author": "Abrasic",
    "version": (1, 2, 1),
    "blender": (2, 90, 1),
    "category": "System",
}

rpcClient = rpc.Presence("766373631424200705")
pidFilePath = os.path.join(os.path.dirname(os.path.normpath(bpy.app.tempdir)), "BlendRpcPid")
startTime = None
isRendering = False
renderedFrames = 0

def register():
    global startTime

    bpy.utils.register_class(RpcPreferences)
    startTime = time.time()
    rpcClient.connect()
    writePidFileAtomic()
    bpy.app.timers.register(updatePresenceTimer, first_interval=1.0, persistent=True)
    bpy.app.handlers.save_post.append(writePidHandler)
    
    # Rendering
    bpy.app.handlers.render_init.append(startRenderJobHandler)
    bpy.app.handlers.render_complete.append(endRenderJobHandler)
    bpy.app.handlers.render_cancel.append(endRenderJobHandler)
    bpy.app.handlers.render_post.append(postRenderHandler)

def unregister():
    global startTime

    startTime = None
    rpcClient.close()
    removePidFile()
    bpy.app.timers.unregister(updatePresenceTimer)
    bpy.app.handlers.save_post.remove(writePidHandler)
    bpy.utils.unregister_class(RpcPreferences)
    
    # Rendering
    bpy.app.handlers.render_init.remove(startRenderJobHandler)
    bpy.app.handlers.render_complete.remove(endRenderJobHandler)
    bpy.app.handlers.render_cancel.remove(endRenderJobHandler)
    bpy.app.handlers.render_post.remove(postRenderHandler)

def writePidFileAtomic():
    pid = os.getpid()
    tmpPidFilePath = f"{pidFilePath}-{pid}"
    with open(tmpPidFilePath, "w") as tmpPidFile:
        tmpPidFile.write(str(pid))
        tmpPidFile.flush()
        os.fsync(tmpPidFile.fileno())
    os.replace(tmpPidFilePath, pidFilePath)

def readPidFile():
    try:
        with open(pidFilePath, 'r') as pidFile:
            storedPid = int(pidFile.read())
    except OSError:
        return None
    except ValueError:
        return None
    return storedPid

def removePidFile():
    try:
        os.remove(pidFilePath)
    except OSError:
        pass

@bpy.app.handlers.persistent
def writePidHandler(*args):
    writePidFileAtomic()

@bpy.app.handlers.persistent
def startRenderJobHandler(*args):
    global isRendering
    global startTime
    isRendering = True
    
    if bpy.context.preferences.addons[__name__].preferences.resetTimer:
        startTime = time.time()

@bpy.app.handlers.persistent
def endRenderJobHandler(*args):
    global isRendering
    global renderedFrames
    global startTime
    isRendering = False
    renderedFrames = 0
    
    if bpy.context.preferences.addons[__name__].preferences.resetTimer:
        startTime = time.time()

@bpy.app.handlers.persistent
def postRenderHandler(*args):
    global renderedFrames
    renderedFrames += 1
    
def updatePresenceTimer():
    updatePresence()
    return 5.0

def updatePresence():
    activityState = None
    activityDescription = None
    smallIcon = None
    smallIconText = None
    
    # Pre-Checks
    readPid = readPidFile()
    if readPid is None:
        writePidFileAtomic()
    elif readPid != os.getpid():
        rpcClient.clear()
        return
    
    # Addon Preferences
    prefs = bpy.context.preferences.addons[__name__].preferences

    # Details and State
    if isRendering:

        smallIcon = "render"
        if prefs.displayRenderStats:
            smallIconText = f"{bpy.context.scene.render.resolution_x}x{bpy.context.scene.render.resolution_y}"
        # Rendering Details (prefs)
        if prefs.displayFileName and getFileName():
            activityDescription = f"Rendering {getFileName()}.blend"
        else:
            activityDescription = f"Rendering a project"
        # Rendering State
        if renderedFrames > 0:
            frameRange = getFrameRange()
            if prefs.displayRenderStats:
                smallIconText = f"{bpy.context.scene.render.resolution_x}x{bpy.context.scene.render.resolution_y}@{bpy.context.scene.render.fps}fps"
            if prefs.displayFrames:
                activityState = f"Frame {frameRange[0]} of {frameRange[1]}"
        else:
            if prefs.displayFrames:
                activityState = f"Frame {bpy.context.scene.frame_current}"
    else:
        activityDescription = f"{getFileName()}.blend"
        if prefs.displayFileName and getFileName():
            activityDescription = activityDescription
        else:
            activityDescription = "Working on a project"
            
        if len(prefs.customText) > 2: # Discord gets mad when it's less than two
            activityState = str(prefs.customText)

        activeMode = bpy.context.object.mode

        if prefs.displayMode and activeMode:
            smallIcon = activeMode.lower()
            smallIconText = activeMode.replace("_", " ").title()
            
            if "MODE" in activeMode:
                smallIconText = activeMode.replace("_", " ").title()
            else:
                smallIconText = f'{activeMode.replace("_", " ").title()} Mode'

    # Start Time (prefs)
    if prefs.displayTime and not isRendering:
        fStartTime = startTime
    elif prefs.displayTime and isRendering:
        fStartTime = startTime
    else:
        fStartTime = None

    # Large Icon
    if prefs.displayVersion:
        if prefs.displayEngine:
            largeIconText = getRenderEngineStr() + " in " + getVersionStr()
        else:
            largeIconText = getVersionStr()
    else:
        if prefs.displayEngine:
            largeIconText = getRenderEngineStr()
        else:
            largeIconText = None

    rpcClient.update(
        pid=os.getpid(),
        start=fStartTime,
        state=activityState,
        details=activityDescription,
        small_image=smallIcon,
        small_text=smallIconText,
        large_image='blenderlogo',
        large_text=largeIconText,
    )

def getFileName():
    name = bpy.path.display_name_from_filepath(bpy.data.filepath)
    if name == "":
        return None
    else:
        return name

def getVersionStr():
    verTup = bpy.app.version
    verChar = bpy.app.version_char
    return f"{verTup[0]}.{verTup[1]}.{verTup[2]}{verChar}"

def getRenderEngineStr():
    internalName = bpy.context.engine
    internalNameStripped = internalName.replace("BLENDER_", "").replace("_", " ")
    return internalNameStripped.title() + " Engine"

def getFrameRange():
    """Current frame and total remaining frames"""
    start = bpy.context.scene.frame_start
    end = bpy.context.scene.frame_end
    cursor = bpy.context.scene.frame_current
    return (cursor - start + 1, end - start + 1)


class RpcPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    displayFileName: bpy.props.BoolProperty(
        name = "File name",
        description = "Displays .blend file name of the current project",
        default = False,
    )
    
    displayTime: bpy.props.BoolProperty(
        name = "Elapsed time",
        description = "Displays total amount of time elapsed since the plugin was enabled",
        default = True,
    )
    
    resetTimer: bpy.props.BoolProperty(
        name = "Reset elapsed time on render",
        description = "While enabled, the elapsed time will reset when a render begins",
        default = True,
    )
    
    displayMode: bpy.props.BoolProperty(
        name = "Active mode",
        description = "Displays the current mode (Object, Edit, Pose, etc.) from the 3D Viewport",
        default = True,
    )
    
    displayEngine: bpy.props.BoolProperty(
        name = "Render engine",
        description = "Displays the current render engine",
        default = True,
    )

    displayVersion: bpy.props.BoolProperty(
        name = "Blender version",
        description = "Displays the version of Blender software",
        default = True,
    )
    
    displayFrames: bpy.props.BoolProperty(
        name = "Rendering: Frame count",
        description = "While rendering: Displays the current frame count",
        default = True,
    )
    
    displayRenderStats: bpy.props.BoolProperty(
        name = "Rendering: Render stats",
        description = "While rendering: Displays render information such as camera resolution and FPS",
        default = True,
    )

    customText: bpy.props.StringProperty(
        name = "Custom text",
        description = "A string that will display above the elapsed time. Two characters or longer",
        default = "",
    )

    def draw(self, context):
        row = self.layout.row()
        box1 = row.box()
        box1.label(text="Large Icon Hover", icon="BLENDER")
        box1.prop(self, "displayEngine")
        box1.prop(self, "displayVersion")

        box2 = box1.box()
        box2.label(text="Small Icon Hover", icon="PROP_CON")
        box2.prop(self, "displayMode")
        box2.prop(self, "displayRenderStats")
        
        box3 = row.box()
        box3.label(text="Text Display", icon="TEXT")
        box3.prop(self, "displayFileName")
        box3.prop(self, "displayFrames")
        box3.prop(self, "customText")
        box3.prop(self, "displayTime")
        box3.prop(self, "resetTimer")
