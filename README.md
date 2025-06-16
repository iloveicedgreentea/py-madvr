# MadVR Envy Python Library

This library implements the IP control specification for madVR Envy.

It supports real time notifications and commands asynchronously. It is intended to be used with my official Home Assistant integration ([madvr](https://www.home-assistant.io/integrations/madvr/))

## Wake On Lan

If the client is initialized without a mac, it will assume you provide your own wake on lan automation. Standby does not respond to pings so you may as well do a full power off. You may also provide a mac when you call the power on function.

## Commands

Command structure follows the same in the manual https://madvrenvy.com/wp-content/uploads/EnvyIpControl.pdf?r=112a

For things that take values, use a comma -> `["KeyPress, MENU"]`

Not every single command is implemented, such as submenus or changing complicated options. You can use commands for all the typical stuff the remote can do.

## Typing

This module uses mypy with strict typing.

## Display Commands

```python

async def demo_display_commands():
    """Demonstrate the new display commands."""

    # Initialize MadVR connection
    madvr = Madvr("192.168.1.100")  # Replace with your MadVR IP

    try:
        # Connect to MadVR
        await madvr.open_connection()

        # Display a message for 3 seconds
        await madvr.display_message(3, "Hello from Python!")
        await asyncio.sleep(4)  # Wait for message to clear

        # Display audio volume control (0-100%, currently at 75%)
        await madvr.display_audio_volume(0, 75, 100, "%")
        await asyncio.sleep(3)

        # Show audio mute indicator
        await madvr.display_audio_mute()
        await asyncio.sleep(2)

        # Close the audio mute indicator
        await madvr.close_audio_mute()

        # Display decibel-based volume (AVR style: -80dB to 0dB, currently -25dB)
        await madvr.display_audio_volume(-80, -25, 0, "dB")
        await asyncio.sleep(3)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await madvr.close_connection()
```
