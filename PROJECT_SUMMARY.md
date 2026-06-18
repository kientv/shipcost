# ShipCost API - Project Summary

## Overview
A complete multi-carrier pricing API system built from Excel price tables, featuring:
1. **REST API** (FastAPI) for AI agents and programmatic access
2. **Web Form** (HTML/JS) for manual price lookups
3. **JSON Data** extracted from all 13 Excel sheets

## Files Created
```
/Users/kientv/Workspace/Sale/newport/
├── extract_pricing.py      # Python script to extract Excel → JSON
├── pricing_data.json       # All pricing data (1.2MB, 13 sheets)
├── api_server.py           # FastAPI server with 6 endpoints
├── index.html              # Web form for manual lookups
└── BẢNG GIÁ NEWPOST PUPLIC KHÁCH HÀNG.xlsx  # Source file
```

## Carriers Supported
| Carrier | ID | Pricing Type | Services |
|---------|----|--------------|----------|
| Chuyên Tuyến ỦY Thác (CTU) | `ctu` | Direct country | standard |
| Chuyên Tuyến (CTQ) | `ctq` | Direct country | document, non_document |
| DHL Singapore (DHLS) | `dhl_sing` | Zone-based | doc, non_doc |
| DHL Vietnam (DHLV) | `dhl_vietnam` | Zone-based | doc, non_doc |
| UPS Saver | `ups_saver` | Zone-based | envelope, document, parcel |
| FedEx International Priority | `fedex` | Zone-based | envelope, pak, ip |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/rate` | POST | **Main** - Get rate with full breakdown |
| `/api/zone/{carrier}` | GET | Lookup zone from country |
| `/api/carriers` | GET | List all carriers & services |
| `/api/countries/{carrier}` | GET | List destinations |
| `/api/surcharges/{carrier}` | GET | View surcharge tables |
| `/docs` | GET | Swagger/OpenAPI docs |

## AI Agent Call Example
```python
requests.post("http://localhost:8000/api/rate", json={
    "carrier": "dhl_vietnam",
    "service_type": "doc",
    "weight": 1.5,
    "destination": "Singapore",
    "length": 30, "width": 20, "height": 15,
    "fuel_surcharge_pct": 12.5
})
# Returns: base_rate, volumetric_weight, chargeable_weight, surcharges{}, subtotal, vat, total_vnd
```

## Web Form (`http://localhost:8000/`)
- **Auto zone detection** - Countries match zone data exactly
- **Auto surcharges** - No manual checkboxes:
  - Overweight >70kg (2.435M)
  - Oversize >100cm (545k)
  - Non-standard (volumetric >1.5× actual)
  - DHL remote/high-risk/restricted (auto by zone)
  - Fuel surcharge (user %)
  - HQ items (user selects category)
- **Removed**: COD section, Fuel surcharge % input
- **Fixed**: Error display shows actual API errors

## Data Coverage
- **CTU**: 17 countries × 25 weight breaks
- **CTQ**: 7 destinations × doc/non-doc
- **DHL Sing**: 12 zones × 5 weights × doc/non-doc
- **DHL VN**: 10 zones × 5 weights + transit times
- **UPS Saver**: 16 zones × 40 weights × envelope/doc/parcel
- **FedEx**: 13 zones × 20+ weights × envelope/pak/ip
- **Zone maps**: 643 country→zone mappings
- **Surcharges**: 63 items (DHL VN, UPS, HQ special items)

## Regenerating Data
When the Excel file updates:
```bash
python extract_pricing.py  # Regenerates pricing_data.json
# Restart api_server.py to reload
```