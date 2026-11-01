import json

from django.template import Context, Template
from django.test import SimpleTestCase


class SecureJsonTest(SimpleTestCase):
    def test_script_end_tag_cannot_escape_json_element(self):
        rendered = Template('{% load secure_json %}{% secure_json_script value "sample" %}').render(
            Context({"value": json.dumps({"name": "</script><script>alert(1)</script>"})})
        )
        self.assertEqual(rendered.count("</script>"), 1)
        self.assertIn("\\u003C/script\\u003E", rendered)
