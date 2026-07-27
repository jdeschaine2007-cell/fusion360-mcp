"""
MCP Dialog UI for Fusion 360

Flow (plan-then-confirm):
  1. User types a request in the palette and clicks "Preview Plan".
  2. The palette sends {action:"plan", data:{prompt}} to the add-in.
  3. We forward it to the MCP server as a `plan_action` command. The server
     proposes actions, builds a step plan + a synthetic preview PNG, and returns
     it — WITHOUT touching Fusion geometry.
  4. We push the plan + PNG back to the palette (onAddInMessage / sendInfoToHTML).
  5. The user reviews the schematic. Only on "Execute" do we run the real
     Fusion actions through FusionActionExecutor.
"""

import adsk.core
import adsk.fusion
import json
import threading
import traceback


class MCPDialog:
    """Dialog (palette) for MCP interaction."""

    def __init__(self, app, ui, mcp_client, action_executor):
        self.app = app
        self.ui = ui
        self.mcp_client = mcp_client
        self.action_executor = action_executor
        self.palette = None

        # Model selection (defaults; sync with server/available models)
        self.selected_provider = "ollama"
        self.selected_model = "llama3"

    # ------------------------------------------------------------------ #
    # Palette lifecycle
    # ------------------------------------------------------------------ #
    def show(self):
        try:
            self.palette = self.ui.palettes.itemById('MCPPalette')
            if not self.palette:
                self.palette = self.ui.palettes.add(
                    'MCPPalette',
                    'MCP Assistant',
                    'MCPPalette.html',
                    True,   # isVisible
                    True,   # isCloseable
                    True,   # isResizable
                    800,
                    600
                )
                # THIS was missing before: wire the palette -> add-in channel.
                self.palette.incomingMessage.add(self._on_palette_message)

            self.palette.isVisible = True
        except:
            self.ui.messageBox('Failed to show dialog:\n{}'.format(traceback.format_exc()))

    def close(self):
        if self.palette:
            self.palette.isVisible = False

    # ------------------------------------------------------------------ #
    # Palette -> Add-in messages
    # ------------------------------------------------------------------ #
    def _on_palette_message(self, args):
        """
        Fusion calls this when the HTML palette calls
        adsk.fusion.Palette.sendInfoToHTML(...). `args` is an
        HTMLPaletteMessageEventArgs; args.message holds our JSON string.
        """
        try:
            raw = args.message if args and hasattr(args, 'message') else str(args)
            msg = json.loads(raw)
            action = msg.get('action')
            data = msg.get('data', {}) or {}
            if action == 'plan':
                self._handle_plan_request(data.get('prompt', ''))
            elif action == 'execute':
                self._handle_execute(data.get('actions', []))
            else:
                self._send_to_palette('error', {'message': 'Unknown action: {}'.format(action)})
        except Exception as e:
            self._send_to_palette('error', {'message': str(e)})

    def _send_to_palette(self, action, data):
        """Push a message from the add-in back into the HTML palette."""
        try:
            if self.palette:
                payload = json.dumps({'action': action, 'data': data})
                self.palette.sendInfoToHTML(payload)
        except Exception as e:
            self.ui.messageBox('Failed to send to palette:\n{}'.format(e))

    # ------------------------------------------------------------------ #
    # Plan (no Fusion geometry touched)
    # ------------------------------------------------------------------ #
    def _handle_plan_request(self, prompt):
        if not prompt:
            self._send_to_palette('error', {'message': 'Empty prompt'})
            return

        def worker():
            try:
                context = self._get_design_context()
                command = {
                    "command": "plan_action",   # <-- the new no-execute command
                    "params": {
                        "provider": self.selected_provider,
                        "model": self.selected_model,
                        "prompt": prompt,
                        "temperature": 0.7
                    },
                    "context": context
                }
                response = self.mcp_client.send_command(command)
                if response.get('status') in ('planned', 'success'):
                    md = response.get('metadata_dict', {}) or {}
                    self._send_to_palette('plan_result', {
                        'plan_text': md.get('plan_text', ''),
                        'preview_png': md.get('preview_png', ''),
                        'actions': response.get('actions_to_execute', []),
                    })
                else:
                    self._send_to_palette('error', {
                        'message': response.get('message', 'Plan failed')
                    })
            except Exception as e:
                self._send_to_palette('error', {'message': str(e)})

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Execute (real Fusion geometry — only after user approval)
    # ------------------------------------------------------------------ #
    def _handle_execute(self, actions):
        if not actions:
            self._send_to_palette('error', {'message': 'No actions to execute'})
            return

        def worker():
            ok, fail = 0, 0
            for action in actions:
                try:
                    success = self.action_executor.execute(action)
                    if success:
                        ok += 1
                    else:
                        fail += 1
                        self._log('Failed: {}'.format(action.get('action')))
                except Exception as e:
                    fail += 1
                    self._log('Error executing {}: {}'.format(action.get('action'), e))
            self._send_to_palette('exec_result', {
                'message': 'Executed {} / {} step(s).'.format(ok, ok + fail)
            })

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _get_design_context(self) -> dict:
        try:
            design = adsk.fusion.Design.cast(self.app.activeProduct)
            if not design:
                return {
                    "active_component": "None",
                    "units": "mm",
                    "design_state": "no_design"
                }

            component = design.activeComponent
            component_name = component.name if component else "RootComponent"
            units_manager = design.unitsManager
            default_unit = units_manager.defaultLengthUnits
            body_count = component.bRepBodies.count if component else 0
            sketch_count = component.sketches.count if component else 0

            return {
                "active_component": component_name,
                "units": default_unit,
                "design_state": "has_geometry" if body_count > 0 else "empty",
                "geometry_count": {
                    "bodies": body_count,
                    "sketches": sketch_count
                }
            }
        except:
            return {
                "active_component": "Unknown",
                "units": "mm",
                "design_state": "error"
            }

    def _log(self, message: str):
        try:
            self.ui.messageBox(message)
        except:
            print(message)
