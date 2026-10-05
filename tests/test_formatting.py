import unittest

from formatting import format_lists


class FormattingTests(unittest.TestCase):
    def test_inline_numbered_steps(self):
        self.assertEqual(format_lists('1. Open the store. 2. Find the app. 3. Tap Get.'),
                         '1. Open the store.\n2. Find the app.\n3. Tap Get.')

    def test_bullets(self):
        for marker in ['-', '*', '•']:
            result = format_lists(f'{marker} Open Settings. {marker} Choose Wi-Fi.')
            expected_marker = '-' if marker == '•' else marker
            self.assertEqual(result, f'{expected_marker} Open Settings.\n{expected_marker} Choose Wi-Fi.')

    def test_preserve_code_and_ordinary_numbers(self):
        text = 'Version 3.14 costs 2.50.\n\n```python\nx = "1. First 2. Second • item"\ny = a - b\n```\n\nUse `1. First 2. Second` as text.'
        self.assertEqual(format_lists(text), text)

    def test_existing_lists_and_nested_lists(self):
        text = 'Do this:\n\n1. Open Settings.\n2. Choose Wi-Fi.\n   - Check the network.\n   - Check the password.'
        self.assertEqual(format_lists(text), text)
