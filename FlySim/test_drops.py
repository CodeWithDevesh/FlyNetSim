import swarm_network
import time
import math

engine = swarm_network.RFPhysicsEngine(tx_power_dbm=30, frequency_ghz=5)
brokers = {
    "000": swarm_network.EdgeBroker("000", engine),
    "001": swarm_network.EdgeBroker("001", engine),
    "002": swarm_network.EdgeBroker("002", engine)
}

# Everyone subscribes to telemetry
for b_id, broker in brokers.items():
    for target in brokers:
        if target != b_id:
            broker.update_neighbor_subscription(target, set(["telemetry"]))

# Start at origin
locs = {
    "000": {'lat': 0.0, 'lon': 0.0},
    "001": {'lat': 0.0, 'lon': 0.0},
    "002": {'lat': 0.0, 'lon': 0.0}
}

print("=== STARTING SWARM FLIGHT SIMULATION ===")
for t in range(0, 15):
    print(f"\n--- Time: {t*2}s ---")
    # Move them apart at 20 m/s each
    locs["000"]['lat'] += (20 / 1.113195e5)
    locs["001"]['lon'] += (20 / 1.113195e5)
    locs["002"]['lat'] -= (15 / 1.113195e5)
    locs["002"]['lon'] -= (15 / 1.113195e5)
    
    # Each drone publishes
    for uav_id, broker in brokers.items():
        payload = "telemetry_data"
        msg_id = f"MSG_{uav_id}_{t}"
        # We simulate obstacle_mask randomly true
        targets = broker.publish("telemetry", payload, msg_id, locs[uav_id], locs, obstacle_mask=True)
