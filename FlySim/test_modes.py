import time
from dronekit import connect

print("Connecting...")
vehicle = connect('tcp:127.0.0.1:5760', wait_ready=True)
print("Available modes:")
print(vehicle._flightmode_mapping)
