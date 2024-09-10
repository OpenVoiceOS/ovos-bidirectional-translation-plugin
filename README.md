# OVOS Bidirectional Translation plugin

This package includes a UtteranceTransformer plugin and a DialogTransformer plugin, they work together to allow OVOS to speak in ANY language

> This plugin is still in **alpha**

## Lang support

Refreshser on OVOS language support system

- a default language is defined in mycroft.conf, this is the OVOS primary language
  - all skills, TTS, and STT plugins MUST support this language
- extra languages are defined in mycroft.conf, OVOs can also speak these languages
  - STT and TTS plugins in use MUST support all these languages
  - if installed skills do not support these languages they will be ignored when language is in use
  - support can be per intent (partially translated skills supported)
- skills register intents for all the above languages, this list represents the languages OVOS can speak
- each utterance has an assigned language via Session (message.context)
  - default lang used if missing
  - defined in wake word
  - detected in speech (WIP - functional plugins exist)
  - default lang from user recognition (idea)
  - defined in client application being used (eg, sent from hivemind satellites)

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

- (OPTIONAL) the `ovos-bidirectional-utterance-transformer` plugin will detect the text language, if it doesn't match the Session language it will "fix" that
  - `"verify_lang": true` in config
  - handle use case of a chat platform where users can write in any language (Session may have primary lang wrongly assigned)
  - (OPTIONAL) ignore lang detections that are not in the list of native languages (consider false detection)
    - `"ignore_invalid_langs": true` in config
  - Session is now fixed to detected_lang
- if Session language is not one of the native languages, translate it to the primary language
  - OVOS can now understand the utterance
  - (OPTIONAL) tell `ovos-bidirectional-dialog-transformer` to translate all dialogs to original Session language
    - if not set OVOS will answer in it's primary language, even if you spoke to it in a different one
    - `"bidirectional": true` in config

## Pre Requisites

This plugin assumes you have configured language detection and language translation plugin beforehand

if running in ovos-docker you need this plugin installed in ovos-core and ovos-audio, you also need the translation plugins

Recommend plugins:
- https://github.com/OpenVoiceOS/ovos-translate-plugin-nllb (local)
- https://github.com/OpenVoiceOS/ovos-translate-server-plugin  (remote, public server list)

```
"language": {
    "detection_module": "ovos-lang-detect-ngram-lm",
    "translation_module": "ovos-translate-plugin-nllb",
    "ovos-translate-plugin-nllb": {
        "model": "nllb-200_600M_int8"
    }
}
```

## Configuration

```
"utterance_transformers": {
    "ovos-utterance-translation-plugin": {
      "bidirectional": true,
      "verify_lang": false,
      "ignore_invalid": true,
      "translate_secondary_langs": false
    }
},
"dialog_transformers": {
    "ovos-dialog-translation-plugin": {}
}
```
