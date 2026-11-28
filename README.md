# OVOS Bidirectional Translation Plugin

This package holds two OVOS plugins: a `UtteranceTransformer` and a `DialogTransformer`. Together they let OVOS understand and answer in any language, even one the installed skills do not support directly.

> This plugin is still in **alpha**.

## Install

```console
pip install ovos-bidirectional-translation-plugin
```

## Language support in OVOS

This section is a refresher on how OVOS handles language.

- A default language is set in `mycroft.conf`. This is the OVOS primary language. All skills, TTS plugins, and STT plugins must support it.
- Extra languages can also be set in `mycroft.conf`. STT and TTS plugins in use must support these languages too. If an installed skill does not support one of them, OVOS ignores that skill for that language. Support can also be partial, per intent.
- Skills register intents for each supported language. Together these intents define the languages OVOS can speak.
- Each utterance carries an assigned language, through the session (`message.context`). OVOS picks this language from, in order of preference:
  - the default language, if nothing else is set
  - the wake word used
  - the language detected in speech (functional plugins for this exist, work is ongoing)
  - the language of a recognized user (not yet implemented)
  - the language set by the client application, for example a HiveMind satellite

```javascript
{
  // Primary Language
  // Code is a BCP-47 identifier (https://tools.ietf.org/html/bcp47), lowercased
  "lang": "en-us",

  // Secondary languages will also have their resource files loaded into memory
  // but intents will only be considered if that lang is tagged with the utterance at STT step
  "secondary_langs": []
}
```

## How it works

The `ovos-utterance-translation-plugin` plugin can detect the language of an utterance. When `"verify_lang": true` is set, it compares the detected language against the session language. This handles cases such as a chat platform where a user can write in any language and the session language may be wrong.

When `"ignore_invalid_langs": true` is set, the plugin ignores a detected language that is not one of the configured native languages, to guard against false detections. Otherwise, it fixes the session language to the detected one.

Language tags are compared by tag distance, the same rule the rest of OVOS applies.
A regional variant counts as one of the native languages, so `ar-SA` is native when
the system supports `ar`, and `pt-BR` is native when the system supports `pt-PT`.
A macrolanguage member such as `arz` is a different language and is translated.

If the session language is not one of the native languages, the plugin translates the utterance to the primary language, so OVOS can understand it.

The native languages are the primary language plus the secondary languages. Set `"translate_secondary_langs": true` to keep only the primary language native, so the plugin also translates the secondary languages before OVOS handles them.

A language detector answers from all the languages it knows, which is about 180 for a
typical model. A box that runs two languages still gets an answer from all of them, and
short utterances are where that is least reliable. Set
`"restrict_detection_to_valid_langs": true` to keep only the native languages in the
answer. The plugin reads the detector scores and takes the best native language.

This option is off by default, and it is not a free improvement. The detected language
also decides whether to translate. A detector held to the native languages cannot report
the foreign language that translation exists to handle, so this option trades translation
of other languages for a more stable answer inside a known set. Use it on a multilingual
box that does not want translation. Do not use it on a box that does.

This option needs a language detector that reports scores, which means one with a real
`detect_probs`. Many detectors have only `detect`, and the plugin cannot restrict an
answer it gets no scores for. In that case the plugin writes a warning that the option is
inoperative and uses the plain detection, so the box keeps working and the log says why
the setting does nothing.

If no native language is in the answer, the plugin reports what the detector said, because
a made-up native answer cannot be told apart from a real one.

When `"bidirectional": true` is set, the `ovos-dialog-translation-plugin` plugin then translates OVOS dialogs back to the original session language. Otherwise OVOS answers in its primary language, even if the user spoke in a different one.

## Prerequisites

This plugin needs a language detection plugin and a language translation plugin configured beforehand.

In `ovos-docker`, install this plugin in both `ovos-core` and `ovos-audio`, together with the translation plugins.

Recommended plugins:

- [ovos-translate-plugin-nllb](https://github.com/OpenVoiceOS/ovos-translate-plugin-nllb) (local)
- [ovos-translate-server-plugin](https://github.com/OpenVoiceOS/ovos-translate-server-plugin) (remote, public server list)

```json
{
  "language": {
    "detection_module": "ovos-lang-detect-ngram-lm",
    "translation_module": "ovos-translate-plugin-nllb",
    "ovos-translate-plugin-nllb": {
      "model": "nllb-200_600M_int8"
    }
  }
}
```

## Configuration

```json
{
  "utterance_transformers": {
    "ovos-utterance-translation-plugin": {
      "bidirectional": true,
      "verify_lang": false,
      "ignore_invalid_langs": true,
      "translate_secondary_langs": false,
      "restrict_detection_to_valid_langs": false
    }
  },
  "dialog_transformers": {
    "ovos-dialog-translation-plugin": {}
  }
}
```

## Related projects

- [OpenVoiceOS/ovos-translate-plugin-nllb](https://github.com/OpenVoiceOS/ovos-translate-plugin-nllb) — local translation plugin
- [OpenVoiceOS/ovos-translate-server-plugin](https://github.com/OpenVoiceOS/ovos-translate-server-plugin) — remote translation plugin, backed by a public server list
- [OpenVoiceOS/ovos-google-translate-plugin](https://github.com/OpenVoiceOS/ovos-google-translate-plugin) — translation plugin backed by Google Translate

## License

Apache-2.0. See [LICENSE](LICENSE).
