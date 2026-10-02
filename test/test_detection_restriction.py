"""Restricting the detector's answer to the configured languages.

T-6775, second half. ``LanguageDetector`` takes no candidate list, unlike the
STT template's ``detect_language(audio, valid_langs=...)``, so a box running
two languages still gets an answer drawn from about 180. ``detect_probs``
makes the restriction implementable in the caller, with no change to the
template, which is ovos-plugin-manager's and core's to merge.

It is opt-in. The trade it makes is real and is tested here: a detector held to
the configured languages can never report the foreign language that
bidirectional translation exists to handle.
"""
import unittest
from unittest.mock import Mock, patch

from ovos_bus_client.session import Session

import ovos_bidirectional_translation_plugin as plugin
from ovos_bidirectional_translation_plugin import UtteranceTranslator


def make_translator(langs, probs, detect=None, **config):
    """Build an UtteranceTranslator with a detector returning *probs*."""
    conf = {"lang": langs[0], "secondary_langs": list(langs[1:])}
    with patch.object(plugin.OVOSLangDetectionFactory, "create", Mock()), \
            patch.object(plugin.OVOSLangTranslationFactory, "create", Mock()), \
            patch.object(plugin, "Configuration", Mock(return_value=conf)):
        transformer = UtteranceTranslator(config=config)
    transformer.lang_detector.detect_probs = Mock(return_value=probs)
    best = detect or (max(probs, key=probs.get) if probs else "en")
    transformer.lang_detector.detect = Mock(return_value=best)
    transformer.translator.translate = Mock(return_value="translated")
    transformer._conf = conf
    return transformer


def detect_lang(transformer, utt="speel wat muziek"):
    with patch.object(plugin, "Configuration", Mock(return_value=transformer._conf)):
        return transformer._detect_lang(utt)


def run(transformer, lang, utterance="speel wat muziek"):
    sess = Session(lang=lang)
    with patch.object(plugin, "Configuration", Mock(return_value=transformer._conf)):
        return transformer.transform([utterance], {"session": sess.serialize()})


class TestRestrictionOff(unittest.TestCase):
    """The default must not change what any existing box does."""

    def test_default_uses_plain_detect(self):
        t = make_translator(["en-US", "nl-NL"], {"da": 0.6, "nl": 0.4}, detect="da")
        self.assertEqual(detect_lang(t), "da")
        t.lang_detector.detect_probs.assert_not_called()


class TestRestrictionOn(unittest.TestCase):

    def test_picks_the_best_supported_language(self):
        # the langdetect instability measured under T-6768: Dutch text
        # scoring da/pl/lv on short utterances
        t = make_translator(["en-US", "nl-NL"], {"da": 0.6, "nl": 0.3, "lv": 0.1},
                            detect="da", restrict_detection_to_valid_langs=True)
        self.assertEqual(detect_lang(t), "nl")

    def test_picks_the_higher_of_two_native_candidates(self):
        # test_picks_the_best_supported_language narrows the candidate set to
        # one native language, so max() and min() agree there and the test
        # cannot tell them apart. Here two native languages both survive the
        # restriction with different scores, so swapping max() for min() in
        # _detect_lang flips the answer and this test catches it. The winner
        # is also first in insertion order, so a selection that reads no
        # score at all and returns the first native key still passes this
        # case alone; the next test puts the winner last instead.
        t = make_translator(["en-US", "nl-NL"], {"nl": 0.6, "en": 0.3, "da": 0.1},
                            detect="da", restrict_detection_to_valid_langs=True)
        self.assertEqual(detect_lang(t), "nl")

    def test_the_higher_score_wins_even_when_it_is_not_first(self):
        # the winning language is last in insertion order here, the opposite
        # of the case above. A selection that ignores the scores and returns
        # the first native key, or the first key overall, answers "da" or
        # "en" here and fails; only reading the scores answers "nl".
        t = make_translator(["en-US", "nl-NL"], {"da": 0.1, "en": 0.3, "nl": 0.6},
                            detect="da", restrict_detection_to_valid_langs=True)
        self.assertEqual(detect_lang(t), "nl")

    def test_regional_variant_counts_as_supported(self):
        t = make_translator(["en-US", "pt-PT"], {"fr": 0.7, "pt": 0.3},
                            detect="fr", restrict_detection_to_valid_langs=True)
        self.assertEqual(detect_lang(t), "pt")

    def test_unrestricted_winner_is_kept_when_it_is_supported(self):
        t = make_translator(["en-US", "nl-NL"], {"nl": 0.9, "da": 0.1},
                            detect="nl", restrict_detection_to_valid_langs=True)
        self.assertEqual(detect_lang(t), "nl")

    def test_no_supported_candidate_reports_what_the_detector_said(self):
        # inventing a supported answer would be indistinguishable from a real
        # match, so the real answer is reported and the caller decides.
        #
        # detect() is deliberately made to DISAGREE with max(probs): the
        # detector says "de" while the scores put "fr" on top. Returning the
        # top score instead of asking detect() is the obvious wrong fix, and
        # with the two agreeing this test could not tell them apart.
        t = make_translator(["en-US"], {"fr": 0.8, "de": 0.2},
                            detect="de", restrict_detection_to_valid_langs=True)
        self.assertEqual(detect_lang(t), "de")
        t.lang_detector.detect.assert_called_once()

    def test_detector_without_detect_probs_falls_back(self):
        t = make_translator(["en-US", "nl-NL"], {}, detect="da",
                            restrict_detection_to_valid_langs=True)
        t.lang_detector.detect_probs = Mock(side_effect=NotImplementedError)
        self.assertEqual(detect_lang(t), "da")

    def test_detector_that_returns_no_scores_warns_and_falls_back(self):
        """The shape a real detector actually has.

        ``LanguageDetector.detect_probs`` is declared abstract with no body, and
        a subclass that overrides ``detect()`` only still instantiates, so the
        call RETURNS None rather than raising NotImplementedError. Measured on
        the template: such a subclass instantiates and detect_probs gives None.
        The option cannot work, so it must say so once and use the plain
        detection.
        """
        t = make_translator(["en-US", "nl-NL"], {}, detect="da",
                            restrict_detection_to_valid_langs=True)
        t.lang_detector.detect_probs = Mock(return_value=None)
        with patch.object(plugin.LOG, "warning") as warned:
            self.assertEqual(detect_lang(t), "da")
        self.assertTrue(
            any("inoperative" in str(c) for c in warned.call_args_list),
            f"no inoperative warning was logged: {warned.call_args_list}")

    def test_detector_that_returns_an_empty_score_map_warns_too(self):
        """An empty dict says the same thing as None and takes the same path."""
        t = make_translator(["en-US", "nl-NL"], {}, detect="da",
                            restrict_detection_to_valid_langs=True)
        t.lang_detector.detect_probs = Mock(return_value={})
        with patch.object(plugin.LOG, "warning") as warned:
            self.assertEqual(detect_lang(t), "da")
        self.assertTrue(
            any("inoperative" in str(c) for c in warned.call_args_list),
            f"no inoperative warning was logged: {warned.call_args_list}")


class TestTheTradeItMakes(unittest.TestCase):
    """The cost of the restriction, stated as a test rather than a comment."""

    def test_foreign_utterance_is_translated_when_restriction_is_off(self):
        t = make_translator(["en-US"], {"fr": 0.9, "en": 0.1}, detect="fr",
                            verify_lang=True)
        _, context = run(t, "en-US")
        self.assertTrue(context["was_translated"])

    def test_foreign_utterance_is_NOT_translated_when_restriction_is_on(self):
        # the same box and the same utterance: holding the detector to the
        # configured languages costs the translation this plugin exists for
        t = make_translator(["en-US"], {"fr": 0.9, "en": 0.1}, detect="fr",
                            verify_lang=True,
                            restrict_detection_to_valid_langs=True)
        _, context = run(t, "en-US")
        self.assertFalse(context["was_translated"])


if __name__ == "__main__":
    unittest.main()
