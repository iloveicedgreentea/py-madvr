# madVR Envy Python library

Async IP control and notifications for madVR Envy. Requires Python 3.11 or later.

```sh
pip install py-madvr2
```

The [Home Assistant custom component](https://github.com/iloveicedgreentea/madvr-envy-homeassistant)
bundles its own copy of this library. It does not require a separate pip install.

## Usage

```python
from pymadvr.madvr import Madvr

madvr = Madvr("192.168.1.100")
try:
    await madvr.open_connection()
    response = await madvr.send_command(["GetMacAddress"])
    await madvr.send_command(["KeyPress", "MENU"])
finally:
    await madvr.close_connection()
```

`open_connection()` starts notification, heartbeat, refresh, power-monitoring,
and command-queue tasks. `close_connection()` stops them and closes sockets.
`send_command()` sends immediately; queued controls run in FIFO order.

## Controls

Pass command arguments as separate strings, such as `["KeyPress", "UP"]`.
Legacy comma-separated calls such as `["KeyPress, UP"]` also work. The
[Envy IP control reference](https://madvr.com/EnvyIpControl.pdf) lists command IDs
and option paths.

Convenience methods cover:

- Remote keys: `press_key("UP")`, `hold_key("UP")`, or `send_key("UP", hold=True)`.
- Menus: `open_menu("Profiles")` and `close_menu()`.
- Aspect ratio: `set_aspect_ratio_mode("Auto")`, `"Hold"`, or a documented fixed ratio.
- Profiles: `activate_profile("SOURCE", 2)` or `activate_profile("1", 2)` for a custom group.
- Options: `query_option(path)`, `change_option(path, value)`, and `inherit_option(path)`.
- On-screen text: `display_message(seconds, text)`, `display_alert(text)`, and `close_alert()`.
- Volume overlays: `display_audio_volume(minimum, current, maximum, unit)`,
  `display_audio_mute()`, and `close_audio_mute()`.
- Temporary demo controls: `toggle("ToneMap")`.

The command API also accepts profile creation, renaming, enumeration, and page
membership commands; settings/configuration page enumeration; and option
enumeration. File transfers, calibration deletion, and password-bearing settings
commands are not included.

`KeyHold` sends one Envy long-press event. It does not repeat navigation while
a button stays down. A dashboard must send repeated `KeyPress` commands for
that behavior. Physical Envy hold behavior has not been verified for this beta.

## Breaking changes in 2.0

- Python 3.11 or later is now declared as the minimum, matching the existing
  `asyncio.timeout_at()` calls.
- Command names and arguments reject CR, LF, NUL, and embedded double quotes
  with `ValueError`. Pass one command per call.
- `display_message()` rejects negative durations. `display_audio_volume()`
  rejects values outside `minimum <= current <= maximum`.

The existing `display_audio_volume(channel, current, max_vol, unit)` keyword names
remain supported; `channel` is the minimum value despite its name. Text parameters
containing spaces are quoted during encoding.

## Tests and beta releases

```sh
python -m pip install -r requirements-test.txt
python -m pytest tests/test_MadVR.py tests/test_command_construction.py tests/test_notifications.py -q
```

Run the separate `test_simple_integration.py`, `test_connection_pool.py`, and
`test_power_integration.py` files only against a real Envy. They use `MADVR_HOST`
and `MADVR_PORT`; the power tests also use `MADVR_MAC` and can shut the device down.

Version `2.0.0b1` is a prerelease. GitHub prereleases skip the PyPI publishing
job. A stable GitHub release or a manual workflow dispatch still publishes.
