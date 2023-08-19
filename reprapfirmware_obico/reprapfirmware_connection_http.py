from reprapfirmware_connection_base import RepRapFirmware_Connection_Base, Event
from typing import Optional, Dict, List, Tuple
from numbers import Number
import json
from .config import Config, RepRapFirmwareConfig
import requests
import threading
import time
import logging

_logger = logging.getLogger('obico.rrf_http')

class RepRapFirmware_Connection_HTTP(RepRapFirmware_Connection_Base):
    def __init__(self, app_config, on_event):
        self.id: str = 'rrfconn'
        self.app_config: Config = app_config
        self.reprapfirmware_config = self.app_config.reprapfirmware
        self.threadActive = False
        self.currentThread = None
        self.on_event = on_event
        self.shutdown: bool = False
        _logger.log('rrf.http init')
        return

    def find_all_heaters(self):
        json_response = self.api_get('/rr_model?key=state')
        rrf_heater_state = json.loads(json_response)
        for heaterIdx in  rrf_heater_state.bedHeaters:
            _logger.log(heaterIdx)
        return

    def find_all_thermal_presets(self):

        return

    def find_most_recent_job(self):
        json_response =  self.api_get("rr_model?key=job")
        rrf_job = json.loads(json_response)
        return rrf_job.lastFileName

    def start(self):
        if self.threadActive:
            return
        self.threadActive = True
        self.currentThread = threading.Thread(target=self.rrf_thread_loop(), daemon=True)
        self.currentThread.start()
        return

    def stop(self):
        self.threadActive = False
        return

    def rrf_thread_loop(self) -> None:
        while self.threadActive:
            self.request_status_update()
            time.sleep(0.2)

    def request_status_update(self) -> None:
        json_response = self.api_get('/rr_model?key=state')
        rrf_state = json.loads(json_response)
        _logger.log(rrf_state)
        self.on_event(name='status', sender=self, data=rrf_state)

    def request_jog(self, axes_dict: Dict[str, Number], is_relative: bool, feedrate: int) -> Dict:
        return Dict

    def request_home(self, axes) -> Dict:
        self.api_get('rr_gcode?gcode=G28')

    def api_get(self, method, timeout = 5, raise_for_status=True, **params):
        url = f'{self.reprapfirmware_config.http_address}/{method.replace(".","/")}'
        resp = requests.get(url, timeout=timeout)
        return resp.json()

