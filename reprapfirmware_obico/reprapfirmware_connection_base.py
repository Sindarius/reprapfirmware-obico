from typing import Optional, Dict, List, Tuple
from numbers import Number
from abc import ABC, abstractmethod

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

    def pause_print(self):
        pass
