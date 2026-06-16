import argparse
import csv
from pathlib import Path
import xml.etree.ElementTree as ET


def strip_namespace(name: str) -> str:
    """Return local XML name when ElementTree includes namespace URI."""
    return name.rsplit("}", 1)[-1] if "}" in name else name


def element_rows(element: ET.Element, path: str = ""):
    tag = strip_namespace(element.tag)
    current_path = f"{path}/{tag}" if path else tag
    text = (element.text or "").strip()

    row = {
        "path": current_path,
        "tag": tag,
        "text": text,
    }

    for key, value in element.attrib.items():
        row[f"attr_{strip_namespace(key)}"] = value

    yield row

    for child in element:
        yield from element_rows(child, current_path)


def _find_child(parent: ET.Element, name: str) -> ET.Element | None:
    """First direct child whose Name attribute matches name."""
    for child in parent:
        if child.attrib.get("Name") == name:
            return child
    return None


def _data_string(member: ET.Element | None) -> str:
    """Read CDATA STRING value from a member's DATA DataValueMember."""
    if member is None:
        return ""
    data = _find_child(member, "DATA")
    if data is None or data.text is None:
        return ""
    text = data.text.strip()
    if text.startswith("'") and text.endswith("'"):
        text = text[1:-1]
    return text


def parameter_rows(root: ET.Element, prefix: str):
    """Yield a row dict per StructureMember whose DataType starts with prefix.

    Shared by Settings (ORT_SettingParam_*) and Recipes (ORT_RecipeParam).
    """
    for member in root.iter():
        if strip_namespace(member.tag) != "StructureMember":
            continue
        data_type = member.attrib.get("DataType", "")
        if not data_type.startswith(prefix):
            continue

        parameter = member.attrib.get("Name", "")
        description = _data_string(_find_child(member, "Desc"))

        min_member = _find_child(member, "Min")
        max_member = _find_child(member, "Max")
        min_value = min_member.attrib.get("Value", "") if min_member is not None else "n/a"
        max_value = max_member.attrib.get("Value", "") if max_member is not None else "n/a"

        yield {
            "Parameter": parameter,
            "Description": description,
            "Unit": data_type,
            "Min": min_value,
            "Max": max_value,
        }


def setting_rows(root: ET.Element):
    """Yield one row dict per ORT_SettingParam_* setting in the Settings tag."""
    yield from parameter_rows(root, "ORT_SettingParam_")


def recipe_rows(root: ET.Element):
    """Yield one row dict per ORT_RecipeParam in the Machine_Run_Recipe tag."""
    yield from parameter_rows(root, "ORT_RecipeParam")


def export_settings_to_csv(xml_path: Path, output_path: Path | None = None) -> Path:
    tree = ET.parse(xml_path)
    rows = list(setting_rows(tree.getroot()))

    output_dir = xml_path.parent / "csv"
    output_dir.mkdir(exist_ok=True)
    csv_path = output_path or output_dir / "sd_settings.csv"

    fieldnames = ["Parameter", "Description", "Unit", "Min", "Max"]
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return csv_path


def convert_xml_to_csv(xml_path: Path, output_path: Path | None = None) -> Path:
    tree = ET.parse(xml_path)
    rows = list(element_rows(tree.getroot()))

    output_dir = xml_path.parent / "csv"
    output_dir.mkdir(exist_ok=True)
    csv_path = output_path or output_dir / f"{xml_path.stem}.csv"

    fieldnames = sorted({key for row in rows for key in row})
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert XML elements to CSV rows.")
    parser.add_argument("xml_file", type=Path, help="XML file to convert")
    parser.add_argument("-o", "--output", type=Path, help="Optional CSV output path")
    parser.add_argument(
        "-s",
        "--settings",
        action="store_true",
        help="Export ORT_SettingParam_* settings (Parameter, Description, Unit, Min, Max)",
    )
    args = parser.parse_args()

    if not args.xml_file.is_file():
        raise FileNotFoundError(f"XML file not found: {args.xml_file}")

    if args.settings:
        csv_path = export_settings_to_csv(args.xml_file, args.output)
    else:
        csv_path = convert_xml_to_csv(args.xml_file, args.output)
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()