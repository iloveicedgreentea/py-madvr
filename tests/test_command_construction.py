"""Test command construction for Home Assistant compatibility."""

import pytest

from pymadvr.madvr import Madvr


class TestCommandConstruction:
    """Test command construction with various formats."""

    @pytest.fixture
    def madvr(self):
        """Create a MadVR instance for testing."""
        return Madvr("192.168.1.100")

    @pytest.mark.asyncio
    async def test_comma_separated_commands(self, madvr):
        """Test Home Assistant format with comma-separated commands."""
        test_cases = [
            (["KeyPress, MENU"], b'KeyPress MENU\r\n'),
            (["KeyPress, SETTINGS"], b'KeyPress SETTINGS\r\n'),
            (["OpenMenu, Info"], b'OpenMenu Info\r\n'),
            (["OpenMenu, Settings"], b'OpenMenu Settings\r\n'),
            (["ActivateProfile, SOURCE"], b'ActivateProfile SOURCE\r\n'),
        ]

        for command, expected in test_cases:
            cmd_bytes, _ = await madvr._construct_command(command)
            assert cmd_bytes == expected, f"Failed for command {command}"

    @pytest.mark.asyncio
    async def test_list_format_commands(self, madvr):
        """Test new format with separate list elements."""
        test_cases = [
            (["KeyPress", "MENU"], b'KeyPress MENU\r\n'),
            (["KeyPress", "SETTINGS"], b'KeyPress SETTINGS\r\n'),
            (["OpenMenu", "Info"], b'OpenMenu Info\r\n'),
            (["OpenMenu", "Settings"], b'OpenMenu Settings\r\n'),
            (["ActivateProfile", "SOURCE"], b'ActivateProfile SOURCE\r\n'),
        ]

        for command, expected in test_cases:
            cmd_bytes, _ = await madvr._construct_command(command)
            assert cmd_bytes == expected, f"Failed for command {command}"

    @pytest.mark.asyncio
    async def test_single_commands(self, madvr):
        """Test single commands without parameters."""
        test_cases = [
            (["PowerOff"], b'PowerOff\r\n'),
            (["Standby"], b'Standby\r\n'),
            (["GetMacAddress"], b'GetMacAddress\r\n'),
            (["GetTemperatures"], b'GetTemperatures\r\n'),
            (["CloseMenu"], b'CloseMenu\r\n'),
        ]

        for command, expected in test_cases:
            cmd_bytes, _ = await madvr._construct_command(command)
            assert cmd_bytes == expected, f"Failed for command {command}"

    @pytest.mark.asyncio
    async def test_display_commands(self, madvr):
        """Test display commands with string parameters."""
        test_cases = [
            (["DisplayMessage", "3", "Hello World"], b'DisplayMessage 3 "Hello World"\r\n'),
            (["DisplayMessage", "5", "Test Message"], b'DisplayMessage 5 "Test Message"\r\n'),
        ]

        for command, expected in test_cases:
            cmd_bytes, _ = await madvr._construct_command(command)
            assert cmd_bytes == expected, f"Failed for command {command}"

    @pytest.mark.asyncio
    async def test_numeric_parameters(self, madvr):
        """Test commands with numeric parameters."""
        test_cases = [
            (["ActivateProfile", "CUSTOM", "2"], b'ActivateProfile CUSTOM 2\r\n'),
            (["DisplayAudioVolume", "0", "75", "100", "percent"], b'DisplayAudioVolume 0 75 100 "percent"\r\n'),
        ]

        for command, expected in test_cases:
            cmd_bytes, _ = await madvr._construct_command(command)
            assert cmd_bytes == expected, f"Failed for command {command}"

    @pytest.mark.asyncio
    async def test_invalid_commands(self, madvr):
        """Test that invalid commands raise NotImplementedError."""
        invalid_commands = [
            ["NonExistentCommand"],
            ["InvalidCommand", "PARAM"],
        ]

        for command in invalid_commands:
            with pytest.raises(NotImplementedError):
                await madvr._construct_command(command)

        # Test invalid enum values are passed through as strings
        cmd_bytes, _ = await madvr._construct_command(["KeyPress, INVALID"])
        assert cmd_bytes == b'KeyPress INVALID\r\n'

    @pytest.mark.asyncio
    async def test_empty_command(self, madvr):
        """Test that empty command raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Empty command"):
            await madvr._construct_command([])

    @pytest.mark.asyncio
    async def test_ha_compatibility_edge_cases(self, madvr):
        """Test edge cases from Home Assistant integration."""
        # Test command with multiple commas
        cmd_bytes, _ = await madvr._construct_command(["ActivateProfile, CUSTOM, 2"])
        assert cmd_bytes == b'ActivateProfile CUSTOM 2\r\n'

        # Test command with spaces around commas
        cmd_bytes, _ = await madvr._construct_command(["KeyPress , MENU"])
        assert cmd_bytes == b'KeyPress MENU\r\n'
