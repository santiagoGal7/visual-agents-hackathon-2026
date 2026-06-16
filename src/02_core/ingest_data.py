#!/usr/bin/env python3
"""Cargador industrial de datos para la Hackathon FiftyOne.

Este script ofrece funciones de ingesta de datasets robustas y seguras para
un entorno de producción de hackathon. Lee variables desde `.env`, valida
directorios y crea datasets persistentes en MongoDB con el nombre oficial
`DATASET_NAME`.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

from dotenv import load_dotenv

import fiftyone as fo
from fiftyone import types as fotypes


ROOT_DIR = Path(__file__).resolve().parents[2]
"""Raíz del repositorio, asume: repo/src/02_core/ingest_data.py."""

ENV_PATH = ROOT_DIR / ".env"
"""Ruta por defecto del archivo de variables de entorno."""

DEFAULT_DATASET_NAME = "hackathon-dataset"
"""Nombre oficial del dataset persistente usado por todo el stack."""

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
"""Extensiones de imagen aceptadas para la ingesta de directorio."""

SUPPORTED_STRUCTURED_FORMATS = {
    "coco": fotypes.COCODetectionDataset,
    "yolo": fotypes.YOLOv5Dataset,
}
"""Mapeo de formatos estructurados a tipos de Dataset compatibles con FiftyOne."""


def load_environment(env_path: Optional[Path] = None) -> None:
    """Carga el archivo .env si existe y deja las variables disponibles en os.environ."""
    env_file = env_path or ENV_PATH
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)


def get_dataset_name(explicit_name: Optional[str] = None) -> str:
    """Devuelve el nombre del dataset final a usar, con fallback al valor oficial."""
    if explicit_name and explicit_name.strip():
        return explicit_name.strip()

    return os.getenv("DATASET_NAME", DEFAULT_DATASET_NAME).strip()


def assert_directory_exists(directory: Path) -> None:
    """Valida que el directorio existe y es accesible."""
    if not directory.exists():
        raise FileNotFoundError(f"Directorio no encontrado: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"La ruta no es un directorio válido: {directory}")


def list_image_files(directory: Path) -> list[Path]:
    """Recorre el directorio y devuelve la lista de archivos de imagen soportados."""
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    )


def ensure_clean_dataset(dataset_name: str) -> fo.Dataset:
    """Elimina el dataset existente si ya existe y crea uno nuevo persistent.

    Esto asegura un punto de partida limpio para la ingesta industrial.
    """
    if fo.dataset_exists(dataset_name):
        fo.delete_dataset(dataset_name)

    dataset = fo.Dataset(name=dataset_name)
    dataset.persistent = True
    return dataset


def ingest_images_from_dir(
    image_dir: Path,
    dataset_name: str,
    overwrite: bool = True,
) -> fo.Dataset:
    """Ingesta todas las imágenes de un directorio usando dataset.add_samples()."""
    assert_directory_exists(image_dir)

    image_files = list_image_files(image_dir)
    if not image_files:
        raise ValueError(
            f"No se encontraron imágenes válidas en {image_dir}. "
            f"Extensiones soportadas: {', '.join(sorted(SUPPORTED_IMAGE_EXTENSIONS))}"
        )

    if overwrite:
        dataset = ensure_clean_dataset(dataset_name)
    else:
        dataset = fo.load_dataset(dataset_name) if fo.dataset_exists(dataset_name) else fo.Dataset(name=dataset_name)
        dataset.persistent = True

    print(f"[INFO] Dataset oficial: {dataset_name}")
    print(f"[INFO] Directorio de imágenes: {image_dir}")
    print(f"[INFO] Archivos detectados: {len(image_files)}")

    samples = [fo.Sample(filepath=str(path)) for path in image_files]
    dataset.add_samples(samples)
    dataset.reload()

    print_report(dataset, action="ingest_images")
    return dataset


def import_structured_dataset(
    dataset_dir: Path,
    dataset_format: str,
    dataset_name: str,
    overwrite: bool = True,
) -> fo.Dataset:
    """Importa un dataset estructurado (COCO/YOLO) usando fo.Dataset.from_dir()."""
    assert_directory_exists(dataset_dir)

    dataset_format_key = dataset_format.strip().lower()
    if dataset_format_key not in SUPPORTED_STRUCTURED_FORMATS:
        raise ValueError(
            "Formato no soportado: {dataset_format}. "
            f"Formatos soportados: {', '.join(SUPPORTED_STRUCTURED_FORMATS)}"
        )

    if overwrite and fo.dataset_exists(dataset_name):
        fo.delete_dataset(dataset_name)

    dataset_type = SUPPORTED_STRUCTURED_FORMATS[dataset_format_key]
    print(f"[INFO] Dataset oficial: {dataset_name}")
    print(f"[INFO] Directorio estructurado: {dataset_dir}")
    print(f"[INFO] Formato: {dataset_format_key}")

    dataset = fo.Dataset.from_dir(
        dataset_dir=str(dataset_dir),
        dataset_type=dataset_type,
        name=dataset_name,
    )

    dataset.persistent = True
    dataset.reload()

    print_report(dataset, action="import_structured_dataset")
    return dataset


def print_report(dataset: fo.Dataset, action: str) -> None:
    """Imprime un reporte elegante de la operación de ingesta."""
    sample_count = len(dataset)
    print("""
╔════════════════════════════════════════════════════════════════╗
║                         INGEST DATA REPORT                     ║
╠════════════════════════════════════════════════════════════════╣""")
    print(f"║ Acción          : {action}".ljust(64) + "║")
    print(f"║ Dataset         : {dataset.name}".ljust(64) + "║")
    print(f"║ Persistente     : {dataset.persistent}".ljust(64) + "║")
    print(f"║ Samples cargados: {sample_count}".ljust(64) + "║")
    print("╠════════════════════════════════════════════════════════════════╣")

    fields = dataset.get_field_schema().keys()
    print(f"║ Campos         : {', '.join(fields) or 'Ninguno'}".ljust(64) + "║")
    print("╚════════════════════════════════════════════════════════════════╝")


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Carga datasets en FiftyOne para la hackathon con configuración .env.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--mode",
        choices=["images", "coco", "yolo"],
        required=True,
        help="Modo de ingesta: images desde directorio crudo, coco o yolo desde estructura anotada.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Directorio de origen: imágenes crudas o dataset estructurado.",
    )
    parser.add_argument(
        "--dataset-name",
        type=str,
        default=None,
        help="Nombre del dataset a crear. Si no se define, usa DATASET_NAME del .env o 'hackathon-dataset'.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ENV_PATH,
        help="Archivo de variables de entorno a cargar antes de ejecutar.",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="No sobrescribe datasets existentes; agrega al dataset si ya existe.",
    )
    return parser


def main() -> int:
    parser = build_cli()
    args = parser.parse_args()

    load_environment(args.env_file)
    dataset_name = get_dataset_name(args.dataset_name)
    overwrite = not args.no_overwrite

    try:
        if args.mode == "images":
            ingest_images_from_dir(
                image_dir=args.source,
                dataset_name=dataset_name,
                overwrite=overwrite,
            )
        else:
            import_structured_dataset(
                dataset_dir=args.source,
                dataset_format=args.mode,
                dataset_name=dataset_name,
                overwrite=overwrite,
            )

        return 0

    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
