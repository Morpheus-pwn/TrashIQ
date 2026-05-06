#!/usr/bin/env python3
"""
Merge multiple YOLO (v5/YOLOv8-style) datasets into a single dataset folder,
remapping class indices to a unified class list.

Usage example:
  pip install pyyaml
  python scripts/merge_yolo_datasets.py \
    --datasets "data/ds1" "data/ds2" "data/ds3" \
    --outdir "data/merged" --dry-run

The script detects per-dataset YAML (names/nc), or you can provide a manual
mapping file if needed.
"""
import argparse
import os
import shutil
import yaml
import glob
from collections import OrderedDict


def find_yaml(dataset_dir):
    for ext in ("*.yml", "*.yaml"):
        files = glob.glob(os.path.join(dataset_dir, ext))
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                    if isinstance(data, dict) and ("names" in data or "nc" in data or "train" in data):
                        return f, data
            except Exception:
                continue
    return None, None


def load_names_from_yaml(yaml_data):
    if not yaml_data:
        return None
    if "names" in yaml_data:
        names = yaml_data["names"]
        if isinstance(names, dict):
            # sometimes names are {0: 'a', 1: 'b'}
            # convert to list by numeric keys order
            try:
                max_k = max(int(k) for k in names.keys())
                return [names.get(str(i), names.get(i)) for i in range(max_k + 1)]
            except Exception:
                return list(names.values())
        return list(names)
    return None


def detect_splits(dataset_root):
    # return dict mapping split->(images_dir, labels_dir)
    candidates = {}
    # common split names
    splits = ["train", "val", "valid", "test"]
    for s in splits:
        images = os.path.join(dataset_root, s, "images")
        labels = os.path.join(dataset_root, s, "labels")
        if os.path.isdir(images):
            candidates[s] = (images, labels)
    # also handle flat structure where images/ and labels/ exist at root
    root_images = os.path.join(dataset_root, "images")
    root_labels = os.path.join(dataset_root, "labels")
    if os.path.isdir(root_images):
        candidates.setdefault("train", (root_images, root_labels))
    return candidates


def safe_mkdir(path, dry_run=False):
    if dry_run:
        return
    os.makedirs(path, exist_ok=True)


def copy_and_remap(src_images, src_labels, out_images, out_labels, mapping, prefix, dry_run=False):
    copied = 0
    remapped_labels = 0
    missing_label = 0
    for img_path in glob.glob(os.path.join(src_images, "*")):
        if os.path.isdir(img_path):
            continue
        base = os.path.basename(img_path)
        name, ext = os.path.splitext(base)
        src_label_file = os.path.join(src_labels, name + ".txt") if src_labels else os.path.join(os.path.dirname(src_images), "labels", name + ".txt")
        # create new unique name with prefix
        new_name = f"{prefix}__{name}"
        dest_img = os.path.join(out_images, new_name + ext)
        dest_lbl = os.path.join(out_labels, new_name + ".txt")
        if not dry_run:
            shutil.copy2(img_path, dest_img)
        copied += 1
        if os.path.isfile(src_label_file):
            with open(src_label_file, "r", encoding="utf-8") as fh:
                lines = [l.strip() for l in fh.readlines() if l.strip()]
            out_lines = []
            for l in lines:
                parts = l.split()
                if len(parts) == 0:
                    continue
                old_idx = parts[0]
                try:
                    old_idx_i = int(old_idx)
                except Exception:
                    continue
                new_idx = mapping.get(old_idx_i)
                if new_idx is None:
                    # skip object whose class is unknown
                    continue
                out_lines.append(" ".join([str(new_idx)] + parts[1:]))
            if not dry_run:
                with open(dest_lbl, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(out_lines) + ("\n" if out_lines else ""))
            remapped_labels += 1
        else:
            missing_label += 1
            if not dry_run:
                # create empty label file for consistency
                open(dest_lbl, "w", encoding="utf-8").close()
    return copied, remapped_labels, missing_label


def main():
    p = argparse.ArgumentParser(description="Merge YOLO datasets into one unified dataset.")
    p.add_argument("--datasets", nargs="+", required=True, help="Paths to each dataset root folder")
    p.add_argument("--outdir", required=True, help="Output merged dataset root")
    p.add_argument("--splits", nargs="*", default=["train","val","test"], help="Which splits to merge (default: train val test)")
    p.add_argument("--dry-run", action="store_true", help="Do not copy files, only show planned actions")
    p.add_argument("--suffix", default=None, help="Optional suffix to add to output dataset YAML")
    args = p.parse_args()

    datasets = args.datasets
    outdir = args.outdir
    dry_run = args.dry_run
    splits = args.splits

    print("Scanning datasets for YAML and class names...")
    per_ds_names = []
    per_ds_yaml = []
    per_ds_found = []
    for ds in datasets:
        ypath, ydata = find_yaml(ds)
        names = load_names_from_yaml(ydata)
        per_ds_names.append(names)
        per_ds_yaml.append((ypath, ydata))
        per_ds_found.append(ds)
        print(f"  {ds}: yaml={ypath}, names_count={len(names) if names else 'None'}")

    # build unified ordered names (preserve first-seen ordering)
    unified = []
    seen = set()
    for names in per_ds_names:
        if not names:
            continue
        for n in names:
            if n not in seen:
                unified.append(n)
                seen.add(n)
    if not unified:
        print("No class names found automatically. You must provide class names manually in a YAML or modify the script.")
        return

    print(f"Unified classes ({len(unified)}):")
    for i,n in enumerate(unified):
        print(f"  {i}: {n}")

    # build per-dataset mapping old_index -> new_index
    ds_mappings = []
    for names in per_ds_names:
        mapping = {}
        if not names:
            # no names found, assume empty mapping
            ds_mappings.append(mapping)
            continue
        for old_i, nm in enumerate(names):
            new_i = unified.index(nm)
            mapping[old_i] = new_i
        ds_mappings.append(mapping)

    # prepare output folders
    for s in splits:
        safe_mkdir(os.path.join(outdir, s, "images"), dry_run=dry_run)
        safe_mkdir(os.path.join(outdir, s, "labels"), dry_run=dry_run)

    # perform copying per dataset, per split
    summary = {}
    for ds_idx, ds in enumerate(datasets):
        splits_found = detect_splits(ds)
        prefix = os.path.basename(os.path.normpath(ds)).replace(" ", "_")
        for s in splits:
            # prefer 'val' over 'valid' if both exist
            chosen = None
            if s in splits_found:
                chosen = s
            elif s == "val" and "valid" in splits_found:
                chosen = "valid"
            if not chosen:
                continue
            src_images, src_labels = splits_found[chosen]
            out_images = os.path.join(outdir, s, "images")
            out_labels = os.path.join(outdir, s, "labels")
            print(f"Processing dataset {ds} split {chosen} -> {out_images}")
            safe_mkdir(out_images, dry_run=dry_run)
            safe_mkdir(out_labels, dry_run=dry_run)
            copied, remapped, missing = copy_and_remap(src_images, src_labels, out_images, out_labels, ds_mappings[ds_idx], prefix, dry_run=dry_run)
            summary.setdefault(s, {"images":0, "labels":0, "missing_labels":0})
            summary[s]["images"] += copied
            summary[s]["labels"] += remapped
            summary[s]["missing_labels"] += missing

    print("\nSummary:")
    for s, info in summary.items():
        print(f"  {s}: images={info['images']}, remapped_labels={info['labels']}, missing_labels={info['missing_labels']}")

    # write dataset YAML
    dataset_yaml = {
        "train": os.path.join(outdir, "train", "images") if os.path.isdir(os.path.join(outdir, "train", "images")) else "",
        "val": os.path.join(outdir, "val", "images") if os.path.isdir(os.path.join(outdir, "val", "images")) else "",
        "test": os.path.join(outdir, "test", "images") if os.path.isdir(os.path.join(outdir, "test", "images")) else "",
        "nc": len(unified),
        "names": unified,
    }
    yaml_path = os.path.join(outdir, f"dataset{('_'+args.suffix) if args.suffix else ''}.yaml")
    if not dry_run:
        with open(yaml_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(dataset_yaml, fh, sort_keys=False)
    print(f"Wrote dataset YAML to: {yaml_path} (dry_run={dry_run})")

if __name__ == '__main__':
    main()
