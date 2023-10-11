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
        context["was_translated"] = False

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


class DialogTranslator(DialogTransformer):

    def __init__(self, name="ovos-dialog-translation-plugin", priority=5, config=None):
        super().__init__(name, priority, config)
        self.translator = OVOSLangTranslationFactory.create()
        self.output_langs = {}

    def bind(self, bus=None):
        super().bind(bus)
        self.bus.on("ovos.language.output.force", self.handle_output_lang)
        self.bus.on("ovos.language.output.reset", self.handle_reset_output_lang)

    def handle_output_lang(self, message):
        """ intent to force output in a certain language"""
        sess = SessionManager.get(message)
        new_lang = message.data["lang"]
        self.output_langs[sess.session_id] = new_lang

    def handle_reset_output_lang(self, message):
        """ disable forced output """
        sess = SessionManager.get(message)
        if sess.session_id in self.output_langs:
            self.output_langs.pop(sess.session_id)

    def transform(self, dialog: str, context: dict=None):
        context = context or {}
        if "session" in context:
            sess = Session.deserialize(context["session"])
        else:
            sess = SessionManager.get()

        if sess.session_id in self.output_langs: # override for session
            context["translate_dialogs"] = True
            context["output_lang"] = self.output_langs[sess.session_id]

        if context.get("translate_dialogs"):
            lang = context.get("output_lang") or Configuration().get("lang", "en-us")
            if lang != sess.lang:
                utt = self.translator.translate(dialog, lang, sess.lang)
                sess.lang = lang
                context["was_translated"] = True
                context["session"] = sess.serialize()  # update session

        # return translated utterances + data
        return utterances, context
