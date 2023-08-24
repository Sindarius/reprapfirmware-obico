from typing import Optional, Dict, List, Tuple
from numbers import Number
from abc import ABC, abstractmethod
import dataclasses

@dataclasses.dataclass
class Event:
    name: str
    data: Dict
    sender: Optional[str] = None

@dataclasses.dataclass
class HeaterModel:
    name: str
    type: str
    heater_idx: int
    sensor_idx: int  # sensor index
    tool_idx: int  # tool number or bed number - necessary to set the temp on the correct target
    actual: Number
    target: Number

class RepRapFirmware_Connection_Base(ABC):
    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def find_all_heaters(self):
        pass

    @abstractmethod
    def find_all_thermal_presets(self):
        pass

    @abstractmethod
    def find_most_recent_job(self):
        pass

    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def request_status_update(self):
        pass

    @abstractmethod
    def request_jog(self, axes_dict: Dict[str, Number], is_relative: bool, feedrate: int) -> Dict:
        pass

    @abstractmethod
    def request_home(self, axes) -> Dict:
        pass

    @abstractmethod
    def start_print(self, filename: str):
        pass

    @abstractmethod
    def pause_print(self):
        pass

    @abstractmethod
    def resume_print(self):
        pass

    @abstractmethod
    def cancel_print(self):
        pass

    @abstractmethod
    def request_set_temperature(self):
        pass

    @abstractmethod
    def get_file_info(self, filename: str) -> Dict:
        pass

    @abstractmethod
    def upload_file(self, filename: str, data):
        pass

    @abstractmethod
    def get_file_list(self, dir):
        pass

    @abstractmethod
    def get_current_heater_state(self) -> List[HeaterModel]:
        pass

    @abstractmethod
    def execute_gcode(self, command: str):
        pass


