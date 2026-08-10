"""Language tag matching in the translation transformers.

A regional variant of a supported language needs no translation. A
macrolanguage member also needs no translation, since it matches its
macrolanguage at the inclusive distance-10 threshold. Only a genuinely
different language does.
"""
import unittest
from unittest.mock import Mock, patch

from ovos_bus_client.session import Session

import ovos_bidirectional_translation_plugin as plugin
from ovos_bidirectional_translation_plugin import UtteranceTranslator, DialogTranslator


def make_utterance_translator(langs, **config):
    """Build an UtteranceTranslator with mocked language plugins.

    Args:
        langs (list): The languages the system supports. The first entry is the
            internal language, the rest are secondary languages.
        **config: Plugin configuration overrides.

    Returns:
        UtteranceTranslator: The transformer, with mock detector and translator.
    """
    conf = {"lang": langs[0], "secondary_langs": list(langs[1:])}
    with patch.object(plugin.OVOSLangDetectionFactory, "create", Mock()), \
            patch.object(plugin.OVOSLangTranslationFactory, "create", Mock()), \
            patch.object(plugin, "Configuration", Mock(return_value=conf)):
        transformer = UtteranceTranslator(config=config)
    transformer.translator.translate = Mock(return_value="translated")
    transformer._conf = conf
    return transformer


def run_transform(transformer, lang, utterance="hello"):
    """Transform one utterance in a session of the given language.

    Args:
        transformer (UtteranceTranslator): The transformer under test.
        lang (str): The session language.
        utterance (str): The utterance to transform.

    Returns:
        tuple: The transformed utterances and the resulting context.
    """
    sess = Session(lang=lang)
    with patch.object(plugin, "Configuration", Mock(return_value=transformer._conf)):
        return transformer.transform([utterance], {"session": sess.serialize()})


class TestUtteranceLanguageMatching(unittest.TestCase):

    def test_regional_variant_of_supported_language_is_not_translated(self):
        transformer = make_utterance_translator(["en-US", "ar"])
        _, context = run_transform(transformer, "ar-SA")
        self.assertFalse(context["was_translated"])
        transformer.translator.translate.assert_not_called()

    def test_regional_variant_of_supported_region_is_not_translated(self):
        transformer = make_utterance_translator(["en-US", "pt-PT"])
        _, context = run_transform(transformer, "pt-BR")
        self.assertFalse(context["was_translated"])

    def test_regional_variant_of_internal_language_is_not_translated(self):
        transformer = make_utterance_translator(["en-US"])
        _, context = run_transform(transformer, "en-GB")
        self.assertFalse(context["was_translated"])

    def test_unsupported_language_is_translated(self):
        transformer = make_utterance_translator(["en-US", "ar"])
        utterances, context = run_transform(transformer, "de-DE")
        self.assertTrue(context["was_translated"])
        self.assertEqual(utterances, ["translated"])
        transformer.translator.translate.assert_called_once_with("hello", "en-US", "de-DE")

    def test_macrolanguage_member_is_not_translated(self):
        """A tag distance of exactly 10 is within the match threshold.

        `ovos_spec_tools.closest_lang`/`lang_matches` treat `max_distance` as
        inclusive, and `ovos-plugin-manager`'s dialect lookup relies on the same
        widening (`arz`/`ar` and `wuu`/`zh` match at distance exactly 10). A
        macrolanguage member therefore routes to the macrolanguage's translation
        instead of being translated as a distinct language, matching the rest
        of the OVOS stack.
        """
        for lang in ("arz", "ajp-Arab"):
            with self.subTest(lang=lang):
                transformer = make_utterance_translator(["en-US", "ar"])
                _, context = run_transform(transformer, lang)
                self.assertFalse(context["was_translated"])

    def test_detected_regional_variant_of_supported_language_is_honoured(self):
        transformer = make_utterance_translator(["en-US", "pt-PT"],
                                                verify_lang=True,
                                                ignore_invalid_langs=True)
        transformer.lang_detector.detect = Mock(return_value="pt-BR")
        _, context = run_transform(transformer, "en-US")
        self.assertEqual(context["detected_lang"], "pt-BR")
        self.assertEqual(Session.deserialize(context["session"]).lang, "pt-BR")

    def test_detected_unsupported_language_is_ignored(self):
        transformer = make_utterance_translator(["en-US", "pt-PT"],
                                                verify_lang=True,
                                                ignore_invalid_langs=True)
        transformer.lang_detector.detect = Mock(return_value="de-DE")
        _, context = run_transform(transformer, "en-US")
        self.assertEqual(Session.deserialize(context["session"]).lang, "en-US")
        self.assertFalse(context["was_translated"])


class TestDialogLanguageMatching(unittest.TestCase):

    def make_dialog_translator(self):
        with patch.object(plugin.OVOSLangTranslationFactory, "create", Mock()):
            transformer = DialogTranslator()
        transformer.translator.translate = Mock(return_value="translated")
        return transformer

    def test_output_language_matching_session_is_not_translated(self):
        transformer = self.make_dialog_translator()
        sess = Session(lang="en-US")
        dialog, context = transformer.transform("hello", {"session": sess.serialize(),
                                                          "translate_dialogs": True,
                                                          "output_lang": "en-GB"})
        self.assertEqual(dialog, "hello")
        transformer.translator.translate.assert_not_called()

    def test_output_language_differing_from_session_is_translated(self):
        transformer = self.make_dialog_translator()
        sess = Session(lang="en-US")
        dialog, context = transformer.transform("hello", {"session": sess.serialize(),
                                                          "translate_dialogs": True,
                                                          "output_lang": "de-DE"})
        self.assertEqual(dialog, "translated")
        transformer.translator.translate.assert_called_once_with("hello", "de-DE", "en-US")


if __name__ == "__main__":
    unittest.main()
