# Antenna arrays and compact device names

Sionna RT uses one shared `scene.tx_array` for all transmitters and one shared `scene.rx_array` for all receivers. The TX and RX profiles are configured independently in **Simulation Settings > Antenna Arrays**. Devices of the same role cannot use different patterns or array dimensions in one simulation run.

Per-device orientation is encoded in a compact object name:

```text
TX_001__tr38901-4x4-V__look-RX_001
RX_001__iso-1x1-V__look-TX_001
TX_002__dipole-1x1-H__obj
RX_002__iso-1x1-V__rot-90,0,0
```

The compact antenna token is a readable summary of the role-wide array. Runtime array values come from the separate TX/RX controls, including wavelength spacing and polarization model. The orientation token is device-specific and is read from the name at simulation time.

`look-<target>` points Sionna's local positive X-axis toward the evaluated Blender target position for every simulated frame. An isotropic pattern has no directional beam, so changing its orientation does not alter element gain.
