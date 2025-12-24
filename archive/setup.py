from setuptools import setup

APP = ['scoreboard.py']
DATA_FILES = [('.', ['.env'])]
OPTIONS = {
    'argv_emulation': False,
    'semi_standalone': True,
    'packages': ['rumps', 'requests', 'dotenv', 'urllib3', 'certifi', 'charset_normalizer', 'idna'],
    'plist': {
        'LSUIElement': True,
        'CFBundleName': 'NBA Scoreboard',
    },
    'includes': ['dotenv'],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
