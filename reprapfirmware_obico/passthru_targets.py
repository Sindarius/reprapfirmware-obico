import logging
import traceback

import requests
import os
import sys
import time
import threading
import io
import pathlib
from .reprapfirmware_connection_base import RepRapFirmware_Connection_Base

from .utils import sanitize_filename
from .state_transition import call_func_with_state_transition

_logger = logging.getLogger('obico.file_downloader')

MAX_GCODE_DOWNLOAD_SECONDS = 10 * 60


class FileDownloader:

    def __init__(self, model, rrfconn: RepRapFirmware_Connection_Base, server_conn, sentry):
        self.model = model
        self.rrfconn = rrfconn
        self.server_conn = server_conn
        self.sentry = sentry

    def download(self, g_code_file) -> None:

        def _download_and_print():
            try:
                _logger.info(
                    f'downloading from {g_code_file["url"]}')

                safe_filename = sanitize_filename(g_code_file['safe_filename'])
                r = requests.get(
                    g_code_file['url'],
                    allow_redirects=True,
                    timeout=60 * 30
                )
                r.raise_for_status()
                _logger.info(f'uploading "{safe_filename}" to RRF')
                resp_data = self.rrfconn.upload_file(safe_filename, r.content)
                _logger.debug(f'upload response: {resp_data}')
                time.sleep(1)
                filepath_on_rrf = f'/gcodes/{safe_filename}'
                file_metadata = self.rrfconn.get_file_info(filename=safe_filename)
                file_metadata['url'] = g_code_file['url']

                basename = safe_filename  # filename in the response is actually the relative path

                g_code_data = dict(
                    safe_filename=basename,
                    agent_signature='ts:{}'.format(file_metadata['lastModified']),
                    )

                # PATCH /api/v1/octo/g_code_files/{}/ should be called before printer/print/start call so that the file can be properly matched to the server record at the moment of PrintStarted Event
                resp = self.server_conn.send_http_request('PATCH', '/api/v1/octo/g_code_files/{}/'.format(g_code_file['id']), timeout=60, data=g_code_data, raise_exception=True)
                _logger.info(f'uploading "{safe_filename}" finished.')
                self.rrfconn.start_print(filename=filepath_on_rrf)  # start the print
            except:
                self.sentry.captureException()
                raise


        if self.model.printer_state.is_printing():
            return None, 'Printer busy!'

        call_func_with_state_transition(self.server_conn, self.model.printer_state, self.model.printer_state.STATE_GCODE_DOWNLOADING, _download_and_print, MAX_GCODE_DOWNLOAD_SECONDS)
        return {'target_path': g_code_file['filename']}, None


class Printer:

    def __init__(self, model, rrfconn: RepRapFirmware_Connection_Base, server_conn):
        self.model = model
        self.rrfconn = rrfconn
        self.server_conn = server_conn

    def call_printer_api_with_state_transition(self, printer_action, transient_state, timeout=5*60):

        def _call_printer_api():
            resp_data = printer_action()

        call_func_with_state_transition(self.server_conn, self.model.printer_state, transient_state, _call_printer_api, timeout=timeout)

    def resume(self):
        self.call_printer_api_with_state_transition(self.rrfconn.resume_print, self.model.printer_state.STATE_RESUMING)

    def cancel(self):
        self.call_printer_api_with_state_transition(self.rrfconn.cancel_print, self.model.printer_state.STATE_CANCELLING)

    def pause(self):
        self.call_printer_api_with_state_transition(self.rrfconn.pause_print, self.model.printer_state.STATE_PAUSING)

    def jog(self, axes_dict) -> None:
        if not self.rrfconn:
            return None, 'Printer is not connected!'

        self.rrfconn.request_jog(axes_dict, True, 0)
        return None, None

    def home(self, axes) -> None:
        if not self.rrfconn:
            return None, 'Printer is not connected!'

        self.rrfconn.request_home(axes=axes)
        return None, None

    def set_temperature(self, heater, target_temp) -> None:
        if not self.rrfconn:
            return None, 'Printer is not connected!'

        #mr_heater = self.model.config.get_mapped_mr_heater_name(heater)
        #self.moonrakerconn.request_set_temperature(heater=mr_heater, target_temp=target_temp)
        return None, None


class FileOperations:
    def __init__(self, model, rrfconn: RepRapFirmware_Connection_Base, sentry ):
        self.model = model
        self.rrfconn = rrfconn
        self.sentry = sentry


    def check_filepath_and_agent_signature(self, filepath, server_signature):
        file_metadata = None

        try:
            file_metadata = self.rrfconn.get_file_info(filename=filepath)
            filepath_signature = 'ts:{}'.format(file_metadata['lastModified'])
            return filepath_signature == server_signature # check if signatures match -> Boolean
        except Exception as e:
            return False # file has been deleted, moved, or renamed

    def start_printer_local_print(self, file_to_print):
        if not self.rrfconn:
            return None, 'Printer is not connected!'

        ret_value = None
        error = None
        filepath = file_to_print['url']
        file_is_not_modified = self.check_filepath_and_agent_signature(filepath, file_to_print['agent_signature'])

        if file_is_not_modified:
            ret_value = 'Success'
            self.rrfconn.start_print(filename=filepath)
            return ret_value, error
        else:
            error = 'File has been modified! Did you move, delete, or overwrite this file?'
            return ret_value, error
