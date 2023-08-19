from .reprapfirmware_connection_base import RepRapFirmware_Connection_Base
from typing import Optional, Dict, List, Tuple
from numbers import Number
import json
from .config import Config, RepRapFirmwareConfig
import threading

class RepRapFirmware_Connection_Serial(RepRapFirmware_Connection_Base):
    def __init__(self, app_config, on_event):
        self.id: str = 'rrfconn'
        self.app_config: Config = app_config
        self.reprapfirmware_config = self.app_config.reprapfirmware
        self.serialThread: Optional[threading.Thread] = None
        return

    def find_all_heaters(self):
        return

    def find_all_thermal_presets(self):
        return

    def find_most_recent_job(self):
        return

    def start(self):
 #       if self.serialThread is None:

        return

    def stop(self):
#        if self.serialThread is None:

        return

    def request_status_update(self):
        return

    def request_jog(self, axes_dict: Dict[str, Number], is_relative: bool, feedrate: int) -> Dict:
        return Dict

    def request_home(self, axes) -> Dict:
        return Dict
