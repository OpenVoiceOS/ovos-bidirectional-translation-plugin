from typing import List, Tuple, Optional, Dict, Any

from ovos_bus_client.session import Session, SessionManager
from ovos_config.config import Configuration
from ovos_plugin_manager.language import OVOSLangDetectionFactory, OVOSLangTranslationFactory
from ovos_plugin_manager.templates.transformers import UtteranceTransformer, DialogTransformer
from ovos_plugin_manager.templates.language import LanguageDetector, LanguageTranslator
from ovos_spec_tools import closest_lang, lang_matches
from ovos_utils.log import LOG

# a tag distance up to and including 10 is a usable match, the threshold the
# rest of the OVOS stack applies to language tags (max_distance is inclusive,
# per ovos_spec_tools and the ovos-plugin-manager dialect lookup). "pt-BR"
# matches "pt-PT", and a macrolanguage member such as "arz" matches "ar" at
# distance exactly 10, routing it to the macrolanguage's translation.
MAX_LANG_DISTANCE = 10


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
        # Restrict the detector's answer to the configured languages. OFF by
        # default, and deliberately so: see _detect_lang.
        self.restrict_detection = self.config.get("restrict_detection_to_valid_langs", False)

    @property
    def internal_lang(self) -> str:
        """Return the internal language set for the system."""
        return Configuration().get("lang", "en-us")

    @property
    def valid_langs(self) -> List[str]:
        """
        Return the languages the assistant handles without translation.

        The primary language is always one of them. The secondary languages join
        it unless `translate_secondary_langs` is set, which asks for everything
        outside the primary language to be translated.

        Returns:
            List[str]: The language tags that need no translation.
        """
        if self.translate_secondary:
            return [self.internal_lang]
        return list(set([self.internal_lang] + Configuration().get("secondary_langs", [])))

    def match_lang(self, lang: str) -> Optional[str]:
        """
        Return the supported language closest to the requested tag.

        A regional variant resolves to the supported tag of the same language,
        so "ar-SA" matches a system that supports "ar". Return None when no
        supported language is close enough.

        Args:
            lang (str): The requested BCP-47 language tag.

        Returns:
            Optional[str]: The matching entry of valid_langs, or None.
        """
        return closest_lang(lang, self.valid_langs, max_distance=MAX_LANG_DISTANCE)

    def _detect_lang(self, utt: str) -> str:
        """Detect the language of *utt*, optionally restricted to valid_langs.

        The LanguageDetector template takes no candidate list, unlike the STT
        template's ``detect_language(audio, valid_langs=...)``. A box that runs
        two languages still gets an answer drawn from about 180, and the short
        utterances this transformer sees are where that is least reliable.
        ``detect_probs`` makes the restriction implementable here, with no
        change to the template, which is ovos-plugin-manager's and core's to
        merge.

        It is OFF by default because it is not a free improvement: for this
        plugin the detected language is also what decides whether to TRANSLATE.
        A detector held to the configured languages can never report the
        foreign language that bidirectional translation exists to handle, so
        turning this on trades cross-language translation for stability within
        a known set. That is the right trade for a multilingual box that does
        not want translation, and the wrong one for a box that does.

        Args:
            utt (str): The utterance to classify.

        Returns:
            str: The detected language tag.
        """
        if not self.restrict_detection:
            return self.lang_detector.detect(utt)
        try:
            probs = self.lang_detector.detect_probs(utt)
        except NotImplementedError:
            # A detector that declines the call by raising.
            probs = None
        if not probs:
            # The common case is quieter than a raise: LanguageDetector
            # declares detect_probs abstract with no body, and a subclass that
            # overrides detect() only still instantiates, so the call RETURNS
            # None instead of raising. An empty map says the same thing. Either
            # way there are no scores to restrict, and the option cannot work.
            LOG.warning(f"{self.lang_detector} returned no detection scores; "
                        f"restrict_detection_to_valid_langs is inoperative")
            return self.lang_detector.detect(utt)
        candidates = {lang: score for lang, score in probs.items()
                      if self.match_lang(lang) is not None}
        if not candidates:
            # Nothing the box supports was in the running. Report what the
            # detector actually said rather than inventing a supported answer:
            # the caller still has to decide, and a fabricated match would be
            # indistinguishable from a real one.
            LOG.debug(f"no valid language among detections {probs}")
            return self.lang_detector.detect(utt)
        best = max(candidates, key=candidates.get)
        if max(probs, key=probs.get) != best:
            LOG.debug(f"restricted detection to {best} from {probs}")
        return best

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
        detected_lang = None
        rejected = False
        if self.verify_lang:
            detected_lang = self._detect_lang(utt)
            if not lang_matches(sess.lang, detected_lang, max_distance=MAX_LANG_DISTANCE):
                LOG.warning(f"Specified lang: {sess.lang} but detected {detected_lang}")
                if self.ignore_invalid and self.match_lang(detected_lang) is None:
                    LOG.error(f"Ignoring lang detection, {detected_lang} not in valid languages: {self.valid_langs}")
                    rejected = True
                else:
                    sess.lang = detected_lang

        # Check if the detected language is unsupported
        if self.match_lang(sess.lang) is None:
            # Translate the utterance to the internal language
            utt = self.translator.translate(utt, self.internal_lang, sess.lang)
            LOG.info(f"Translated utterance: {utt}")

            # this only solves the issue for the first utterance in the list, but better than it not working at all
            utterances = [utt] + utterances[1:] if len(utterances) > 1 else [utt]
            context["was_translated"] = True

            # signal DialogTransformer to translate everything back to the input language
            if self.bidirectional:
                context["output_lang"] = sess.lang
                context["translate_dialogs"] = True  # Consumed in DialogTransformer

            sess.lang = self.internal_lang

        # Publish the detection only when it still describes the utterance
        # core is about to see. Core ranks context["detected_lang"] ABOVE the
        # session language in disambiguate_lang, so a stale value here does
        # not merely sit unused: it outranks a session the lines above already
        # corrected.
        #
        # Two ways a detection stops describing that utterance. The guard
        # above REJECTS it, and the log says "Ignoring lang detection"; this
        # used to still publish because core applies its own filter against
        # get_valid_languages(), which hides the stale key whenever that set
        # matches valid_langs. The two diverge under translate_secondary_langs,
        # which narrows valid_langs to the internal language while core keeps
        # the secondary languages, so the rejected detection reached core and
        # won while the log claimed it was ignored.
        #
        # A detection core NEVER sees: once the block above translates, the
        # text core receives is internal_lang, not detected_lang, and the
        # session was just set to internal_lang to match. Publishing the
        # pre-translation tag here would outrank that correction with a
        # language the utterance is no longer written in.
        if detected_lang is not None and not rejected and not context["was_translated"]:
            context["detected_lang"] = detected_lang

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
            if not lang_matches(lang, sess.lang, max_distance=MAX_LANG_DISTANCE):
                dialog = self.translator.translate(dialog, lang, sess.lang)
                sess.lang = lang
                context["was_translated"] = True
                context["session"] = sess.serialize()  # Update session in context

        # Return translated dialog and updated context
        return dialog, context
