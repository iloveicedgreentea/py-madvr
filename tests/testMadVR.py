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
    def test__construct_command(self):
        """ensure it can construct a command"""

        cmd, isin = madvr._construct_command("key_press, menu")

        self.assertEqual(cmd, b'KeyPress MENU\r\n')
        self.assertEqual(isin, False)

    def test_menuopen(self):
        """Verify menu opens and closes"""

        madvr.send_command("key_press, menu")
        time.sleep(1)
        madvr.send_command("key_press, menu")

if __name__ == '__main__':
    unittest.main()