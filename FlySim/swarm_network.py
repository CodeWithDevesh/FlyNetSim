import math
import random
import time
from collections import defaultdict, deque

class RFPhysicsEngine:
    def __init__(self, tx_power_dbm=30, frequency_ghz=5, noise_floor_dbm=-90):
        self.tx_power_dbm = tx_power_dbm
        self.frequency_ghz = frequency_ghz
        self.noise_floor_dbm = noise_floor_dbm
        self.d0 = 1.0  # reference distance (1 meter)
        
        # Free space path loss at 1m for 5GHz is approx 46.4 dB
        self.pl_d0 = 20 * math.log10(self.d0) + 20 * math.log10(self.frequency_ghz * 1000) - 27.55
        self.path_loss_exponent = 2.5  # Urban/Suburban kinetic environment
        self.shadow_fading_std_dev = 4.0 # Log-normal fading standard deviation (dB)
        self.obstacle_attenuation_db = 15.0 # Concrete/Steel penalty

    def check_nlos(self, loc_a, loc_b, obstacle_mask):
        """
        Check if the line of sight between loc_a and loc_b intersects an obstacle.
        In a real implementation, this would use Bresenham's line algorithm on the 2D obstacle_mask grid.
        For now, we mock it: 10% chance of NLoS if distance > 50m.
        """
        if not obstacle_mask:
            return False
        dist = self.calculate_euclidean_distance(loc_a, loc_b)
        if dist > 50 and random.random() < 0.1:
            return True
        return False

    def calculate_euclidean_distance(self, loc_a, loc_b):
        """ Approximate distance in meters between two lat/lon dictionaries. """
        dlat = loc_b['lat'] - loc_a['lat']
        dlon = loc_b['lon'] - loc_a['lon']
        # Rough approximation for small distances
        return math.sqrt(dlat**2 + dlon**2) * 1.113195e5

    def calculate_snr_per(self, loc_a, loc_b, obstacle_mask=None):
        """ Calculate SNR and map it to a Packet Error Rate (PER). """
        dist = self.calculate_euclidean_distance(loc_a, loc_b)
        dist = max(dist, self.d0)

        # Log-Distance Path Loss
        pl = self.pl_d0 + 10 * self.path_loss_exponent * math.log10(dist / self.d0)
        
        # Shadow Fading
        shadowing = random.gauss(0, self.shadow_fading_std_dev)
        pl += shadowing

        # NLoS Attenuation
        if self.check_nlos(loc_a, loc_b, obstacle_mask):
            pl += self.obstacle_attenuation_db

        # Signal-to-Noise Ratio
        rx_power_dbm = self.tx_power_dbm - pl
        snr_db = rx_power_dbm - self.noise_floor_dbm

        # Translate SNR to PER using a sigmoid approximation (Waterfall curve)
        # Assuming QAM modulation where SNR < 10dB drops almost everything, SNR > 20dB is perfect.
        if snr_db > 25:
            per = 0.0
        elif snr_db < 5:
            per = 1.0
        else:
            # Smooth transition between 5dB and 25dB
            per = 1.0 - (1.0 / (1.0 + math.exp(-0.5 * (snr_db - 15))))
        
        return snr_db, per


class EdgeBroker:
    def __init__(self, node_id, physics_engine):
        self.node_id = node_id
        self.physics_engine = physics_engine
        
        # DMLT Topic Subscription Table: dict[neighbor_id] -> set(topics)
        self.neighbor_subscriptions = defaultdict(set)
        
        # QoS 1 Store-and-Forward Buffers: dict[neighbor_id] -> deque(payloads)
        self.qos1_buffers = defaultdict(deque)
        
        # Local state storage
        self.local_subscriptions = set(["map_sync", "telemetry"])
        self.received_messages = set()

    def update_neighbor_subscription(self, neighbor_id, topics):
        """ DMLT Phase: Nodes advertise what topics they care about. """
        self.neighbor_subscriptions[neighbor_id].update(topics)

    def publish(self, topic, payload, message_id, my_loc, swarm_locations, obstacle_mask=None):
        """ 
        Attempt to broadcast a message to physical neighbors. 
        Enforces DMLT routing and QoS 1 buffering.
        Returns a list of neighbor_ids that successfully passed the PER physics check.
        """
        if message_id in self.received_messages:
            return [] # Prevent infinite routing loops
        
        self.received_messages.add(message_id)
        
        # Flush existing buffers first if connections are restored
        flushed_deliveries = self.flush_buffers(my_loc, swarm_locations, obstacle_mask)
        successful_targets = set(flushed_deliveries)

        # Attempt delivery to all physical neighbors
        for neighbor_id, neighbor_loc in swarm_locations.items():
            if neighbor_id == self.node_id:
                continue
            
            # DMLT Routing Check
            if topic not in self.neighbor_subscriptions.get(neighbor_id, set()):
                # Suppress packet: neighbor is not subscribed to this topic
                continue

            if self._attempt_delivery(neighbor_id, my_loc, neighbor_loc, topic, payload, message_id, obstacle_mask):
                successful_targets.add(neighbor_id)
                
        return list(successful_targets)

    def _attempt_delivery(self, neighbor_id, my_loc, neighbor_loc, topic, payload, message_id, obstacle_mask):
        """ Handle the physics check and QoS 1 queuing. Returns True if successful. """
        snr, per = self.physics_engine.calculate_snr_per(my_loc, neighbor_loc, obstacle_mask)
        
        # Roll against the Packet Error Rate probability
        if random.random() >= per:
            print(f"[{self.node_id}] Delivered {message_id} to {neighbor_id} (SNR: {snr:.1f}dB)")
            return True
        else:
            # FAILURE: Hard packet drop. Buffer for QoS 1 delivery.
            print(f"[{self.node_id}] DROP {message_id} to {neighbor_id} (PER: {per:.2f}). Buffering.")
            self.qos1_buffers[neighbor_id].append({
                'topic': topic,
                'payload': payload,
                'message_id': message_id,
                'timestamp': time.time()
            })
            return False

    def flush_buffers(self, my_loc, swarm_locations, obstacle_mask):
        """ Attempt to synchronize buffered QoS 1 packets when link is restored. """
        flushed_targets = []
        for neighbor_id, buffer in list(self.qos1_buffers.items()):
            if not buffer or neighbor_id not in swarm_locations:
                continue
                
            neighbor_loc = swarm_locations[neighbor_id]
            snr, per = self.physics_engine.calculate_snr_per(my_loc, neighbor_loc, obstacle_mask)
            
            if per < 0.2: # Link is highly stable again
                # Flush the queue (In integration, we return the targets to be rebroadcast)
                flushed_targets.append(neighbor_id)
                print(f"[{self.node_id}] FLUSHED {len(buffer)} buffered msgs to {neighbor_id}")
                buffer.clear()
        return flushed_targets
