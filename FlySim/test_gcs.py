import zmq
import time

context = zmq.Context()
sock = context.socket(zmq.PUB)
sock.bind("tcp://127.0.0.1:5601")

def send_cmd(cmd):
    msg = f"@@@G_000***1***{time.time()}***{cmd}***0***0***"
    sock.send_string(msg)
    print(f"Sent: {cmd}")

time.sleep(1)
send_cmd("COMMAND:CONNECT")
time.sleep(5)
send_cmd("COMMAND:ARM")
time.sleep(20) # wait for EKF and arm
send_cmd("COMMAND:TAKEOFF|ALT=10|MODE=GUIDED|SPEED=10")
