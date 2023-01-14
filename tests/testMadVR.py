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
        # self.skipTest("")

        self.assertEqual(madvr.incoming_res, "")
        madvr.poll_status()
        self.assertNotEqual(madvr.incoming_res, "")
        self.assertNotEqual(madvr.outgoing_color_space, "")
        print(
            madvr.hdr_flag,
            madvr.incoming_aspect_ratio,
            madvr.incoming_frame_rate
        )

        signal = madvr.send_command("GetAspectRatio")
        self.assertNotEqual(signal, "Command not found")

        signal = madvr.send_command("KeyPress, UP")
        self.assertNotEqual(signal, "Command not found")

        fake_cmd = madvr.send_command("FakeCommand")
        self.assertEqual(fake_cmd, "Command not found")

        fake_param = madvr.send_command("KeyPress, FAKEKEY")
        self.assertEqual(fake_param, "Command not found")
        
        # print("running test_d_notifications")
        # madvr.read_notifications(True)

        cmd = madvr.send_command("KeyPress, MENU")
        self.assertNotEqual(cmd, "Command not found")
        
        time.sleep(1)
        cmd = madvr.send_command("KeyPress, MENU")
        self.assertNotEqual(cmd, "Command not found")

        madvr.close_connection()
        self.assertEqual(True, madvr.is_closed)

if __name__ == "__main__":
    unittest.main(failfast=True)
