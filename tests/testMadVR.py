# pylint: disable=protected-access, missing-function-docstring, missing-class-docstring, invalid-name, missing-module-docstring
import unittest
import os
from dotenv import load_dotenv
from madvr.madvr import Madvr
import time

# load .env
load_dotenv()

host = os.getenv("MADVR_HOST")

madvr = Madvr(host=host, connect_timeout=10)


class TestLib(unittest.TestCase):
    def test_a_process_info(self):
        """Verify the process info func works"""
        info = madvr._process_info(
            b"Ok\r\nIncomingSignalInfo 3840x2160 23.976p 2D 422 10bit HDR10 2020 TV 16:9\r\nAspect Ratio ETC ETC\r\n",
            "IncomingSignalInfo",
        )
        self.assertEqual(
            info, "IncomingSignalInfo 3840x2160 23.976p 2D 422 10bit HDR10 2020 TV 16:9"
        )

    def test_b_construct_cmd(self):
        """test constructing commands"""
        try:
            cmd, isinfo, _ = madvr._construct_command("KeyPress, MENU")
            self.assertEqual(cmd, b"KeyPress MENU\r\n")
            self.assertEqual(isinfo, False)
        except NotImplementedError:
            self.fail("Command exists but got not implemented")

        try:
            cmd, isinfo, _ = madvr._construct_command("GetAspectRatio")
            self.assertEqual(cmd, b"GetAspectRatio\r\n")
            self.assertEqual(isinfo, True)
        except NotImplementedError:
            self.fail("Command exists but got not implemented")

        # Should fail
        with self.assertRaises(NotImplementedError):
            _, _, _ = madvr._construct_command("KeyPress, FAKE")
        with self.assertRaises(NotImplementedError):
            _, _, _ = madvr._construct_command("Fakecmd, Param")


class TestFunctional(unittest.TestCase):
    """Test suite"""
    madvr.open_connection()

    def test_a_poll(self):
        self.skipTest("")
        
        self.assertEqual(madvr.incoming_res, "")
        madvr.poll_status()
        self.assertNotEqual(madvr.incoming_res, "")

    def test_b_aspect(self):
        """Ensure commands actually send"""
        self.skipTest("")
        signal = madvr.send_command("GetAspectRatio")
        self.assertNotEqual(signal, "Command not found")

        signal = madvr.send_command("KeyPress, UP")
        self.assertNotEqual(signal, "Command not found")

    def test_c_command_notfound(self):
        """Ensure wrong commands are caught"""
        self.skipTest("")
        fake_cmd = madvr.send_command("FakeCommand")
        self.assertEqual(fake_cmd, "Command not found")

        fake_param = madvr.send_command("KeyPress, FAKEKEY")
        self.assertEqual(fake_param, "Command not found")

    def test_d_notifications(self):
        """Make sure notifications work"""
        self.skipTest("Temp")
        madvr.read_notifications(True)

    def test_e_menuopen(self):
        """Functional test - menu opens and closes"""

        madvr.send_command("key_press, menu")
        time.sleep(1)
        madvr.send_command("key_press, menu")

    def test_z_ConnClose(self):
        madvr.close_connection()
        self.assertEqual(True, madvr.is_closed)

if __name__ == "__main__":
    unittest.main()
