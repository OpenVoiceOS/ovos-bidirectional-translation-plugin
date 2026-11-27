import unittest
from importlib.metadata import entry_points
from unittest.mock import MagicMock, patch

from ovos_bus_client.session import Session

import ovos_bidirectional_translation_plugin as plugin


def load(group, name):
    return entry_points(group=group)[name].load()


class TestUtteranceTranslator(unittest.TestCase):
    @patch.object(plugin, "Configuration", return_value={"lang": "en-US", "secondary_langs": []})
    @patch.object(plugin, "OVOSLangDetectionFactory")
    @patch.object(plugin, "OVOSLangTranslationFactory")
    def test_translates_unsupported_lang(self, translation_factory, detection_factory, _config):
        translator = MagicMock()
        translator.translate.return_value = "what time is it"
        translation_factory.create.return_value = translator
        detection_factory.create.return_value = MagicMock()

        cls = load("opm.transformer.text", "ovos-utterance-translation-plugin")
        self.assertIs(cls, plugin.UtteranceTranslator)
        sess = Session(lang="de-DE")
        utts, ctx = cls().transform(["wie spät ist es"], {"session": sess.serialize()})

        translator.translate.assert_called_once_with("wie spät ist es", "en-US", "de-DE")
        self.assertEqual(utts, ["what time is it"])
        self.assertTrue(ctx["was_translated"])
        self.assertEqual(ctx["output_lang"], "de-DE")
        self.assertEqual(Session.deserialize(ctx["session"]).lang, "en-US")


class TestDialogTranslator(unittest.TestCase):
    @patch.object(plugin, "Configuration", return_value={"lang": "en-US"})
    @patch.object(plugin, "OVOSLangTranslationFactory")
    def test_translates_dialog_back(self, translation_factory, _config):
        translator = MagicMock()
        translator.translate.return_value = "es ist zehn Uhr"
        translation_factory.create.return_value = translator

        cls = load("opm.transformer.dialog", "ovos-dialog-translation-plugin")
        self.assertIs(cls, plugin.DialogTranslator)
        ctx = {"session": Session(lang="en-US").serialize(),
               "translate_dialogs": True, "output_lang": "de-DE"}
        dialog, ctx = cls().transform("it is ten o'clock", ctx)

        translator.translate.assert_called_once_with("it is ten o'clock", "de-DE", "en-US")
        self.assertEqual(dialog, "es ist zehn Uhr")
        self.assertEqual(Session.deserialize(ctx["session"]).lang, "de-DE")


if __name__ == "__main__":
    unittest.main()
