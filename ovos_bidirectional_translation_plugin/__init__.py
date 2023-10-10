from ovos_bus_client.session import Session, SessionManager
from ovos_config.config import Configuration
from ovos_config.locale import get_default_lang
from ovos_plugin_manager.language import OVOSLangDetectionFactory, OVOSLangTranslationFactory
from ovos_plugin_manager.templates.transformers import UtteranceTransformer,DialogTransformer
from ovos_utils.log import LOG


class UtteranceTranslator(UtteranceTransformer):

    def __init__(self, name="ovos-utterance-translation-plugin", priority=5, config=None):
        super().__init__(name, priority, config)
        self.lang_detector = OVOSLangDetectionFactory.create()
        self.translator = OVOSLangTranslationFactory.create()

        self.bidirectional = self.config.get("bidirectional", True)
        self.verify_lang = self.config.get("verify_lang", False)
        self.ignore_invalid = self.config.get("ignore_invalid_langs", False)

    @property
    def internal_lang(self):
        return Configuration().get("lang", "en-us")

    @property
    def valid_langs(self):
        return list(set([self.internal_lang] + Configuration().get("secondary_langs", [])))

    def transform(self, utterances, context=None):
        context = context or {}
        if "session" in context:
            sess = Session.deserialize(context["session"])
        else:
            sess = SessionManager.get()

        utt = utterances[0]
        context["translation_mode"] = self.mode.value
        context["was_translated"] = False

        tx = False

        # check for language mismatch (default / detected)
        # - handle use case of a chat platform where users can write in any language
        if self.verify_lang:
            detected_lang = self.lang_detector.detect(utt)
            context["detected_lang"] = detected_lang
            if sess.lang != detected_lang:
                LOG.warning(f"Specified lang: {sess.lang} but detected {detected_lang}")
                if self.ignore_invalid and detected_lang not in self.valid_langs:
                    LOG.error(f"ignoring lang detection, {detected_lang} "
                              f"not in valid languages: {self.valid_langs}")
                else:
                    sess.lang = detected_lang

        # check if lang is unsupported
        if sess.lang not in self.valid_langs:
            # translate langs we know OVOS can't handle to a supported lang
            utt = self.translator.translate(utt, self.internal_lang, sess.lang)
            LOG.info(f"translated utterance: {utt}")
            context["was_translated"] = True

            # signal DialogTransformer to translate everything back to the input language
            if self.bidirectional:
                context["output_lang"] = sess.lang
                context["translate_dialogs"] = True  # consumed in DialogTransformer

            sess.lang = self.internal_lang

        context["session"] = sess.serialize()  # update session

        # return translated utterances + data
        return utterances, context


class DialogTranslator(UtteranceTransformer):

    def __init__(self, name="ovos-dialog-translation-plugin", priority=5, config=None):
        super().__init__(name, priority, config)
        self.translator = OVOSLangTranslationFactory.create()

    def transform(self, dialog: str, context: dict=None):
        context = context or {}
        if "session" in context:
            sess = Session.deserialize(context["session"])
        else:
            sess = SessionManager.get()

        if context.get("translate_dialogs"):
            lang = context.get("output_lang") or Configuration().get("lang", "en-us")
            utt = self.translator.translate(dialog, lang, sess.lang)
            sess.lang = lang
            context["was_translated"] = True
            context["session"] = sess.serialize()  # update session

        # return translated utterances + data
        return utterances, context
