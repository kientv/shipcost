"""
Shipping Rate Calculator API
FastAPI server with pricing data from Excel
"""
import json
from pathlib import Path
from typing import Optional, Literal
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Load pricing data
DATA_FILE = Path(__file__).parent / "pricing_data.json"
with open(DATA_FILE, encoding='utf-8') as f:
    PRICING_DATA = json.load(f)

app = FastAPI(
    title="ShipCost API",
    description="Multi-carrier shipping rate calculator API",
    version="1.0.0"
)

# ===== Models =====
class RateQuery(BaseModel):
    carrier: Literal["ctu", "ctq", "dhl_sing", "dhl_vietnam", "ups_saver", "fedex"]
    service_type: Optional[str] = None  # doc, non_doc, envelope, pak, ip, etc.
    weight: float = Field(..., gt=0, description="Weight in kg")
    destination: str = Field(..., description="Country name or zone")
    shipment_type: Optional[str] = None  # document, parcel, etc.
    
    # Additional parameters for accurate pricing
    length: Optional[float] = Field(None, description="Length in cm")
    width: Optional[float] = Field(None, description="Width in cm")
    height: Optional[float] = Field(None, description="Height in cm")
    volumetric_weight: Optional[float] = Field(None, description="Volumetric weight (calculated if dims provided)")
    
    # Surcharges
    fuel_surcharge_pct: Optional[float] = Field(None, description="Fuel surcharge percentage")
    remote_area: Optional[bool] = Field(False, description="Remote area delivery")
    high_risk_area: Optional[bool] = Field(False, description="High risk/security surcharge")
    restricted_area: Optional[bool] = Field(False, description="Restricted destination")
    address_correction: Optional[bool] = Field(False, description="Address correction needed")
    oversize_weight: Optional[bool] = Field(False, description="Overweight piece (>70kg)")
    oversize_dim: Optional[bool] = Field(False, description="Oversize piece (>100cm)")
    non_standard: Optional[bool] = Field(False, description="Non-standard packaging")
    non_stackable: Optional[bool] = Field(False, description="Non-stackable pallet")
    peak_surcharge: Optional[bool] = Field(False, description="Peak season surcharge")
    saturday_delivery: Optional[bool] = Field(False, description="Saturday delivery")
    customs_payment: Optional[bool] = Field(False, description="Customs duty payment by shipper")
    max_limit_exceeded: Optional[bool] = Field(False, description="Exceeds max weight/size limits")
    
    # HQ special item categories
    item_category: Optional[str] = Field(None, description="Special item category for HQ surcharges")
    item_quantity: Optional[int] = Field(1, description="Quantity of items")
    item_value: Optional[float] = Field(None, description="Declared value for insurance")
    
    # COD
    cod_amount: Optional[float] = Field(None, description="COD amount (if applicable)")

class RateResponse(BaseModel):
    carrier: str
    service_type: str
    weight: float
    destination: str
    zone: Optional[str] = None
    rate_vnd: Optional[float] = None
    transit_time: Optional[str] = None
    found: bool
    message: Optional[str] = None
    
    # Charge breakdown
    base_rate: Optional[float] = None
    volumetric_weight: Optional[float] = None
    chargeable_weight: Optional[float] = None
    surcharges: Optional[dict] = None
    subtotal: Optional[float] = None
    vat: Optional[float] = None
    total_vnd: Optional[float] = None

class ZoneLookupResponse(BaseModel):
    destination: str
    zone: Optional[int] = None
    carrier: str
    found: bool

# ===== Helper Functions =====
def parse_rate(rate_str: str) -> float:
    """Parse rate string like '770,000 VND/lô hàng' to float 770000"""
    import re
    if not rate_str:
        return 0.0
    rate_str = str(rate_str)
    # Extract first number from string
    nums = re.findall(r'[\d.,]+', rate_str.replace(',', ''))
    if nums:
        return float(nums[0])
    return 0.0

def get_surcharge_config(carrier: str) -> dict:
    """Get surcharge configuration from pricing data"""
    # DHL surcharges
    if carrier in ["dhl_sing", "dhl_vietnam"]:
        surcharges = PRICING_DATA.get("surcharge_dhl_vietnam", [])
        config = {}
        for s in surcharges:
            stype = s.get("type", "").lower()
            rate_str = s.get("rate", "")
            note = s.get("note", "")
            config[stype] = {"rate": rate_str, "amount": parse_rate(rate_str), "note": note}
        return config
    # UPS surcharges
    if carrier == "ups_saver":
        surcharges = PRICING_DATA.get("ups_surcharge", [])
        config = {}
        for s in surcharges:
            stype = s.get("type", "").lower()
            rate_str = s.get("rate", "")
            config[stype] = {"rate": rate_str, "amount": parse_rate(rate_str)}
        return config
    # HQ surcharges
    if carrier in ["ctu", "ctq"]:
        surcharges = PRICING_DATA.get("surcharge_hq", [])
        config = {}
        for s in surcharges:
            item = s.get("item", "").lower()
            rate_str = s.get("rate", "")
            config[item] = {"rate": rate_str, "amount": parse_rate(rate_str), "note": s.get("note", "")}
        return config
    return {}

def get_zone(carrier: str, destination: str) -> Optional[int]:
    """Get zone number for a destination"""
    zone_map = {
        "dhl_sing": PRICING_DATA.get("zone_dhl_sing", {}),
        "dhl_vietnam": PRICING_DATA.get("zone_dhl_vietnam", {}),
        "ups": PRICING_DATA.get("ups_zone", {}),
        "fedex": PRICING_DATA.get("zone_fedex", {}),
    }
    zone_data = zone_map.get(carrier, {})
    # Try exact match first
    if destination in zone_data:
        return zone_data[destination]
    # Try case-insensitive partial match
    dest_lower = destination.lower()
    for k, v in zone_data.items():
        if dest_lower in k.lower() or k.lower() in dest_lower:
            return v
    return None


def get_zone_info(carrier: str, destination: str) -> dict:
    """Get zone number and matched country name for a destination"""
    zone_map = {
        "dhl_sing": PRICING_DATA.get("zone_dhl_sing", {}),
        "dhl_vietnam": PRICING_DATA.get("zone_dhl_vietnam", {}),
        "ups": PRICING_DATA.get("ups_zone", {}),
        "fedex": PRICING_DATA.get("zone_fedex", {}),
    }
    zone_data = zone_map.get(carrier, {})
    # Try exact match first
    if destination in zone_data:
        return {"zone": zone_data[destination], "matched": destination}
    # Try case-insensitive partial match
    dest_lower = destination.lower()
    for k, v in zone_data.items():
        if dest_lower in k.lower() or k.lower() in dest_lower:
            return {"zone": v, "matched": k}
    return {"zone": None, "matched": None}


def is_remote_zone(carrier: str, zone: int) -> bool:
    """Check if zone is considered remote area"""
    remote_zones = {
        "dhl_sing": set([7, 8, 9, 10, 11, 12]),
        "dhl_vietnam": set([6, 7, 8, 9, 10]),
    }
    return zone in remote_zones.get(carrier, set())


def is_high_risk_zone(carrier: str, zone: int, matched_country: str) -> bool:
    """Check if destination is in high-risk area (war/terrorism)"""
    high_risk_countries = [
        "afghanistan", "burkina faso", "congo", "dr congo", "haiti", 
        "iraq", "israel", "lebanon", "libya", "mali", 
        "somalia", "sudan", "syria", "ukraine", "venezuela", "yemen"
    ]
    matched = matched_country.lower()
    return any(risk in matched for risk in high_risk_countries)


def is_restricted_zone(carrier: str, zone: int, matched_country: str) -> bool:
    """Check if destination is restricted (UN sanctions)"""
    restricted_countries = [
        "iraq", "iran", "yemen", "congo", "dr congo", "libya",
        "north korea", "somalia", "syria", "central african republic",
        "afghanistan", "belarus", "lebanon", "myanmar", "russia", "zimbabwe"
    ]
    matched = matched_country.lower()
    return any(rest in matched for rest in restricted_countries)

def find_rate(data: dict, weight: float, zone_or_country: str) -> Optional[float]:
    """Find rate for weight and zone/country"""
    weight_key = str(weight)
    if weight_key not in data:
        # Find closest weight
        weights = [float(k) for k in data.keys()]
        if not weights:
            return None
        closest = min(weights, key=lambda x: abs(x - weight))
        weight_key = str(closest)
    
    weight_data = data.get(weight_key, {})
    if zone_or_country in weight_data:
        return weight_data[zone_or_country]
    
    # Try case-insensitive match
    zone_lower = zone_or_country.lower()
    for k, v in weight_data.items():
        if zone_lower == k.lower():
            return v
    return None


def calculate_volumetric_weight(length: float, width: float, height: float) -> float:
    """Calculate volumetric weight: L x W x H / 5000 (standard) or 6000"""
    return (length * width * height) / 5000.0


def calculate_surcharges(carrier: str, query: RateQuery, base_rate: float, chargeable_weight: float, zone: int = None, matched_country: str = None, dimensions: dict = None) -> dict:
    """Calculate all applicable surcharges - auto-detect from rules and JSON config"""
    surcharges = {}
    surcharge_details = {}
    
    # Get surcharge config from JSON
    surcharge_config = get_surcharge_config(carrier)
    
    # Fuel surcharge (user-provided)
    if query.fuel_surcharge_pct and query.fuel_surcharge_pct > 0:
        fuel_amt = base_rate * (query.fuel_surcharge_pct / 100)
        surcharges["fuel_surcharge"] = fuel_amt
        surcharge_details["fuel_surcharge"] = {"rate": f"{query.fuel_surcharge_pct}%", "amount": fuel_amt}
    
    # Get dimensions
    length = dimensions.get("length") if dimensions else None
    width = dimensions.get("width") if dimensions else None
    height = dimensions.get("height") if dimensions else None
    
    # Auto-detect surcharges for all carriers
    # Overweight > 70kg
    if chargeable_weight > 70:
        overweight_amt = surcharge_config.get("phụ phí kiện hàng quá trọng", {}).get("amount", 2435000)
        surcharges["oversize_weight"] = overweight_amt
        surcharge_details["oversize_weight"] = {"rate": "2,435,000 VND/kiện (>70kg)", "amount": overweight_amt, "auto": True}
    
    # Oversize > 100cm any dimension
    if length and length > 100 or width and width > 100 or height and height > 100:
        oversize_amt = surcharge_config.get("phụ phí kiện hàng quá khổ", {}).get("amount", 545000)
        surcharges["oversize_dim"] = oversize_amt
        surcharge_details["oversize_dim"] = {"rate": "545,000 VND/kiện (>100cm)", "amount": oversize_amt, "auto": True}
    
    # Non-standard if volumetric > 1.5x actual (loose packing)
    if dimensions and length and width and height:
        volumetric = (length * width * height) / 5000.0
        if volumetric > chargeable_weight * 1.5:
            nonstd_amt = surcharge_config.get("phụ phí hàng hóa không theo tiêu chuẩn", {}).get("amount", 545000)
            surcharges["non_standard"] = nonstd_amt
            surcharge_details["non_standard"] = {"rate": "545,000 VND/kiện (khổ lớn)", "amount": nonstd_amt, "auto": True}
    
    # Zone-based surcharges (auto-detect from zone)
    if carrier in ["dhl_sing", "dhl_vietnam"] and zone is not None:
        # Remote area surcharge - read from JSON
        remote_config = surcharge_config.get("phụ phí vùng sâu vùng xa", {})
        remote_rate_per_kg = remote_config.get("per_kg", 13000)
        remote_min = remote_config.get("min_amount", 600000)
        if is_remote_zone(carrier, zone):
            remote_amt = max(chargeable_weight * remote_rate_per_kg, remote_min)
            surcharges["remote_area"] = remote_amt
            surcharge_details["remote_area"] = {"rate": f"{remote_rate_per_kg} VND/kg (min {remote_min}) - Tự động theo zone", "amount": remote_amt, "auto": True}
        
        # High risk area
        if matched_country and is_high_risk_zone(carrier, zone, matched_country):
            high_risk_amt = surcharge_config.get("phụ phí an ninh – rủi ro cao", {}).get("amount", 770000)
            surcharges["high_risk"] = high_risk_amt
            surcharge_details["high_risk"] = {"rate": "770,000 VND/lô hàng - Tự động theo quốc gia", "amount": high_risk_amt, "auto": True}
        
        # Restricted area
        if matched_country and is_restricted_zone(carrier, zone, matched_country):
            restricted_amt = surcharge_config.get("phụ phí an ninh – điểm đến bị hạn chế", {}).get("amount", 750000)
            surcharges["restricted_area"] = restricted_amt
            surcharge_details["restricted_area"] = {"rate": "750,000 VND/lô hàng - Tự động theo quốc gia", "amount": restricted_amt, "auto": True}
        
        # Address correction surcharge
        addr_amt = surcharge_config.get("phụ phí điều chỉnh địa chỉ", {}).get("amount", 300000)
        surcharges["address_correction"] = addr_amt
        surcharge_details["address_correction"] = {"rate": "300,000 VND/lô hàng", "amount": addr_amt, "auto": True}
        
        # Peak surcharge (flag only - varies by season)
        surcharges["peak_surcharge"] = 0
        surcharge_details["peak_surcharge"] = {"rate": "Theo mùa (check mydhl.express.dhl)", "amount": 0, "auto": True}
    
    # UPS surcharges
    if carrier == "ups_saver":
        # Saturday delivery (user option)
        if query.saturday_delivery:
            sat_amt = surcharge_config.get("phụ phí giao hàng vào ngày thứ bảy", {}).get("amount", 258500)
            surcharges["saturday_delivery"] = sat_amt
            surcharge_details["saturday_delivery"] = {"rate": "258,500 VND/lô hàng", "amount": sat_amt}
        
        # Customs payment (user option)
        if query.customs_payment:
            customs_amt = surcharge_config.get("phụ phí chuyển thuế hải quan", {}).get("amount", 600425)
            surcharges["customs_payment"] = customs_amt
            surcharge_details["customs_payment"] = {"rate": "600,425 VND/lô hàng", "amount": customs_amt}
        
        # Max limit exceeded
        if query.max_limit_exceeded:
            max_amt = surcharge_config.get("phí vượt quá giới hạn tối đa", {}).get("amount", 6580000)
            surcharges["max_limit_exceeded"] = max_amt
            surcharge_details["max_limit_exceeded"] = {"rate": "6,580,000 VND/kiện", "amount": max_amt}
        
        # Overweight (same as DHL)
        if chargeable_weight > 70:
            overweight_amt = surcharge_config.get("phụ phí kiện hàng quá trọng (ups)", {}).get("amount", 2435000)
            surcharges["oversize_weight"] = overweight_amt
            surcharge_details["oversize_weight"] = {"rate": "2,435,000 VND/kiện (>70kg)", "amount": overweight_amt, "auto": True}
        
        # Oversize
        if length and length > 100 or width and width > 100 or height and height > 100:
            oversize_amt = surcharge_config.get("phụ phí kiện hàng quá khổ (ups)", {}).get("amount", 545000)
            surcharges["oversize_dim"] = oversize_amt
            surcharge_details["oversize_dim"] = {"rate": "545,000 VND/kiện (>100cm)", "amount": oversize_amt, "auto": True}
    
    # FedEx surcharges
    if carrier == "fedex":
        # Remote area
        if query.remote_area:
            surcharges["remote_area"] = 0
            surcharge_details["remote_area"] = {"rate": "Tùy điểm đến", "amount": 0}
        # Address correction
        if query.address_correction:
            addr_amt = surcharge_config.get("phụ phí điều chỉnh địa chỉ", {}).get("amount", 300000)
            surcharges["address_correction"] = addr_amt
            surcharge_details["address_correction"] = {"rate": "300,000 VND/lô hàng", "amount": addr_amt}
    
    # HQ special item surcharges (applies to CTU/CTQ) - user selected
    if carrier in ["ctu", "ctq"] and query.item_category:
        hq_config = get_surcharge_config(carrier)
        import unicodedata
        def strip_accents(text: str) -> str:
            """Remove diacritics from text"""
            nfkd = unicodedata.normalize('NFD', text)
            return ''.join(c for c in nfkd if not unicodedata.combining(c))

        cat_key = query.item_category.lower().replace(' ', '_')
        for item, cfg in hq_config.items():
            item_lower = item.lower()
            # Flexible matching: check if query words are in item name
            query_parts = query.item_category.lower().split('_')
            if len(query_parts) >= 2:
                item_no_accents = ''.join(c for c in unicodedata.normalize('NFD', item.lower()) if not unicodedata.combining(c))
                if all(part in item_no_accents for part in query.item_category.lower().split('_') if len(part) > 1):
                    # Calculate amount based on rate string
                    rate_str = cfg.get("rate", "")
                    amount = cfg.get("amount", 0)
                    if "kg" in cfg.get("rate", "") and "/" in cfg.get("rate", ""):
                        # Per kg rate
                        import re
                        nums = re.findall(r'[\d.,]+', cfg.get("rate", "").replace(',', ''))
                        if nums:
                            per_kg = float(nums[0])
                            amount = per_kg * chargeable_weight * query.item_quantity
                        else:
                            amount = cfg.get("amount", 0) * query.item_quantity
                    elif any(kw in cfg.get("rate", "") for kw in ["cái", "chiếc", "con", "tượng", "máy", "kiện"]):
                        amount = cfg.get("amount", 0) * query.item_quantity
                    else:
                        amount = cfg.get("amount", 0) * query.item_quantity
                    
                    surcharges[f"hq_{item.replace(' ', '_')}"] = amount
                    surcharge_details[f"hq_{item.replace(' ', '_')}"] = {"rate": cfg.get("rate", ""), "amount": amount}
                    break
    return {"surcharges": surcharges, "details": surcharge_details}

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}

@app.get("/api/carriers")
async def list_carriers():
    """List available carriers and their service types"""
    return {
        "carriers": [
            {
                "id": "ctu",
                "name": "Chuyên Tuyến ỦY Thác (CTU)",
                "description": "Dedicated line to Southeast Asia, China, etc.",
                "pricing_by": "country",
                "service_types": ["standard"]
            },
            {
                "id": "ctq",
                "name": "Chuyên Tuyến (CTQ)",
                "description": "Dedicated line to Hong Kong, Taiwan, Japan, Singapore, China, Korea, India",
                "pricing_by": "country",
                "service_types": ["document", "non_document"]
            },
            {
                "id": "dhl_sing",
                "name": "DHL Singapore (DHLS)",
                "description": "DHL via Singapore gateway",
                "pricing_by": "zone",
                "service_types": ["doc", "non_doc"],
                "zones": list(set(PRICING_DATA.get("zone_dhl_sing", {}).values()))
            },
            {
                "id": "dhl_vietnam",
                "name": "DHL Vietnam (DHLV)",
                "description": "DHL Vietnam domestic/international",
                "pricing_by": "zone",
                "service_types": ["doc", "non_doc"],
                "zones": list(set(PRICING_DATA.get("zone_dhl_vietnam", {}).values()))
            },
            {
                "id": "ups_saver",
                "name": "UPS Saver",
                "description": "UPS Saver service",
                "pricing_by": "zone",
                "service_types": ["envelope", "document", "parcel"],
                "zones": list(set(PRICING_DATA.get("ups_zone", {}).values()))
            },
            {
                "id": "fedex",
                "name": "FedEx International Priority",
                "description": "FedEx IP export service",
                "pricing_by": "zone",
                "service_types": ["envelope", "pak", "ip"],
                "zones": list(set(PRICING_DATA.get("zone_fedex", {}).values()))
            }
        ]
    }

@app.get("/api/zone/{carrier}")
async def lookup_zone(carrier: str, destination: str = Query(..., description="Country name")):
    """Look up zone for a destination"""
    zone = get_zone(carrier, destination)
    return ZoneLookupResponse(
        destination=destination,
        zone=zone,
        carrier=carrier,
        found=zone is not None
    )

@app.post("/api/rate", response_model=RateResponse)
async def get_rate(query: RateQuery):
    """Get shipping rate for given parameters with full charge breakdown"""
    carrier = query.carrier
    weight = query.weight
    destination = query.destination
    service_type = query.service_type
    
    # Calculate volumetric weight from dimensions if provided
    volumetric_weight = query.volumetric_weight
    if volumetric_weight is None and query.length and query.width and query.height:
        volumetric_weight = calculate_volumetric_weight(query.length, query.width, query.height)
    
    # Chargeable weight = max(actual weight, volumetric weight)
    chargeable_weight = max(weight, volumetric_weight) if volumetric_weight else weight
    
    # Rate finding logic for each carrier
    base_rate = None
    zone_str = None
    transit = None
    found = False
    message = None
    
    if carrier == "ctu":
        data = PRICING_DATA.get("ctu", {})
        countries = data.get("countries", [])
        rates = data.get("rates", [])
        
        if destination not in countries:
            return RateResponse(
                carrier=carrier, service_type="standard", weight=weight,
                destination=destination, found=False,
                message=f"Country '{destination}' not found. Available: {', '.join(countries)}"
            )
        
        for r in rates:
            if r["weight"] == chargeable_weight or abs(r["weight"] - chargeable_weight) < 0.1:
                base_rate = r["rates"].get(destination)
                transit = data.get("timeline", {}).get(destination)
                found = base_rate is not None
                break
        
        if base_rate is None:
            weights = [r["weight"] for r in rates]
            closest = min(weights, key=lambda x: abs(x - chargeable_weight))
            for r in rates:
                if r["weight"] == closest:
                    base_rate = r["rates"].get(destination)
                    transit = data.get("timeline", {}).get(destination)
                    zone_str = str(closest)
                    found = base_rate is not None
                    message = f"Using closest weight: {closest}kg"
                    break
        service_type = "standard"
    
    elif carrier == "ctq":
        data = PRICING_DATA.get("ctq", {})
        svc = service_type or "document"
        rate_data = data.get(svc, {})
        
        base_rate = find_rate(rate_data, chargeable_weight, destination)
        found = base_rate is not None
        service_type = svc
    
    elif carrier in ["dhl_sing", "dhl_vietnam"]:
        data = PRICING_DATA.get("dhl_sing" if carrier == "dhl_sing" else "dhl_vietnam", {})
        svc = service_type or "doc"
        rate_data = data.get(svc, {})
        
        zone_info = get_zone_info(carrier, destination)
        zone = zone_info["zone"]
        matched_country = zone_info["matched"]
        
        if zone is None:
            return RateResponse(
                carrier=carrier, service_type=svc, weight=weight,
                destination=destination, found=False,
                message=f"Zone not found for '{destination}'"
            )
        
        zone_str = f"Zone {zone}"
        # Try zone string first, then destination name (for DHL Sing non-doc which uses country names)
        base_rate = find_rate(rate_data, chargeable_weight, zone_str)
        if base_rate is None and carrier == "dhl_sing" and svc == "non_doc":
            base_rate = find_rate(rate_data, chargeable_weight, destination)
        transit = data.get("transit", {}).get(zone_str)
        found = base_rate is not None
        service_type = svc
    
    elif carrier == "ups_saver":
        data = PRICING_DATA.get("ups_saver", {})
        svc = service_type or "document"
        rate_data = data.get(svc, {})
        
        zone_info = get_zone_info("ups", destination)
        zone = zone_info["zone"]
        matched_country = zone_info["matched"]
        
        if zone is None:
            return RateResponse(
                carrier=carrier, service_type=svc, weight=weight,
                destination=destination, found=False,
                message=f"UPS zone not found for '{destination}'"
            )
        
        zone_str = str(zone)
        base_rate = find_rate(rate_data, chargeable_weight, zone_str)
        found = base_rate is not None
        service_type = svc
    
    elif carrier == "fedex":
        data = PRICING_DATA.get("fedex", {})
        svc = service_type or "ip"
        rate_data = data.get(svc, {})
        
        zone_info = get_zone_info("fedex", destination)
        zone = zone_info["zone"]
        matched_country = zone_info["matched"]
        
        if zone is None:
            return RateResponse(
                carrier=carrier, service_type=svc, weight=weight,
                destination=destination, found=False,
                message=f"FedEx zone not found for '{destination}'"
            )
        
        zone_str = str(zone)
        base_rate = find_rate(rate_data, chargeable_weight, zone_str)
        found = base_rate is not None
        service_type = svc
    
    else:
        raise HTTPException(400, f"Unknown carrier: {carrier}")
    
    if not found or base_rate is None:
        return RateResponse(
            carrier=carrier, service_type=service_type, weight=weight,
            destination=destination, found=False,
            message=message or "No rate found for given parameters"
        )
    
    # Prepare dimensions dict
    dimensions = None
    if query.length or query.width or query.height:
        dimensions = {
            "length": query.length,
            "width": query.width,
            "height": query.height
        }
    
    # Calculate surcharges with auto-detection
    surcharge_result = calculate_surcharges(
        carrier, query, base_rate, chargeable_weight, 
        zone=zone if 'zone' in locals() else None,
        matched_country=matched_country if 'matched_country' in locals() else None,
        dimensions=dimensions
    )
    surcharges = surcharge_result["surcharges"]
    surcharge_details = surcharge_result["details"]
    
    # Calculate totals
    total_surcharges = sum(surcharges.values())
    subtotal = base_rate + total_surcharges
    vat = calculate_vat(subtotal)  # 10% VAT
    total_vnd = subtotal + vat
    
    return RateResponse(
        carrier=carrier,
        service_type=service_type,
        weight=weight,
        destination=destination,
        zone=zone_str,
        rate_vnd=base_rate,  # base rate
        transit_time=transit,
        found=True,
        message=message,
        base_rate=base_rate,
        volumetric_weight=volumetric_weight,
        chargeable_weight=chargeable_weight,
        surcharges=surcharges,
        subtotal=subtotal,
        vat=vat,
        total_vnd=total_vnd
    )

@app.get("/api/surcharges/{carrier}")
async def get_surcharges(carrier: str):
    """Get surcharges for a carrier"""
    surcharge_map = {
        "dhl_vietnam": PRICING_DATA.get("surcharge_dhl_vietnam", []),
        "ups": PRICING_DATA.get("ups_surcharge", []),
        "hq": PRICING_DATA.get("surcharge_hq", []),
    }
    return {"carrier": carrier, "surcharges": surcharge_map.get(carrier, [])}

@app.get("/api/countries/{carrier}")
async def list_countries(carrier: str):
    """List countries/destinations for direct country-based pricing"""
    if carrier == "ctu":
        return {"carrier": carrier, "countries": PRICING_DATA.get("ctu", {}).get("countries", [])}
    elif carrier == "ctq":
        countries = set()
        for svc in ["document", "non_document"]:
            for wdata in PRICING_DATA.get("ctq", {}).get(svc, {}).values():
                countries.update(wdata.keys())
        return {"carrier": carrier, "countries": sorted(countries)}
    else:
        # For zone-based carriers, return zone mapping
        zone_map = {
            "dhl_sing": PRICING_DATA.get("zone_dhl_sing", {}),
            "dhl_vietnam": PRICING_DATA.get("zone_dhl_vietnam", {}),
            "ups": PRICING_DATA.get("ups_zone", {}),
            "fedex": PRICING_DATA.get("zone_fedex", {}),
        }
        zones = zone_map.get(carrier, {})
        return {"carrier": carrier, "zone_map": zones}

def calculate_vat(amount: float, vat_rate: float = 0.1) -> float:
    """Calculate VAT (10% default)"""
    return amount * vat_rate

@app.get("/")
async def root():
    return FileResponse("index.html")

# ===== Run =====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

@app.get("/")
async def root():
    return FileResponse("index.html")

# ===== Run =====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
