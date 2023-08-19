from .reprapfirmware_connection_base import RepRapFirmware_Connection_Base
from .config import Config, RRFConnectionTypes
from .reprapfirmware_connection_http import RepRapFirmware_Connection_HTTP
from .reprapfirmware_connection_serial import RepRapFirmware_Connection_Serial


def get_connection(app_config: Config, event) -> RepRapFirmware_Connection_Base:
    if app_config.reprapfirmware.connectiontype == RRFConnectionTypes.HTTP:
        return RepRapFirmware_Connection_HTTP(app_config, event)
    elif app_config.reprapfirmware.connectiontype == RRFConnectionTypes.Serial:
        return RepRapFirmware_Connection_Serial(app_config, event)
    return None
