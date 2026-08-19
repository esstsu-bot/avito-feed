#!/usr/bin/env python3
"""Собирает feed.xml для автозагрузки Авито из ads/*.json + config/*.json"""
import json
import glob
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom

BASE = "/Users/sonia/avito-feed"

with open(f"{BASE}/config/common_fields.json", encoding="utf-8") as f:
    COMMON = json.load(f)

with open(f"{BASE}/config/categories.json", encoding="utf-8") as f:
    CATEGORIES = json.load(f)

FIELD_ORDER = [
    "Id", "ManagerName", "ContactPhone", "ContactMethod", "InternetCalls",
    "PropertyRights", "Description", "Category", "OperationType", "MarketType",
    "Address", "Price",
]


def build_ad(ad, errors):
    cat_key = ad["category"]
    if cat_key not in CATEGORIES:
        errors.append(f"{ad.get('id','?')}: неизвестная категория '{cat_key}'")
        return None
    cat_cfg = CATEGORIES[cat_key]

    values = {}
    values["Id"] = ad["id"]
    values["ManagerName"] = COMMON["ManagerName"]
    values["ContactPhone"] = COMMON["ContactPhone"]
    values["ContactMethod"] = COMMON["ContactMethod"]
    values["InternetCalls"] = COMMON["InternetCalls"]
    values["PropertyRights"] = COMMON["PropertyRights"]
    values["Description"] = ad["description"]
    values["Category"] = cat_cfg["Category"]
    values["OperationType"] = cat_cfg["OperationType"]
    if cat_cfg.get("MarketType"):
        values["MarketType"] = cat_cfg["MarketType"]
    values["Address"] = ad["address"]
    values["Price"] = str(ad["price"])

    # комиссия: только в аренде, где применимо; в продаже не ставим
    commission = cat_cfg.get("commission")
    if commission:
        if commission.get("presence_tag"):
            values[commission["presence_tag"]] = "Да"
        values[commission["size_tag"]] = str(COMMON["commission_rental_percent"])

    # категорийные поля из объявления
    fields = ad.get("fields", {})
    values.update(fields)

    # проверка обязательных полей
    for rf in cat_cfg["required_fields"]:
        if rf["tag"] not in values or not values[rf["tag"]]:
            errors.append(f"{ad['id']}: не хватает обязательного поля '{rf['label']}' ({rf['tag']})"
                           + (f", допустимые значения: {rf['values']}" if rf["values"] else ""))

    ad_el = ET.Element("Ad")
    ordered_tags = [t for t in FIELD_ORDER if t in values]
    ordered_tags += [t for t in values if t not in FIELD_ORDER and t != "Images"]

    for tag in ordered_tags:
        el = ET.SubElement(ad_el, tag)
        el.text = values[tag]
        # вставляем Images сразу после Description
        if tag == "Description":
            images_el = ET.SubElement(ad_el, "Images")
            for url in ad.get("images", []):
                ET.SubElement(images_el, "Image", url=url)

    return ad_el


def main():
    errors = []
    ads_root = ET.Element("Ads", formatVersion="3", target="Avito.ru")
    files = sorted(glob.glob(f"{BASE}/ads/*.json"))
    for path in files:
        with open(path, encoding="utf-8") as f:
            ad = json.load(f)
        ad_el = build_ad(ad, errors)
        if ad_el is not None:
            ads_root.append(ad_el)

    if errors:
        print("ПРЕДУПРЕЖДЕНИЯ (Avito может отклонить поля из этого списка — "
              "многие обязательны только для отдельных видов объекта):", file=sys.stderr)
        for e in errors:
            print(" -", e, file=sys.stderr)

    rough = ET.tostring(ads_root, encoding="unicode")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ")
    pretty = "\n".join(line for line in pretty.split("\n") if line.strip())

    with open(f"{BASE}/feed.xml", "w", encoding="utf-8") as f:
        f.write(pretty)

    print(f"OK: собрано объявлений {len(files)} -> feed.xml")


if __name__ == "__main__":
    main()
