import json
import os
import time

try:
    import obsws_python as obs
    import logging
    logging.getLogger("obsws_python").setLevel(logging.CRITICAL)
    logging.getLogger("obsws_python.reqs").setLevel(logging.CRITICAL)
except ImportError:
    obs = None

def _read_obs_password() -> str:
    import re
    OBS_GLOBAL_INI = os.path.expanduser("~/.config/obs-studio/global.ini")
    OBS_WEBSOCKET_JSON = os.path.expanduser("~/.config/obs-studio/plugin_config/obs-websocket/config.json")
    if os.path.exists(OBS_WEBSOCKET_JSON):
        try:
            with open(OBS_WEBSOCKET_JSON, "r") as f:
                data = json.load(f)
                return data.get("server_password", "")
        except: pass
    if os.path.exists(OBS_GLOBAL_INI):
        try:
            with open(OBS_GLOBAL_INI, "r") as f:
                content = f.read()
            match = re.search(r"(?:ServerPassword|server_password)\s*=\s*(.+)", content, re.IGNORECASE)
            if match: return match.group(1).strip()
        except: pass
    return ""

class OBSController:
    def __init__(self, host: str, port: int, source_name: str):
        self.host = host
        self.port = port
        self.source_name = source_name
        self.client = None
        self.connected = False

    def connect(self, password: str, retries: int = 1, delay: int = 3) -> bool:
        if obs is None:
            return False
        for _ in range(retries):
            try:
                self.client = obs.ReqClient(
                    host=self.host, port=self.port, password=password, timeout=5
                )
                self.connected = True
                return True
            except Exception:
                time.sleep(delay)
        return False

    def play_file(self, filepath: str) -> bool:
        if not self.connected: return False
        try:
            self.client.set_input_settings(
                name=self.source_name,
                settings={
                    "local_file": filepath, 
                    "is_local_file": True,
                    "looping": False
                },
                overlay=True,
            )
            self.client.trigger_media_input_action(
                name=self.source_name,
                action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART",
            )
            return True
        except Exception:
            return False

    def pause_media(self) -> bool:
        if not self.connected: return False
        try:
            self.client.trigger_media_input_action(
                name=self.source_name, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PAUSE"
            )
            return True
        except Exception:
            return False

    def resume_media(self) -> bool:
        if not self.connected: return False
        try:
            self.client.trigger_media_input_action(
                name=self.source_name, action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_PLAY"
            )
            return True
        except Exception:
            return False

    def get_media_status(self) -> tuple[str, int, int]:
        if not self.connected: return ("unknown", 0, 0)
        try:
            resp = self.client.get_media_input_status(name=self.source_name)
            return (resp.media_state or "unknown", resp.media_cursor or 0, resp.media_duration or 0)
        except Exception:
            return ("unknown", 0, 0)

    def set_input_settings(self, input_name: str, settings: dict) -> bool:
        if not self.connected: return False
        try:
            self.client.set_input_settings(name=input_name, settings=settings, overlay=True)
            return True
        except Exception:
            return False

    def get_scene_item_id(self, scene_name: str, source_name: str) -> int | None:
        if not self.connected: return None
        try:
            resp = self.client.get_scene_item_id(scene_name=scene_name, source_name=source_name)
            return resp.scene_item_id
        except Exception:
            return None

    def set_scene_item_transform(self, scene_name: str, item_id: int, transform: dict) -> bool:
        if not self.connected: return False
        try:
            self.client.set_scene_item_transform(scene_name=scene_name, scene_item_id=item_id, scene_item_transform=transform)
            return True
        except Exception:
            return False
