# SPDX-License-Identifier: Apache-2.0
# Exécutable autonome de DevOps Builder (PyInstaller) : un dossier par système, sans Python à installer.
# Construit par .github/workflows/publication.yml ; en local : pyinstaller packaging/devops-builder.spec
import shutil
import sys
from importlib import metadata
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

datas = collect_data_files("devops_builder") + collect_data_files("qt_material") + collect_data_files("qtawesome")
# métadonnées (version) et licences des paquets embarqués, dans leurs dossiers *.dist-info
for dist in ("izinum-devops-builder", "PySide6_Essentials", "shiboken6", "QtAwesome", "QtPy", "qt-material", "pydantic",
             "pydantic_core", "PyYAML", "Jinja2", "MarkupSafe", "typing_extensions", "annotated-types", "typing-inspection"):
    datas += copy_metadata(dist)

# Licences jointes (LGPL de Qt et PySide6, polices, Python) et adresses des sources de Qt et PySide6
build = Path(workpath)
build.mkdir(parents=True, exist_ok=True)
pyside = metadata.version("PySide6_Essentials")
qt = ".".join(pyside.split(".")[:3])
(build / "SOURCES.txt").write_text(
    f"PySide6 et shiboken6 {pyside} : https://download.qt.io/official_releases/QtForPython/pyside6/"
    f"PySide6-{pyside}-src/\n"
    f"Qt {qt} : https://download.qt.io/official_releases/qt/{'.'.join(qt.split('.')[:2])}/{qt}/single/\n"
    "Dépôt de PySide6 : https://code.qt.io/cgit/pyside/pyside-setup.git/\n", encoding="utf-8")
python_licence = next(p for p in (Path(sys.base_prefix) / "LICENSE.txt",
                                  *Path(sys.base_prefix).glob(f"lib/python{sys.version_info[0]}.{sys.version_info[1]}/LICENSE.txt"))
                      if p.exists())
shutil.copy(python_licence, build / "PYTHON-LICENSE.txt")
licences = [(str(p), "LICENCES") for p in Path("licences").iterdir()]
licences += [(str(build / "SOURCES.txt"), "LICENCES"), (str(build / "PYTHON-LICENSE.txt"), "LICENCES"),
             ("../LICENSE", "LICENCES"), ("../NOTICE", "LICENCES"), ("../docs/licences-tierces.md", "LICENCES")]
datas += licences
# PySide6 : seuls les modules utilisés sont embarqués (le paquet complet dépasse 1 Go)
excludes = ["PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras", "PySide6.Qt3DInput",
            "PySide6.Qt3DLogic", "PySide6.Qt3DRender", "PySide6.QtBluetooth", "PySide6.QtCharts",
            "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtLocation", "PySide6.QtMultimedia",
            "PySide6.QtMultimediaWidgets", "PySide6.QtNfc", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
            "PySide6.QtPositioning", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtRemoteObjects",
            "PySide6.QtScxml", "PySide6.QtSensors", "PySide6.QtSerialBus", "PySide6.QtSerialPort",
            "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtWebChannel", "PySide6.QtWebEngineCore",
            "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets", "PySide6.QtWebView", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
            "tkinter", "numpy"]

a = Analysis(["lanceur.py"], pathex=[".."], datas=datas, hiddenimports=["devops_builder.ui.app"], excludes=excludes)
# Le greffon du clavier virtuel tire Qt Quick et QML (une trentaine de Mo) : inutiles à une application Widgets
UNUSED = ("Qt6Qml", "QtQml", "Qt6Quick", "QtQuick", "Qt6Pdf", "QtPdf", "VirtualKeyboard", "virtualkeyboard", "qpdf")
a.binaries = [b for b in a.binaries if not any(u in b[0] for u in UNUSED)]
a.datas = [d for d in a.datas if not any(u in d[0] for u in UNUSED)]
pyz = PYZ(a.pure)
# Python en mode UTF-8 : fichiers et sorties en UTF-8 quel que soit le système
exe = EXE(pyz, a.scripts, [("X utf8_mode=1", None, "OPTION")], exclude_binaries=True, name="devops-builder", console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="devops-builder", upx=False)
if sys.platform == "darwin":
    app = BUNDLE(coll, name="DevOps Builder.app", bundle_identifier="fr.izinum.devops-builder",
                 info_plist={"NSHighResolutionCapable": True, "LSApplicationCategoryType": "public.app-category.developer-tools"})
