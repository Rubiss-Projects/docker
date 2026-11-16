"""Check the Beerus exception's language preferences using real release naming."""

import json
from pathlib import Path
import re
import unittest


POLICY = json.loads(Path(__file__).with_name("beerus-policy.json").read_text())


def score(title, languages, resolution=1080):
    total = 0
    for entry in POLICY["formats"]:
        matches = []
        for spec in entry["customFormat"]["specifications"]:
            assert spec["required"], "This evaluator covers required conditions only"
            value = spec["fields"]["value"]
            kind = spec["implementation"]
            if kind == "LanguageSpecification":
                matched = value in languages
            elif kind == "ResolutionSpecification":
                matched = value == resolution
            elif kind == "ReleaseTitleSpecification":
                matched = re.search(value, title, re.IGNORECASE) is not None
            else:
                raise AssertionError(f"Unsupported condition: {kind}")
            matches.append(not matched if spec["negate"] else matched)
        if all(matches):
            total += entry["score"]
    return total


class BeerusPolicyTests(unittest.TestCase):
    def test_japanese_fallback_does_not_require_subtitles_in_filename(self):
        self.assertEqual(score("Beerus.S01E02.1080p.CR.WEB-DL.AAC2.0-AnoZu", {8}), 110)
        self.assertEqual(score("Beerus 02 [720p][MultiSub]", {8}, 720), 100)

    def test_english_audio_is_preferred(self):
        self.assertEqual(score("Beerus.S01E02.English.Dub", {1}), 1010)

    def test_dual_names_before_and_after_import(self):
        for title in ("Beerus.S01E01.DUAL.DDP2.0-AnoZu", "Beerus_DUAL_AUDIO",
                      "Beerus Dual-Audio", "Beerus [DUAL]", "Beerus [JA+EN]",
                      "Beerus.DUAL.English.Subs"):
            for languages in ({8}, {8, 1}):
                with self.subTest(title=title, languages=languages):
                    self.assertEqual(score(title, languages), 2010)

    def test_subtitle_label_is_not_an_english_dub(self):
        for separator in (" ", ".", "_", "-"):
            for label in ("English Subs", "ENG Subtitles", "Subs English"):
                title = separator.join(("Beerus", *label.split(), "1080p"))
                with self.subTest(title=title):
                    self.assertEqual(score(title, {8}), 110)
                    self.assertLess(score(title, {1}), POLICY["minFormatScore"])
                    self.assertEqual(score(title + separator + "English_Dub", {1}), 1010)

    def test_subtitle_information_does_not_reject_dual_language_pairs(self):
        for label in ("JA+EN", "JPN-ENG", "ENG_JPN", "EN/JA",
                      "Japanese English", "English Japanese"):
            for separator in (" ", ".", "_", "-"):
                for languages in ({8}, {8, 1}):
                    titles = (f"Beerus.S01E02.1080p.[{label}]",
                              separator.join(("Beerus", "S01E02", "1080p", label)))
                    for title in titles:
                        with self.subTest(title=title, languages=languages):
                            self.assertEqual(score(title, languages), 2010)
                            self.assertEqual(score(title + separator + "English_Subs", languages), 2010)

    def test_unrelated_language_and_dual_substrings_do_not_qualify(self):
        for title in ("Beerus.German", "Beerus English Subs", "Beerus.Individual"):
            self.assertLess(score(title, {4}), POLICY["minFormatScore"])
        self.assertEqual(score("Beerus.Individual", {8}), 110)
        for label in ("XJA+EN", "JA+ENX", "XJapanese_English", "English_JapaneseX"):
            with self.subTest(label=label):
                self.assertEqual(score(f"Beerus_{label}", {8}), 110)


if __name__ == "__main__":
    unittest.main()
