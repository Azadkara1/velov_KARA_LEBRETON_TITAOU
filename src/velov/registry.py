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

Usage :
    python -m velov.registry promote            # applique la règle, pose l'alias champion si OK
    python -m velov.registry promote --dry-run  # affiche seulement le verdict
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from velov.tracking import CHALLENGER_ALIAS, REGISTERED_MODEL, require_tracking_uri

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Registre : promotion du challenger.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("promote", help="applique la règle de promotion")
    p.add_argument("--margin", type=float, default=DEFAULT_MARGIN)
    p.add_argument("--peak-tolerance", type=float, default=DEFAULT_PEAK_TOLERANCE)
    p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    decision = promote(args.margin, args.peak_tolerance, args.dry_run)
    sys.exit(0 if decision.promote or decision.noop else 1)  # code 1 si refusé : utilisable dans un pipeline


if __name__ == "__main__":
    main()
