# Obico for RepRapFirmware

This is a RepRapFirmware plugin that enables the RepRapFirmware-based 3D printers to connect to Obico.

[Obico](https://www.obico.io) is a community-built, open-source smart 3D printing platform used by makers, enthusiasts, and tinkerers around the world.


# Installation

    cd ~
    git clone https://github.com/sindarius/reprapfirmware-obico.git
    cd reprapfirmware-obico
    ./install.sh

[Detailed documentation](https://obico.io/docs/user-guides/klipper-setup/).


# Uninstall

    sudo systemctl stop reprapfirmware-obico.service
    sudo systemctl disable reprapfirmware-obico.service
    sudo rm /etc/systemd/system/reprapfirmware-obico.service
    sudo systemctl daemon-reload
    sudo systemctl reset-failed
    rm -rf ~/reprapfirmware-obico
    rm -rf ~/reprapfirmware-obico-env


# Set up a dev environment

    cd ~
    git clone https://github.com/sindarius/reprapfirmware-obico.git
    cd reprapfirmware-obico
    virtualenv -p /usr/bin/python3 --system-site-packages ~/reprapfirmware-obico-env
    source ~/reprapfirmware-obico-env/bin/activate
    pip3 install -r requirements.txt

    # fill in essential configuration
    cp moonraker-obico.cfg.sample moonraker-obico.cfg

    # link printer (grab Obico auth token)
    python3 -m reprapfirmware_obico.link -c moonraker-obico.cfg

    # start app
    python3 -m reprapfirmware_obico.app -c moonraker-obico.cfg
