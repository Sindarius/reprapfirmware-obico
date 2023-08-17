import reprapfirmware_connection_base
from config import Config, RRFConnectionTypes
from reprapfirmware_connection_http import RepRapFirmware_Connection_HTTP
from reprapfirmware_connection_serial import RepRapFirmware_Connection_Serial


def get_connection(app_config: Config) -> reprapfirmware_connection_base:
    if app_config.reprapfirmware.connectiontype == RRFConnectionTypes.HTTP:
        return RepRapFirmware_Connection_HTTP(app_config, None)
    elif app_config.reprapfirmware.connectiontype == RRFConnectionTypes.Serial:
        return RepRapFirmware_Connection_Serial(app_config, None)
    return None
