# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['s2xml_gui.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('bhav_encoder.py', '.'),
        ('bhav_sugar.py', '.'),
        ('bhav_xml_helpers.py', '.'),
        ('dbpf_reader.py', '.'),
        ('dbpf_writer.py', '.'),
        ('glob_objd_encoders.py', '.'),
        ('linter.py', '.'),
        ('misc_encoders.py', '.'),
        ('opcodes.py', '.'),
        ('s2xml_compile.py', '.'),
        ('s2xml_decompile.py', '.'),
        ('s2xml_diff.py', '.'),
        ('str_encoder.py', '.'),
        ('ttab_ctss_bcon_encoders.py', '.'),
        ('txtr_encoder.py', '.'),
        ('nref_vers_encoders.py', '.'),
        ('xml_parser.py', '.'),
        ('xml_serializer.py', '.'),
        ('example_mod', 'example_mod'),
    ],
    hiddenimports=[
        'xml.etree.ElementTree',
        'tkinter', 'tkinter.ttk', 'tkinter.filedialog',
        'tkinter.messagebox', 'tkinter.font',
        'pathlib', 'threading', 'queue',
        'PIL', 'PIL.Image',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='S2XML Compiler',
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
