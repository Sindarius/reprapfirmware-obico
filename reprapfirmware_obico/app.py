from __future__ import absolute_import
from typing import Optional, Dict, List, Tuple
from numbers import Number
import argparse
import dataclasses
import time
import logging
import threading
import collections
import queue
import json
import re
import signal
import backoff
import pathlib

import requests  # type: ignore

from .version import VERSION
from .utils import SentryWrapper, fix_rrf_filename
from .webcam_capture import JpegPoster
from .logger import setup_logging
from .printer import PrinterState
from .config import ServerConfig, Config
from .server_conn import ServerConn
from .janus import JanusConn
from .tunnel import LocalTunnel
from .passthru_targets import FileDownloader, Printer, FileOperations, RepRapFirmwareApi
from  .reprapfirmware_connection_factory import get_connection

_logger = logging.getLogger('obico.app')
_default_int_handler = None
_default_term_handler = None

ACKREF_EXPIRE_SECS = 300


class App(object):

    @dataclasses.dataclass
    class Model:
        config: Config
        remote_status: Dict
        linked_printer: Dict
        printer_state: PrinterState
        seen_refs: collections.deque

        def is_configured(self):
            return True  # FIXME

    def __init__(self):
        self.shutdown = False
        self.model = None
        self.sentry = None
        self.server_conn = None
        self.rrfconn = None
        self.jpeg_poster = None
        self.janus = None
        self.local_tunnel = None
        self.target_file_downloader = None
        self.target__printer = None   # The client would pass "_printer" instead of "printer" for historic reasons
        self.q: queue.Queue = queue.Queue(maxsize=1000)
        self.target_file_operations = None
        self.target_moonraker_api = None # This has to be called this for now because of the server reflective API call

    def push_event(self, event):
        if self.shutdown:
            _logger.debug(f'is shutdown, dropping event {event}')
            return False

        try:
            self.q.put_nowait(event)
            return True
        except queue.Full:
            _logger.error(f'event queue is full, dropping event {event}')
            return False

    @backoff.on_exception(backoff.expo, Exception, max_value=60)
    def wait_for_auth_token(self, args):
        while True:
            config = Config(args.config_path)
            if args.log_path:
                config.logging.path = args.log_path
            if args.debug:
                config.logging.level = 'DEBUG'
            setup_logging(config.logging)

            if config.server.auth_token:
                break

            _logger.warning('auth_token not configured. Retry after 2s')
            time.sleep(2)

        _logger.info(f'starting reprapfirmware-obico (v{VERSION})')
        _logger.info('Fetching linked printer...')
        linked_printer = ServerConn(config, None, None, None).get_linked_printer()
        _logger.info('Linked printer: {}'.format(linked_printer))

        self.model = App.Model(
            config=config,
            remote_status={'viewing': False, 'should_watch': False},
            linked_printer=linked_printer,
            printer_state=PrinterState(config),
            seen_refs=collections.deque(maxlen=100),
        )
        self.sentry = SentryWrapper(config=config)

    def start(self, args):
        # TODO: This doesn't work as ffmpeg seems to mess with signals as well
        # global _default_int_handler, _default_term_handler
        # _default_int_handler = signal.signal(signal.SIGINT, self.interrupted)
        # _default_term_handler = signal.signal(signal.SIGTERM, self.interrupted)

        # Blocking call. When continued, server is guaranteed to be properly configured, self.model.linked_printer existed.
        self.wait_for_auth_token(args)

        _cfg = self.model.config._config
        _logger.debug(f'reprapfirmware-obico configurations: { {section: dict(_cfg[section]) for section in _cfg.sections()} }')
        self.rrfconn = get_connection(self.model.config, self.push_event)
        self.model.printer_state.set_connection(self.rrfconn)  # set the connection to collect printer information
        self.server_conn = ServerConn(self.model.config, self.model.printer_state, self.process_server_msg, self.sentry)
        self.janus = JanusConn(self.model, self.server_conn, self.sentry)
        self.jpeg_poster = JpegPoster(self.model, self.server_conn, self.sentry)
        self.target_file_downloader = FileDownloader(self.model, self.rrfconn, self.server_conn, self.sentry)
        self.target__printer = Printer(self.model, self.rrfconn, self.server_conn)
        self.target_file_operations = FileOperations(self.model, self.rrfconn, self.sentry)
        self.target_moonraker_api = RepRapFirmwareApi(self.model, self.rrfconn, self.sentry)

        self.local_tunnel = LocalTunnel(
            tunnel_config=self.model.config.tunnel,
            on_http_response=self.server_conn.send_ws_msg_to_server,
            on_ws_message=self.server_conn.send_ws_msg_to_server,
            sentry=self.sentry)

        #self.rrfconn.update_webcam_config_from_moonraker()
        self.model.printer_state.thermal_presets = self.rrfconn.find_all_thermal_presets()
        #self.model.printer_state.installed_plugins = self.rrfconn.find_all_installed_plugins()

        thread = threading.Thread(target=self.server_conn.start)
        thread.daemon = True
        thread.start()

        thread = threading.Thread(target=self.rrfconn.start)
        thread.daemon = True
        thread.start()

        jpeg_post_thread = threading.Thread(target=self.jpeg_poster.pic_post_loop)
        jpeg_post_thread.daemon = True
        jpeg_post_thread.start()

        thread = threading.Thread(target=self.event_loop)
        thread.daemon = True
        thread.start()

        # Janus may take a while to start, or fail to start. Put it in thread to make sure it does not block
        janus_thread = threading.Thread(target=self.janus.start)
        janus_thread.daemon = True
        janus_thread.start()

        try:
            thread.join()
        except Exception:
            self.sentry.captureException()

    def stop(self, cause=None):
        if cause:
            _logger.error(f'shutdown ({cause})')
        else:
            _logger.info('shutdown')

        self.shutdown = True
        if self.server_conn:
            self.server_conn.close()
        if self.rrfconn:
            self.rrfconn.close()
        if self.janus:
            self.janus.shutdown()

    # TODO: This doesn't work as ffmpeg seems to mess with signals as well
    def interrupted(self, signum, frame):
        print('Cleaning up moonraker-obico service... Press Ctrl-C again to quit immediately')
        self.stop()

        global _default_int_handler, _default_term_handler

        if _default_int_handler:
            signal.signal(signal.SIGINT, _default_int_handler)
            _default_int_handler = None

        if _default_term_handler:
            signal.signal(signal.SIGTERM, _default_term_handler)
            _default_term_handler = None


    def event_loop(self):
        # processes app events
        # alters state of app
        while self.shutdown is False:
            try:
                event = self.q.get()
                self._process_event(event)
            except Exception:
                self.sentry.captureException(msg=f'error processing event {event}')

    def _process_event(self, event):
        if event.name == 'fatal_error':
            self.stop(cause=event.data.get('exc'))

        elif event.name == 'shutdown':
            self.stop()

        elif event.sender == 'rrfconn':
            self._on_rrfconn_event(event)

    def _on_rrfconn_event(self, event):
        # todo Fix this up for RRF specific data
        # _logger.info("App : RRFCONN EVENT")
        if event.name == 'mr_disconnected':
            # clear app's rrf state to indicate the loss of connection to RRF
            self._received_rrf_update({"status": {}, })

        elif event.name == 'message':
            if 'error' in event.data:
                _logger.warning(f'error response from moonraker, {event}')

            elif event.data.get('result') == 'ok':
                # printer action response
                self.rrfconn.request_status_update()

            elif event.data.get('method', '') == 'notify_status_update':
                # something important has changed,
                # fetching full status
                self.rrfconn.request_status_update()

            elif event.data.get('method', '') == 'notify_history_changed':
                self.rrfconn.request_status_update()

            elif event.data.get('method', '') == 'notify_gcode_response':
                msg = (event.data.get('params') or [''])[0]
                if msg.startswith('!!'):  # It seems to an undocumented feature that some gcode errors that are critical for the users to know are received as notify_gcode_response with "!!"
                    self.server_conn.post_printer_event_to_server('Moonraker Error', msg, attach_snapshot=True)
                    self.server_conn.send_ws_msg_to_server({'passthru': {'terminal_feed': {'msg': msg,'_ts': time.time()}}})
                else:
                    readable_msg = msg.replace('// ', '')
                    self.server_conn.send_ws_msg_to_server({'passthru': {'terminal_feed': {'msg': readable_msg,'_ts': time.time()}}})

        elif event.name == 'status_update':
            # full state update from RRF
            self._received_rrf_update(event.data)

    def set_current_print(self, printer_state):

        def find_current_print_ts():
            cur_job = self.rrfconn.find_most_recent_job()
            cur_job['start_time'] = round(time.time()*1000) + cur_job.get('duration', '0')
            if cur_job:
                return int(cur_job['start_time'])  # todo Chase down what this is doing - RRF does not have a start time built in
            else:
                _logger.error(f'Active job indicate in print_stats: {printer_state.status}, but not in job history: {cur_job}')
                return None

        printer_state.set_current_print_ts(find_current_print_ts())
        filename = printer_state.status.get('job',{}).get('file', {}).get('fileName')
        file_metadata = self.rrfconn.get_file_info(filename=filename)
        printer_state.current_file_metadata = file_metadata

        # So that Obico server can associate the current print with a gcodefile record in the DB
        printer_state.set_obico_g_code_file_id(self.find_obico_g_code_file_id(printer_state.status, file_metadata))

    def unset_current_print(self, printer_state):
        _logger.debug('Unsetting print')
        printer_state.set_current_print_ts(-1)
        printer_state.current_file_metadata = None

#todo This is getitng busted when searching for the file.
    def find_obico_g_code_file_id(self, cur_status, file_metadata):
        time.sleep(1)
        file = cur_status.get('job', {}).get('file', {})
        basename = fix_rrf_filename(file.get('fileName',''))
        if basename == '':
            basename = fix_rrf_filename(file.get('lastFileName',''))
        _logger.info(basename)
        g_code_data = dict(
            safe_filename=basename,
            agent_signature='ts:{}'.format(file_metadata.get('lastModified')),
            )

        resp = self.server_conn.send_http_request('POST', '/api/v1/octo/g_code_files/', timeout=60, data=g_code_data, raise_exception=True)
        return resp.json()['id']


    def post_print_event(self, print_event):
        ts = self.model.printer_state.current_print_ts
        if ts == -1:
            raise Exception('current_print_ts is -1 on a print_event, which is not supposed to happen.')

        _logger.info(f'print event: {print_event} ({ts})')

        self.server_conn.post_status_update_to_server(print_event=print_event)


    def _received_rrf_update(self, data):
        printer_state = self.model.printer_state

        prev_status = printer_state.update_status(data)

        prev_state = PrinterState.get_state_from_status(prev_status)
        cur_state = PrinterState.get_state_from_status(printer_state.status)

        if prev_state != cur_state:
            _logger.info(
                'detected state change: {} -> {}'.format(
                    prev_state, cur_state
                )
            )

        if cur_state == PrinterState.STATE_OFFLINE:
            printer_state.set_current_print_ts(None)  # Offline means actually printing status unknown. It may or may not be printing.
            self.server_conn.post_status_update_to_server()
            return

        if printer_state.current_print_ts is None:
            # This should cover all the edge cases when there is an active job, but current_print_ts is not set,
            # e.g., moonraker-obico is restarted in the middle of a print
            if printer_state.has_active_job():
                self.set_current_print(printer_state)
            else:
                self.unset_current_print(printer_state)

        if cur_state == PrinterState.STATE_PRINTING:
            if prev_state == PrinterState.STATE_PAUSED:
                self.post_print_event(PrinterState.EVENT_RESUMED)
                return
            if prev_state == PrinterState.STATE_OPERATIONAL:
                self.set_current_print(printer_state)
                self.post_print_event(PrinterState.EVENT_STARTED)
                return

        if cur_state == PrinterState.STATE_PAUSED and prev_state == PrinterState.STATE_PRINTING:
            self.post_print_event(PrinterState.EVENT_PAUSED)
            return

        if cur_state == PrinterState.STATE_OPERATIONAL and prev_state in PrinterState.ACTIVE_STATES:
                # todo come up with a better way to check final result here.
                _job = self.rrfconn.find_most_recent_job()  # lets get the final state of the job
                _state = data['state']['status']
                _logger.info(_job)
                _cancelled = prev_state in [PrinterState.STATE_CANCELLING, PrinterState.EVENT_CANCELLED]
                _logger.info(_cancelled)
                if _state == 'cancelled':
                    self.post_print_event(PrinterState.EVENT_CANCELLED)
                    # PrintFailed as well to be consistent with OctoPrint
                    time.sleep(0.5)
                    self.post_print_event(PrinterState.EVENT_FAILED)
                elif _state == 'idle':
                    if _cancelled:
                        self.post_print_event(PrinterState.EVENT_CANCELLED)
                        _logger.info('Print Cancelled')
                        time.sleep(0.5)
                        self.post_print_event(PrinterState.EVENT_FAILED)
                    else:
                        _logger.info("Print Complete")
                        self.post_print_event(PrinterState.EVENT_DONE)
                elif _state == 'error':
                    self.post_print_event(PrinterState.EVENT_FAILED)
                else:
                    # FIXME
                    _logger.error(
                        f'unexpected state "{_state}", please report.')

                self.unset_current_print(printer_state)
                return

        self.server_conn.post_status_update_to_server()

    def process_server_msg(self, msg):
        if 'remote_status' in msg:
            self.model.remote_status.update(msg['remote_status'])
            if self.model.remote_status['viewing']:
                self.jpeg_poster.need_viewing_boost.set()

        if 'commands' in msg:
            _logger.debug(f'Received commands from server: {msg}')

            for command in msg['commands']:
                if command['cmd'] == 'pause':
                    self.target__printer.pause()
                if command['cmd'] == 'cancel':
                    self.target__printer.cancel()
                if command['cmd'] == 'resume':
                    self.target__printer.resume()

        if 'passthru' in msg:
            _logger.debug(f'Received passthru from server: {msg}')

            passthru = msg['passthru']
            ack_ref = passthru.get('ref')
            if ack_ref is not None:
                # same msg may arrive through both ws and datachannel
                if ack_ref in self.model.seen_refs:
                    _logger.debug('Ignoring already processed passthru message')
                    return
                # no need to remove item or check size
                # as deque manages that when maxlen is set
                self.model.seen_refs.append(ack_ref)

            error = None
            try:
                _logger.info(passthru)
                target = getattr(self, 'target_' + passthru.get('target'))
                _logger.info(target)
                _logger.info(passthru['func'])
                func = getattr(target, passthru['func'], None)
                _logger.info(func)
                ret_value, error = func(*(passthru.get("args", [])), **(passthru.get("kwargs", {})))
            except AttributeError:
                error = 'Request not supported. Please make sure moonraker-obico is updated to the latest version. If moonraker-obico is already up to date and you still see this error, please contact Obico support at support@obico.io'
            except Exception as e:
                error = str(e)
                self.sentry.captureException()

            if ack_ref is not None:
                if error:
                    resp = {'ref': ack_ref, 'error': error}
                else:
                    resp = {'ref': ack_ref, 'ret': ret_value}

                self.server_conn.send_ws_msg_to_server({'passthru': resp})

        if msg.get('janus') and self.janus:
            _logger.debug(f'Received janus from server: {msg}')
            self.janus.pass_to_janus(msg.get('janus'))

        if msg.get('http.tunnelv2') and self.local_tunnel:
            kwargs = msg.get('http.tunnelv2')
            tunnel_thread = threading.Thread(
                target=self.local_tunnel.send_http_to_local_v2,
                kwargs=kwargs)
            tunnel_thread.is_daemon = True
            tunnel_thread.start()

        if msg.get('ws.tunnel') and self.local_tunnel:
            kwargs = msg.get('ws.tunnel')
            kwargs['type_'] = kwargs.pop('type')
            self.local_tunnel.send_ws_to_local(**kwargs)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-c', '--config', dest='config_path', required=True,
        help='Path to config file (cfg)'
    )
    parser.add_argument(
        '-l', '--log-file', dest='log_path', required=False,
        help='Path to log file'
    )
    parser.add_argument(
        '-d', '--debug', dest='debug', required=False,
        action='store_true', default=False,
        help='Enable debug logging'
    )
    args = parser.parse_args()
    App().start(args)
