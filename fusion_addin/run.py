"""
Fusion 360 add-in entry point for the FusionMCP server.

Drop this file (and fusion_mcp_server.py, fusion_geometry.py, preview support)
into a Fusion add-ins folder, or load this folder as an add-in. Running the
"FusionMCP" command starts the MCP (SSE) server in a background thread.

A note on the LLM used by plan_design: this add-in is provider-agnostic. Wire
your own by calling fusion_mcp_server.set_llm_callable(fn) where fn(prompt, system)
returns the model's raw JSON text. (Leave it unset and plan_design returns an
error, while the geometry tools still work standalone.)
"""

import os
import sys
import traceback

import adsk.core
import adsk.fusion

# Make sibling modules + the shared preview package importable.
_ADDIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _ADDIN_DIR not in sys.path:
    sys.path.insert(0, _ADDIN_DIR)

app = adsk.core.Application.get()
ui = app.userInterface
_handlers = []
_server_thread = None


def _on_command_created(args):
    cmd = args.command
    try:
        info = cmd.commandInputs.addTextBoxCommandInput(
            "info", "", "Start the FusionMCP server so MCP clients (Claude, Cursor) can connect.", 2, True
        )
        from fusion_mcp_server import run_server
        global _server_thread
        if _server_thread is None or not _server_thread.is_alive():
            _server_thread = run_server()
            ui.messageBox("FusionMCP server started (SSE) at http://127.0.0.1:3000/sse")
        else:
            ui.messageBox("FusionMCP server already running.")
    except:
        ui.messageBox("Failed to start server:\n{}".format(traceback.format_exc()))


def _create_ui():
    cmd_def = ui.commandDefinitions.itemById("FusionMCPCommand")
    if not cmd_def:
        cmd_def = ui.commandDefinitions.addButtonDefinition(
            "FusionMCPCommand", "FusionMCP", "Start the FusionMCP server"
        )
    h = adsk.core.CommandCreatedEventHandler.create(_on_command_created)
    cmd_def.commandCreated.add(h)
    _handlers.append(h)
    panel = ui.allToolbarPanels.itemById("SolidScriptsAddinsPanel")
    if panel and not panel.controls.itemById("FusionMCPCommand"):
        panel.controls.addCommand(cmd_def)


def run(context):
    try:
        _create_ui()
    except:
        if ui:
            ui.messageBox("FusionMCP init failed:\n{}".format(traceback.format_exc()))


def stop(context):
    try:
        cmd_def = ui.commandDefinitions.itemById("FusionMCPCommand")
        if cmd_def:
            cmd_def.deleteMe()
        panel = ui.allToolbarPanels.itemById("SolidScriptsAddinsPanel")
        ctrl = panel.controls.itemById("FusionMCPCommand") if panel else None
        if ctrl:
            ctrl.deleteMe()
    except:
        if ui:
            ui.messageBox("FusionMCP cleanup failed:\n{}".format(traceback.format_exc()))
