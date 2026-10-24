# Feature Specification: Lap Telemetry Analysis

**Feature Branch**: `002-lap-telemetry-analysis`

**Created**: 2026-10-24

**Status**: Draft

**Input**: User description: "Make the analysis with graphs and with other data, like the velocity, steering and acceleration." Clarified with the owner: acceleration means **both** the throttle pedal and g-forces; all four views are wanted (lap comparison traces, time gained or lost, a track map, lap times across a session); and any two laps should be comparable, across sessions.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare How Two Laps Were Driven (Priority: P1)

The driver picks two laps and sees them overlaid, aligned by position on the track: speed, throttle, brake, steering, gear, engine revs and the forces on the car. Pointing at any spot on one chart shows that same spot on every other chart, for both laps. They can see exactly where they braked later, carried more speed, or got back on the throttle earlier.

**Why this priority**: This is the core of telemetry analysis and the reason the driver asked for the feature. Everything else in this feature is a different view of the same aligned data. It also answers questions a lap time cannot. The reference race shows it: at 2,300 m the driver was 9 km/h faster on lap 5 than on lap 2, in a lower gear, with an extra braking zone. Neither lap time hints at that.

**Independent Test**: Open two laps from the reference Interlagos race and confirm the traces line up by track position, and that a known braking point appears at the same place on both laps.

**Acceptance Scenarios**:

1. **Given** two recorded laps at the same circuit, **When** the driver chooses to compare them, **Then** speed, throttle, brake, steering and gear are shown for both, aligned by distance around the lap.
2. **Given** a comparison is open, **When** the driver points at a place on one chart, **Then** every chart marks that same place on the track and shows both laps' values there.
3. **Given** a comparison is open, **When** the driver zooms into a section of the lap, **Then** every chart zooms to the same section.
4. **Given** a comparison is open, **When** the driver looks at the forces on the car, **Then** cornering force and braking/acceleration force are shown for both laps on the same track-distance alignment.
5. **Given** a lap that did not count (for example the pit lap), **When** the driver selects it, **Then** it can still be compared but is clearly marked with the reason it does not count.
6. **Given** two laps from different sessions, **When** they are compared, **Then** the conditions of each lap are shown side by side, and differences that affect lap time are highlighted.

---

### User Story 2 - See Exactly Where Time Is Gained or Lost (Priority: P2)

Alongside the traces, a single line shows the running time gap between the two laps around the lap. Where it rises, the driver is losing time; where it falls, they are gaining. They can see straight away which corner costs them the most.

**Why this priority**: The traces show *how* the laps differ, and this shows *what that costs*. It is the fastest route from "I am slower" to "I am slower at turn 4". It depends on the aligned data from User Story 1 but adds the most value per unit of effort.

**Independent Test**: Compare laps 2 and 5 of the reference race and confirm the gap at the finish line equals the difference between the two recorded lap times.

**Acceptance Scenarios**:

1. **Given** two laps are being compared, **When** the comparison opens, **Then** a running time gap is shown along the whole lap.
2. **Given** a running time gap, **When** it reaches the finish line, **Then** it equals the difference between the two laps' official times.
3. **Given** no reference lap has been chosen, **When** a session is opened for comparison, **Then** the session's best counting lap is used as the reference by default.
4. **Given** a running time gap, **When** the driver looks at it, **Then** the sections where the most time was lost are easy to identify.

---

### User Story 3 - Pace Across a Session (Priority: P3)

The driver opens a session and sees every lap time plotted in order, with tyre stints marked and laps that did not count visibly distinguished. They can see how pace changed as the tyres aged and where the pit stop fell.

**Why this priority**: It needs no new recorded data, since lap times, stints and exclusion reasons already exist, so it is the cheapest view to deliver. It is also the natural way into lap comparison: spot an odd lap here, then open it in User Story 1.

**Independent Test**: Open the reference race and confirm all five laps appear in order, with the two stints marked and laps 1, 3, 4 and 5 shown as not counting, each with its reason.

**Acceptance Scenarios**:

1. **Given** a recorded session, **When** the driver opens it, **Then** lap times are shown in lap order on one chart.
2. **Given** a session with a pit stop, **When** the chart is shown, **Then** each stint and its tyre compound is visibly marked.
3. **Given** laps that did not count, **When** the chart is shown, **Then** they are distinguished from counting laps and their reason is available.
4. **Given** the pace chart, **When** the driver selects a lap on it, **Then** they can go straight to comparing that lap.

---

### User Story 4 - The Lap on a Map of the Circuit (Priority: P4)

The driver sees an outline of the circuit drawn from where their car actually went, coloured by speed, throttle or brake. The point they are pointing at on the traces also shows on the map, so a spike on a chart can be matched to a corner they recognise.

**Why this priority**: Distance in metres means little to a driver. "Turn 4" means a lot. The map turns chart positions into corners they recognise. It comes last because it depends on position data not yet decoded, and the other stories are useful without it.

**Independent Test**: Open the reference race and confirm the map traces the shape of Interlagos, closes into a loop, and that pointing at a heavy braking zone on the traces marks a corner entry on the map.

**Acceptance Scenarios**:

1. **Given** a recorded lap, **When** the driver opens the map, **Then** the shape of the circuit is drawn from the car's own recorded positions.
2. **Given** the map is shown, **When** the driver chooses to colour it by speed, throttle or brake, **Then** the line is coloured accordingly.
3. **Given** a comparison is open, **When** the driver points at a place on any chart, **Then** the matching place is marked on the map.

---

### Edge Cases

- **Laps from different circuits.** Comparing them is meaningless, since track distance means different places on each. It must not be possible, and the reason must be stated.
- **Sessions recorded before this feature existed.** Their charts must become available by re-processing the existing recordings, without re-driving. The reference Interlagos race is the first case.
- **A session whose original recording was deleted.** Only possible if the driver ran pruning by hand. Its lap times stay available but charts cannot; this must be said plainly rather than shown as empty charts.
- **Packet loss in the middle of a lap.** Short gaps can be bridged; longer gaps must show as gaps rather than invented values. The reference capture contains one 79-frame gap.
- **Laps that start before the line.** Track distance is reported as negative just before the start/finish line on some laps. Those samples must not distort the start of the trace.
- **A flashback in the middle of a lap.** Track position jumps backwards. Only the samples from the lap as finally driven may be used. The project owner never uses flashbacks, but the system must not produce a corrupt trace if one happens.
- **The pit lap.** Part of it is driven in the pit lane, which is a different path from the track. It can be compared but must be marked, and its map line may leave the circuit outline.
- **The first lap of a race.** It starts from the grid, not the line. Its trace starts from a standstill and must be shown as such, not treated as a fault.
- **Laps of very different length.** A lap cut short by retiring or a session ending is incomplete and must not be used as a reference.
- **Two laps where conditions differ.** Different assists, tyres, weather or fuel make a comparison misleading. It is still allowed, but the differences must be visible on the comparison itself (constitution principle VI).

## Requirements *(mandatory)*

### Functional Requirements

#### Recorded channels

- **FR-001**: System MUST record, for every lap of the player's car: speed, throttle, brake, steering, gear, engine revs, DRS state, cornering force, braking/acceleration force, and position on the circuit.
- **FR-002**: System MUST align every channel by distance around the lap, at a resolution of at least one value per metre.
- **FR-003**: System MUST derive these channels for previously recorded sessions by re-processing their existing recordings, without re-driving.
- **FR-004**: System MUST show a gap in the recording as a gap, and MUST NOT invent values across a gap longer than a short bridging threshold.
- **FR-005**: System MUST use only the samples from the lap as finally driven when track position jumps backwards within a lap.
- **FR-006**: System MUST state plainly when a session's charts are unavailable because its original recording no longer exists.

#### Lap comparison

- **FR-007**: Users MUST be able to choose any two laps from any sessions at the same circuit and compare them.
- **FR-008**: System MUST NOT allow laps from different circuits or layouts to be compared, and MUST say why.
- **FR-009**: System MUST display speed, throttle, brake, steering, gear and engine revs as stacked charts sharing one track-distance axis.
- **FR-010**: System MUST display cornering force and braking/acceleration force on the same shared track-distance axis.
- **FR-011**: Pointing at a place on any chart MUST mark that place on every chart and show both laps' values there.
- **FR-012**: Zooming into a section of the lap on any chart MUST zoom every chart to the same section.
- **FR-013**: System MUST mark sector boundaries on the charts.
- **FR-014**: System MUST show the comparability context of both laps side by side (assists, tyre compound and age, fuel, weather, track temperature, difficulty) and MUST highlight where they differ.
- **FR-015**: Users MUST be able to compare a lap that did not count, and the system MUST mark it as not counting, with its reason.

#### Time gained or lost

- **FR-016**: System MUST display the running time gap between the two compared laps along the whole lap.
- **FR-017**: The running time gap at the finish line MUST equal the difference between the two laps' recorded lap times, within a small tolerance.
- **FR-018**: System MUST default the reference lap to the session's best counting lap.
- **FR-019**: System MUST NOT allow an incomplete lap to be chosen as the reference.

#### Pace across a session

- **FR-020**: System MUST display every lap time of a session in lap order on a single chart.
- **FR-021**: The pace chart MUST mark each tyre stint and its compound.
- **FR-022**: The pace chart MUST distinguish laps that did not count and make their reason available.
- **FR-023**: Selecting a lap on the pace chart MUST allow the driver to go straight to comparing it.

#### Circuit map

- **FR-024**: System MUST draw the circuit from the car's own recorded positions, with no external map data.
- **FR-025**: Users MUST be able to colour the map line by speed, throttle or brake.
- **FR-026**: Pointing at a place on any chart MUST mark the matching place on the map.

### Key Entities

- **Lap Trace**: One lap's driving, recorded as a value for each channel at every metre around the circuit, plus the elapsed time at each point. Derived from the recording and regenerable from it.
- **Channel**: One kind of measurement in a trace: speed, throttle, brake, steering, gear, engine revs, DRS, cornering force, braking/acceleration force, or position on the circuit.
- **Comparison**: Two lap traces from the same circuit, one of them the reference, with the running time gap between them and both laps' comparability context.
- **Circuit Outline**: The shape of a circuit, drawn from a recorded lap's positions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A comparison of two laps opens, with every chart drawn, in under 2 seconds.
- **SC-002**: The running time gap at the finish line matches the difference between the two official lap times to within 50 milliseconds.
- **SC-003**: A braking point at the same corner lands within 5 metres of the same track position on two laps of the same circuit.
- **SC-004**: The reference Interlagos race, recorded before this feature existed, shows full charts with no re-driving.
- **SC-005**: Pointing at a chart updates every other chart, and the map, with no lag the driver can perceive.
- **SC-006**: A driver can name the section of the lap where they lost the most time within 30 seconds of opening a comparison.
- **SC-007**: Storing channel data adds no more than 50 MB per hour of driving.
- **SC-008**: No comparison between laps from different circuits can be created.

## Assumptions

- **The player's car only.** Opponents' traces are out of scope; the recording retains them should that change.
- **F1 23, official full-length circuits**, as for feature 001. The project owner drives no short layouts.
- **Desktop browser**, through the existing local library app.
- **One metre** is the alignment resolution. At the 60 Hz send rate the driver uses, the game provides a reading every 0.4–0.9 m through braking zones, so a one-metre grid loses nothing there.
- **Cornering and braking/acceleration forces only.** The vertical force (bumps and kerbs) is recorded in the source data but not charted.
- **The circuit map is a flat top-down outline.** Elevation is not shown.
- **Comparisons are viewed, not saved.** Bookmarking or sharing a comparison is out of scope.
- **The raw recordings of existing sessions are still present.** True for the reference race, because automatic pruning was deliberately left disabled until this feature exists (feature 001, plan: *Deferred by design*).
- **Lap times over a session** reuse the lap times, stints and exclusion reasons feature 001 already derives. No new recorded data is needed for User Story 3.
