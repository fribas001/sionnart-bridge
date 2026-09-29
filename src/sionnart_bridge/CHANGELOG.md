# 2.0.0

This release consolidates procedural simulation, vegetation measurement and parameter analysis with a broader workflow regression suite.

## Reliability fixes

- Isolated Windows workers now flush their streams and exit through a shared process-exit routine. This avoids the reproducible Mitsuba/Dr.Jit DLL-detach crash while preserving success/failure codes. Runtime probes use the same routine.
- Nonzero worker exits are rejected and diagnostic files retained.
- Completed workers remain owned until their outputs have been consumed; all run operators check every simulation category.
- Added Stop Simulation. Cancellation clears queued outputs, retains partial files and releases the owned run lock. File loading and extension disabling stop owned workers.
- Zero-path solutions retain an empty embedded result and complete parameter observations; gain is unavailable rather than an invented finite floor.
- Optional curve import no longer removes the embedded paths result or unrelated objects in its collection.
- A later successful batch output no longer hides an earlier output failure. Failed/cancelled receipts are never recovered as successful.
- Live movement detection now uses original Blender object identities consistently, fixing a missed first movement when dependency-graph updates contain evaluated IDs.
- New scenes refresh static geometry by default; intentional cache reuse has a visible reminder.

## Included scientific workflow

Per-frame Geometry Nodes metadata, parameter plots and descriptive statistics, vegetation measurements, reference leaf/wood materials, 2D/projected/stacked radio maps, antenna arrays, device motion and Doppler are retained. Optional sensing is retained, disabled by default and covered by a self-contained test. RIS and crowd integrations remain excluded.

The extension identifier and existing result schemas remain compatible with the preceding release. No existing simulation data or Blender project is modified by installing this ZIP. Defaults stored in an older project retain their saved values.
