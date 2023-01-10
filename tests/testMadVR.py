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

class TestMenu(unittest.TestCase):
    """Test suite"""

    def test_get_signal_info(self):
        signal = madvr.send_command("get_aspect_ratio")
        print(signal)

    def test_notifications(self):
        # self.skipTest("reason")
        madvr.read_notifications(True)

    def test_incoming_info(self):
        self.skipTest("reason")

        c = madvr.poll_hdr()
        self.assertIsInstance(c, bool)

    def test__construct_command(self):
        """ensure it can construct a command"""

        self.skipTest("reason")

        cmd, isin, _ = madvr._construct_command("key_press, menu")

        self.assertEqual(cmd, b'KeyPress MENU\r\n')
        self.assertEqual(isin, False)

    def test_gettemp(self):
        """Test informational command"""

        self.skipTest("reason")
        cmd = madvr.send_command("get_temperature")
        print(cmd)
        # TODO: make this a dict
        self.assertFalse("Error" in cmd)

    # def test_menuopen(self):
    #     """Functional test - menu opens and closes"""

    #     madvr.send_command("key_press, menu")
    #     time.sleep(1)
    #     madvr.send_command("key_press, menu")

if __name__ == '__main__':
    unittest.main()