"""The detected_lang context key, and what core does with it.

T-6775. ``context["detected_lang"]`` was written before the validity guard
beneath it, so a detection the transformer had explicitly REJECTED was still
published to core. Core ranks ``detected_lang`` above the session language in
``disambiguate_lang``.

Core filters the key against its OWN valid languages, so the two agree whenever
the transformer's ``valid_langs`` and core's ``get_valid_languages()`` hold the
same set, and the stale key is then harmless. They diverge under
``translate_secondary_langs``, which narrows the transformer's set to the
internal language alone while core keeps the secondary languages. On that
configuration a rejected detection reached core, passed core's own filter and
replaced a correctly configured session language, while the transformer logged
"Ignoring lang detection". The log said the detection was ignored and it was
not.
"""
import unittest
from unittest.mock import Mock, patch

from ovos_bus_client.session import Session

import ovos_bidirectional_translation_plugin as plugin
from ovos_bidirectional_translation_plugin import UtteranceTranslator


def make_translator(langs, detected, **config):
    """Build an UtteranceTranslator whose detector returns *detected*."""
    conf = {"lang": langs[0], "secondary_langs": list(langs[1:])}
    with patch.object(plugin.OVOSLangDetectionFactory, "create", Mock()), \
            patch.object(plugin.OVOSLangTranslationFactory, "create", Mock()), \
            patch.object(plugin, "Configuration", Mock(return_value=conf)):
        transformer = UtteranceTranslator(config=config)
    transformer.lang_detector.detect = Mock(return_value=detected)
    transformer.translator.translate = Mock(return_value="translated")
    transformer._conf = conf
    return transformer


def run(transformer, lang, utterance="speel wat muziek"):
    sess = Session(lang=lang)
    with patch.object(plugin, "Configuration", Mock(return_value=transformer._conf)):
        return transformer.transform([utterance], {"session": sess.serialize()})


def match_lang(transformer, lang):
    """``match_lang`` reads Configuration() at call time, so a precondition
    checked outside the patched config would read the real box config."""
    with patch.object(plugin, "Configuration", Mock(return_value=transformer._conf)):
        return transformer.match_lang(lang)


class TestRejectedDetectionIsNotPublished(unittest.TestCase):
    """A detection the guard rejects must leave no detected_lang behind."""

    def test_rejected_detection_leaves_no_detected_lang(self):
        # translate_secondary_langs narrows valid_langs to the internal
        # language, so "nl" is rejected here even though the box runs nl-NL as
        # a secondary language. This is the configuration on which the stale
        # key reached core and won.
        transformer = make_translator(
            ["en-US", "nl-NL"], "nl",
            verify_lang=True, ignore_invalid_langs=True,
            translate_secondary_langs=True)
        self.assertIsNone(match_lang(transformer, "nl"),
                          "precondition: the transformer must reject this detection")
        _, context = run(transformer, "en-US")
        self.assertNotIn("detected_lang", context)

    def test_rejected_detection_does_not_move_the_session_language(self):
        transformer = make_translator(
            ["en-US", "nl-NL"], "nl",
            verify_lang=True, ignore_invalid_langs=True,
            translate_secondary_langs=True)
        _, context = run(transformer, "en-US")
        self.assertEqual(Session.deserialize(context["session"]).lang, "en-US")


class TestAcceptedDetectionIsStillPublished(unittest.TestCase):
    """The control: the fix must not stop publishing a GOOD detection."""

    def test_accepted_detection_is_published(self):
        transformer = make_translator(
            ["en-US", "nl-NL"], "nl",
            verify_lang=True, ignore_invalid_langs=True)
        self.assertIsNotNone(match_lang(transformer, "nl"),
                             "precondition: the transformer must accept this detection")
        _, context = run(transformer, "en-US")
        self.assertEqual(context.get("detected_lang"), "nl")

    def test_detection_agreeing_with_the_session_is_published(self):
        transformer = make_translator(["en-US", "nl-NL"], "en",
                                      verify_lang=True, ignore_invalid_langs=True)
        _, context = run(transformer, "en-US")
        self.assertEqual(context.get("detected_lang"), "en")

    def test_no_detection_when_verify_lang_is_off(self):
        transformer = make_translator(["en-US"], "nl")
        _, context = run(transformer, "en-US")
        self.assertNotIn("detected_lang", context)


class TestTranslatedUtteranceDoesNotPublishStaleDetection(unittest.TestCase):
    """A detection that triggers translation must leave no detected_lang
    behind either, by the same reasoning as the rejected-detection guard.

    The utterance and the session both move to the internal language. A
    published pre-translation tag would still outrank that correction in
    ``disambiguate_lang``, regardless of ``ignore_invalid_langs``.
    """

    def test_foreign_detection_that_triggers_translation_is_not_published(self):
        # ignore_invalid_langs is False by default, so the detection is ACTED
        # on (it moves sess.lang) rather than rejected. The utterance is then
        # translated, because "fr" is not in valid_langs.
        transformer = make_translator(["en-US"], "fr", verify_lang=True)
        _, context = run(transformer, "en-US")
        self.assertNotIn("detected_lang", context)
        self.assertTrue(context["was_translated"])
        self.assertEqual(Session.deserialize(context["session"]).lang, "en-US",
                         "a foreign utterance is translated, so the session "
                         "returns to the internal language")

    def test_secondary_language_narrowed_out_by_translate_secondary_langs(self):
        # The exact configuration under which the stale key used to reach
        # core and win: a secondary language that translate_secondary_langs
        # excludes from valid_langs, with the default ignore_invalid_langs
        # (False), so the guard above does not reject the detection and the
        # old code still published it.
        transformer = make_translator(
            ["en-US", "nl-NL"], "nl",
            verify_lang=True, translate_secondary_langs=True)
        _, context = run(transformer, "en-US")
        self.assertNotIn("detected_lang", context)
        self.assertTrue(context["was_translated"])
        self.assertEqual(Session.deserialize(context["session"]).lang, "en-US")


if __name__ == "__main__":
    unittest.main()
