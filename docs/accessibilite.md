# Accessibilité de l'application

État au 16 octobre 2026, version 0.20. Ce document décrit ce qui est vérifié, comment, et ce qui ne l'est pas
encore. Ce n'est pas une déclaration de conformité au sens du RGAA, qui s'applique aux sites et applications
web : pour un logiciel de bureau, le référentiel est la norme européenne **EN 301 549** (chapitre 11,
logiciels), qui reprend les critères des **WCAG 2.1** au niveau AA. Les critères du RGAA sont cités quand ils
correspondent, pour qui a l'habitude de les lire.

## Méthode

**Audit automatisé** (`devops_builder/ui/audit.py`, lancé par `python tools/audit_accessibilite.py` et par les
tests) : la fenêtre principale ouverte sur un exemple, puis chacun des onze dialogues et chaque page de
l'assistant, dans les deux thèmes. Il lit l'arbre d'accessibilité que Qt expose aux technologies d'assistance
et mesure le rendu à l'écran :

| Contrôle | Critère (WCAG 2.1 ; EN 301 549 ; RGAA) | Comment |
| --- | --- | --- |
| Nom accessible de chaque contrôle | 4.1.2 ; 11.4.1.2 ; 11.1, 7.1 | nom calculé par Qt, celui que reçoit le lecteur d'écran |
| Accès au clavier | 2.1.1 ; 11.2.1.1 ; 7.3 | chaque contrôle actif entre dans la tabulation (boutons radio : le groupe, puis les flèches ; barre d'outils : action présente au menu ou raccourci) |
| Focus visible | 2.4.7 ; 11.2.4.7 ; 10.7 | capture avant et après la prise de focus : au moins une ligne de pixels change avec un contraste de 3:1 |
| Contraste du texte | 1.4.3 ; 11.1.4.3 ; 3.2 | couleur du texte déclarée contre le fond réellement dessiné ; couples dessinés à la main (cartes, puces, gravités) calculés |
| Contraste des éléments graphiques | 1.4.11 ; 11.1.4.11 ; 3.3 | icônes de gravité et bord des cartes au focus : 3:1 |
| Titre de chaque fenêtre | 2.4.2 ; 11.2.4.2 ; 8.5 | non vide |
| Langue | 3.1.2 ; 11.3.1.2 ; 8.7 | aucun texte de Qt resté en anglais (boutons standard, docks, menus contextuels) |
| Raccourcis | 2.1.4 ; 11.2.1.4 ; 12.10 | aucun raccourci d'une seule touche caractère, aucun partagé par deux actions |
| Texte agrandi à 200 % | 1.4.4 ; 11.1.4.4 ; 10.4 | aucun libellé ni bouton coupé, fenêtre et dialogues sur un écran de 1920×1080 |

**Arbre lu par les lecteurs d'écran**, à chaque modification du code (CI) : l'application est lancée dans un
écran virtuel et son arbre est lu comme le lisent Orca, par AT-SPI sous Linux (`tools/arbre_accessibilite.py`),
et NVDA ou le Narrateur, par UI Automation sous Windows (`tools/arbre_uia.py`) : fenêtre principale, puis
dialogue des paramètres ouvert par l'action du bouton. Aucun élément atteignable au clavier ne doit être sans
nom, aucun texte de Qt en anglais. L'arbre lu est conservé comme artefact du job.

## Résultat

Les deux audits ne relèvent aucun constat sur la version 0.20. Ils ont trouvé, et la 0.20 a corrigé :

- les textes de Qt en anglais (« Close », « Float », « Cancel », boutons des boîtes de message, menus
  contextuels des champs) : la traduction française de Qt est chargée ;
- un focus presque invisible sur la plupart des contrôles (le thème Material ne le marquait que d'une légère
  teinte) : un anneau de deux pixels, dans la couleur principale, entoure le contrôle actif ;
- des contrastes insuffisants : avertissements en orange à 3,5:1, boutons d'action (« Générer », « Analyser »,
  « Exporter vers Git… ») à 2,8:1, boutons principaux à 4:1 ; couleurs ajustées, 4,5:1 au moins ;
- les messages de la barre d'état (brique ajoutée, refusée, déplacée, correction appliquée) n'étaient pas lus :
  ils sont annoncés aux lecteurs d'écran, sans déplacer le focus ; l'ajout et le déplacement d'une brique
  disent l'étape et la position ;
- les icônes d'étape étaient exposées comme des images sans nom ; deux zones de défilement et un jeu d'onglets
  n'avaient pas de nom ;
- réordonner une brique dans son étape demandait la souris : Alt+↑ et Alt+↓ ;
- la taille du texte était fixe : elle se règle de 100 à 200 % (Affichage › Taille du texte, Ctrl++ et Ctrl+-),
  sans texte coupé ; à 200 %, les messages des diagnostics passent à la ligne au lieu d'être tronqués.

Ce qui était déjà en place : un nom pour chaque contrôle et chaque brique (avec son niveau de prise en charge et
la gravité de son diagnostic), une alternative au clavier pour chaque glisser-déposer, l'information jamais
donnée par la seule couleur (gravité écrite et icône distincte), les deux thèmes.

## Ce qui n'est pas encore vérifié

- **Restitution réelle par un lecteur d'écran** : l'arbre est vérifié, pas l'écoute d'une session complète
  avec NVDA, le Narrateur, Orca ou VoiceOver (ordre de lecture, verbosité, annonces). VoiceOver n'est pas
  couvert du tout. Une session par lecteur, sur les quatre tutoriels du guide, est la prochaine étape.
- **Ordre de tabulation** (2.4.3 ; RGAA 12.8) : tous les contrôles y entrent, l'ordre n'est pas comparé à
  l'ordre visuel automatiquement.
- **Préférences du système** (EN 301 549 11.7) : le thème Material impose ses couleurs ; le mode contraste
  élevé de Windows et la taille de police du système ne sont pas suivis (la taille du texte se règle dans
  l'application).
- **Réagencement** (1.4.10) : à 200 %, la fenêtre tient sur un écran de 1920×1080 ; sur un écran plus petit, les
  panneaux se masquent ou se détachent (menu Affichage), sans réagencement automatique.
- **Contenu des cartes du pipeline** : le lecteur d'écran lit le nom de la brique, son niveau de prise en
  charge et la gravité de son diagnostic ; le sous-titre affiché (rôle, fournisseur) est dans l'infobulle et
  dans le panneau Propriétés, pas dans le nom.
- **Délai des messages** : un message de la barre d'état reste affiché quatre à cinq secondes ; il est annoncé
  au lecteur d'écran, et les diagnostics, eux, restent jusqu'à leur correction.

## Refaire les contrôles

```bash
QT_QPA_PLATFORM=offscreen python tools/audit_accessibilite.py      # audit hors écran, les deux thèmes
python tools/arbre_accessibilite.py --sortie arbre.txt             # Linux : Xvfb, at-spi2-core, python3-pyatspi
python tools/arbre_uia.py --sortie arbre.txt                       # Windows : pip install uiautomation
```

## Signaler un problème

Une difficulté d'accès, avec n'importe quelle technologie d'assistance : ouvrir un ticket sur
[github.com/denvi44/devops-builder/issues](https://github.com/denvi44/devops-builder/issues), en indiquant le
système, le lecteur d'écran ou l'outil utilisé et l'écran concerné.
