# Obico for RepRapFirmware

**If running Duet Software Framework (SBC) then version 3.5-beta4 or greater is required**

This is a RepRapFirmware plugin that enables the RepRapFirmware-based 3D printers to connect to Obico.

[Obico](https://www.obico.io) is a community-built, open-source smart 3D printing platform used by makers, enthusiasts, and tinkerers around the world.

 [RepRapFirmware](https://github.com/Duet3D/RepRapFirmware/wiki) RepRapFirmware is a comprehensive motion control firmware intended primarily for controlling 3D printers, but with applications in laser engraving/cutting and CNC too

# Installation

    cd ~
    git clone https://github.com/sindarius/reprapfirmware-obico.git
    cd reprapfirmware-obico
    ./install.sh

### If you get a virtualenv error do the following
#### 1) Install virtualenv
    pip install virtualenv
#### 2) Modify the path in ~/.profile
    sudo nano ~/.profile
#### 3) Add the following line at the end of the file
    PATH="$PATH:$HOME/.local/bin"
#### 4) Log out of SSH/Console and rerun installation

# Installation of Crowsnest (May not work on current DSF image_2023-04-12-DuetPi)
I recommend installation of Crowsnest to get the webcam stream up and running

    cd ~
    git clone https://github.com/mainsail-crew/crowsnest.git
    cd ~/crowsnest
    sudo make install

# Installation of uStreamer (Alternative to Crowsnest)

    git clone --depth=1 https://github.com/pikvm/ustreamer
    cd ustreamer
    sudo apt install libevent-dev libjpeg9-dev libbsd-dev libasound2-dev libspeex-dev libspeexdsp-dev libopus-dev
    sudo make install

### Create uStreamer user and service

    sudo useradd -r ustreamer
    sudo usermod -a -G video ustreamer

#### Modify/create ustreamer.service
    sudo nano /etc/systemd/system/ustreamer.service

#### Copy following to ustreamer.service and save.

You may need to update /dev/video0 to match camera device

    [Unit]
    Description=uStreamer service
    After=network.target
    [Service]
    User=ustreamer
    ExecStart=/usr/local/bin/ustreamer --log-level 0 --device /dev/video0 --desired-fps=25 --host=0.0.0.0 --port=8080
    [Install]
    WantedBy=multi-user.target

### Enable and start uStreamer service
    sudo systemctl enable ustreamer.service
    sudo systemctl start ustreamer.service

### Restart service

# Updating

    cd ~/reprapfirmware-obico
    ./install.sh -U

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
    cp reprapfirmware-obico.cfg.sample reprapfirmware-obico.cfg

    # link printer (grab Obico auth token)
    python3 -m reprapfirmware_obico.link -c reprapfirmware-obico.cfg

    # start app
    python3 -m reprapfirmware_obico.app -c reprapfirmware-obico.cfg

# Raspberry Pi Camera
You may have to use `sudo raspi-config` to enable the raspberry pi camera.

# Notes

    Configuration files are located in ~/printer_data/config
