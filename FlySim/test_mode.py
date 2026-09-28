import time
from dronekit import connect, VehicleMode

print("Connecting...")
vehicle = connect('tcp:127.0.0.1:5760', wait_ready=True)

print("Waiting for is_armable...")
while not vehicle.is_armable:
    time.sleep(1)

print("Setting mode to GUIDED...")
vehicle.mode = VehicleMode("GUIDED")
time.sleep(2)

print("Arming...")
vehicle.armed = True
while not vehicle.armed:
    time.sleep(1)
print("Armed successfully!")

print("Taking off...")
vehicle.simple_takeoff(10)
for i in range(15):
    print("Alt:", vehicle.location.global_relative_frame.alt)
    time.sleep(1)
