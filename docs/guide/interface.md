# Prise en main de l'interface

![Fenêtre principale : le catalogue à gauche, le pipeline au centre en colonnes par étape, les propriétés de la
brique sélectionnée à droite et les diagnostics en bas](../captures/01-pipeline.png)

## Les zones de l'écran

**Barre du projet** (en haut du centre) : le nom du projet ; la carte de l'application (dossier analysé,
langage, port — Ctrl+Maj+A) ; des puces qui résument la cible, les environnements et l'authentification de la
CI ; le bouton **Vues** (ports et données par environnement) ; les paramètres du projet (F2) ; **Générer**.

**Pipeline** (au centre) : une colonne par étape, de la source à l'observabilité — Source, Build, Tests &
qualité, Sécurité, Artefacts, Infrastructure, Données, Déploiement, Plateforme, Observabilité. Chaque brique
affiche son nom, son rôle et, si un diagnostic la concerne, l'icône de sa gravité.

**Catalogue** (à gauche) : les outils vérifiés, rangés par étape, avec une recherche (Ctrl+F) et des filtres :
étape, maturité CNCF, open source uniquement, « Adapté au projet » (masque ce que le projet écarterait :
cible, forge, licence, SecNumCloud, cloud, rôle déjà tenu) et « Inclure tout le Landscape » (les ~1 000 entrées
du CNCF Landscape, sans fiche de compatibilité).

**Propriétés** (à droite) : la fiche de la brique sélectionnée (licence, maturité, prise en charge, ce qu'elle
fournit) et le formulaire de ses paramètres. Au-dessus du formulaire, le choix de l'environnement permet de
**surcharger** une valeur pour un seul environnement ; un champ laissé vide hérite de la valeur commune.

**Diagnostics** (en bas) : les règles de compatibilité qui s'appliquent au projet, avec leur gravité. Le
diagnostic sélectionné montre ses corrections à droite ; Entrée applique la première. Toute correction
s'annule par Ctrl+Z.

**Barre d'état** (tout en bas) : le dernier message (brique ajoutée, déplacée, refusée…) et le compte des
briques et des erreurs bloquantes. Les lecteurs d'écran annoncent ces messages.

## Construire au clavier

Tout se fait sans souris ; le glisser-déposer a toujours son équivalent clavier.

| Action | Clavier |
| --- | --- |
| Rechercher dans le catalogue | Ctrl+F, puis Tab jusqu'à l'arbre |
| Ajouter l'outil sélectionné à son étape | Entrée (ou double-clic) |
| Aller au pipeline, aux diagnostics | Ctrl+2, Ctrl+3 |
| Changer une brique d'étape | Alt+← ou Alt+→ (saute à l'étape autorisée suivante) |
| Déplacer une brique dans son étape | Alt+↑ ou Alt+↓ |
| Retirer une brique | Suppr |
| Appliquer la première correction d'un diagnostic | Entrée sur le diagnostic |
| Annuler, rétablir | Ctrl+Z, Ctrl+Y |
| Nouveau projet (assistant), projet vide | Ctrl+N, Ctrl+Maj+N |
| Ouvrir, enregistrer | Ctrl+O, Ctrl+S |
| Paramètres du projet | F2 |
| Application, ports, données | Ctrl+Maj+A, Ctrl+Maj+P, Ctrl+Maj+D |
| Générer, valider | Ctrl+G, Ctrl+Maj+V |
| Thème sombre | Ctrl+T |
| Agrandir, réduire le texte | Ctrl++, Ctrl+- |

Une brique ne peut être posée que dans une étape qui l'accepte : un dépôt refusé, au clavier comme à la souris,
dit pourquoi dans la barre d'état.

## Affichage

- **Thème sombre** : Affichage › Thème sombre (Ctrl+T). Les deux thèmes respectent les contrastes minimaux
  (4,5:1 pour le texte, 3:1 pour les icônes et l'indicateur de focus).
- **Taille du texte** : Affichage › Taille du texte, de 100 à 200 %. Le choix est retenu d'une session à
  l'autre ; à 150 % et plus, le nom du projet passe sur sa propre ligne.
- **Focus** : le contrôle actif est entouré d'un anneau de deux pixels dans la couleur principale du thème.
- **Panneaux** : Affichage permet de masquer ou de rétablir le catalogue, les propriétés et les diagnostics ;
  chaque panneau peut aussi être détaché.

## Lecteurs d'écran

L'interface expose son arbre d'accessibilité aux lecteurs d'écran : NVDA et le Narrateur (Windows) le lisent
par UI Automation, Orca (Linux) par AT-SPI, VoiceOver (macOS) par l'API d'accessibilité d'Apple. Les deux
premiers arbres sont vérifiés à chaque modification du code ; VoiceOver ne l'est pas encore. Chaque
contrôle a un nom, les briques sont annoncées avec leur niveau de prise en charge et la gravité de leur
diagnostic (« Trivy, info »), les messages de la barre d'état sont lus sans déplacer le focus. Le détail des
contrôles et leurs limites : [Accessibilité de l'application](../accessibilite.md).

## Ouvrir un projet existant

Fichier › Ouvrir (Ctrl+O), ou depuis un terminal : `devops-builder mon-projet.devops.yaml`. Un fichier écrit par
une version plus ancienne s'ouvre sans perte ; un fichier modifié à la main qui contient une erreur est refusé
avec un message qui dit où et pourquoi (« YAML invalide ligne 12, colonne 3 : tabulation interdite en YAML :
indenter avec des espaces »). Quatre exemples sont livrés dans Fichier › Ouvrir un exemple.
