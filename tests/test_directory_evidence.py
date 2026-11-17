"""Accelerator-profile corroboration must not convert access failures into death."""
import unittest

from zombiecheck.evidence import inactive_directory_evidence
from zombiecheck.rules import classify
from tests.test_core import records, TODAY


class DirectoryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.row={"name":"Acme","website":"https://acme.example",
                  "reference_url":"https://www.ycombinator.com/companies/acme"}

    def identity(self):
        return {"status":"unknown","verified":False,"canonical_url":self.row["website"]}

    def profile(self,url=None,title=None,text=None):
        url=url or self.row["reference_url"]
        return {"url":url,"final_url":url,"title":title or "Acme | Y Combinator",
                "text":text or "# Acme\nStatus: Inactive\nWebsite: https://acme.example",
                "links":[self.row["website"]]}

    def test_transient_homepage_failures_never_confirm_closure(self):
        for code,status in (("timeout",None),("target_unreachable",None),("bot_blocked",None),
                            ("login_required",None),("target_http_error",403),("target_http_error",503),
                            ("empty_content",None),("no_response",None)):
            with self.subTest(error=code,status=status):
                identity=self.identity()
                homepage={"verified":False,"url":self.row["website"],"error":{"error":code,"status":status}}
                closure=inactive_directory_evidence(self.row,identity,self.profile(),homepage)
                self.assertIsNone(closure)
                self.assertFalse(identity["verified"])
                self.assertNotEqual(classify(records(),identity,homepage,closure,today=TODAY)["verdict"],"zombie")

    def test_unverified_homepage_without_terminal_error_never_confirms_closure(self):
        identity=self.identity()
        closure=inactive_directory_evidence(self.row,identity,self.profile(),{"verified":False,"error":None})
        self.assertIsNone(closure)
        self.assertFalse(identity["verified"])

    def test_other_profile_mentions_cannot_identify_the_original_company(self):
        identity=self.identity()
        wrong=self.profile(url="https://www.ycombinator.com/companies/otherco",
                           title="OtherCo | Y Combinator",
                           text="# OtherCo\nStatus: Inactive\nAcme used the same technology.")
        closure=inactive_directory_evidence(self.row,identity,wrong,{"verified":False,"error":{"error":"page_not_found","status":404}})
        self.assertIsNone(closure)
        self.assertFalse(identity["verified"])

    def test_inactive_word_about_another_company_is_not_subject_status(self):
        identity=self.identity()
        profile=self.profile(text="# Acme\nStatus: Active\nRelated company OtherCo is inactive.")
        closure=inactive_directory_evidence(self.row,identity,profile,{"verified":False,"error":{"error":"page_not_found","status":404}})
        self.assertIsNone(closure)

    def test_exact_profile_and_terminal_original_404_support_corroboration(self):
        identity=self.identity()
        homepage={"verified":False,"url":self.row["website"],"error":{"error":"page_not_found","status":404}}
        closure=inactive_directory_evidence(self.row,identity,self.profile(),homepage)
        self.assertIsNotNone(closure)
        self.assertTrue(closure["verified"])
        self.assertEqual(closure["url"],self.row["reference_url"])
        self.assertIn("Inactive",closure["quote"])
        self.assertEqual(identity["status"],"closed")

    def test_exact_profile_and_terminal_original_410_support_corroboration(self):
        closure=inactive_directory_evidence(self.row,self.identity(),self.profile(),
                    {"verified":False,"error":{"error":"page_not_found","status":410}})
        self.assertIsNotNone(closure)

    def test_directory_search_page_is_not_exact_company_profile(self):
        identity=self.identity()
        listing=self.profile(url="https://www.ycombinator.com/companies",title="YC Startup Directory",
                             text="Search results\nAcme\nStatus: Inactive")
        closure=inactive_directory_evidence(self.row,identity,listing,{"verified":False,"error":{"error":"page_not_found","status":404}})
        self.assertIsNone(closure)

    def test_lookalike_yc_host_is_not_trusted(self):
        fake=self.profile(url="https://ycombinator.com.evil.example/companies/acme")
        closure=inactive_directory_evidence(self.row,self.identity(),fake,{"verified":False,"error":{"error":"page_not_found","status":404}})
        self.assertIsNone(closure)

    def test_missing_reference_requires_exact_slug_and_title(self):
        row=dict(self.row)
        row.pop("reference_url")
        exact=inactive_directory_evidence(row,self.identity(),self.profile(),{"verified":False,"error":{"error":"page_not_found","status":404}})
        self.assertIsNotNone(exact)
        longer=self.profile(url="https://www.ycombinator.com/companies/acme-labs",title="Acme Labs | Y Combinator",
                            text="# Acme Labs\nStatus: Inactive\nAcme Labs was a robotics startup.")
        wrong=inactive_directory_evidence(row,self.identity(),longer,{"verified":False,"error":{"error":"page_not_found","status":404}})
        self.assertIsNone(wrong)

    def test_supplied_reference_is_authoritative_over_name_slug(self):
        row=dict(self.row,reference_url="https://www.ycombinator.com/companies/acme-original")
        closure=inactive_directory_evidence(row,self.identity(),self.profile(),
                    {"verified":False,"error":{"error":"page_not_found","status":404}})
        self.assertIsNone(closure)

    def test_title_prefix_is_not_an_exact_company_name_match(self):
        different=self.profile(title="Acme Labs | Y Combinator",
                               text="# Acme Labs\nStatus: Inactive\nWebsite: https://labs.example")
        closure=inactive_directory_evidence(self.row,self.identity(),different,
                    {"verified":False,"error":{"error":"page_not_found","status":404}})
        self.assertIsNone(closure)

    def test_supporting_quote_is_subject_inactive_status(self):
        profile=self.profile(text="# Acme\nRelated company OtherCo is inactive.\nStatus: Inactive\nWebsite: https://acme.example")
        closure=inactive_directory_evidence(self.row,self.identity(),profile,
                    {"verified":False,"error":{"error":"page_not_found","status":404}})
        self.assertIsNotNone(closure)
        self.assertIn("Status",closure["quote"])
        self.assertNotIn("OtherCo",closure["quote"])


if __name__=="__main__":unittest.main()
