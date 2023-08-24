import traceback

from .reprapfirmware_connection_base import RepRapFirmware_Connection_Base, Event, HeaterModel
from typing import Optional, Dict, List, Tuple
from numbers import Number
import json
from .config import Config, RepRapFirmwareConfig
from  threading import Thread, Lock
import time
from serial import Serial
import logging
from .utils import fix_rrf_filename

_logger = logging.getLogger('obico.rrf_serial')

class RepRapFirmware_Connection_Serial(RepRapFirmware_Connection_Base):
    def __init__(self, app_config, on_event):
        self.id: str = 'rrfconn'
        self.app_config: Config = app_config
        self.reprapfirmware_config = self.app_config.reprapfirmware
        self.threadActive = False
        self.currentThread = None
        self.mutex = Lock()
        self.on_event = on_event
        self.serial_connection : Optional[Serial] = None
        self.reloadSettings = True
        self.heater_strings = [b'T0:', b'B:']
        return

    def api_get(self, command, waitresponse= True):
        try:
            self.mutex.acquire(blocking=True, timeout=60)
            if self.serial_connection is None or not self.serial_connection.is_open:
                _logger.warning("Connection not open")
                return {}
            _logger.debug(f'RRF Serial api_get command : {command}')
            self.serial_connection.readall() #empty out the buffer before we issue a command
            b = bytes(f'{command}\n','utf-8')
            self.serial_connection.write(b) #write the bytes
            result = b''
            while True:
                data = self.serial_connection.readline()
                #discard periodic heater messages
                if all(s in data for s in self.heater_strings):
                    continue
                if data != b'ok\n':  #data != b'' and data != b'\n':
                    result += data
                else:
                    break
            try:
                json_data = json.loads(result.decode()) #attempt to decode the results into json.
                return json_data
            except:
                _logger.info(result)
                return result.decode()  # data likely a string return those results instead
        finally:
            self.mutex.release()

    def api_upload(self, command, data):
        try:
            self.mutex.acquire(blocking=True, timeout=-1)
            if self.serial_connection is None or not self.serial_connection.is_open:
                return False
            b = bytes(f'{command}\n', 'utf-8')
            self.serial_connection.write(b)
            self.serial_connection.write(data)
            self.serial_connection.write(b'<!-- **EoF** -->\n')
            time.sleep(1)
            self.serial_connection.flush()
            if self.serial_connection.inWaiting() > 0:
                _logger.info("Dumping data")
                self.serial_connection.readall()  # read what's there and toss it
            self.serial_connection.reset_output_buffer()
            self.serial_connection.reset_input_buffer()

        finally:
            self.mutex.release()
        return True

    def find_all_heaters(self):
        return

    def find_all_thermal_presets(self):
        return

    def update_heaters(self):
        resp = self.api_get('M409 K"heat"').get('result',{}).get('heaters', [])
        for heat in self.heaters:
            try:
                heater = resp[heat.heater_idx]
                heat.target = heater['active']
                heat.actual = heater['current']
            except:
                _logger.error("Unable to find heater")

    def find_most_recent_job(self):
        time.sleep(1)
        data = self.api_get('M409 K"job"')['result']
        return data

    def start(self):
        self.threadActive = True
        self.currentThread = Thread(target=self.rrf_thread_loop(), daemon=True)
        self.currentThread.start()
        return

    def stop(self):
        _logger.info('Stopping thread')
        if self.serial_connection is not None and not self.serial_connection.is_open:
            self.serial_connection.close()
        self.serial_connection = None
        return

    def rrf_thread_loop(self) -> None:
        while self.threadActive:
            try:
                if self.serial_connection is None or not self.serial_connection.is_open:
                    try:
                        _logger.info(f'Attempting serial connection to {self.app_config.reprapfirmware.serial_port}')
                        self.serial_connection = Serial(baudrate=115200, port=self.app_config.reprapfirmware.serial_port, timeout=1)  # attempt to reconnect
                        if not self.serial_connection.is_open:
                            self.serial_connection.open()
                        if self.serial_connection.is_open:
                            _logger.info("Serial connection is open.")
                            if self.mutex.locked():
                                self.mutex.release()  # force release the lock
                            self.api_get('<!-- **EoF** -->')  # incase we got stuck in a write when it died
                            self.reloadSettings = True
                    except Exception as e:
                        _logger.error('Unable to connect to serial connection')
                        _logger.error('You may have to issue this command to grant permissions to your account to access the serial port')
                        _logger.error('sudo usermod -a -G dialout <username>')
                        _logger.error(e)
                        self.serial_connection.close()
                        self.serial_connection = None
                        time.sleep(1) #sleep a second and then restart loop
                        continue

                if self.reloadSettings:
                    self.reload_configuration()
                    self.reloadSettings = False

                if not self.mutex.locked():  # skip status query if we are doing another serial request action
                   self.request_status_update()
            except Exception as e:  # if we fail to get the current status it's possible our connection needs to be reset.
                _logger.warning("Unable to retrieve current status.")
                _logger.warning(e)
                _logger.error(traceback.print_exc())
                self.serial_connection.close()
                self.serial_connection = None
                self.reloadSettings = True
            time.sleep(1)

    def request_status_update(self):
        rrf_state = self.api_get('M409 K"state"')['result']
        job_state = self.api_get('M409 K"job"')['result']
        move = self.api_get('M409 K"move"')['result']
        rrf_state = {**{'state': rrf_state}, **{'job': job_state},
                     **{'move': move}}  # merge the results to get a full status
        self.on_event(Event(name='status_update', sender="rrfconn", data=rrf_state))
        return

    def reload_configuration(self):
        self.heaters = []  # wipe out existing data
        heat = self.api_get('M409 K"heat"')['result']
        tools = self.api_get('M409 K"tools"')['result']
        analog = self.api_get('M409 K"sensors.analog"')['result']

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

    def request_jog(self, axes_dict: Dict[str, Number], is_relative: bool, feedrate: int) -> Dict:
        _logger.debug(axes_dict)
        gcode = "M120\nG91\nG0 "
        for axis in axes_dict:
            gcode += axis + f"{axes_dict[axis]}"
        gcode += "G90\nM121"
        self.api_get(gcode, False)
        return dict()

    def request_home(self, axes) -> Dict:
        self.api_get('G28', False)

    def start_print(self, filename: str):
        _logger.info(f'Starting Print {filename}')
        resp = self.api_get(f'M32 "{filename}"', False)
        return

    def pause_print(self):
        _logger.debug('Pause print')
        self.api_get('M25', False)
        return

    def resume_print(self):
        _logger.debug('Resume print')
        self.api_get('M24', False)
        return

    def cancel_print(self):
        _logger.info('Cancel Print')
        self.pause_print()
        self.api_get('M0', False)
        return

    def get_file_info(self, filename: str) -> Dict:
        data = self.api_get(f'M36 "/gcodes/{fix_rrf_filename(filename)}"')
        return data

    def upload_file(self, filename: str, data):
        data = self.api_upload(f'M560 P"/gcodes/{filename}"', data=data)
        return data

    def get_file_list(self, dir= ''):
        dir = dir.replace('gcodes/', '')
        data = self.api_get(f'M20 S3 P"/gcodes/{fix_rrf_filename(dir)}"')
        return data

    def get_current_heater_state(self):
        self.update_heaters()
        return self.heaters

    def request_set_temperature(self):
        return

    def execute_gcode(self, command: str):
        try:
            data = self.api_get(command)
            return data, False
        except:
            return 'Error executing gcode', True
