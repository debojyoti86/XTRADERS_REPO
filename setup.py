from cx_Freeze import setup, Executable
import sys

# Define the entry point of the application
entry_point = 'trading_ui.py'

# Define the build options
build_options = {
    'packages': [
        'decimal',
        'streamlit',
        'websockets',
        'requests',
        'dotenv',
        'pandas',
        'typing_extensions',
        'dataclasses',
        'yaml',
        'sqlalchemy',
        'firebase_admin',
        'google.protobuf',
        'altair',
        'numpy',
        'packaging',
        'PIL',
        'plotly',
        'protobuf',
        'pyarrow',
        'pydeck',
        'setuptools',
        'tornado',
        'watchdog'
    ],
    'includes': [
        'trading_engine',
        'trading_ui',
        'wallet',
        'exchange',
        'firebase_service'
    ],
    'excludes': ['tkinter', 'test'],
    'include_files': [
        ('.env', '.env'),
        ('requirements.txt', 'requirements.txt')
    ],
    'build_exe': './build/xtraders/',
    'include_msvcr': True
}

# Define the executables
executables = [
    Executable(
        script=entry_point,
        target_name='xtraders.exe',
        base=None
    )
]

# Setup the application
setup(
    name='XTraders',
    version='1.0',
    description='XTraders Trading Application',
    options={'build_exe': build_options},
    executables=executables
)