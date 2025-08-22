from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
import csv, os, random

app = FastAPI(title="Warehouse Free Space API (No-BRC)")

BASE_DIR = os.path.dirname(__file__)
LOCATIONS_CSV = os.path.join(BASE_DIR, "locations.csv")

class Reservation(BaseModel):
    id: str
    location_ids: List[str]
    ref: Optional[str] = None
    from_ts: Optional[str] = None
    until_ts: Optional[str] = None
    status: str = "ACTIVE"

locations = {}
reservations = {}

def _generate_fake_dataset(path: str, count_racked=900, count_flex1=100, count_flex2_groups=25, docks=4, yard=20):
    rows = []
    # RACKED (3 areas)
    def add_racked(area_id, aisles, bays, levels, positions):
        for a in range(1, aisles+1):
            for b in range(1, bays+1):
                for l in range(1, levels+1):
                    for p in range(1, positions+1):
                        rows.append({
                            "id": f"R-A{a:02d}-B{b:02d}-L{l:02d}-P{p:02d}-{area_id}",
                            "area_id": area_id, "area_type":"RACKED",
                            "aisle": a, "bay": b, "level": l, "position": p,
                            "length_mm": random.choice([1200,1200,1000]),
                            "width_mm": random.choice([800,1000]),
                            "height_mm": random.choice([1500,1600,1700]),
                            "max_weight_kg": random.choice([800,1000,1200,1500]),
                            "status": random.choices(["FREE","OCCUPIED","RESERVED","BLOCKED","MAINT"], [65,25,5,3,2])[0],
                            "group_id": ""
                        })
    add_racked("RACK-01", 12, 10, 3, 1)  # 360
    add_racked("RACK-02", 10, 10, 3, 1)  # 300
    add_racked("RACK-03", 8, 10, 3, 1)   # 240  -> 900

    # FLEX-01 grid 10x10
    for i in range(1, 101):
        rows.append({
            "id": f"FLEX-01-G{i:03d}", "area_id": "FLEX-01", "area_type":"FLEX",
            "aisle":"", "bay":"", "level":"", "position":"",
            "length_mm": 1000, "width_mm": 1000, "height_mm": 2000,
            "max_weight_kg": 2000,
            "status": random.choices(["FREE","OCCUPIED","RESERVED","BLOCKED","MAINT"], [70,20,5,3,2])[0],
            "group_id": ""
        })
    # FLEX-02 oversize groups (25x2)
    for g in range(1, 26):
        gid = f"FLEX-02-OVR-{g:02d}"
        for s in range(1, 2+1):
            rows.append({
                "id": f"{gid}-S{s}", "area_id": "FLEX-02", "area_type":"FLEX",
                "aisle":"", "bay":"", "level":"", "position":"",
                "length_mm": 2000 if s==1 else 1000, "width_mm": 1000, "height_mm": 2200,
                "max_weight_kg": 2500,
                "status": random.choices(["FREE","OCCUPIED","RESERVED","BLOCKED","MAINT"], [60,25,7,5,3])[0],
                "group_id": gid
            })
    # DOCKS
    for d in range(1, docks+1):
        rows.append({
            "id": f"DOCK-D{d:02d}", "area_id": "DOCK", "area_type":"DOCK",
            "aisle":"", "bay":"", "level":"", "position":"",
            "length_mm": 2500, "width_mm": 2200, "height_mm": 2500,
            "max_weight_kg": 3000, "status": random.choice(["FREE","OCCUPIED"]), "group_id":""
        })
    # YARD pads
    for y in range(1, yard+1):
        rows.append({
            "id": f"YARD-PAD-{y:02d}", "area_id": "YARD", "area_type":"YARD",
            "aisle":"", "bay":"", "level":"", "position":"",
            "length_mm": 3000, "width_mm": 3000, "height_mm": 0,
            "max_weight_kg": 5000, "status": random.choice(["FREE","OCCUPIED","RESERVED"]), "group_id":""
        })
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

def load_locations():
    # jeśli nie ma CSV w repo – wygeneruj automatycznie
    if not os.path.exists(LOCATIONS_CSV):
        _generate_fake_dataset(LOCATIONS_CSV)
    with open(LOCATIONS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            def _to_int(x):
                return int(x) if x not in ("", "None", None) else None
            r["aisle"] = _to_int(r.get("aisle"))
            r["bay"] = _to_int(r.get("bay"))
            r["level"] = _to_int(r.get("level"))
            r["position"] = _to_int(r.get("position"))
            r["length_mm"] = int(r["length_mm"])
            r["width_mm"] = int(r["width_mm"])
            r["height_mm"] = int(r["height_mm"])
            r["max_weight_kg"] = int(r["max_weight_kg"])
            locations[r["id"]] = r

load_locations()

@app.get("/health")
def health():
    return {"ok": True, "locations": len(locations)}

@app.get("/locations")
def get_locations(
    status: Optional[str] = Query(None, regex="^(FREE|OCCUPIED|RESERVED|BLOCKED|MAINT)$"),
    area_type: Optional[str] = Query(None, regex="^(RACKED|FLEX|DOCK|YARD)$"),
    area_id: Optional[str] = None,
    min_l: Optional[int] = None,
    min_w: Optional[int] = None,
    min_h: Optional[int] = None,
    min_weight: Optional[int] = None,
    group_id: Optional[str] = None,
    limit: int = 100
):
    results = []
    for loc in locations.values():
        if status and loc["status"] != status: continue
        if area_type and loc["area_type"] != area_type: continue
        if area_id and loc["area_id"] != area_id: continue
        if group_id and loc["group_id"] != group_id: continue
        if min_l and loc["length_mm"] < min_l: continue
        if min_w and loc["width_mm"] < min_w: continue
        if min_h and loc["height_mm"] < min_h: continue
        if min_weight and loc["max_weight_kg"] < min_weight: continue
        results.append(loc)
        if len(results) >= limit: break
    return {"count": len(results), "items": results}

@app.post("/reserve")
def reserve(res: Reservation):
    for lid in res.location_ids:
        if lid not in locations: raise HTTPException(404, f"Location {lid} not found")
        if locations[lid]["status"] != "FREE": raise HTTPException(409, f"Location {lid} not FREE")
    for lid in res.location_ids: locations[lid]["status"] = "RESERVED"
    reservations[res.id] = res.dict()
    return {"ok": True, "reservation": reservations[res.id]}

@app.post("/occupy/{location_id}")
def occupy(location_id: str, pallet_ref: Optional[str] = None):
    if location_id not in locations: raise HTTPException(404, "Location not found")
    if locations[location_id]["status"] not in ("FREE", "RESERVED"): raise HTTPException(409, "Location not FREE/RESERVED")
    locations[location_id]["status"] = "OCCUPIED"
    return {"ok": True, "location": locations[location_id]}

@app.post("/free/{location_id}")
def free(location_id: str):
    if location_id not in locations: raise HTTPException(404, "Location not found")
    locations[location_id]["status"] = "FREE"
    return {"ok": True, "location": locations[location_id]}

@app.post("/move")
def move(from_location_id: str, to_location_id: str, pallet_ref: Optional[str] = None):
    if from_location_id not in locations or to_location_id not in locations:
        raise HTTPException(404, "Location not found")
    if locations[from_location_id]["status"] != "OCCUPIED":
        raise HTTPException(409, "From location not OCCUPIED")
    if locations[to_location_id]["status"] not in ("FREE", "RESERVED"):
        raise HTTPException(409, "To location not FREE/RESERVED")
    locations[from_location_id]["status"] = "FREE"
    locations[to_location_id]["status"] = "OCCUPIED"
    return {"ok": True, "from": locations[from_location_id], "to": locations[to_location_id]}
