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
