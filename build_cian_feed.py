#!/usr/bin/env python3
"""Собирает cian_feed.xml для автозагрузки ЦИАН из тех же ads/*.json, что и Авито."""
import json
import glob
import re
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom

BASE = "/Users/sonia/avito-feed"

with open(f"{BASE}/config/common_fields.json", encoding="utf-8") as f:
    COMMON = json.load(f)

with open(f"{BASE}/config/categories.json", encoding="utf-8") as f:
    AVITO_CATEGORIES = json.load(f)

with open(f"{BASE}/config/cian_categories.json", encoding="utf-8") as f:
    CIAN_CATEGORIES = json.load(f)

EMAPS = CIAN_CATEGORIES["_enum_maps"]


def sub(parent, tag, text):
    if text is None or text == "":
        return None
    el = ET.SubElement(parent, tag)
    el.text = str(text)
    return el


def parse_phone(phone_str):
    digits = re.sub(r"\D", "", phone_str)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if digits.startswith("7") and len(digits) == 11:
        return "+7", digits[1:]
    return "+7", digits[-10:]


def cian_category_for(ad, cat_key, avito_cfg):
    mapping = CIAN_CATEGORIES.get(cat_key)
    if mapping is None:
        return None
    if "cian_category" in mapping:
        return mapping["cian_category"]
    object_type = ad.get("fields", {}).get("ObjectType")
    return mapping.get("by_object_type", {}).get(object_type)


def build_phones(parent):
    phones = sub(parent, "Phones", None) or ET.SubElement(parent, "Phones")
    schema = ET.SubElement(phones, "PhoneSchema")
    code, number = parse_phone(COMMON["ContactPhone"])
    sub(schema, "CountryCode", code)
    sub(schema, "Number", number)


def build_photos(parent, images):
    if not images:
        return
    photos = ET.SubElement(parent, "Photos")
    for i, url in enumerate(images):
        p = ET.SubElement(photos, "PhotoSchema")
        sub(p, "FullUrl", url)
        if i == 0:
            sub(p, "IsDefault", "true")


def lease_price_type(price_type):
    return "squareMeter" if price_type == "в месяц за м2" else "all"


def build_bargain_terms_rent(parent, ad, cat_cfg, fields):
    price_type = lease_price_type(fields.get("PriceType"))
    total_monthly = ad["price"] * float(fields.get("Square", 1)) if price_type == "squareMeter" else ad["price"]

    bt = ET.SubElement(parent, "BargainTerms")
    sub(bt, "Price", ad["price"])
    sub(bt, "PriceType", price_type)
    sub(bt, "Currency", "rur")
    sub(bt, "PaymentPeriod", "monthly")
    lease_type = EMAPS["RentalType_to_LeaseType"].get(
        cat_cfg.get("defaults", {}).get("RentalType"), "direct"
    )
    sub(bt, "LeaseType", lease_type)

    deposit_text = cat_cfg.get("defaults", {}).get("LeaseDeposit")
    m = re.search(r"([\d,.]+)", deposit_text or "")
    if m:
        months = float(m.group(1).replace(",", "."))
        sub(bt, "SecurityDeposit", round(total_monthly * months))

    min_period = cat_cfg.get("defaults", {}).get("RentalMinimumPeriod")
    if min_period:
        sub(bt, "MinLeaseTerm", min_period)

    commission = cat_cfg.get("commission")
    if commission:
        bonus = ET.SubElement(bt, "AgentBonus")
        sub(bonus, "Value", COMMON["commission_rental_percent"])
        sub(bonus, "PaymentType", "percent")
        sub(bonus, "Currency", "rur")


def build_bargain_terms_sale(parent, ad, fields):
    bt = ET.SubElement(parent, "BargainTerms")
    sub(bt, "Price", ad["price"])
    sub(bt, "Currency", "rur")
    sale_type = EMAPS["DealType_to_SaleType"].get(fields.get("DealType"), "free")
    sub(bt, "SaleType", sale_type)


def build_commercial_building(parent, fields):
    heating = EMAPS["Heating_to_HeatingType"].get(fields.get("Heating"))
    btype = EMAPS["BuildingType_to_Type"].get(fields.get("BuildingType"))
    ceiling = fields.get("CeilingHeight")
    if not (heating or btype or ceiling):
        return
    b = ET.SubElement(parent, "Building")
    sub(b, "HeatingType", heating)
    sub(b, "CeilingHeight", ceiling)
    sub(b, "Type", btype)


def build_flat_building(parent, fields):
    material = EMAPS["HouseType_to_MaterialType"].get(fields.get("HouseType"))
    floors = fields.get("Floors")
    ceiling = fields.get("CeilingHeight")
    if not (material or floors or ceiling):
        return
    b = ET.SubElement(parent, "Building")
    sub(b, "MaterialType", material)
    sub(b, "FloorsCount", floors)
    sub(b, "CeilingHeight", ceiling)


def build_object(ad, errors):
    cat_key = ad["category"]
    avito_cfg = AVITO_CATEGORIES.get(cat_key)
    if avito_cfg is None:
        errors.append(f"{ad['id']}: неизвестная категория '{cat_key}'")
        return None

    cian_cat = cian_category_for(ad, cat_key, avito_cfg)
    if cian_cat is None:
        errors.append(f"{ad['id']}: не нашла соответствие в cian_categories.json "
                       f"(категория '{cat_key}', ObjectType '{ad.get('fields', {}).get('ObjectType')}')")
        return None

    fields = ad.get("fields", {})
    obj = ET.Element("object")
    sub(obj, "Category", cian_cat)
    sub(obj, "ExternalId", ad["id"])
    sub(obj, "Description", ad["description"])
    sub(obj, "Address", ad["address"])
    build_phones(obj)
    sub(obj, "TotalArea", fields.get("Square"))
    sub(obj, "FloorNumber", fields.get("Floor"))
    build_photos(obj, ad.get("images", []))

    is_rent = cian_cat.endswith("Rent")
    is_flat = cian_cat.startswith("flat")

    if is_flat:
        sub(obj, "FlatRoomsCount", fields.get("Rooms"))
        sub(obj, "LivingArea", fields.get("LivingSpace"))
        sub(obj, "KitchenArea", fields.get("KitchenSpace"))
        room_type = EMAPS["RoomType_to_CIAN"].get(fields.get("RoomType"))
        sub(obj, "RoomType", room_type)
        sub(obj, "RepairType", EMAPS["Renovation_to_RepairType"].get(fields.get("Renovation")))
        wv = EMAPS["ViewFromWindows_to_WindowsViewType"].get(fields.get("ViewFromWindows"))
        sub(obj, "WindowsViewType", wv)
        if fields.get("BathroomMulti") == "Раздельный":
            sub(obj, "SeparateWcsCount", 1)
        elif fields.get("BathroomMulti") == "Совмещённый":
            sub(obj, "CombinedWcsCount", 1)
        build_flat_building(obj, fields)
        build_bargain_terms_sale(obj, ad, fields)
    else:
        sub(obj, "ConditionType", EMAPS["Decoration_to_ConditionType"].get(fields.get("Decoration")))
        build_commercial_building(obj, fields)
        if is_rent:
            build_bargain_terms_rent(obj, ad, avito_cfg, fields)
        else:
            build_bargain_terms_sale(obj, ad, fields)

    return obj


def main():
    errors = []
    feed = ET.Element("feed")
    sub(feed, "feed_version", "2")
    files = sorted(glob.glob(f"{BASE}/ads/*.json"))
    count = 0
    for path in files:
        with open(path, encoding="utf-8") as f:
            ad = json.load(f)
        obj = build_object(ad, errors)
        if obj is not None:
            feed.append(obj)
            count += 1

    if errors:
        print("ПРЕДУПРЕЖДЕНИЯ (ЦИАН):", file=sys.stderr)
        for e in errors:
            print(" -", e, file=sys.stderr)

    rough = ET.tostring(feed, encoding="unicode")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ")
    pretty = "\n".join(line for line in pretty.split("\n") if line.strip())

    with open(f"{BASE}/cian_feed.xml", "w", encoding="utf-8") as f:
        f.write(pretty)

    print(f"OK: собрано объявлений для ЦИАН {count} -> cian_feed.xml")


if __name__ == "__main__":
    main()
