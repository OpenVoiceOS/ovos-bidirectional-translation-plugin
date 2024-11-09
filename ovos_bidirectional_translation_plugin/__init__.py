from typing import List, Tuple, Optional, Dict, Any

from ovos_bus_client.session import Session, SessionManager
from ovos_config.config import Configuration
from ovos_plugin_manager.language import OVOSLangDetectionFactory, OVOSLangTranslationFactory
from ovos_plugin_manager.templates.transformers import UtteranceTransformer, DialogTransformer
from ovos_plugin_manager.templates.language import LanguageDetector, LanguageTranslator
from ovos_utils.log import LOG


class UtteranceTranslator(UtteranceTransformer):
    """A transformer that translates user utterances to a supported language if needed."""

    def __init__(self, name: str = "ovos-utterance-translation-plugin", priority: int = 5,
                 config: Optional[Dict[str, Any]] = None):
        """
        Initialize the UtteranceTranslator with optional configuration.

        Args:
            name (str): Name of the plugin.
            priority (int): Priority of the transformer.
            config (Optional[Dict[str, Any]]): Configuration dictionary.
        """
        super().__init__(name, priority, config)
        self.lang_detector: LanguageDetector = OVOSLangDetectionFactory.create()
        self.translator: LanguageTranslator = OVOSLangTranslationFactory.create()
        self.bidirectional = self.config.get("bidirectional", True)
        self.verify_lang = self.config.get("verify_lang", False)
        self.ignore_invalid = self.config.get("ignore_invalid_langs", False)
        self.translate_secondary = self.config.get("translate_secondary_langs", False)

    @property
    def internal_lang(self) -> str:
        """Return the internal language set for the system."""
        return Configuration().get("lang", "en-us")

    @property
    def valid_langs(self) -> List[str]:
        """Return the list of valid languages for translation."""
        if self.translate_secondary:
            return [self.internal_lang]
        return list(set([self.internal_lang] + Configuration().get("secondary_langs", [])))

    def transform(self, utterances: List[str], context: Optional[Dict[str, Any]] = None) -> Tuple[
        List[str], Dict[str, Any]]:
        """
        Transform the provided utterances by translating them to a valid language if needed.

        Args:
            utterances (List[str]): List of user-provided utterances.
            context (Optional[Dict[str, Any]]): Contextual data for the session.

        Returns:
            Tuple[List[str], Dict[str, Any]]: The possibly translated utterances and updated context.
        """
        context = context or {}
        if "session" in context:
            sess = Session.deserialize(context["session"])
        else:
            sess = SessionManager.get()

        utt = utterances[0]
        context["was_translated"] = False

        # Check for language mismatch (specified vs detected)
        if self.verify_lang:
            detected_lang = self.lang_detector.detect(utt)
            context["detected_lang"] = detected_lang
            if sess.lang != detected_lang:
                LOG.warning(f"Specified lang: {sess.lang} but detected {detected_lang}")
                if self.ignore_invalid and detected_lang not in self.valid_langs:
                    LOG.error(f"Ignoring lang detection, {detected_lang} not in valid languages: {self.valid_langs}")
                else:
                    sess.lang = detected_lang

        # Check if the detected language is unsupported
        if sess.lang not in self.valid_langs:
            # Translate the utterance to the internal language
            utt = self.translator.translate(utt, self.internal_lang, sess.lang)
            LOG.info(f"Translated utterance: {utt}")
            context["was_translated"] = True

            # signal DialogTransformer to translate everything back to the input language
            if self.bidirectional:
                context["output_lang"] = sess.lang
                context["translate_dialogs"] = True  # Consumed in DialogTransformer

            sess.lang = self.internal_lang

        context["session"] = sess.serialize()  # Update session in context

        # Return the translated utterances and updated context
        return utterances, context


class DialogTranslator(DialogTransformer):
    """A transformer that translates system dialog to the desired output language."""

    def __init__(self, name: str = "ovos-dialog-translation-plugin", priority: int = 5,
                 config: Optional[Dict[str, Any]] = None):
        """
        Initialize the DialogTranslator with optional configuration.

        Args:
            name (str): Name of the plugin.
            priority (int): Priority of the transformer.
            config (Optional[Dict[str, Any]]): Configuration dictionary.
        """
        super().__init__(name, priority, config)
        self.translator = OVOSLangTranslationFactory.create()
        self.output_langs = {}

    def bind(self, bus=None):
        """
        Bind the dialog translator to the message bus and set up language output events.

        Args:
            bus: The message bus instance to bind to.
        """
        super().bind(bus)
        self.bus.on("ovos.language.output.force", self.handle_output_lang)
        self.bus.on("ovos.language.output.reset", self.handle_reset_output_lang)

    def handle_output_lang(self, message):
        """
        Handle intent to force output in a specified language.

        Args:
            message: Message containing the target language for output.
        """
        sess = SessionManager.get(message)
        new_lang = message.data["lang"]
        self.output_langs[sess.session_id] = new_lang

    def handle_reset_output_lang(self, message):
        """
        Disable forced output language for a session.

        Args:
            message: Message indicating reset of forced language output.
        """
        sess = SessionManager.get(message)
        if sess.session_id in self.output_langs:
            self.output_langs.pop(sess.session_id)

    def transform(self, dialog: str, context: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Transform the dialog by translating it to the output language if needed.

        Args:
            dialog (str): The system-provided dialog.
            context (Optional[Dict[str, Any]]): Contextual data for the session.

        Returns:
            Tuple[str, Dict[str, Any]]: The possibly translated dialog and updated context.
        """
        context = context or {}
        if "session" in context:
            sess = Session.deserialize(context["session"])
        else:
            sess = SessionManager.get()

        # Override language for session if specified
        if sess.session_id in self.output_langs:
            context["translate_dialogs"] = True
            context["output_lang"] = self.output_langs[sess.session_id]

        if context.get("translate_dialogs"):
            lang = context.get("output_lang") or Configuration().get("lang", "en-us")
            if lang != sess.lang:
                dialog = self.translator.translate(dialog, lang, sess.lang)
                sess.lang = lang
                context["was_translated"] = True
                context["session"] = sess.serialize()  # Update session in context

        # Return translated dialog and updated context
        return dialog, context
