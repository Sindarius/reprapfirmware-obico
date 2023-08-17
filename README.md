# Obico for RepRapFirmware

This is a RepRapFirmware plugin that enables the RepRapFirmware-based 3D printers to connect to Obico.

[Obico](https://www.obico.io) is a community-built, open-source smart 3D printing platform used by makers, enthusiasts, and tinkerers around the world.


# Installation

    cd ~
    git clone https://github.com/TheSpaghettiDetective/moonraker-obico.git
    cd moonraker-obico
    ./install.sh

[Detailed documentation](https://obico.io/docs/user-guides/klipper-setup/).


# Uninstall

    sudo systemctl stop moonraker-obico.service
    sudo systemctl disable moonraker-obico.service
    sudo rm /etc/systemd/system/moonraker-obico.service
    sudo systemctl daemon-reload
    sudo systemctl reset-failed
    rm -rf ~/moonraker-obico
    rm -rf ~/moonraker-obico-env


# Set up a dev environment

    cd ~
    git clone https://github.com/TheSpaghettiDetective/moonraker-obico.git
    cd moonraker-obico
    virtualenv -p /usr/bin/python3 --system-site-packages ~/moonraker-obico-env
    source ~/moonraker-obico-env/bin/activate
    pip3 install -r requirements.txt

    # fill in essential configuration
    cp moonraker-obico.cfg.sample moonraker-obico.cfg

    # link printer (grab Obico auth token)
    python3 -m moonraker_obico.link -c moonraker-obico.cfg

    # start app
    python3 -m moonraker_obico.app -c moonraker-obico.cfg
