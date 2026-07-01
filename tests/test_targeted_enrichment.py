import os
import sys
import unittest
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.enrichment.contact_sample import company_cache_slug
from src.core.enrichment.source import source_contacts
from src.schemas import Job, OutreachSettings


class TestTargetedEnrichmentCaching(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.job_ca = Job(
            id=1,
            title="Engineer",
            company="TestCo",
            companyUrl="https://linkedin.com/company/testco",
            location="Montreal, QC",
            status="accepted"
        )
        self.job_us = Job(
            id=2,
            title="Engineer",
            company="TestCo",
            companyUrl="https://linkedin.com/company/testco",
            location="New York, NY",
            status="accepted"
        )
        self.settings = OutreachSettings(target_recruiters=True, target_russian_speakers=False)

    def test_cache_slug_logic(self):
        # Direct verification of the slug helper
        slug_ca = company_cache_slug("TestCo", "https://linkedin.com/company/testco", country="Canada")
        slug_us = company_cache_slug("TestCo", "https://linkedin.com/company/testco", country="United States")
        slug_remote = company_cache_slug("TestCo", "https://linkedin.com/company/testco", country=None)
        
        self.assertEqual(slug_ca, "testco-canada")
        self.assertEqual(slug_us, "testco-united-states")
        self.assertEqual(slug_remote, "testco")
        self.assertNotEqual(slug_ca, slug_us)

    @patch("src.db.cache.get_contact_sample")
    @patch("src.db.cache.set_contact_sample")
    @patch("src.core.enrichment.source._run_apify_for_recruiters")
    @patch("src.core.enrichment.source.classify_contacts")
    @patch("src.db.jobs.log_activity")
    async def test_enrichment_uses_targeted_cache(self, mock_log, mock_classify, mock_apify, mock_set_cache, mock_get_cache):
        mock_get_cache.return_value = None # Cache miss
        mock_apify.return_value = [{"name": "Recruiter"}]
        mock_classify.return_value = [{"name": "Recruiter", "is_recruiter": True, "url": "https://linkedin.com/in/recruiter"}]
        
        # 1. Enrich Canada Job
        await source_contacts(self.job_ca, settings=self.settings)
        
        # Verify first cache set was for Canada
        args, kwargs = mock_set_cache.call_args
        self.assertEqual(args[0], "testco-canada")
        self.assertEqual(mock_apify.call_args[1]["locations"], ["Canada"])
        
        # 2. Enrich US Job
        mock_get_cache.reset_mock()
        mock_get_cache.return_value = None # Cache miss for US too
        mock_apify.reset_mock()
        
        await source_contacts(self.job_us, settings=self.settings)
        
        # Verify second cache set was for United States
        args, kwargs = mock_set_cache.call_args
        self.assertEqual(args[0], "testco-united-states")
        self.assertEqual(mock_apify.call_args[1]["locations"], ["United States"])

    @patch("src.db.cache.get_contact_sample")
    @patch("src.db.cache.set_contact_sample")
    @patch("src.core.enrichment.source._run_apify_for_recruiters")
    @patch("src.core.enrichment.source.classify_contacts")
    @patch("src.db.jobs.log_activity")
    async def test_cache_hit_when_country_matches(self, mock_log, mock_classify, mock_apify, mock_set_cache, mock_get_cache):
        """Enriching the same country should hit the cache and skip Apify."""
        cached_entry = {
            "profiles": [{"name": "Recruiter", "is_recruiter": True, "url": "https://linkedin.com/in/recruiter"}],
            "display_name": "TestCo",
            "fetched_at": "2024-01-01",
        }
        mock_get_cache.return_value = cached_entry
        mock_classify.return_value = cached_entry["profiles"]

        await source_contacts(self.job_ca, settings=self.settings)

        mock_get_cache.assert_called_with("testco-canada", stream="recruiters")
        mock_apify.assert_not_called()
        mock_set_cache.assert_not_called()

    @patch("src.db.cache.get_contact_sample")
    @patch("src.db.cache.set_contact_sample")
    @patch("src.core.enrichment.source._run_apify_for_recruiters")
    @patch("src.core.enrichment.source.classify_contacts")
    @patch("src.db.jobs.log_activity")
    async def test_cache_miss_when_country_differs(self, mock_log, mock_classify, mock_apify, mock_set_cache, mock_get_cache):
        """Same company but different country produces a cache miss and a fresh Apify call."""
        canada_entry = {
            "profiles": [{"name": "CA Recruiter", "is_recruiter": True, "url": "https://linkedin.com/in/ca-rec"}],
            "display_name": "TestCo",
            "fetched_at": "2024-01-01",
        }

        def selective_cache(slug, stream=""):
            if slug == "testco-canada":
                return canada_entry
            return None

        mock_get_cache.side_effect = selective_cache
        mock_apify.return_value = [{"name": "US Recruiter"}]
        mock_classify.return_value = [{"name": "US Recruiter", "is_recruiter": True, "url": "https://linkedin.com/in/us-rec"}]

        await source_contacts(self.job_us, settings=self.settings)

        mock_get_cache.assert_called_with("testco-united-states", stream="recruiters")
        mock_apify.assert_called_once()
        self.assertEqual(mock_apify.call_args[1]["locations"], ["United States"])
        args, _ = mock_set_cache.call_args
        self.assertEqual(args[0], "testco-united-states")


if __name__ == "__main__":
    unittest.main()
