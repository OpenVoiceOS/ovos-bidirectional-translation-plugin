from setuptools import setup
from os import path, getenv
import os
UTTERANCE_ENTRY_POINT = 'ovos-utterance-translation-plugin=ovos_bidirectional_translation_plugin:UtteranceTranslator'
DIALOG_ENTRY_POINT = 'ovos-dialog-translation-plugin=ovos_bidirectional_translation_plugin:DialogTranslator'

def get_version():
    """ Find the version of the package"""
    version = None
    version_file = os.path.join('ovos_bidirectional_translation_plugin', 'version.py')
    print(f"ERROR: version file: {version_file}")
    major, minor, build, alpha = (None, None, None, None)
    with open(version_file) as f:
        for line in f:
            if 'VERSION_MAJOR' in line:
                major = line.split('=')[1].strip()
            elif 'VERSION_MINOR' in line:
                minor = line.split('=')[1].strip()
            elif 'VERSION_BUILD' in line:
                build = line.split('=')[1].strip()
            elif 'VERSION_ALPHA' in line:
                alpha = line.split('=')[1].strip()

            if ((major and minor and build and alpha) or
                    '# END_VERSION_BLOCK' in line):
                break
    version = f"{major}.{minor}.{build}"
    if alpha and int(alpha) > 0:
        version += f"a{alpha}"
    return version

setup(
    name='ovos-bidirectional-translation-plugin',
    version=get_version(),
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
