#!/usr/bin/env python3
"""Cálculo de embeddings CLIP y reducción UMAP para el Hackathon FiftyOne."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

import fiftyone as fo
import fiftyone.brain as fob
import fiftyone.zoo as foz

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"
DEFAULT_DATASET_NAME = "hackathon-dataset"
DEFAULT_MODEL_NAME = "clip-vit-base-patch32"


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


def load_clip_model(model_name: str) -> object:
    try:
        print(f"[INFO] Cargando modelo CLIP desde el Zoo de FiftyOne: {model_name}")
        model = foz.load_zoo_model(model_name)
        print("[INFO] Modelo CLIP cargado correctamente.")
        return model
    except Exception as exc:
        raise RuntimeError(
            "No se pudo cargar el modelo CLIP desde FiftyOne Zoo. "
            "Verifica la conectividad de red y el cache de FiftyOne."
        ) from exc


def compute_clip_embeddings(
    dataset: fo.Dataset,
    model_name: str = DEFAULT_MODEL_NAME,
    embeddings_field: str = "clip_embeddings",
) -> fo.Dataset:
    print(f"[INFO] Calculando embeddings CLIP para dataset: {dataset.name}")
    if embeddings_field in dataset.get_field_schema():
        print(f"[WARN] El campo '{embeddings_field}' ya existe y será sobrescrito.")

    model = load_clip_model(model_name)
    start_time = time.perf_counter()

    try:
        dataset.compute_embeddings(
            model=model,
            embeddings_field=embeddings_field,
        )
    except Exception as exc:
        raise RuntimeError(
            "Fallo en compute_embeddings(). Revisa que el dataset tenga muestras "
            "y que el modelo CLIP se haya cargado correctamente."
        ) from exc

    elapsed = time.perf_counter() - start_time
    print("[OK] Embeddings CLIP almacenados en '" + embeddings_field + "'.")
    print(f"[INFO] Tiempo total de cálculo: {elapsed:.2f} segundos.")
    return dataset


def compute_umap_projection(
    dataset: fo.Dataset,
    embeddings_field: str = "clip_embeddings",
    brain_key: str = "clip_vis",
    num_dims: int = 2,
) -> None:
    print(f"[INFO] Calculando UMAP 2D desde embeddings '{embeddings_field}'...")
    if embeddings_field not in dataset.get_field_schema():
        raise RuntimeError(
            f"El campo de embeddings '{embeddings_field}' no existe en el dataset. "
            "Ejecuta primero compute_clip_embeddings()."
        )

    start_time = time.perf_counter()
    try:
        fob.compute_visualization(
            dataset,
            embeddings=embeddings_field,
            method="umap",
            brain_key=brain_key,
            num_dims=num_dims,
        )
    except Exception as exc:
        raise RuntimeError(
            "Fallo en compute_visualization() para UMAP. "
            "Revisa que el campo de embeddings sea válido y que UMAP esté disponible."
        ) from exc

    elapsed = time.perf_counter() - start_time
    print("[OK] Reducción UMAP guardada con brain_key='" + brain_key + "'.")
    print(f"[INFO] Tiempo total de UMAP: {elapsed:.2f} segundos.")


def print_report(dataset: fo.Dataset, embeddings_field: str, brain_key: str) -> None:
    sample_count = len(dataset)
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                         BRAIN COMPUTE REPORT                      ║
╠══════════════════════════════════════════════════════════════════╣""")
    print(f"║ Dataset          : {dataset.name}".ljust(66) + "║")
    print(f"║ Samples          : {sample_count}".ljust(66) + "║")
    print(f"║ Embeddings field : {embeddings_field}".ljust(66) + "║")
    print(f"║ UMAP brain key   : {brain_key}".ljust(66) + "║")
    print("╚══════════════════════════════════════════════════════════════════╝")


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Genera embeddings CLIP y visualización UMAP para hackathon-dataset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dataset-name",
        type=str,
        default=None,
        help="Nombre del dataset en MongoDB. Si no se especifica, se lee de DATASET_NAME en .env.",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default=DEFAULT_MODEL_NAME,
        help="Nombre del modelo CLIP a cargar desde FiftyOne Zoo.",
    )
    parser.add_argument(
        "--embeddings-field",
        type=str,
        default="clip_embeddings",
        help="Campo donde se almacenarán los embeddings generados.",
    )
    parser.add_argument(
        "--brain-key",
        type=str,
        default="clip_vis",
        help="Clave de brain donde se guardará la visualización UMAP.",
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

        dataset = compute_clip_embeddings(
            dataset,
            model_name=args.model_name,
            embeddings_field=args.embeddings_field,
        )
        compute_umap_projection(
            dataset,
            embeddings_field=args.embeddings_field,
            brain_key=args.brain_key,
        )
        print_report(dataset, args.embeddings_field, args.brain_key)
        return 0

    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
