import unittest
import os
from dotenv import load_dotenv
from madvr.madvr import Madvr
import time

# load .env
load_dotenv()

host = os.getenv("MADVR_HOST")

madvr = Madvr(host=host, connect_timeout=10)
madvr.open_connection()


class TestInfo(unittest.TestCase):
    def test_process_info(self):
        s = madvr._process_info(
            b"IncomingSignalInfo 3840x2160 23.976p 2D 422 10bit HDR10 2020 TV 16:9",
            "IncomingSignalInfo",
        )
        self.assertIsInstance(s, str)


class TestPoll(unittest.TestCase):
    def test_poll(self):
        self.assertEqual(madvr.incoming_res, "")
        madvr.poll_status()
        self.assertNotEqual(madvr.incoming_res, "")


class TestMenu(unittest.TestCase):
    """Test suite"""

    def test_construct_cmd(self):
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

    def test_aspect(self):
        """Ensure commands actually send"""
        self.skipTest("")
        signal = madvr.send_command("GetAspectRatio")
        self.assertNotEqual(signal, "Command not found")

        signal = madvr.send_command("KeyPress, UP")
        self.assertNotEqual(signal, "Command not found")

    def test_command_notfound(self):
        """Ensure wrong commands are caught"""
        self.skipTest("")
        fake_cmd = madvr.send_command("FakeCommand")
        self.assertEqual(fake_cmd, "Command not found")

        fake_param = madvr.send_command("KeyPress, FAKEKEY")
        self.assertEqual(fake_param, "Command not found")

    def test_notifications(self):
        """Make sure notifications work"""
        self.skipTest("Temp")
        madvr.read_notifications(True)

    # def test_incoming_info(self):
    #     self.skipTest("reason")

    #     c = madvr.poll_hdr()
    #     self.assertIsInstance(c, bool)
    # def test_menuopen(self):
    #     """Functional test - menu opens and closes"""

    #     madvr.send_command("key_press, menu")
    #     time.sleep(1)
    #     madvr.send_command("key_press, menu")


if __name__ == "__main__":
    unittest.main()
