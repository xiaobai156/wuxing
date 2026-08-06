import base64
import unittest

from wuxing.domain.enums import SourceKind
from wuxing.domain.models import SourceDocument
from wuxing.sources.documents import DocumentCollector


class SourceDocumentTests(unittest.TestCase):
    def test_unpaired_surrogates_are_removed_before_digest(self):
        document = SourceDocument("doc", "https://example.com", SourceKind.PAGE, "209期\ud9c1木行", 0)
        self.assertNotIn("\ud9c1", document.text)
        self.assertIsInstance(document.content_sha256, str)

    def test_collector_preserves_script_iframe_and_decoded_parentage(self):
        encoded = base64.b64encode("209期精杀一行【木行】".encode()).decode()
        pages = {
            "https://example.com/topic": (
                f"<html><script src='/view.js'></script><iframe src='/frame'></iframe>"
                f"<script>strdecode('{encoded}')</script></html>"
            ),
            "https://example.com/view.js": "const marker = 'script';",
            "https://example.com/frame": "<div>frame body</div>",
        }

        documents = DocumentCollector(lambda url, _timeout: pages[url]).collect(
            "https://example.com/topic", timeout=5
        )

        self.assertEqual(documents[0].source_kind, SourceKind.PAGE)
        self.assertEqual({item.source_kind for item in documents}, {SourceKind.PAGE, SourceKind.SCRIPT, SourceKind.IFRAME})
        decoded = next(item for item in documents if "209期" in item.text)
        self.assertEqual(decoded.parent_document_id, documents[0].document_id)
        self.assertEqual(dict(decoded.metadata)["decoded"], "true")

    def test_collector_rejects_cross_origin_iframe(self):
        pages = {
            "https://example.com/topic": "<iframe src='https://other.example/frame'></iframe>",
        }

        documents = DocumentCollector(lambda url, _timeout: pages[url]).collect(
            "https://example.com/topic", timeout=5
        )

        self.assertEqual(len(documents), 1)


if __name__ == "__main__":
    unittest.main()
