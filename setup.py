from setuptools import setup
from os import path, getenv

UTTERANCE_ENTRY_POINT = 'ovos-utterance-translation-plugin=ovos_bidirectional_translation_plugin:UtteranceTranslator'
DIALOG_ENTRY_POINT = 'ovos-dialog-translation-plugin=ovos_bidirectional_translation_plugin:DialogTranslator'


setup(
    name='ovos-bidirectional-translation-plugin',
    version="0.0.0a1",
    description='Bidirectional translation plugin to make OVOS understand any language',
    url='https://github.com/OpenVoiceOS/ovos_bidirectional_translation_plugin',
    author='jarbasAi',
    author_email='jarbasai@mailfence.com',
    packages=['ovos_bidirectional_translation_plugin'],
    zip_safe=True,
    keywords='OVOS plugin utterance transformer',
    entry_points={
        'neon.plugin.text': UTTERANCE_ENTRY_POINT,
        "opm.transformer.dialog": DIALOG_ENTRY_POINT
    }
)
