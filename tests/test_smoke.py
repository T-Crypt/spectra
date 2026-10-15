import unittest


class SmokeTest(unittest.TestCase):
    def test_discovery_finds_tests(self):
        # Python 3.12+ exits 5 when discovery finds no tests.
        # This keeps `python -m unittest discover -s tests` meaningful.
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
