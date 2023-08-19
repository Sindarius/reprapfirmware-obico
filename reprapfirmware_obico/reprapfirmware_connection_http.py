from .reprapfirmware_connection_base import RepRapFirmware_Connection_Base, Event
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
        _logger.info('rrf.http init')
        return

    def find_all_heaters(self):
        json_response = self.api_get('rr_model?key=state')
        rrf_heater_state = json.loads(json_response)
        for heaterIdx in rrf_heater_state.bedHeaters:
            _logger.info(heaterIdx)
        return

    def find_all_thermal_presets(self):

        return

    def find_most_recent_job(self):
        json_response = self.api_get("rr_model?key=job")
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
            time.sleep(1)

    def request_status_update(self) -> None:
        rrf_state = self.api_get('rr_model?key=state')
        # _logger.info(rrf_state)
        self.on_event(Event(name='status_update', sender="rrfconn", data=rrf_state))

    def request_jog(self, axes_dict: Dict[str, Number], is_relative: bool, feedrate: int) -> dict:
        _logger.info(axes_dict)
        return dict()

    def request_home(self, axes) -> Dict:
        self.api_get('rr_gcode?gcode=G28')

    def api_get(self, method, timeout=5, raise_for_status=True, **params):
        url = f'{self.reprapfirmware_config.http_address()}/{method.replace(".","/")}'
        #_logger.info(url)
        resp = requests.get(url, timeout=timeout)
        json_data = resp.json()
        resp.close()
        return json_data

    def start_print(self, filename: str):
        _logger.info(f'Starting Print {filename}')
        return

    def pause_print(self):
        _logger.info(f'Pausing Print')
        return

    def resume_print(self):
        _logger.info(f'Resume Print')
        return

    def cancel_print(self):
        _logger.info(f'Cancel Print')
        return

    def request_set_temperature(self):
        return
