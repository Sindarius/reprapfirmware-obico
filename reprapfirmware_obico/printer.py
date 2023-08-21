import math
import platform
from typing import Optional, Dict
import threading
import time
import pathlib

from .config import Config
from .version import VERSION
from .utils import sanitize_filename
from .reprapfirmware_connection_base import RepRapFirmware_Connection_Base
import logging

_logger = logging.getLogger('obico.printer')


class PrinterState:
    STATE_OFFLINE = 'Offline'
    STATE_OPERATIONAL = 'Operational'
    STATE_GCODE_DOWNLOADING = 'G-Code Downloading'
    STATE_PRINTING = 'Printing'
    STATE_PAUSING = 'Pausing'
    STATE_PAUSED = 'Paused'
    STATE_RESUMING = 'Resuming'
    STATE_CANCELLING = 'Cancelling'

    EVENT_STARTED = 'PrintStarted'
    EVENT_RESUMED = 'PrintResumed'
    EVENT_PAUSED = 'PrintPaused'
    EVENT_CANCELLED = 'PrintCancelled'
    EVENT_DONE = 'PrintDone'
    EVENT_FAILED = 'PrintFailed'

    ACTIVE_STATES = [STATE_PRINTING, STATE_PAUSED, STATE_PAUSING, STATE_RESUMING, STATE_CANCELLING]

    def __init__(self, app_config: Config):
        self._mutex = threading.RLock()
        self.app_config = app_config
        self.status = {}
        self.current_print_ts = None
        self.obico_g_code_file_id = None
        self.transient_state = None
        self.thermal_presets = []
        self.installed_plugins = []
        self.current_file_metadata = None
        self.rrfconn: Optional[RepRapFirmware_Connection_Base] = None

    def set_connection(self, rrfconn : RepRapFirmware_Connection_Base):
        self.rrfconn = rrfconn

    def has_active_job(self) -> bool:
        return PrinterState.get_state_from_status(self.status) in PrinterState.ACTIVE_STATES

    def is_printing(self) -> bool:
        with self._mutex:
            return self.status.get('state',{}).get('status','unknown') == 'processing'

    # Return: The old status.
    def update_status(self, new_status: Dict) -> Dict:
        with self._mutex:
            old_status = self.status
            self.status = new_status
        return old_status

    # Return: The old current_print_ts.
    def set_current_print_ts(self, new_current_print_ts):
        with self._mutex:
            old_current_print_ts = self.current_print_ts
            self.current_print_ts = new_current_print_ts
            if self.current_print_ts == -1:
                self.set_obico_g_code_file_id(None)

        return old_current_print_ts

    def set_obico_g_code_file_id(self, obico_g_code_file_id):
        with self._mutex:
            self.obico_g_code_file_id = obico_g_code_file_id

    def set_transient_state(self, transient_state):
        with self._mutex:
            self.transient_state = transient_state

    def get_obico_g_code_file_id(self):
        with self._mutex:
            return self.obico_g_code_file_id

    @classmethod
    def get_state_from_status(cls, data: Dict) -> str:
        return {
            'idle': PrinterState.STATE_OPERATIONAL,
            'processing': PrinterState.STATE_PRINTING,
            'paused': PrinterState.STATE_PAUSED,
            'pausing': PrinterState.STATE_PAUSED,
            'error': PrinterState.STATE_OPERATIONAL,
            # state is "error" when printer quits a print due to an error, but operational
            'simulating': PrinterState.STATE_PRINTING,
            'busy': PrinterState.STATE_OPERATIONAL,
            'changingTool': PrinterState.STATE_OPERATIONAL,
            'resuming': PrinterState.STATE_RESUMING,
            'cancelling':PrinterState.STATE_CANCELLING
        }.get(data.get('state', {}).get('status', 'unknown'), PrinterState.STATE_OFFLINE)

    def to_dict(
        self, print_event: Optional[str] = None, with_config: Optional[bool] = False
    ) -> Dict:
        with self._mutex:
            data = {
                'current_print_ts': self.current_print_ts,
                'status': self.to_status(),
            } if self.current_print_ts is not None else {}  # Print status is un-deterministic when current_print_ts is None

            if print_event:
                data['event'] = {'event_type': print_event}

            if with_config:
                config = self.app_config
                data["settings"] = dict(
                    webcam=dict(
                        flipV=config.webcam.flip_v,
                        flipH=config.webcam.flip_h,
                        rotation=config.webcam.rotation,
                        streamRatio="16:9" if config.webcam.aspect_ratio_169 else "4:3",
                    ),
                    temperature=dict(dict(profiles=self.thermal_presets)),
                    agent=dict(
                        #name="reprapfirmware_obico",
                        name= "moonraker_obico",
                        version=VERSION,
                    ),
                    platform_uname=list(platform.uname()),
                    installed_plugins=self.installed_plugins,
                )
                try:
                    with open('/proc/device-tree/model', 'r') as file:
                        model = file.read().strip()
                    data['settings']['platform_uname'].append(model)
                except:
                    data['settings']['platform_uname'].append('')
            return data

# TODO Fix this to look at RRF properties
    def to_status(self) -> Dict:
        with self._mutex:
            state = self.get_state_from_status(self.status)

            if self.transient_state is not None:
                state = self.transient_state

            has_error = ''  # self.status.get('print_stats', {}).get('state', '') == 'error'

            temps = {}

            rrf_state = self.status.get('state',{})
            rrf_job = self.status.get('job', {})
            rrf_move = self.status.get('move', {})

            if self.rrfconn is not None:
                for heater in self.rrfconn.get_current_heater_state():
                    temps[heater.name] = {
                        'actual': heater.actual,
                        'offset': 0,
                        'target': heater.target
                    }

            filepath = rrf_job.get('file', {}).get('fileName', '') if rrf_job else None
            filename = pathlib.Path(filepath).name if filepath else None
            file_display_name = sanitize_filename(filename) if filename else None

            if state == PrinterState.STATE_OFFLINE:
                return {}

            completion, print_time, print_time_left = self.get_time_info(rrf_job)
            current_z, max_z, total_layers, current_layer = self.get_z_info()
            return {
                '_ts': time.time(),
                'state': {
                    'text': state,
                    'flags': {
                        'operational': state not in [PrinterState.STATE_OFFLINE, PrinterState.STATE_GCODE_DOWNLOADING],
                        'paused': state == PrinterState.STATE_PAUSED,
                        'printing': state == PrinterState.STATE_PRINTING,
                        'cancelling': state == PrinterState.STATE_CANCELLING,
                        'pausing': state == PrinterState.STATE_PAUSING,
                        'error': has_error,
                        'ready': state == PrinterState.STATE_OPERATIONAL,
                        'closedOrError': False,
                        # OctoPrint uses this flag to indicate the printer is connectable. It should always be false until we support connecting moonraker to printer
                    },
                    'error': ''  # print_stats.get('message') if has_error else None
                },
                'currentZ': current_z,
                'job': {
                    'file': {
                        'name': filename,
                        'path': filepath,
                        'display': file_display_name,
                        'obico_g_code_file_id': self.get_obico_g_code_file_id(),
                    },
                    'estimatedPrintTime': None,
                    'user': None,
                },
                'progress': {
                    'completion': completion * 100,
                    'filepos': rrf_job.get('filePosition', 0),
                    'printTime': print_time,
                    'printTimeLeft': print_time_left,
                    'filamentUsed': rrf_job.get('rawExtrusion', 0)
                },
                'temperatures': temps,
                'file_metadata': {
                    'analysis': {
                        'printingArea': {
                            'maxZ': max_z
                        }
                    },
                    'obico': {
                        'totalLayerCount': total_layers
                    }
                },
                'currentLayerHeight': current_layer,
                'currentFeedRate': self.status.get('move',{}).get('speedFactor', 0),  # gcode_move.get('speed_factor'),
                'currentFlowRate': 0,  # gcode_move.get('extrude_factor'),
                'currentFanSpeed': 0  # fan.get('speed'),
            }

    def get_z_info(self):
        is_not_printing = self.is_printing() is False or self.transient_state is not None
        move = self.status.get('move')
        job =self.status.get('job', {})
        file = job.get('file', {})

        z_axis = next((z for z in move['axes'] if z['letter'] == 'Z'), None)
        current_z = float(z_axis.get('userPosition', 0)) if z_axis is not None else 0
        max_z = file.get('height',0)

        current_layer = job.get('layer', None)
        total_layers = file.get('numLayers', None)

        if is_not_printing:
            current_layer = None
            total_layers = None

        return current_z, max_z, total_layers, current_layer

    def get_time_info(self, job):
        try:
            completed = job.get('filePosition', 1) / job.get('file', {}).get('size', 1)
        except:
            completed = 0
        return completed, job.get('duration', 0), job.get('timesLeft', {}).get('file', 0)
        # return (completion, print_time, print_time_left)
