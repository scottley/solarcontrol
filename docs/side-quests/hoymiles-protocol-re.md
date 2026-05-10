# Side Quest: Reverse-Engineer the Hoymiles DTU "Get Economy Schedule" Call

## Why
The `hoymiles-wifi` Python library lets us **write** an Economy schedule to the inverter but not **read** the current one. Without a read path, solarcontrol's Prepper Mode can't snapshot-and-restore the user's existing schedule when toggling modes — we'd have to hand-maintain it in `config.py`. The S-Miles iPhone app reads the schedule, so the protocol almost certainly supports it; the library just doesn't implement it.

## Goal
Add `async_get_energy_storage_user_set()` (and ideally other missing reads) to a fork of `suaveolent/hoymiles-wifi`, then upstream a PR. Side benefit: many other DTU operations in `CMD_ACTION_*` aren't exposed either — anything found is a building block for future features.

## What we know
- `hoymiles-wifi` v0.5.6, upstream at https://github.com/suaveolent/hoymiles-wifi
- DTU runs its own Wi-Fi AP; iPhone S-Miles app connects directly to it. No LAN traffic to sniff via the main router.
- DTU is also reachable on the home LAN at `192.168.1.5` — both paths likely speak the same protocol.
- Library has `crypt_util.py` with `is_encrypted_dtu` checks — there's an app-layer encryption step we may need to apply when decoding captures.
- Existing CMD codes in `const.py`: `CMD_ES_USER_SET_RES_DTO = b"\xc3\x08"` is the WRITE; no corresponding READ defined.
- Protobuf module `ESUserSet_pb2` has `ESUserSetPutReqDTO` / `ESUserSetPutResDTO` (the WRITE pair). The READ pair is presumably similar but not present.

## Approach (ordered by effort)
1. **APK decompile (Tier 1)** — grab the S-Miles Android APK from APKMirror, `jadx-gui` it, search for `ESUserSet`, hex `0xc3`/`0xa3`, etc. Likely reveals the missing CMD byte and the message type. Cheapest path. ~30–60 min.
2. **rvictl on Mac (Tier 2)** — plug iPhone into Mac, `rvictl -s <UDID>`, `tcpdump -i rvi0 -w hoymiles.pcap host <DTU>`, open S-Miles app to the Economy page. Decode with the existing `.proto` files in Wireshark. Apply library's decrypt step if traffic is encrypted. Use only if Tier 1 is ambiguous.
3. **CMD-code fuzzer (Tier 3)** — script using the existing library that walks unknown `\xc3\xXX` / `\xa3\xXX` values and logs anything that comes back. Cheap and may stumble onto the answer fast.

## Workspace structure
- New Cowork-selected folder pointing at a fresh local clone of a personal fork (`scottley/hoymiles-wifi`), separate from `solarcontrol/`.
- Fresh conversation — don't carry solarcontrol context across.
- Branch `add-es-user-set-read` for the upstream-bound work.
- `docs/` or `research/` folder for `.pcap`s, APK decompile notes, fuzzer output — not for upstream merge.

## Model
- **Opus** for the discovery phase (binary/protocol analysis, hypothesis generation).
- **Sonnet** once the protocol is mapped, for implementing the method + tests.
- Switch mid-conversation.

## Definition of done
A merged-or-pending PR upstream adding (at minimum) `async_get_energy_storage_user_set()`. Then in this repo: bump `hoymiles-wifi` to the new version, replace the hand-maintained `ECONOMY_SCHEDULE` with a runtime capture from the inverter, and the Prepper Mode auto-revert path uses real data.

## Bridge back to solarcontrol
While the side quest runs, solarcontrol can proceed with **option B** (hand-maintained `ECONOMY_SCHEDULE`) so Prepper Mode ships now. When the read method lands upstream, we swap the snapshot source from "hand-maintained" to "captured-at-startup" without changing the Prepper state machine.
