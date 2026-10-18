# Le schéma réseau

**Vues › Réseau** (Ctrl+Maj+R) dessine le réseau d'un environnement : qui est joint depuis Internet, par où, ce
qui parle à quoi, et où sont les erreurs. Le schéma se tire du projet : il suit chaque modification.

![Le réseau de la production en plan 2D : Internet, Traefik, l'application, Prometheus et Grafana, PostgreSQL ;
Traefik, Prometheus et Grafana portent une pastille d'avertissement](captures/reseau-2d.png)

## Deux affichages

- **Plan 2D** : un plan par bande, de haut en bas : Internet, entrée (Traefik, Ingress), application et services,
  données, hébergement (fournisseur cloud, cluster, machine). Les flèches portent le port.
- **Isométrique 3D** : les mêmes plans, empilés, pour lire d'un coup d'œil ce qui traverse quoi. Le choix est
  retenu d'une session à l'autre.

![Le même réseau en isométrique : un plan par couche, les composants posés dessus](captures/reseau-3d.png)

L'environnement se choisit en haut (la production par défaut) ; **Enregistrer l'image…** écrit le schéma en PNG,
pour un dossier d'architecture ou une revue.

## Lire les erreurs sur le schéma

Une pastille sur un composant dit qu'un constat le concerne : **disque barré** pour une erreur bloquante,
**triangle** pour un avertissement, **disque** pour une information. Le contour du composant prend la couleur de la
gravité, mais la forme et le texte suffisent : la liste de droite écrit chaque constat.

Deux sortes de constats se posent sur le schéma :

- ceux des **règles** du projet (R34 : valeur d'exemple à renseigner ; R39 : deux services sur le même port ;
  R52 : machine trop petite…), rattachés au composant de la brique concernée. Une règle propre à un environnement
  n'apparaît que sur cet environnement ;
- ceux du **réseau**, qui n'ont de sens que sur le schéma : un service publié sur l'hôte sans passer par l'entrée
  (Grafana et Prometheus, par exemple), une application exposée en HTTP simple, un cluster sans point d'entrée.

Les diagnostics qui ne touchent aucun composant (CI, sécurité, plateforme) restent dans le panneau Diagnostics ;
le bas de la fenêtre en donne le nombre.

## Agir depuis le schéma

- Cliquer un composant (ou ← → ↑ ↓ au clavier) le sélectionne dans le dessin et dans la liste, et annonce ses
  constats aux lecteurs d'écran.
- Choisir un constat dans la liste affiche son message, sa source (« règle R52 », « réseau ») et, quand la règle en
  propose une, un bouton **Corriger** : la correction s'applique au projet (Ctrl+Z l'annule) et le schéma se met à
  jour.
- **Voir la brique** (ou Entrée, ou un double-clic) ferme le schéma et sélectionne la brique dans le pipeline.

La liste « Composants et constats » donne la même information que le dessin, en texte : c'est elle que les
lecteurs d'écran et le clavier parcourent.
