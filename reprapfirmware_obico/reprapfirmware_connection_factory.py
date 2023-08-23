from .reprapfirmware_connection_base import RepRapFirmware_Connection_Base
from .config import Config, RRFConnectionTypes
from .reprapfirmware_connection_http import RepRapFirmware_Connection_HTTP
from .reprapfirmware_connection_serial import RepRapFirmware_Connection_Serial
import logging

_logger = logging.Logger('rrf_factory')

def get_connection(app_config: Config, event) -> RepRapFirmware_Connection_Base:
    if app_config.reprapfirmware.connection_type == 0:
        return RepRapFirmware_Connection_HTTP(app_config, event)
    elif app_config.reprapfirmware.connection_type == 2:
        _logger.info('create Serial connection')
        return RepRapFirmware_Connection_Serial(app_config, event)
    return None
