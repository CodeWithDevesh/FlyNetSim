#!/bin/bash

# Clone and init ardupilot if not already done
if [ ! -d "ardupilot" ]; then
    git clone https://github.com/ArduPilot/ardupilot
    cd ardupilot
    git submodule update --init --recursive
    cd ..
fi

cd ardupilot
./Tools/environment_install/install-prereqs-arch.sh -y

cd ..

# Create virtual environment instead of system-wide install
echo "Setting up Python virtual environment..."
python -m venv venv
source venv/bin/activate
pip install wheel
pip install dronekit dronekit-sitl pyzmq PyQt5

