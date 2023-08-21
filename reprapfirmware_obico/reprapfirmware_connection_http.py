from .reprapfirmware_connection_base import RepRapFirmware_Connection_Base, Event, HeaterModel
from typing import Optional, Dict, List, Tuple
from numbers import Number
import json
from .config import Config, RepRapFirmwareConfig
import requests
import threading
import time
import logging
from .utils import fix_rrf_filename

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
        self.sessionKey = ''
        self.heaters: List[HeaterModel] = []

        # this is used to load up heater profiles and other settings which may be made
        # available to Obico on first load or reconnection since settings may have changed
        self.reloadSettings = True
        _logger.debug('rrf.http init')
        return

    def find_all_heaters(self):
        json_response = self.api_get('rr_model?key=state')
        rrf_heater_state = json.loads(json_response)
        for heaterIdx in rrf_heater_state.bedHeaters:
            _logger.info(heaterIdx)
        return

    def find_all_thermal_presets(self):

        return

    def reload_configuration(self):
        self.heaters = []  # wipe out existing data

        heat = self.api_get('rr_model?key=heat')['result']
        tools = self.api_get('rr_model?key=tools')['result']
        analog = self.api_get('rr_model?key=sensors.analog')['result']

        #Build heater models for tracking
        for bedHeaterIdx in range(len(heat['bedHeaters'])):
            bed_heater = heat['bedHeaters'][bedHeaterIdx]
            if bed_heater != -1:
                heater = HeaterModel(name=analog[bed_heater]['name'], type='bed', heater_idx= bed_heater, sensor_idx=int(bed_heater),
                                     tool_idx=int(bedHeaterIdx), actual=0, target=0)
                self.heaters.append(heater)

        #load tool heaters
        for toolIdx in range(len(tools)):
            t = tools[toolIdx]
            heater = HeaterModel(name='', heater_idx=-1, sensor_idx=-1, type='tool', tool_idx=toolIdx, actual=0, target=0)
            heater_idx = int(t.get('heaters', [-1])[0])
            if heater_idx > -1:  # we are only going to support the first heater for now...
                sensorIdx = int(heat['heaters'][heater_idx]['sensor'])
                sensor = analog[sensorIdx]
                heater.name = sensor.get('name', f'Heater {heater_idx}')
                heater.heater_idx = heater_idx
                heater.sensor_idx = sensorIdx
                heater.tool_idx = toolIdx
                self.heaters.append(heater)

    def update_heaters(self):
        resp = self.api_get("rr_model?key=heat").get('result', {}).get('heaters', [])
        for heat in self.heaters:
            try:
                heater = resp[heat.heater_idx]
                heat.target = heater['active']
                heat.actual = heater['current']
            except:
                _logger.error("Unable to find heater")

    def find_most_recent_job(self):
        time.sleep(1)
        data = self.api_get("rr_model?key=job").get('result', {})
        return data

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
            try:
                if self.reloadSettings:
                    self.reload_configuration()
                    self.reloadSettings = False
                self.request_status_update()
            except Exception as e:
                _logger.warning("Unable to retrieve current status.")
                _logger.warning(e)
                self.reloadSettings = True
            time.sleep(1)

    def request_status_update(self) -> None:
        rrf_state = self.api_get('rr_model?key=state')
        job_state = self.api_get('rr_model?key=job')
        move = self.api_get('rr_model?key=move')
        rrf_state = {**{'state': rrf_state['result']}, **{'job': job_state['result']}, **{'move': move['result']}} #merge the results to get a full status
        self.on_event(Event(name='status_update', sender="rrfconn", data=rrf_state))

    def request_jog(self, axes_dict: Dict[str, Number], is_relative: bool, feedrate: int) -> dict:
        _logger.debug(axes_dict)
        gcode = "rr_gcode?gcode=M120\nG91\nG0 "
        for axis in axes_dict:
            gcode += axis + f"{axes_dict[axis]}"
        gcode += "G90\nM121"
        self.api_get(gcode)
        return dict()

    def request_home(self, axes) -> Dict:
        self.api_get('rr_gcode?gcode=G28')

    def api_get(self, method, timeout=5, raise_for_status=True, **params):
        url = f'{self.reprapfirmware_config.http_address()}/{method}'
        resp = requests.get(url, timeout=timeout)
        json_data = resp.json()
        resp.close()
        return json_data

    def api_post(self, method, filedata):
        url = f'{self.reprapfirmware_config.http_address()}/{method}'
        resp = requests.post(url,data=filedata)
        json_data = resp.json()
        resp.close()
        return json_data

    def start_print(self, filename: str):
        _logger.info(f'Starting Print {filename}')
        resp = self.api_get(f'rr_gcode?gcode=M32 "{filename}"')
        return

    def pause_print(self):
        _logger.debug('Pause print')
        self.api_get('rr_gcode?gcode=M25')
        return

    def resume_print(self):
        _logger.debug('Resume print')
        self.api_get('rr_gcode?gcode=M24')
        return

    def cancel_print(self):
        _logger.info('Cancel Print')
        self.pause_print()
        self.api_get('rr_gcode?gcode=M0')
        return

    def request_set_temperature(self):
        return

    def get_file_info(self, filename: str) -> Dict:
        data = self.api_get(f"rr_fileinfo?name=/gcodes/{fix_rrf_filename(filename)}")
        return data

    def upload_file(self, filename: str, data):
        data = self.api_post(f"rr_upload?name=/gcodes/{filename}", filedata=data)
        return data

    def get_file_list(self, dir= ''):
        dir = dir.replace('gcodes/', '')
        data = self.api_get(f"rr_filelist?dir=/gcodes/{fix_rrf_filename(dir)}")
        return data

    def get_current_heater_state(self):
        self.update_heaters()
        return self.heaters
