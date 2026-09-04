# Feature Specification: Session Capture & Library

**Feature Branch**: `001-session-capture-library`

**Created**: 2026-09-04

**Status**: Draft

**Input**: User description: "Record a session and see it in the library. Capture the telemetry the game broadcasts, store it durably, turn it into per-lap information, and let the driver browse everything they have driven — with the context needed to know whether two lap times are actually comparable."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One Click Before Playing, Then Forget It (Priority: P1)

Before sitting down to play, the driver performs a single action to start recording. The app immediately and unmistakably tells them it is listening. They then play for as long as they like — one session or ten, practice, qualifying or race — and every one is captured without any further interaction. When they finish, they close it.

**Why this priority**: This is the foundation and the highest-risk part of the whole product. The game broadcasts its telemetry once and never again — there is no replay and no way to recover a session that was not captured. A session missed is lost permanently. Every other feature is built on whatever this story captures, so it must be correct before anything else has value.

Because recording is started deliberately rather than automatically, the cost of forgetting falls on the driver. The design must therefore make starting trivially easy, make the running state obvious at a glance, and make a late start visible rather than silent.

**Independent Test**: Start the recorder with one action, drive several consecutive sessions without touching it again, and confirm each was recorded separately with a measured data-loss figure. Delivers value on its own: sessions are preserved even before any analysis exists.

**Acceptance Scenarios**:

1. **Given** the recorder is not running, **When** the driver starts it with a single action, **Then** it is listening within a few seconds and states so unambiguously.
2. **Given** the recorder is listening, **When** the driver completes several sessions in succession, **Then** each is recorded separately, none truncated or merged, with no further interaction.
3. **Given** the recorder is listening, **When** a session is in progress, **Then** the driver can see which circuit and session type is currently being recorded.
4. **Given** a recording has completed, **When** the driver inspects it, **Then** the proportion of telemetry lost during that session is reported to them.
5. **Given** the game is not running, **When** the recorder is listening, **Then** it consumes negligible resources and creates no empty recordings.
6. **Given** the driver is only navigating menus and never enters a session, **When** the recorder receives that menu activity, **Then** no session appears in the library.
7. **Given** a session is already under way in the game, **When** the driver starts the recorder late, **Then** they are warned that the earlier part of that session was not captured.
8. **Given** the recorder is not running at all, **When** the driver opens the library, **Then** it is clearly indicated that nothing is currently being recorded.

---

### User Story 2 - Browse Everything I Have Driven (Priority: P2)

The driver opens the app and sees every session they have recorded, most recent first. Each entry tells them at a glance where they drove, what kind of session it was, when it happened, what the conditions were, and how fast they went. They can narrow the list down to find a specific past session.

**Why this priority**: This is what converts a pile of recordings into something usable. It is also the feature whose value compounds — a library of 5 sessions is mildly interesting, a library of 500 is the reason the product exists. Under-investing here produces an app full of data the driver cannot navigate.

**Independent Test**: Load the library against previously recorded sessions and confirm every session is listed with correct circuit, type, date, conditions and best lap, and can be found by filtering. Testable against existing recordings without driving anything new.

**Acceptance Scenarios**:

1. **Given** several recorded sessions exist, **When** the driver opens the library, **Then** all sessions are listed most recent first with circuit, session type, date, conditions and best lap time.
2. **Given** a library containing many sessions, **When** the driver filters by circuit, **Then** only sessions at that circuit are shown.
3. **Given** a library containing many sessions, **When** the driver filters by session type or date range, **Then** the list narrows accordingly.
4. **Given** a session that was recorded with significant data loss, **When** it appears in the library, **Then** it is visibly marked as incomplete.
5. **Given** a session that the driver abandoned partway, **When** it appears in the library, **Then** it is distinguishable from a session that ran to its natural end.

---

### User Story 3 - Inspect One Session Lap by Lap (Priority: P3)

The driver opens a single session and sees every lap they drove: the lap time, the sector times, which tyres were on the car and how old they were, whether the lap counted, and whether it was an in-lap, out-lap or a lap under pit conditions. Alongside the laps, they see the context that makes those times mean something — assists, weather, temperatures, fuel and difficulty.

**Why this priority**: This is where lap times become trustworthy rather than merely present. It is also the point at which the comparability rules become visible to the driver, which is what protects every later analysis feature from quietly comparing laps that should never be compared.

**Independent Test**: Open a recorded race session and confirm every lap matches the game's own reported times, with correct tyre, validity, and pit information, and the session context displayed alongside.

**Acceptance Scenarios**:

1. **Given** a recorded session, **When** the driver opens it, **Then** every lap is listed with lap number, lap time and sector times matching what the game reported.
2. **Given** a lap driven on a particular tyre, **When** that lap is displayed, **Then** the tyre compound and its age in laps are shown.
3. **Given** a lap that did not count, **When** it is displayed, **Then** it is marked as not counting, using the rule appropriate to that session type.
4. **Given** a session containing a pit stop, **When** the laps are displayed, **Then** the in-lap, out-lap and pit stop are identifiable.
5. **Given** any session, **When** the driver views it, **Then** the assist configuration, weather, air and track temperature, and difficulty in effect are shown alongside the lap times.
6. **Given** a session where a lap time is longer than one minute, **When** sector times are displayed, **Then** they are correct and not truncated.

---

### Edge Cases

- **A session is interrupted.** The driver quits to the menu mid-session, or the game crashes. The partial recording must remain usable up to the point of interruption and be marked as incomplete rather than discarded or presented as whole.
- **The driver restarts a session.** A restarted race produces a new session. The abandoned attempt and the restarted one must both be preserved and must not be merged, but the abandoned one must be distinguishable so it does not pollute personal-best figures.
- **The driver forgets to start the recorder.** That session is lost permanently and cannot be reconstructed — this is the accepted consequence of manual start. The system must not pretend otherwise: it must never present a partially captured session as complete, and it must make its own running state obvious enough that forgetting is unlikely.
- **The recorder is started midway through a session already in progress.** Whatever remains must still be captured and marked as a partial recording, with the driver told that the earlier portion is missing.
- **Menu activity arrives that belongs to no session.** This must never produce a library entry.
- **Two recordings are attempted at once.** If a second recorder is already listening, the situation must be reported clearly rather than silently capturing nothing.
- **The same recording is processed twice.** Processing a recording again must produce exactly the same result and must never create duplicate sessions in the library.
- **Disk space runs out mid-session.** The driver must be warned before recording degrades, and whatever was captured before the failure must remain usable.
- **A session ends without a normal finish.** A session the driver retires from, or that ends under a red flag, must still be recorded and listed.
- **A recording contains information the app cannot yet interpret.** It must be preserved in full so that a future version can extract it, and its presence must not prevent the rest of the session from being processed.
- **A future version of the game sends an unfamiliar telemetry format.** This must be reported rather than misinterpreted as the known format.
- **A lap runs unusually long** (safety car, damage, a slow circuit). Lap and sector times must remain correct rather than wrapping or overflowing.

## Requirements *(mandatory)*

### Functional Requirements

#### Capture

- **FR-001**: System MUST, once started by the driver, record every session the game broadcasts until the driver stops it, with no further interaction required between sessions.
- **FR-025**: Users MUST be able to start recording with a single action and no configuration, from the desktop and without using a command line.
- **FR-026**: System MUST indicate unambiguously and at all times whether it is currently listening, and while a session is in progress MUST show which circuit and session type is being recorded.
- **FR-027**: System MUST warn the driver when recording is started while a session is already under way, because the earlier part of that session cannot be recovered.
- **FR-028**: System MUST continue recording across any number of consecutive sessions within one run, without requiring the driver to restart or reconfigure it.
- **FR-002**: System MUST preserve the complete, unmodified telemetry stream of every session, including any information the system cannot currently interpret.
- **FR-003**: System MUST measure and report the proportion of telemetry lost during each session.
- **FR-004**: System MUST record sessions to a location outside any cloud-synchronised folder by default, and MUST allow that location to be changed.
- **FR-005**: System MUST warn the driver when remaining storage is insufficient to continue recording safely, before recording quality is affected.
- **FR-006**: System MUST report clearly when it cannot listen for telemetry because another application already is.

#### Interpretation

- **FR-007**: System MUST discard telemetry that does not belong to a real session, so that menu activity never produces a library entry.
- **FR-008**: System MUST identify each session's circuit, session type, start date and time, duration, weather, air temperature, track temperature and difficulty.
- **FR-009**: System MUST record the driver-assist configuration in effect for each session.
- **FR-010**: System MUST divide each session into laps and record each lap's number, lap time and sector times exactly as the game reported them.
- **FR-011**: System MUST record the tyre compound fitted and its age in laps for every lap.
- **FR-012**: System MUST mark each lap as counting or not counting, applying a rule appropriate to the session type rather than a single rule across all session types.
- **FR-013**: System MUST identify in-laps, out-laps, pit stops and laps completed under pit conditions.
- **FR-014**: System MUST distinguish a session that ran to its natural end from one that was abandoned or interrupted.
- **FR-015**: System MUST produce identical results when the same recording is processed more than once, and MUST NOT create duplicate library entries when doing so.
- **FR-016**: System MUST allow any past recording to be re-interpreted without the driver re-driving it.
- **FR-017**: System MUST report, rather than guess at, telemetry in a format it does not recognise.

#### Library

- **FR-018**: Users MUST be able to see all recorded sessions in a single list ordered by most recent first.
- **FR-019**: Each library entry MUST show circuit, session type, date, conditions and best lap time.
- **FR-020**: Users MUST be able to narrow the library by circuit, by session type and by date range.
- **FR-021**: Users MUST be able to open a session and see all of its laps with times, sector times, tyre information and whether each lap counted.
- **FR-022**: System MUST display the comparability context — assists, weather, temperatures, difficulty, fuel and tyre state — alongside any lap time it presents.
- **FR-023**: System MUST visibly mark sessions that were recorded incompletely or with significant data loss.
- **FR-024**: System MUST NOT present a lap time as a personal best when that lap did not count or came from an abandoned session.
- **FR-029**: System MUST indicate in the library when recording is not currently running, so the driver is never misled into believing a session is being captured when it is not.

### Key Entities

- **Recording**: The complete, unaltered telemetry stream captured from one session, together with when it was captured and how much of it was lost. The permanent record from which everything else is derived.
- **Session**: One continuous period of driving at one circuit — its type, date, duration, conditions, difficulty, assist configuration, and how it ended.
- **Lap**: One lap within a session — its number, lap time, sector times, whether it counted, and its role in the session (normal, in-lap, out-lap, under pit conditions).
- **Stint**: A continuous run of laps on one set of tyres, bounded by pit stops — its compound and the laps it covers.
- **Conditions**: The weather, air temperature and track temperature under which a session was driven.
- **Assist Configuration**: The driving aids enabled for a session, which materially change achievable lap times and therefore govern whether two sessions can be compared.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A driver can start recording in a single action, in under 5 seconds, and then complete any number of consecutive sessions without touching the app again — finding each in their library within one minute of leaving it.
- **SC-010**: A driver can tell whether recording is currently active within 2 seconds of looking, without navigating anywhere or interpreting logs.
- **SC-002**: Under normal operation, fewer than 0.1% of telemetry frames are lost in a recorded session.
- **SC-003**: 100% of lap times and sector times shown in the app match the times the game itself reported for those laps.
- **SC-004**: A driver can locate a specific past session, given the circuit and roughly when it happened, in under 15 seconds.
- **SC-005**: Re-processing any recording produces an identical result 100% of the time, with no duplicate library entries.
- **SC-006**: One hour of driving consumes no more than 1.5 GB of storage.
- **SC-007**: The library remains responsive, listing sessions in under 2 seconds, with at least 500 recorded sessions present.
- **SC-008**: No lap that did not count is ever presented as a personal best.
- **SC-009**: Every lap time displayed is accompanied by the context needed to judge whether it is comparable to another.

## Assumptions

- **Single driver, single machine, entirely local.** No accounts, no sharing, no cloud synchronisation, no multi-user support in this feature.
- **One game title.** This feature targets F1 23 only. Support for other titles is out of scope here, though the design must not prevent it (constitution principle III).
- **The player's own car only.** Detailed lap and telemetry information covers the driver's car. Whole-field information is limited to what the game provides cheaply for all cars, and deeper rival analysis is deferred to a later feature.
- **No live view.** This feature is entirely after-the-fact. Nothing is displayed while driving.
- **Telemetry output is enabled in the game** and pointed at this machine at the documented rate and format. Guiding the driver through that setup is assumed to be part of first-run experience but is not itself specified here.
- **Recordings are retained for 90 days by default**, with derived session information retained indefinitely, and the driver able to mark individual sessions to be kept permanently. This keeps storage bounded while preserving the ability to re-interpret recent history.
- **Windows desktop** is the target environment.
- **A previously captured five-lap race recording exists** and serves as the reference fixture for validating interpretation (constitution principle IV).
- **Restarted sessions are recorded separately.** The abandoned attempt is preserved but flagged so it does not contribute to personal bests.

## Resolved Decisions

- **Recorder lifecycle (resolved 2026-09-04)**: The recorder is **started manually by the driver**, once per sitting, and runs until they close it. It does **not** start with Windows and does not run continuously in the background.

  *Alternatives considered*: automatic start with Windows (never misses a session, but always running); a watcher that starts it when the game launches (still requires an always-on process, with more moving parts).

  *Accepted trade-off*: a session driven before the recorder is started cannot be recovered, because the game broadcasts its telemetry only once. This risk is accepted deliberately in exchange for nothing running unless the driver wants it to.

  *Consequent requirements*: because the driver bears the cost of forgetting, the design must reduce both the chance and the cost of it — FR-025 (single action to start), FR-026 (state visible at a glance), FR-027 (warn on a late start), FR-028 (one start covers a whole sitting), FR-029 (library shows when nothing is recording), and SC-010 (state readable within 2 seconds).
