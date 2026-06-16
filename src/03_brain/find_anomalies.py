#!/usr/bin/env python3
"""Cura automáticamente muestras problemáticas con uniqueness y mistakenness."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

import fiftyone as fo
import fiftyone.brain as fob
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"
DEFAULT_DATASET_NAME = "hackathon-dataset"
DEFAULT_VIEW_NAME = "muestras_corruptas"
DEFAULT_TOP_K = 100


def load_environment(env_file: Optional[Path] = None) -> None:
    env_file = env_file or ENV_PATH
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)


def get_dataset_name(explicit_name: Optional[str] = None) -> str:
    if explicit_name and explicit_name.strip():
        return explicit_name.strip()
    return os.getenv("DATASET_NAME", DEFAULT_DATASET_NAME).strip()


def assert_dataset_exists(dataset_name: str) -> fo.Dataset:
    if not fo.dataset_exists(dataset_name):
        raise RuntimeError(
            f"Dataset '{dataset_name}' no existe en MongoDB. "
            "Ejecuta primero la ingesta con src/02_core/ingest_data.py."
        )
    return fo.load_dataset(dataset_name)


def has_predictions(dataset: fo.Dataset) -> bool:
    schema = dataset.get_field_schema()
    return "predictions" in schema


def compute_uniqueness(dataset: fo.Dataset, embeddings_field: str = "clip_embeddings") -> None:
    print(f"[INFO] Calculando uniqueness usando embeddings '{embeddings_field}'...")
    if embeddings_field not in dataset.get_field_schema():
        raise RuntimeError(
            f"El campo de embeddings '{embeddings_field}' no existe en el dataset. "
            "Ejecuta primero src/03_brain/compute_embeddings.py."
        )

    try:
        fob.compute_uniqueness(
            dataset,
            embeddings=embeddings_field,
            uniqueness_field="uniqueness",
        )
    except Exception as exc:
        raise RuntimeError(
            "Fallo en compute_uniqueness(). Revisa la integridad del dataset y los embeddings."
        ) from exc

    print("[OK] Uniqueness calculado y almacenado en 'uniqueness'.")


def compute_mistakenness(dataset: fo.Dataset) -> None:
    print("[INFO] Detectando mistakenness sobre las predicciones existentes...")

    if not has_predictions(dataset):
        raise RuntimeError(
            "El campo 'predictions' no existe en el dataset. "
            "No se puede ejecutar compute_mistakenness()."
        )

    if "ground_truth" not in dataset.get_field_schema():
        raise RuntimeError(
            "El campo 'ground_truth' no existe en el dataset. "
            "compute_mistakenness() requiere compararlo contra las etiquetas reales."
        )

    try:
        fob.compute_mistakenness(
            dataset,
            pred_field="predictions",
            label_field="ground_truth",
            mistakenness_field="mistakenness",
        )
    except Exception as exc:
        raise RuntimeError(
            "Fallo en compute_mistakenness(). Verifica que 'predictions' contenga logits/confianza completa."
        ) from exc

    print("[OK] Mistakenness calculado y almacenado en 'mistakenness'.")


def save_critical_view(
    dataset: fo.Dataset,
    view_name: str = DEFAULT_VIEW_NAME,
    top_k: int = DEFAULT_TOP_K,
) -> fo.DatasetView:
    if "mistakenness" in dataset.get_field_schema():
        view = dataset.sort_by("mistakenness", reverse=True).limit(top_k)
        description = (
            f"Top {top_k} muestras más sospechosas de tener etiquetas corruptas "
            "según mistakenness."
        )
    else:
        view = dataset.sort_by("uniqueness").limit(top_k)
        description = (
            f"Top {top_k} muestras menos únicas (duplicados o redundancia visual). "
            "Revisión recomendada."
        )

    dataset.save_view(view_name, view, description=description)
    print(f"[OK] DatasetView guardada como '{view_name}'.")
    return view_name, view


def print_report(dataset: fo.Dataset, view_name: str, view: fo.DatasetView, top_k: int) -> None:
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                          ANOMALY CURATION REPORT                      ║
╠══════════════════════════════════════════════════════════════════════╣""")
    print(f"║ Dataset          : {dataset.name}".ljust(72) + "║")
    print(f"║ Samples totales  : {len(dataset)}".ljust(72) + "║")
    print(f"║ View guardada    : {view.name}".ljust(72) + "║")
    print(f"║ Muestras en view : {len(view)}".ljust(72) + "║")
    print(f"║ Top k            : {top_k}".ljust(72) + "║")
    print("╚══════════════════════════════════════════════════════════════════════╝")


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ejecuta curación automática de anomalies con uniqueness y mistakenness.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dataset-name",
        type=str,
        default=None,
        help="Nombre del dataset en MongoDB. Si no se especifica, se lee de DATASET_NAME en .env.",
    )
    parser.add_argument(
        "--view-name",
        type=str,
        default=DEFAULT_VIEW_NAME,
        help="Nombre de la DatasetView guardada para revisión.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Número de muestras a incluir en la DatasetView.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ENV_PATH,
        help="Ruta al archivo .env con variables de entorno.",
    )
    return parser


def main() -> int:
    parser = build_cli()
    args = parser.parse_args()

    try:
        load_environment(args.env_file)
        dataset_name = get_dataset_name(args.dataset_name)
        dataset = assert_dataset_exists(dataset_name)

        compute_uniqueness(dataset)

        if has_predictions(dataset):
            compute_mistakenness(dataset)
        else:
            print("[WARN] No se detectó el campo 'predictions'. Se omitirá el cómputo de mistakenness.")

        view_name, view = save_critical_view(dataset, view_name=args.view_name, top_k=args.top_k)
        print_report(dataset, view_name, view, args.top_k)
        return 0

    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
