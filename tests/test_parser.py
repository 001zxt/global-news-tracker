import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from news_fetcher import Source, clean_text, normalize_key, parse_feed, repair_mojibake, score_article


class ParserTests(unittest.TestCase):
    def test_clean_text_removes_html(self):
        self.assertEqual(clean_text("<p>Hello&nbsp;world</p>"), "Hello world")

    def test_repair_mojibake(self):
        self.assertEqual(repair_mojibake("CEO鈥檚 plan won鈥檛 stop"), "CEO’s plan won’t stop")

    def test_normalize_key_removes_punctuation(self):
        self.assertEqual(normalize_key("AI: New rules!"), "ai new rules")

    def test_parse_rss_feed(self):
        source = Source(name="Example", url="https://example.com/rss", region="World", weight=50)
        xml = b"""<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Global AI election security update</title>
              <link>https://example.com/story</link>
              <description><![CDATA[<p>Major update for election security.</p>]]></description>
              <pubDate>Thu, 28 May 2026 10:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>"""

        articles = parse_feed(xml, source)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Global AI election security update")
        self.assertEqual(articles[0].link, "https://example.com/story")
        self.assertIn("ai", articles[0].keywords)
        self.assertIn("election", articles[0].keywords)

    def test_keywords_match_whole_terms(self):
        source = Source(name="Example", url="https://example.com/rss", region="World", weight=50)
        _, keywords = score_article(source, "Australia said talks continue", "", None)
        self.assertNotIn("ai", keywords)
        self.assertNotIn("us", keywords)


if __name__ == "__main__":
    unittest.main()
