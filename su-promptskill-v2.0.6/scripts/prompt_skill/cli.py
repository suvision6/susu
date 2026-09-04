"""su-promptskill internal module: atomic delivery and CLI dispatch."""

from __future__ import annotations

from . import formats as _previous

globals().update({
    key: value
    for key, value in vars(_previous).items()
    if not key.startswith("__")
})

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Responsibility module behind scripts/prompt_delivery.py."

def write_json_atomic(path: Path | str, value: Any) -> None:
    """Atomically write stable JSON next to the requested output."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.write("\n")
            handle.flush()
        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def build_failure_delivery(
    message: str,
    source_document: Any = None,
    delivery_slug: str | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    normalized, normalization_issues = normalize_input(source_document)
    profile = resolve_model_profile()
    failure_issue = _issue(
        "GLOBAL_CONTRACT_UNREADABLE",
        "ERROR",
        "source",
        "$",
        message,
        ("prompt_compilation", "delivery"),
    )
    empty_task = {
        "primary": "",
        "input_topology": "",
        "modules": [],
        "source": "unresolved",
    }
    empty_generation = {
        "mode": "",
        "mode_source": "unresolved",
        "available_reference_tags": [],
        "reference_role_map": [],
        "edit_scope": [],
        "edit_deltas": [],
        "extend_context": {},
        "asset_assignments": [],
        "asset_binding": {"state": "unmapped", "source": "none"},
        "unused_assets": [],
        "story_contract": {},
        "task_modules": [],
        "global_reference_section": _global_reference_section(profile),
        "runtime_decisions_hash": None,
        "global_blocked": True,
        "invalid_shot_ids": [],
    }
    plan: dict[str, Any] = {
        "contract_name": PLAN_CONTRACT_NAME,
        "contract_version": PLAN_CONTRACT_VERSION,
        "skill": {"name": SKILL_NAME, "version": SKILL_VERSION},
        "delivery": {
            "slug": (
                _ascii_kebab_slug(delivery_slug)
                if delivery_slug is not None
                else derive_delivery_slug(None, source_document)
            ),
            "files": {},
        },
        "compiler_inputs": _compiler_inputs(normalized, None, profile),
        "source": copy.deepcopy(normalized["source"]),
        "task": copy.deepcopy(empty_task),
        "operations": [
            {
                "operation_id": "OP001",
                "order": 1,
                "depends_on_operation_id": None,
                "task": copy.deepcopy(empty_task),
                "generation": copy.deepcopy(empty_generation),
                "prompt_unit_ids": [],
                "submission_ready": False,
            }
        ],
        "story_contract": {},
        "required_entities": [],
        "dialogue_ledger": [],
        "asset_binding": {"state": "unmapped", "source": "none"},
        "asset_inventory": {"complete": False, "items": []},
        "asset_assignments": [],
        "unused_assets": [],
        "mapping_confidence": "low",
        "request_configuration": {
            "raw": {},
            "normalized": {},
            "prompt_isolation": True,
        },
        "prompt_advisories": [],
        "submission_ready": False,
        "generation": empty_generation,
        "model_profile": profile,
        "prompt_units": [],
        "diagnostics": [],
        "validation": {},
    }
    plan["delivery"]["files"] = delivery_file_map(
        plan["delivery"]["slug"]
    )
    issues = _deduplicate_issues(
        list(normalization_issues) + [failure_issue]
    )
    plan["diagnostics"] = issues
    plan["validation"] = _validation_object(normalized, [], issues)
    plan["content_hash"] = prompt_plan_content_hash(plan)
    return plan, derive_delivery_artifacts(plan)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"Build or validate {PLAN_CONTRACT_NAME}/"
            f"{PLAN_CONTRACT_VERSION} deliveries."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser(
        "build", help="Build the four-file Prompt delivery"
    )
    build_parser.add_argument("--input", required=True, type=Path)
    build_parser.add_argument("--output-dir", required=True, type=Path)
    build_parser.add_argument("--decisions", type=Path)
    profile_group = build_parser.add_mutually_exclusive_group()
    profile_group.add_argument("--profile-id", choices=sorted(BUILTIN_PROFILES))
    profile_group.add_argument("--profile-file", type=Path)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate the four-file delivery against its immutable source",
    )
    validate_parser.add_argument("--input", required=True, type=Path)
    validate_parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    source_document: Any = None
    delivery_slug = derive_delivery_slug(args.input.name)
    try:
        source_document = load_json(args.input)
        delivery_slug = derive_delivery_slug(
            args.input.name, source_document
        )
        if args.command == "build":
            decisions = (
                load_json(args.decisions) if args.decisions is not None else None
            )
            profile_document = (
                load_json(args.profile_file)
                if args.profile_file is not None
                else None
            )
            profile = resolve_model_profile(
                profile_id=args.profile_id,
                profile_document=profile_document,
            )
            plan, artifacts = build_delivery_package(
                source_document,
                decisions=decisions,
                model_profile=profile,
                delivery_slug=delivery_slug,
            )
            write_delivery_package(args.output_dir, artifacts)
            print(
                json.dumps(
                    {
                        "status": plan["validation"]["status"],
                        "output_dir": str(args.output_dir),
                        "files": list(artifacts),
                        "summary": plan["validation"]["summary"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return (
                0
                if plan["validation"]["status"] in {"PASS", "WARN"}
                else 2
            )

        report = validate_delivery_package(
            source_document,
            args.output_dir,
            delivery_slug=delivery_slug,
        )
        print(
            json.dumps(
                report,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
        return 0 if report["status"] in {"PASS", "WARN"} else 2
    except (GroupingReviewError, AssetBindingError) as exc:
        print(
            json.dumps(
                {"status": "FAIL", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except (DeliveryError, InvalidOperation) as exc:
        if args.command == "build":
            try:
                plan, artifacts = build_failure_delivery(
                    str(exc),
                    source_document=source_document,
                    delivery_slug=delivery_slug,
                )
                write_delivery_package(args.output_dir, artifacts)
                print(
                    json.dumps(
                        {
                            "status": "FAIL",
                            "error": str(exc),
                            "output_dir": str(args.output_dir),
                            "files": list(artifacts),
                            "summary": plan["validation"]["summary"],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                return 2
            except (DeliveryError, OSError, InvalidOperation) as write_exc:
                print(
                    json.dumps(
                        {
                            "status": "FAIL",
                            "error": str(exc),
                            "delivery_error": str(write_exc),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                )
                return 2
        print(
            json.dumps(
                {"status": "FAIL", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
