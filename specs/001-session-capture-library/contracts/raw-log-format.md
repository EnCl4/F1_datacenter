# Contract: Raw Log Format (`.f1raw`)

**Status**: Stable — this is the system of record. Changes are breaking and require a format
version bump plus a reader that handles both.

The raw log is the one artifact that cannot be regenerated. Its format is deliberately the
simplest thing that preserves everything and can be written without parsing.

## File header

16 bytes, written once when the file is created.

| Offset | Size | Type | Value |
|---:|---:|---|---|
| 0 | 8 | bytes | Magic `F1DCRAW\x00` |
| 8 | 2 | uint16 LE | Format version, currently `1` |
| 10 | 2 | uint16 LE | UDP port listened on |
| 12 | 4 | uint32 LE | Reserved, zero |

## Records

Repeated to end of file. No index, no trailer — a truncated file is readable up to its last
complete record, which is what makes an interrupted capture usable (spec edge case).

| Size | Type | Field |
|---:|---|---|
| 4 | uint32 LE | Datagram length in bytes |
| 8 | float64 LE | Receive timestamp, monotonic seconds since capture start |
| *n* | bytes | **The datagram, byte-for-byte, unmodified** |

The monotonic timestamp is what allows a capture to be replayed with original timing and
makes inter-packet gaps measurable after the fact.

## Guarantees

1. **Nothing is filtered.** Every datagram received on the port is written, including
   packet types this software cannot decode, malformed datagrams, and `sessionUID == 0`
   menu traffic. Filtering happens at ingest, never at capture (principle I).
2. **Nothing is transformed.** No byte-order conversion, no field extraction, no
   compression while writing (principle II, R4).
3. **Append-only.** The writer never seeks backwards. A reader may safely read a file that
   is still being written.
4. **One file per session boundary.** The recorder starts a new file when `sessionUID`
   changes. Records with `sessionUID == 0` are written to the file currently open, and
   discarded later by ingest.

## Compression

After a session closes, ingest compresses the file to `.f1raw.zst` (zstandard, level 10) and
removes the original only after the compressed file is verified readable. Compression is
never performed by the recorder.

## Naming

```text
<ISO8601 capture start, colons replaced by hyphens>_<sessionUID>.f1raw[.zst]
2026-09-04T11-04_15975277775803518192.f1raw.zst
```

## Packet header within each datagram

Not part of this contract — it is the game's format — but stated here because every reader
needs it. 29 bytes, little-endian, packed:

```text
uint16 packetFormat      uint8  gameYear         uint8  gameMajorVersion
uint8  gameMinorVersion  uint8  packetVersion    uint8  packetId
uint64 sessionUID        float  sessionTime      uint32 frameIdentifier
uint32 overallFrameIdentifier   uint8 playerCarIndex  uint8 secondaryPlayerCarIndex
```

`frameIdentifier` resets on a flashback while `overallFrameIdentifier` does not; their
divergence is an exact flashback signal requiring no heuristics.
