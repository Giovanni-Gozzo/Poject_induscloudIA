"""Crée une nouvelle clé d'API (ADR-0007).

Lancement, depuis la racine du projet :
    python -m scripts.new_api_key --name boutique-web --role user --days 90

La clé est affichée UNE seule fois : la transmettre au client par un canal sûr.
Seule son empreinte (sha256) est ajoutée à la variable API_KEYS dans Coolify.
"""
import argparse
import json
from datetime import date, timedelta

from app.security import Role, generate_key, hash_key

DEFAULT_VALIDITY_DAYS = 90


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère une clé d'API et son entrée API_KEYS")
    parser.add_argument("--name", required=True, help="propriétaire de la clé, ex. boutique-web")
    parser.add_argument("--role", choices=[r.value for r in Role], default=Role.user.value)
    parser.add_argument("--days", type=int, default=DEFAULT_VALIDITY_DAYS,
                        help="durée de validité en jours")
    args = parser.parse_args()
    if args.days <= 0:
        parser.error("--days doit être strictement positif")

    raw_key = generate_key()
    entry = {
        "name": args.name,
        "role": args.role,
        "sha256": hash_key(raw_key),
        "expires_at": (date.today() + timedelta(days=args.days)).isoformat(),
    }
    print(f"Clé à transmettre au client (affichée une seule fois) :\n  {raw_key}\n")
    print("Entrée à ajouter à la liste JSON de la variable API_KEYS dans Coolify :")
    print(f"  {json.dumps(entry)}")


if __name__ == "__main__":
    main()
