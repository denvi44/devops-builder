# Sécurité

## Versions suivies

Jusqu'à la 1.0, seule la dernière version mineure reçoit des corrections de sécurité.

## Ce qui compte comme une vulnérabilité

- Une faille de l'application elle-même : lecture d'un fichier projet ou d'un dossier d'application qui
  exécute du code, écriture hors du dossier de sortie, fuite d'un jeton.
- **Un défaut de sécurité dans ce qu'elle génère** : un secret écrit en clair dans un fichier versionné, une
  permission de CI trop large, un port exposé sans raison, une image ou une action non épinglée là où le
  générateur prétend l'épingler, une production déployable sans l'approbation demandée. Les fichiers générés
  sont commités puis exécutés par d'autres : ces défauts sont traités comme des vulnérabilités, pas comme des
  anomalies ordinaires.

Les limites déjà décrites dans le README (section « Limites connues ») et dans `docs/prise-en-charge.md` ne
sont pas des vulnérabilités, mais une limite qui n'y figure pas en est peut-être une.

## Signaler

En privé, par le signalement de vulnérabilité de GitHub :
<https://github.com/denvi44/devops-builder/security/advisories/new>. Jamais dans un ticket public.

Indiquer la version (`devops-builder --version`), le fichier projet réduit qui montre le problème (sans
secret réel) et le fichier généré concerné.

Le mainteneur accuse réception dès que possible, convient avec vous d'un délai de correction, puis publie la
correction et un avis de sécurité qui vous crédite, sauf si vous préférez rester anonyme.
