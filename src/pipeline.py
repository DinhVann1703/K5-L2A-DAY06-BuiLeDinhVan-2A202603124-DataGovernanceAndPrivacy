"""YOUR PoC PIPELINE — this is the file your group owns.

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)
    02 process   your algorithm / model (the research part)
    03 rank      prioritise for a fixed review budget B
    04 review    human-in-the-loop: queue -> reviewer decisions -> overrides + audit log
    05 decide    GO / HOLD / REWORK (or track equivalent) with reason_code + owner, write outputs

Required output: out/<pred_file> with the columns listed for your track in
docs/tracks/TXX.md (also in src/metrics/tracks.py::TRACKS). Then evaluate with
    python -m src.evaluate --track tXX --pred out/<pred_file>

Rules: never read fixtures/*/gt/ here (the GT guard will stop you); seed everything via ctx.rng;
no network calls; fail loudly on missing models instead of downloading.
See src/examples/random_baseline.py for a minimal end-to-end wiring example.
"""
from __future__ import annotations

import pandas as pd

from .common.image_ops import (
    load_rgb,
    laplacian_variance,
    brightness_stats,
)
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import (
    apply_overrides,
    load_review_decisions,
    make_review_queue,
    write_review_queue,
)
from .metrics.tracks import get_track


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = (
        verify_manifest(manifest)
        if manifest.exists()
        else [{"problem": "no_manifest"}]
    )

    if problems:
        ctx.audit.log(
            actor="pipeline",
            action="provenance_problems",
            item_id=str(manifest),
            after=problems[:20],
        )
        if ctx.config.get("strict_provenance", True):
            raise ValueError(
                f"provenance check failed ({len(problems)} problems), "
                f"first: {problems[:3]}"
            )

    data = {
        "manifest": pd.read_csv(manifest) if manifest.exists() else None
    }
    data["images"] = pd.read_csv(ctx.input_dir / "images.csv")
    return data


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    rows = []

    for row in data["images"].itertuples(index=False):
        image_path = ctx.input_dir / row.path

        if not image_path.exists():
            raise FileNotFoundError(f"Không tìm thấy ảnh: {image_path}")

        image = load_rgb(image_path)
        sharpness = laplacian_variance(image)
        light_stats = brightness_stats(image)

        rows.append(
            {
                "image_id": row.image_id,
                "path": row.path,
                "camera_id": row.camera_id,
                "light": row.light,
                "split": row.split,
                "sharpness": sharpness,
                "frac_dark": light_stats["frac_dark"],
                "frac_saturated": light_stats["frac_saturated"],
            }
        )

    features = pd.DataFrame(rows)
    dev_name = str(ctx.param("dev_split", "dev"))
    dev = features[features["split"].astype(str) == dev_name]

    if dev.empty:
        raise ValueError(
            f"Không có ảnh split={dev_name!r} để làm mốc PoC"
        )

    scored = []

    for row in features.itertuples(index=False):
        camera_ref = dev.loc[
            dev["camera_id"] == row.camera_id,
            "sharpness",
        ]
        if len(camera_ref) < 5:
            camera_ref = dev["sharpness"]

        light_ref = dev[dev["light"] == row.light]
        if len(light_ref) < 5:
            light_ref = dev

        blur_risk = float(
            (camera_ref >= row.sharpness).mean()
        )
        dark_risk = float(
            (light_ref["frac_dark"] <= row.frac_dark).mean()
        )
        glare_risk = float(
            (
                light_ref["frac_saturated"]
                <= row.frac_saturated
            ).mean()
        )

        risks = {
            "low_sharpness": blur_risk,
            "underexposed": dark_risk,
            "high_saturation": glare_risk,
        }

        # Ba tín hiệu có trọng số bằng nhau; score cao = ưu tiên review.
        score = sum(risks.values()) / 3.0
        reason = max(risks, key=risks.get)

        scored.append(
            {
                "image_id": row.image_id,
                "score": score,
                "reason": reason,
                "path": row.path,
                "light": row.light,
                "camera_id": row.camera_id,
            }
        )

    return pd.DataFrame(scored)


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Xếp hạng theo score; score cao hơn được review trước."""
    budget = int(ctx.param("budget", 20))

    if "score" not in scored.columns:
        raise ValueError(
            "rank(): process() phải tạo cột score dạng số "
            "(score cao hơn = ưu tiên review)"
        )

    q = make_review_queue(
        scored,
        id_col="image_id",
        score_col="score",
        budget=budget,
        reason_col="reason" if "reason" in scored.columns else None,
    )
    write_review_queue(q, ctx.out("review_queue.csv"))
    return q


# ---------------------------------------------------------------- 04 review
def review(
    ctx: RunContext,
    scored: pd.DataFrame,
    queue: pd.DataFrame,
) -> pd.DataFrame:
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"

    final = scored.copy()
    final["pred_action"] = ""

    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)

        final = apply_overrides(
            final,
            reviewed,
            id_col="image_id",
            value_col="pred_action",
            audit=ctx.audit,
        )

    return final


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    return Decision(
        status="HOLD",
        reason_code="OFFICIAL_EVAL_PENDING",
        reason=(
            "Ground-truth labels are not distributed in the student repository; "
            "awaiting official instructor evaluation before release."
        ),
        owner=ctx.config.get("owner", "Bùi Lê Đình Văn"),
        scope=ctx.track,
        evidence=[
            str(ctx.output_dir / "ranked_review.csv"),
            str(ctx.output_dir / "review_queue_reviewed.csv"),
        ],
    )


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)

    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)

    extra_columns = [
        column
        for column in final.columns
        if column not in spec.pred_columns
    ]
    final[spec.pred_columns + extra_columns].to_csv(
        ctx.out(spec.pred_file),
        index=False,
    )

    write_decision(
        decide(ctx, final),
        ctx.out("decision.json"),
        ctx.out("decision_log.csv"),
    )