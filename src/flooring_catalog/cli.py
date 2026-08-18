"""CLI for catalog profiling."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from flooring_catalog.profiling import CatalogProfile, profile_catalog


def _summary(profile: CatalogProfile) -> dict[str, object]:
    return {
        "source_file": profile.source_file,
        "total_products": profile.total_products,
        "field_count": len(profile.discovered_fields),
        "discovered_fields": profile.discovered_fields,
        "z_prod_type_distribution": profile.z_prod_type_distribution,
        "status_distribution": profile.status_distribution,
        "active_products": profile.active_products,
        "rejected_status_not_active": profile.rejected_status_not_active,
        "products_with_valid_swatch": profile.products_with_valid_swatch,
        "rejected_swatch_empty_or_missing": profile.rejected_swatch_empty_or_missing,
        "eligible_products": profile.eligible_products,
        "sku_statistics": profile.sku_statistics,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile a flooring product JSON catalog")
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sku-key")
    args = parser.parse_args(argv)

    profile = profile_catalog(args.catalog, sku_key=args.sku_key)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(profile.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(_summary(profile), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

