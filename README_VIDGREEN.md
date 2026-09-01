# VIDGREEN

**VIDGREEN** est un lecteur vidéo ASCII avancé pour terminal. Il convertit n'importe quelle vidéo en une représentation textuelle colorée (vert Matrix par défaut), directement dans votre console.

> 🎬 Transformez vos vidéos en expériences retro-futuristes ASCII en temps réel.

---

## Fonctionnalités

- Lecture vidéo en ASCII avec palette personnalisable
- Couleur verte Matrix par défaut, avec support multi-couleurs
- Synchronisation audio/vidéo
- Lecture en boucle
- Redimensionnement automatique selon la taille du terminal
- Ajustement du contraste, luminosité, seuil
- Plusieurs algorithmes de conversion ASCII
- Mode plein écran terminal
- Barre de progression et contrôles interactifs
- Export des frames ASCII
- Support des formats MP4, AVI, MKV, MOV, WEBM, etc.

---

## Installation

```bash
pip install -r requirements_vidgreen.txt
```

> Sous Linux, installez aussi ffmpeg :
```bash
sudo apt install ffmpeg
```

---

## Utilisation

```bash
python vidgreen.py /chemin/vers/video.mp4
```

### Options

| Option | Description |
|--------|-------------|
| `--width` | Largeur ASCII en caractères |
| `--height` | Hauteur ASCII en caractères |
| `--fps` | Forcer le FPS |
| `--no-audio` | Désactiver l'audio |
| `--loop` | Lire en boucle |
| `--color` | Choisir la couleur (green, red, blue, yellow, cyan, white, rainbow) |
| `--invert` | Inverser les niveaux de gris |
| `--contrast` | Facteur de contraste |
| `--brightness` | Facteur de luminosité |
| `--charset` | Ensemble de caractères ASCII (standard, blocks, minimal, detailed) |
| `--export-frames` | Exporter les frames ASCII dans un dossier |
| `--fullscreen` | Mode plein écran terminal |

---

## Exemples

```bash
# Style Matrix vert
python vidgreen.py video.mp4 --color green

# Arc-en-ciel
python vidgreen.py video.mp4 --color rainbow --charset blocks

# Export des frames
python vidgreen.py video.mp4 --export-frames ./frames_ascii
```

---

## Architecture

VIDGREEN est structuré en classes modulaires :

- `VidgreenConfig` : configuration CLI et validation
- `TerminalCanvas` : gestion de l'affichage terminal
- `AsciiConverter` : conversion image → ASCII
- `AudioPlayer` : lecture audio synchronisée
- `VideoReader` : lecture vidéo avec OpenCV
- `PlaybackController` : contrôles lecture/pause/seek
- `VidgreenApp` : orchestrateur principal

---

## Licence

MIT - Projet éducatif.
