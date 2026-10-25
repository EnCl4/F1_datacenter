# Feature Specification: Car and Race Data

**Feature Branch**: `003-car-and-race-data`

**Created**: 2026-10-24

**Status**: Draft

**Input**: The owner (in Portuguese): show tyre and brake temperatures, battery and fuel,
track-limit excursions, the fight with other cars and tyre wear. *"se tiver mais dados eu
também quero"*: any other useful data too. And one chart showing longitudinal and lateral
acceleration together.

**Context**: Every item below is already in the owner's recordings and was measured on
the reference Interlagos race before this spec was written. Nothing requires re-driving.
The owner's long-term goal is an AI race engineer (not part of this feature), so this data
should also be in a form such an engineer could later reason over.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tyres and Brakes (Priority: P1)

For any session, the driver sees tyre temperature (surface and core), brake temperature
and tyre pressure for all four wheels, lap by lap. Comparing two laps, they also see these
around the lap. Tyre wear per lap is charted too.

**Why this priority**: The owner asked for this first, and it is the data that explains
pace loss over a stint. In the reference race the front tyre cores reached 105–107 °C by
lap 3, a fresh set started at 83 °C after the stop, and the front-right ran hotter than the
front-left on every lap. In the 71-lap race, front-left wear reached 64%.

**Independent Test**: Open the reference race and confirm the front core temperatures
climb across laps 1–3 and drop on the lap after the stop, with each wheel shown separately.

**Acceptance Scenarios**:

1. **Given** a session, **When** the driver opens its car data, **Then** tyre surface and
   core temperature, brake temperature and tyre pressure are shown per lap for each wheel.
2. **Given** a session, **When** tyre wear is shown, **Then** each wheel's wear is shown
   per lap, and the reset at each tyre change is visible.
3. **Given** two laps being compared, **When** the driver looks at temperatures, **Then**
   they are shown around the lap on the same distance axis as the other traces.
4. **Given** any per-wheel value, **When** it is shown, **Then** the wheel is labelled
   (front-left, front-right, rear-left, rear-right) and never inferred from position.

---

### User Story 2 - Battery and Fuel (Priority: P2)

Per lap, the driver sees battery (ERS) charge at the start and end of the lap, energy
deployed and harvested, the ERS mode used, fuel used, and the fuel mix setting.

**Why this priority**: Energy management decides races and is invisible in lap times. In
the reference race the battery fell from 3.9 MJ to 0.09 MJ over five laps: more energy was
deployed than harvested on every lap.

**Independent Test**: Open the reference race and confirm battery charge falls lap by lap
from about 3.9 MJ to under 0.2 MJ, with deployed exceeding harvested.

**Acceptance Scenarios**:

1. **Given** a session, **When** the driver views energy, **Then** battery charge at lap
   start and end, energy deployed and energy harvested are shown per lap.
2. **Given** a lap where more energy was deployed than harvested, **When** it is shown,
   **Then** the deficit is visible.
3. **Given** a session, **When** the driver views fuel, **Then** fuel used per lap and fuel
   remaining are shown.

---

### User Story 3 - Track Limits (Priority: P3)

The driver sees where on the circuit their wheels left the track (onto grass, gravel or
sand), marked on the circuit map, and how many times per lap. Corner-cutting warnings and
penalties appear alongside.

**Why this priority**: This is where time and penalties are lost, and it is cheap, since
the data is already in every frame. In the reference race the best lap was the only racing
lap with no excursions at all; laps 3–5 had between 46 and 120 readings off the track.

**Independent Test**: Open the reference race and confirm lap 2 shows zero excursions
while laps 3–5 show some, located on the map.

**Acceptance Scenarios**:

1. **Given** a lap, **When** the driver views it, **Then** the number of off-track
   excursions is shown, and each excursion is located on the circuit map.
2. **Given** a comparison, **When** one lap went off track and the other did not, **Then**
   the difference is visible on the map and on the traces.
3. **Given** a session, **When** the driver views laps, **Then** corner-cutting warnings
   and penalties are shown per lap.

---

### User Story 4 - Grip Used: Acceleration in One Chart (Priority: P4)

The driver sees lateral and longitudinal acceleration together: a G-G diagram plotting
cornering force against braking/acceleration force for a lap, and a trace with both forces
on one chart. They can see how close to the limit they drove, and where they braked and
turned at the same time.

**Why this priority**: The owner asked for this explicitly. The G-G diagram is the
standard way to see how much grip a driver is using, which separate force traces cannot
show.

**Independent Test**: Open lap 2 of the reference race and confirm the G-G diagram spans
about ±4 g lateral, −4 g braking and +1.6 g acceleration.

**Acceptance Scenarios**:

1. **Given** a lap, **When** the driver opens the G-G diagram, **Then** every sample is
   plotted as cornering force against braking/acceleration force.
2. **Given** two laps being compared, **When** the G-G diagram is shown, **Then** both laps
   appear, distinguishable.
3. **Given** the traces, **When** acceleration is shown, **Then** lateral and longitudinal
   forces share one chart.
4. **Given** a point under the cursor on the traces, **When** the G-G diagram is open,
   **Then** that moment is highlighted on it.

---

### User Story 5 - The Race Around You (Priority: P5)

The driver sees their position over the race, the gap to the car ahead, and how their pace
compared with the whole field: every driver's lap times, best laps and stints, named.

**Why this priority**: "Disputa" was one of the owner's choices, and it answers questions
the driver's own data cannot, such as whether they were slow or the field was fast. The
game provides every car's lap history cheaply, without recording rivals' full telemetry
(consistent with feature 001's scope). In the reference race the driver's best lap ranked
8th of 20, against a fastest lap of 1:10.900.

**Independent Test**: Open the reference race and confirm the field's best laps are
listed with driver names, the driver's best lap ranked 8th of 20.

**Acceptance Scenarios**:

1. **Given** a race, **When** the driver views it, **Then** their position on each lap is
   shown.
2. **Given** a race, **When** the driver views it, **Then** the gap to the car ahead is
   shown along the race.
3. **Given** a session, **When** the driver views the field, **Then** every driver's best
   lap, lap times and tyre stints are shown, named, with the driver's own row
   distinguished.
4. **Given** the field, **When** the driver's best lap is shown, **Then** its rank in the
   field is stated.

---

### User Story 6 - Car Condition, Settings and Strategy (Priority: P6)

The driver sees what changed during the session: damage (wings, floor, gearbox, engine),
in-race setting changes (brake bias, ERS mode, fuel mix), how weather and track
temperature evolved, the game's estimate of how fast each available tyre set would be,
and race events (overtakes, penalties, fastest laps).

**Why this priority**: These are the "other data" the owner asked for. Each explains a lap
time the others cannot. The reference race had 27% front-left wing damage that nothing
currently shows, and brake bias moved from 63% to 57% on laps 3–4.

**Independent Test**: Open the reference race and confirm the 27% front-left wing damage
and the brake-bias change on laps 3–4 are shown on the laps where they occurred.

**Acceptance Scenarios**:

1. **Given** a session with damage, **When** the driver views it, **Then** each damaged
   part is shown with the lap it occurred on.
2. **Given** setting changes during a session, **When** the driver views laps, **Then**
   each lap shows the settings in use, with changes highlighted.
3. **Given** a session, **When** the driver views conditions, **Then** weather and track
   and air temperature are shown over its duration.
4. **Given** a session, **When** the driver views tyre sets, **Then** each available set
   is listed with the game's estimated lap-time difference against the fitted set.
5. **Given** a session, **When** the driver views events, **Then** overtakes, penalties
   and fastest laps are listed with their lap.

---

### Edge Cases

- **Sessions recorded before this feature.** Every new value must come from existing
  recordings by re-ingesting, with no re-driving (as feature 002 did).
- **The pit lane.** Brakes and tyres cool and pressure changes there; values on pit laps
  must be marked, as lap times already are.
- **A tyre change mid-lap** resets wear and temperatures part-way through the lap. Per-lap
  values must not average two different sets into one misleading number.
- **The pit lane surface** is not "off track". Only grass, gravel, sand, mud and rock
  count as excursions.
- **Kerbs and rumble strips** are part of the track and are not excursions.
- **Wet sessions.** On intermediates and wets, temperatures and wear behave differently;
  the compound must be visible beside them.
- **Single-player vs online.** Rival names may be hidden online; the field view must
  still work, with placeholder names.
- **AI cars that retire** stop producing lap history. They must still appear in the field
  with the laps they completed.
- **Battery counters reset at the line.** Per-lap deployed and harvested energy must be
  read before the reset, or the final lap reads as zero (as found on the reference race's
  last lap).
- **Missing samples.** As in feature 002, gaps stay gaps.

## Requirements *(mandatory)*

### Functional Requirements

#### Tyres and brakes

- **FR-001**: System MUST record per lap, for each wheel, tyre surface temperature, tyre
  core temperature, brake temperature and tyre pressure (average and peak).
- **FR-002**: System MUST make tyre temperatures, brake temperatures and pressures
  available around the lap on the same distance axis as the other traces.
- **FR-003**: System MUST chart tyre wear per lap for each wheel.
- **FR-004**: Every per-wheel value MUST be labelled by wheel.
- **FR-005**: Per-lap values MUST NOT combine readings from two different tyre sets.

#### Energy and fuel

- **FR-006**: System MUST record per lap: battery charge at lap start and end, energy
  deployed, energy harvested, ERS modes used, fuel used, fuel remaining and fuel mix.
- **FR-007**: System MUST read per-lap energy counters before they reset at the line.
- **FR-008**: System MUST make the energy balance of each lap (deployed minus harvested)
  visible.

#### Track limits

- **FR-009**: System MUST detect each off-track excursion, meaning any wheel on grass,
  gravel, sand, mud or rock, and record where on the lap it began and how long it lasted.
- **FR-010**: System MUST NOT count kerbs, rumble strips or the pit lane as excursions.
- **FR-011**: System MUST show excursions on the circuit map and count them per lap.
- **FR-012**: System MUST show corner-cutting warnings and penalties per lap.

#### Acceleration

- **FR-013**: System MUST display a G-G diagram of cornering force against
  braking/acceleration force for a lap, with two laps distinguishable when comparing.
- **FR-014**: System MUST display lateral and longitudinal force on a single trace chart.
- **FR-015**: The point under the cursor on the traces MUST be highlighted on the G-G
  diagram.

#### The race around you

- **FR-016**: System MUST record the driver's position per lap and the gap to the car
  ahead along the race.
- **FR-017**: System MUST record every car's lap times, best lap and tyre stints, with
  driver names where the game provides them.
- **FR-018**: System MUST display the field's best laps ranked, with the driver's own row
  distinguished and its rank stated.
- **FR-019**: When names are hidden, the field view MUST still work using placeholders.

#### Condition, settings and strategy

- **FR-020**: System MUST record damage to each part and the lap on which it first
  appeared or increased.
- **FR-021**: System MUST record per lap the brake bias, ERS mode and fuel mix in use, and
  highlight changes.
- **FR-022**: System MUST record weather, track temperature and air temperature over the
  session.
- **FR-023**: System MUST list the available tyre sets with the game's estimated lap-time
  difference against the fitted set.
- **FR-024**: System MUST list race events (overtakes, penalties, fastest laps) with
  their lap.

#### General

- **FR-025**: Every new value MUST be derivable from existing recordings by
  re-processing, without re-driving.
- **FR-026**: New per-lap values MUST be stored, not only drawn, in a form that can be
  queried per lap and per session (so a future analysis, such as the AI engineer, can
  read them).

### Key Entities

- **Lap Car Data**: per lap, the tyre, brake, energy, fuel, settings and damage readings
  for the player's car.
- **Excursion**: one departure from the track: the lap, start distance, length, and
  which wheels.
- **Field Entry**: one rival in a session: name, team, best lap, lap times, stints,
  finishing position.
- **Session Timeline**: how weather and temperatures evolved, plus race events with their
  laps.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every value in this spec is available for the owner's 35 existing sessions
  after one re-ingest, with no re-driving.
- **SC-002**: For the reference race, the values shown match those measured during
  design: front core temperatures 105–107 °C by lap 3; battery 3.9 → 0.09 MJ; zero
  excursions on lap 2; 27% front-left wing damage; brake bias 63 → 57 % on laps 3–4; best
  lap ranked 8th of 20.
- **SC-003**: A driver can find the lap with the most excursions, and where they happened,
  within 15 seconds.
- **SC-004**: A driver can state whether a lap ran an energy deficit within 10 seconds of
  opening a session.
- **SC-005**: Pages with the new data open in under 2 seconds.
- **SC-006**: The new stored data adds no more than 25 MB per hour of driving.

## Assumptions

- **"Acceleration in one chart"** is taken to mean the G-G diagram, plus a single trace
  carrying both forces. The owner asked for lateral and longitudinal together; the G-G
  diagram is the standard view of that in motorsport.
- **Rivals get lap history, not full telemetry.** Consistent with feature 001: the game
  sends every car's lap times and stints cheaply, and the raw recordings keep the rest.
- **Rival names** come from a packet not yet decoded (Participants). Its layout must be
  verified against real bytes before use (constitution principle IV).
- **The player's car only** for temperatures, energy, settings, damage and excursions.
- **No new recording is needed**: the recorder already captures every packet involved.
- **The AI race engineer is out of scope.** FR-026 only ensures the data it would need is
  stored in a queryable form.
