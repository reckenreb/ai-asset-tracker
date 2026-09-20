import os, csv, glob, base64
from datetime import datetime
from flask import Flask, request, redirect, url_for, render_template, flash, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me")

APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "changeme")

def check_auth(auth_header):
    if not auth_header or not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header.split(" ", 1)[1]).decode("utf-8")
        user, pw = decoded.split(":", 1)
    except Exception:
        return False
    return user == APP_USERNAME and pw == APP_PASSWORD

@app.before_request
def require_auth():
    auth_header = request.headers.get("Authorization")
    if not check_auth(auth_header):
        return (
            "Login erforderlich",
            401,
            {"WWW-Authenticate": 'Basic realm="Asset Tracker"'},
        )

DATA_DIR = os.environ.get("DATA_DIR", "/data")
ASSETS_DIR = os.path.join(DATA_DIR, "assets")
PORTFOLIOS_FILE = os.path.join(DATA_DIR, "portfolios.csv")
LOCK_DAYS = 7

os.makedirs(ASSETS_DIR, exist_ok=True)
if not os.path.exists(PORTFOLIOS_FILE):
    with open(PORTFOLIOS_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["name", "assets"])

def safe_name(name):
    return "".join(c for c in name if c.isalnum() or c in ("-", "_", " ")).strip().replace(" ", "_")

def asset_path(name):
    return os.path.join(ASSETS_DIR, f"{safe_name(name)}.csv")

def list_assets():
    return sorted(
        os.path.splitext(os.path.basename(p))[0]
        for p in glob.glob(os.path.join(ASSETS_DIR, "*.csv"))
    )

def read_asset(name):
    path = asset_path(name)
    rows = []
    if os.path.exists(path):
        with open(path, newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) >= 2 and row[0]:
                    rows.append((row[0], float(row[1])))
    return sorted(rows, key=lambda r: r[0])

def write_asset(name, rows):
    path = asset_path(name)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "value"])
        for d, v in sorted(rows, key=lambda r: r[0]):
            writer.writerow([d, v])

def is_locked(date_str):
    try:
        entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return True
    return (datetime.utcnow().date() - entry_date).days > LOCK_DAYS

def read_portfolios():
    portfolios = {}
    with open(PORTFOLIOS_FILE, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                portfolios[row[0]] = [a for a in row[1].split("|") if a]
    return portfolios

def write_portfolios(portfolios):
    with open(PORTFOLIOS_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "assets"])
        for name, assets in portfolios.items():
            writer.writerow([name, "|".join(assets)])

def portfolio_series(asset_names):
    series = {a: dict(read_asset(a)) for a in asset_names}
    all_dates = sorted(set(d for s in series.values() for d in s.keys()))
    result = []
    last_known = {a: None for a in asset_names}
    for d in all_dates:
        total = 0.0
        for a in asset_names:
            if d in series[a]:
                last_known[a] = series[a][d]
            if last_known[a] is not None:
                total += last_known[a]
        result.append((d, round(total, 2)))
    return result

@app.route("/")
def index():
    assets = list_assets()
    portfolios = read_portfolios()
    asset_counts = {a: len(read_asset(a)) for a in assets}
    return render_template("index.html", assets=assets, asset_counts=asset_counts, portfolios=portfolios)

@app.route("/asset/create", methods=["POST"])
def create_asset():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Name darf nicht leer sein.")
        return redirect(url_for("index"))
    path = asset_path(name)
    if os.path.exists(path):
        flash("Asset existiert bereits.")
    else:
        write_asset(name, [])
        flash(f"Asset '{name}' angelegt.")
    return redirect(url_for("index"))

@app.route("/asset/<name>")
def asset_detail(name):
    rows = read_asset(name)
    rows_with_lock = [(d, v, is_locked(d)) for d, v in rows]
    return render_template("asset.html", name=name, rows=rows_with_lock, lock_days=LOCK_DAYS)

@app.route("/asset/<name>/add", methods=["POST"])
def asset_add_value(name):
    date = request.form.get("date", "").strip()
    value = request.form.get("value", "").strip()
    try:
        datetime.strptime(date, "%Y-%m-%d")
        value_f = float(value.replace(",", "."))
    except ValueError:
        flash("Ungueltiges Datum oder Wert. Format: YYYY-MM-DD und Zahl.")
        return redirect(url_for("asset_detail", name=name))
    existing_rows = read_asset(name)
    existing_dates = {r[0] for r in existing_rows}
    if date in existing_dates and is_locked(date):
        flash(f"Dieser Eintrag ist aelter als {LOCK_DAYS} Tage und kann ueber das Webinterface nicht mehr bearbeitet werden.")
        return redirect(url_for("asset_detail", name=name))
    rows = [r for r in existing_rows if r[0] != date]
    rows.append((date, value_f))
    write_asset(name, rows)
    flash("Wert gespeichert.")
    return redirect(url_for("asset_detail", name=name))

@app.route("/assets/bulk_add", methods=["POST"])
def bulk_add_values():
    """Werte für mehrere Assets gleichzeitig eintragen (Startseite)"""
    date = request.form.get("date", "").strip()

    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        flash("Ungueltiges Datum. Format: YYYY-MM-DD")
        return redirect(url_for("index"))

    assets = list_assets()
    saved_count = 0

    for asset in assets:
        value_key = f"value_{asset}"
        value = request.form.get(value_key, "").strip()

        if value:
            try:
                value_f = float(value.replace(",", "."))
            except ValueError:
                continue

            existing_rows = read_asset(asset)
            existing_dates = {r[0] for r in existing_rows}

            if date in existing_dates and is_locked(date):
                continue

            rows = [r for r in existing_rows if r[0] != date]
            rows.append((date, value_f))
            write_asset(asset, rows)
            saved_count += 1

    flash(f"{saved_count} Werte fuer {date} gespeichert.")
    return redirect(url_for("index"))

@app.route("/asset/<name>/delete_entry", methods=["POST"])
def delete_entry(name):
    date = request.form.get("date")
    if is_locked(date):
        flash(f"Dieser Eintrag ist aelter als {LOCK_DAYS} Tage und kann ueber das Webinterface nicht mehr geloescht werden.")
        return redirect(url_for("asset_detail", name=name))
    rows = [r for r in read_asset(name) if r[0] != date]
    write_asset(name, rows)
    flash("Eintrag geloescht.")
    return redirect(url_for("asset_detail", name=name))

@app.route("/asset/<name>/delete", methods=["POST"])
def delete_asset(name):
    path = asset_path(name)
    if os.path.exists(path):
        os.remove(path)
    portfolios = read_portfolios()
    changed = False
    for pname, assets in portfolios.items():
        if name in assets:
            assets.remove(name)
            changed = True
    if changed:
        write_portfolios(portfolios)
    flash(f"Asset '{name}' geloescht.")
    return redirect(url_for("index"))

@app.route("/asset/<name>/rename", methods=["POST"])
def rename_asset(name):
    new_name = request.form.get("new_name", "").strip()
    if not new_name:
        flash("Neuer Name darf nicht leer sein.")
        return redirect(url_for("asset_detail", name=name))
    old_path = asset_path(name)
    new_path = asset_path(new_name)
    if not os.path.exists(old_path):
        flash("Asset nicht gefunden.")
        return redirect(url_for("index"))
    new_safe = safe_name(new_name)
    if os.path.exists(new_path) and new_safe != safe_name(name):
        flash("Es existiert bereits ein Asset mit diesem Namen.")
        return redirect(url_for("asset_detail", name=name))
    os.rename(old_path, new_path)
    portfolios = read_portfolios()
    changed = False
    for pname, assets in portfolios.items():
        if name in assets:
            assets[assets.index(name)] = new_safe
            changed = True
    if changed:
        write_portfolios(portfolios)
    flash(f"Asset '{name}' umbenannt in '{new_safe}'.")
    return redirect(url_for("asset_detail", name=new_safe))

@app.route("/portfolio/create", methods=["POST"])
def create_portfolio():
    name = request.form.get("name", "").strip()
    assets = request.form.getlist("assets")
    if not name or not assets:
        flash("Name und mindestens ein Asset erforderlich.")
        return redirect(url_for("index"))
    portfolios = read_portfolios()
    portfolios[name] = assets
    write_portfolios(portfolios)
    flash(f"Portfolio '{name}' gespeichert.")
    return redirect(url_for("index"))

@app.route("/portfolio/<name>")
def portfolio_detail(name):
    portfolios = read_portfolios()
    assets = portfolios.get(name, [])
    series = portfolio_series(assets)
    return render_template("portfolio.html", name=name, assets=assets, series=series)

@app.route("/portfolio/<name>/delete", methods=["POST"])
def delete_portfolio(name):
    portfolios = read_portfolios()
    portfolios.pop(name, None)
    write_portfolios(portfolios)
    return redirect(url_for("index"))

@app.route("/api/portfolio/<name>")
def api_portfolio(name):
    portfolios = read_portfolios()
    assets = portfolios.get(name, [])
    return jsonify(portfolio_series(assets))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
