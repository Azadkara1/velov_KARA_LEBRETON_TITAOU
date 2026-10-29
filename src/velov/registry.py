"""Registre des modèles et règle de promotion challenger -> champion (TP4, étape 3).

Deux alias sur le modèle `velov-availability` :
- `challenger` : le dernier candidat entraîné (posé par velov.tracking) ;
- `champion`   : le modèle autorisé à être servi.

Un candidat n'est jamais promu "parce qu'il est récent" : il doit passer une règle écrite,
automatisable, testée. La décision est une fonction pure (`decide`) : mêmes métriques en entrée,
même verdict, sans serveur MLflow, donc testable en CI.

Règle : promotion si les TROIS conditions sont vraies.
  1. Le challenger bat la baseline de persistance (EX-05).
  2. Il bat le champion actuel d'au moins `margin` vélos de MAE. Sans cette marge, on
     promouvrait du bruit : deux entraînements identiques à une seed près diffèrent déjà
     (voir README, écart entre les seeds 42 et 7).
  3. Il ne se dégrade pas aux heures de pointe (tolérance `peak_tolerance`) : une
     meilleure moyenne globale peut cacher une pire prédiction quand le service compte.
S'il n'y a pas encore de champion, seule la condition 1 s'applique (premier modèle).

Livraison (Should) : `deliver` télécharge le paquet du champion dans models/ (ce que l'image Docker
embarque), après avoir vérifié son empreinte SHA-256. `rollback` repose l'alias champion sur une
version antérieure : revenir en arrière, c'est repointer l'alias puis relivrer, pas ré-entraîner.

Usage :
    python -m velov.registry promote            # applique la règle, pose l'alias champion si OK
    python -m velov.registry promote --dry-run  # affiche seulement le verdict
    python -m velov.registry deliver            # models/ <- paquet du champion
    python -m velov.registry rollback --to 1    # le champion redevient la version 1
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from velov.tracking import CHALLENGER_ALIAS, REGISTERED_MODEL, require_tracking_uri
from velov.train import METADATA_FILENAME, sha256_of

CHAMPION_ALIAS = "champion"
# Seuils fixés AU-DESSUS du bruit lié à la seed, mesuré sur 8 seeds (voir README) :
# MAE globale entre 1,339 et 1,360 (étendue 0,021) -> marge 0,03 ;
# MAE de pointe entre 1,395 et 1,467 (étendue 0,072) -> tolérance 0,08.
DEFAULT_MARGIN = 0.03
DEFAULT_PEAK_TOLERANCE = 0.08


@dataclass
class Decision:
    promote: bool
    reasons: list[str] = field(default_factory=list)
    noop: bool = False  # rien à décider (déjà champion)


def decide(
    challenger: dict[str, float],
    champion: dict[str, float] | None,
    margin: float = DEFAULT_MARGIN,
    peak_tolerance: float = DEFAULT_PEAK_TOLERANCE,
) -> Decision:
    """Applique la règle en trois conditions. Retourne le verdict et la raison de chaque échec."""
    reasons: list[str] = []

    if challenger["mae_model"] >= challenger["mae_baseline_persistence"]:
        reasons.append(
            f"1. ne bat pas la baseline : MAE {challenger['mae_model']:.3f} >= "
            f"persistance {challenger['mae_baseline_persistence']:.3f}"
        )

    if champion is not None:
        gain = champion["mae_model"] - challenger["mae_model"]
        if gain < margin:
            reasons.append(f"2. gain {gain:+.3f} vélo(s) < marge exigée {margin:.3f} (bruit possible)")

        worse_peak = challenger["mae_model_peak_hours"] - champion["mae_model_peak_hours"]
        if worse_peak > peak_tolerance:
            reasons.append(f"3. dégradation aux heures de pointe : +{worse_peak:.3f} > tolérance {peak_tolerance:.3f}")

    return Decision(promote=not reasons, reasons=reasons)


def _metrics_of(client, version) -> dict[str, float]:
    return client.get_run(version.run_id).data.metrics


def promote(margin: float, peak_tolerance: float, dry_run: bool = False) -> Decision:
    from mlflow import MlflowClient
    from mlflow.exceptions import MlflowException

    require_tracking_uri()
    client = MlflowClient()
    try:
        challenger = client.get_model_version_by_alias(REGISTERED_MODEL, CHALLENGER_ALIAS)
    except MlflowException as e:
        raise SystemExit(f"Aucun challenger à évaluer : lancer `python -m velov.train --mlflow` ({e})") from e
    try:
        champion = client.get_model_version_by_alias(REGISTERED_MODEL, CHAMPION_ALIAS)
    except MlflowException:
        champion = None

    if champion is not None and champion.version == challenger.version:
        print(f"La version {challenger.version} est déjà champion : rien à faire.")
        return Decision(promote=False, noop=True)

    decision = decide(
        _metrics_of(client, challenger),
        _metrics_of(client, champion) if champion else None,
        margin,
        peak_tolerance,
    )
    old = f"champion actuel v{champion.version}" if champion else "pas de champion"
    if decision.promote:
        print(f"PROMU : challenger v{challenger.version} -> champion ({old})")
        if not dry_run:
            client.set_registered_model_alias(REGISTERED_MODEL, CHAMPION_ALIAS, challenger.version)
    else:
        print(f"REFUSÉ : challenger v{challenger.version} ({old})")
        for r in decision.reasons:
            print(f"  - {r}")
    return decision


def deliver(out_dir: Path, version: str | None = None) -> dict:
    """Copie le paquet (model.joblib + metadata.json) du champion (ou d'une version) dans `out_dir`.

    Refuse de livrer si l'empreinte du fichier ne correspond pas à celle écrite dans metadata.json :
    un artefact altéré ou tronqué en route ne doit jamais atteindre l'image.
    """
    import mlflow
    from mlflow import MlflowClient

    require_tracking_uri()
    client = MlflowClient()
    mv = (
        client.get_model_version(REGISTERED_MODEL, version)
        if version
        else client.get_model_version_by_alias(REGISTERED_MODEL, CHAMPION_ALIAS)
    )
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(mlflow.artifacts.download_artifacts(run_id=mv.run_id, artifact_path="package", dst_path=tmp))
        metadata = json.loads((local / METADATA_FILENAME).read_text(encoding="utf-8"))
        model_file = local / metadata["artifact"]["file"]
        if sha256_of(model_file) != metadata["artifact"]["sha256"]:
            raise SystemExit(f"Livraison refusée : empreinte invalide pour la version {mv.version}")
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(model_file, out_dir / model_file.name)
        shutil.copy2(local / METADATA_FILENAME, out_dir / METADATA_FILENAME)
    sha = metadata["artifact"]["sha256"][:12]
    print(f"Livré : version {mv.version} (run {mv.run_id[:8]}, sha256 {sha}...) -> {out_dir}")
    return metadata


def rollback(to_version: str) -> None:
    """Le champion redevient `to_version`. N'agit que sur l'alias : aucun modèle n'est supprimé."""
    from mlflow import MlflowClient

    require_tracking_uri()
    client = MlflowClient()
    client.get_model_version(REGISTERED_MODEL, to_version)  # lève une erreur si elle n'existe pas
    client.set_registered_model_alias(REGISTERED_MODEL, CHAMPION_ALIAS, to_version)
    print(f"Rollback : le champion est maintenant la version {to_version}. Relivrer puis reconstruire l'image.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Registre : promotion du challenger.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("promote", help="applique la règle de promotion")
    p.add_argument("--margin", type=float, default=DEFAULT_MARGIN)
    p.add_argument("--peak-tolerance", type=float, default=DEFAULT_PEAK_TOLERANCE)
    p.add_argument("--dry-run", action="store_true")
    d = sub.add_parser("deliver", help="copie le paquet du champion dans models/")
    d.add_argument("--out", type=Path, default=Path("models"))
    d.add_argument("--version", help="une version précise plutôt que le champion")
    r = sub.add_parser("rollback", help="repose l'alias champion sur une version antérieure")
    r.add_argument("--to", required=True)
    args = parser.parse_args()

    if args.cmd == "deliver":
        deliver(args.out, args.version)
        return
    if args.cmd == "rollback":
        rollback(args.to)
        return

    decision = promote(args.margin, args.peak_tolerance, args.dry_run)
    sys.exit(0 if decision.promote or decision.noop else 1)  # code 1 si refusé : utilisable dans un pipeline


if __name__ == "__main__":
    main()
