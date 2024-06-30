# MadVR Envy Python Library

Support for IP based controls for MadVR Envy

Supports real time notifications and commands

## WOL
If the client is initialized without a mac, it will assume you provide your own wake on lan automation. Standby does not respond to pings so you may as well do a full power off.

## Commands
Command structure follows the same in the manual https://madvrenvy.com/wp-content/uploads/EnvyIpControl.pdf?r=112a

For things that take values, use a comma -> `["KeyPress, MENU"]`

Not every single command is implemented, such as submenus or changing complicated options. You can use commands for all the typical stuff the remote can do.
