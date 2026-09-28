# Swarm Architecture Plan

This document outlines the architecture to transition FlyNetSim into a decentralized, peer-to-peer (P2P) mesh network where each drone operates autonomously with its own "brain."

## 1. The "Brain" (Autonomous Control Loop)
Currently, `uav_pubsub.py` is a passive listener waiting for GUI commands. We will change this:
* Inject a **"Brain Thread"** inside the `UAV` class.
* Instead of waiting for a GCS `TAKEOFF` command, the script will automatically arm, take off, and begin executing its programmed logic (e.g., flying to assigned waypoints, sweeping a grid, or flocking).
* Use the existing DroneKit functions (like `goto_position_target_global_int`) to continuously adjust velocity or heading based on swarm logic.

## 2. Peer-to-Peer (P2P) Messaging
Bypass the central GCS entirely so drones can communicate directly:
* Add a new ZMQ Publish/Subscribe pipeline specifically for **Swarm Telemetry**.
* Every drone will **publish** its current GPS coordinates, ID, and status (e.g., "SEARCHING", "TARGET_FOUND").
* Every drone will **subscribe** to this swarm channel. The "Brain" will maintain a live dictionary of where every other drone is in real-time.
* Implement simple swarm rules: e.g., *Collision Avoidance* (if a drone detects a peer within a certain threshold, it alters its course).

## 3. Simulating a True Mesh in ns-3
Currently, the `uav-net-sim.cc` C++ file creates an Infrastructure Wi-Fi network (a central Access Point) or a cellular LTE network. To simulate a real drone swarm network (where drones relay packets for each other):
* Modify the `ns-3` code to switch the Wi-Fi MAC layer from `ApWifiMac/StaWifiMac` to **`AdhocWifiMac`**.
* Install a routing protocol like **OLSR** (Optimized Link State Routing) or **AODV** (Ad hoc On-Demand Distance Vector).
* If Drone 1 wants to message Drone 3 but they are too far apart, the simulated network will realistically hop the message through Drone 2.

## Implementation Steps
1. **Modify `uav_pubsub.py`**: Add the P2P ZMQ sockets and write a simple autonomous "brain" loop that checks neighboring drone locations.
2. **Modify `FlyNetSim.py`**: Change it so it launches the drones without needing the GCS GUI to be active.
3. **Modify `uav-net-sim.cc`**: Replace the Access Point logic with Ad-Hoc Mesh routing for the network simulation.
