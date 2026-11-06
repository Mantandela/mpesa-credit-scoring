"""Log the public datasets in data/raw/ (source, licence, download date, sha256).

Run from the repo root:  python scripts/download_public_data.py
The files are placed by hand in data/raw/ (flat, no subfolders). This script does not download anything:
it checks that each expected file is there and writes data/raw/SOURCES.csv.

Fix any "FILL" entry below, then run it again. Files already logged are skipped.
"""
import csv, datetime as dt, hashlib, pathlib

RAW = pathlib.Path("data/raw")
LOG = RAW / "SOURCES.csv"

# dataset name: (file in data/raw, source URL, licence)
FILES = {
    "momtsim": ("momt_dataset.csv", "https://data.mendeley.com/datasets/zhj366m53p/2", "CC BY 4.0"),
    "kenya_mobile_money_6k": ("kenya_mobile_money_6k.csv",
                              "https://github.com/stephenomengo/Kenya-Mobile-Money-Analysis",
                              "None stated in the repository (checked 3 Nov 2026). Private reference only, not redistributed"),
    "paysim": ("paysim_dataset.csv", "https://www.kaggle.com/datasets/ealaxi/paysim1",
               "CC BY-SA 4.0 (confirmed on the Kaggle page, 3 Nov 2026)"),
    "uci_german_credit": ("uci_german_credit.data",
                          "https://archive.ics.uci.edu/dataset/144/statlog+german+credit+data",
                          "CC BY 4.0 (confirmed on the UCI page, 3 Nov 2026)"),
    "finaccess_2021_report": ("finacess.pdf", "https://statistics.knbs.or.ke/nada/index.php/catalog/104/related-materials",
                              "Published report; cite with attribution (terms not checked)"),
}

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def already_logged():
    if not LOG.exists():
        return set()
    with open(LOG, newline="") as f:
        return {row["file"] for row in csv.DictReader(f)}

if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    seen = already_logged()
    new = not LOG.exists()
    with open(LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["dataset", "source_url", "licence", "downloaded_on", "file", "sha256"])
        for name, (fname, url, licence) in FILES.items():
            path = RAW / fname
            if not path.exists():
                print(f"MISSING {name}: put {fname} in data/raw/")
                continue
            if path.as_posix() in seen:
                print(f"skip    {name}: already logged")
                continue
            w.writerow([name, url, licence, dt.date.today().isoformat(), path.as_posix(), sha256(path)])
            print(f"logged  {name}: {fname}")
    print("Done. Check data/raw/SOURCES.csv and fix any FILL entries.")