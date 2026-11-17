"""Source publication dates must not be replaced by documentation examples."""
import unittest

from zombiecheck.evidence import observe_page
from zombiecheck.models import dated_activity


class SourceDateRegressions(unittest.TestCase):
    def test_changelog_heading_wins_over_compatibility_date_code_example(self):
        text="""# November 16, 2026
We released an update.
```toml
# Set this to today's date
compatibility_date = '2026-11-17'
```
"""
        self.assertEqual(dated_activity(text),"2026-11-16")

    def test_indented_and_sample_timestamps_do_not_advance_activity_date(self):
        text="""Product release November 16, 2026
    example_timestamp = '2026-11-17'
Sample timestamp: 2026-11-17
Compatibility_date: 2026-11-17
"""
        self.assertEqual(dated_activity(text),"2026-11-16")

    def test_article_publication_metadata_wins_over_example_log_timestamp(self):
        url="https://acme.example/blog/new-feature"
        page={"url":url,"final_url":url,"text":"# A new product feature\nA historical log includes 2026-10-29T12:00:00Z.",
              "published_date":"2026-11-16T05:30:00Z"}
        signal=observe_page("blog",url,page=page,linked=True,company_url="https://acme.example")
        self.assertEqual(signal["latest_date"],"2026-11-16")
        self.assertEqual(signal["date_source"],"page_metadata")
        self.assertTrue(signal["date_verified"])


if __name__=="__main__":unittest.main()
