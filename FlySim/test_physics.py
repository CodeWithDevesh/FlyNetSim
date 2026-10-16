import swarm_network
eng = swarm_network.RFPhysicsEngine()
loc_a = {'lat': 0, 'lon': 0}
# 100 meters away approx
loc_b = {'lat': 100 / 1.113195e5, 'lon': 0}
snr, per = eng.calculate_snr_per(loc_a, loc_b)
print(f"SNR: {snr:.2f}, PER: {per:.2f}")
