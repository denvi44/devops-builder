# Licences de l'exécutable DevOps Builder

DevOps Builder est distribué sous la licence Apache 2.0 (`LICENSE`, `NOTICE`). L'exécutable autonome
embarque aussi Python, Qt (par PySide6), des paquets Python et des polices ; ce dossier joint leurs licences.
Le détail des dépendances est dans `licences-tierces.md`.

## Qt et PySide6 (LGPL-3.0)

Qt et PySide6 sont utilisés sous la GNU Lesser General Public License v3 (`LGPL-3.0.txt`, qui complète la
`GPL-3.0.txt`). Ils restent des bibliothèques séparées et remplaçables : l'exécutable est un dossier, pas un
fichier unique, et les bibliothèques Qt et PySide6 se trouvent dans `_internal/PySide6/` (sous macOS, dans
`DevOps Builder.app/Contents/Frameworks/PySide6/`). Pour utiliser une autre version compatible, remplacer ces
fichiers par ceux d'une version de PySide6 construite pour le même Python.

Versions embarquées et adresses de leurs sources : `SOURCES.txt`. Les sources sont aussi fournies sur
demande, pendant trois ans, par un signalement sur https://github.com/denvi44/devops-builder/issues.

## Paquets Python

Licence de chacun dans son dossier `*.dist-info` (sous `_internal/`) : QtAwesome et QtPy (MIT), qt-material
(BSD-2-Clause), pydantic et pydantic-core (MIT), PyYAML (MIT), Jinja2 et MarkupSafe (BSD-3-Clause),
typing-extensions (PSF-2.0), annotated-types et typing-inspection (MIT). Python lui-même : `PYTHON-LICENSE.txt`
(PSF-2.0).

## Polices

| Police | Fournie par | Licence |
| --- | --- | --- |
| Material Design Icons 5.9.55 et 6.9.96 (Pictogrammers) | QtAwesome | Apache 2.0 (`LICENSE`) ; les icônes de marques n'en font pas partie |
| Font Awesome Free 5.15.4 et 6.7.2 (Fonticons) | QtAwesome | polices : SIL OFL 1.1 (`OFL-1.1.txt`) ; icônes : CC BY 4.0 (`CC-BY-4.0.txt`) |
| Elusive Icons 2.0 (Aristeides Stathopoulos) | QtAwesome | SIL OFL 1.1 (`OFL-1.1.txt`) |
| Phosphor 1.3.0 (Phosphor Icons) | QtAwesome | MIT |
| Remix Icon 2.5.0 (Remix Design) | QtAwesome | Apache 2.0 (`LICENSE`) |
| Codicons 0.0.36 (Microsoft) | QtAwesome | CC BY 4.0 (`CC-BY-4.0.txt`) |
| Roboto 2 (Google) | qt-material | Apache 2.0 (`LICENSE`) |

L'interface n'affiche que des icônes Material Design Icons 6 ; les autres polices sont chargées par QtAwesome.

## Bibliothèques du système

L'exécutable Linux embarque des bibliothèques d'Ubuntu 22.04 dont Qt a besoin (X11, xcb, GTK, cairo,
fontconfig…), chacune sous sa licence (le plus souvent MIT ou LGPL) ; leurs sources sont celles des paquets
Ubuntu 22.04 du même nom. Les exécutables Windows et macOS n'en embarquent pas, hormis celles de Python : OpenSSL
(Apache 2.0), libffi (MIT) et, sous Windows, la bibliothèque d'exécution Visual C++ (redistribuable de Microsoft).
