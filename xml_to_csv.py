import argparse
import csv
import re
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


FAULT_FIELDS = ["Fault", "Scope", "DataType", "Alarm Class", "Severity", "Message"]


def _first_descendant(root: ET.Element, name: str) -> ET.Element | None:
    """First element (any depth) whose local tag matches name."""
    for el in root.iter():
        if strip_namespace(el.tag) == name:
            return el
    return None


# FactoryTalk alarm placeholders, e.g. "/*S:0 %Tag1*/" or
# "/*N:5 %Tag1 NOFILL DP:0*/", where %Tag1 maps to AssocTag1.
_TAG_PLACEHOLDER = re.compile(r"/\*[^*]*?%Tag(\d+)[^*]*?\*/")


def _assoc_tags(root: ET.Element) -> dict[str, str]:
    """Map AssocTagN index -> reference string.

    AssocTagN attributes live on the alarm parameter element, which is
    AlarmDigitalParameters for ALARM_DIGITAL and AlarmAnalogParameters for
    ALARM_ANALOG, so scan every element to cover both.
    """
    out: dict[str, str] = {}
    for el in root.iter():
        for key, value in el.attrib.items():
            match = re.fullmatch(r"AssocTag(\d+)", strip_namespace(key))
            if match:
                out[match.group(1)] = value
    return out


def tag_description(name: str, search_dirs) -> str:
    """Return the <Description> CDATA of tag `name` from the first dir holding it."""
    name = (name or "").strip()
    if not name:
        return ""
    for directory in search_dirs:
        path = Path(directory) / f"{name}.xml"
        if path.is_file():
            try:
                root = ET.parse(path).getroot()
            except ET.ParseError:
                return ""
            desc = _first_descendant(root, "Description")
            return (desc.text or "").strip() if desc is not None else ""
    return ""


def _resolve_message(text: str, assoc: dict[str, str], resolve_desc) -> str:
    """Replace FactoryTalk %TagN placeholders with their associated tag + desc.

    "Vac Failure on /*S:0 %Tag1*/" -> "Vac Failure on actCanInsertVac.Desc
    (Can Insert Vacuum)". The reference comes from AssocTagN; resolve_desc
    supplies the tag's description. Placeholders with no association are left
    untouched; a found reference without a description shows just the reference.
    """
    if not text or resolve_desc is None:
        return text

    def repl(match: re.Match) -> str:
        num = match.group(1)
        token = match.group(0)
        ref = assoc.get(num)
        if not ref:
            return token
        desc = resolve_desc(ref)
        return f"{ref} ({desc})" if desc else ref

    return _TAG_PLACEHOLDER.sub(repl, text)


def fault_severity(root: ET.Element) -> int | None:
    """Return the alarm Severity code for a fault Tag root, or None.

    The Severity attribute lives on the alarm parameter element
    (AlarmDigitalParameters for ALARM_DIGITAL). ALARM_ANALOG tags carry no
    single Severity, but per-level severities (HHSeverity, HSeverity, ...); for
    those the highest severity wins so the fault is classified by its most
    serious level. Returns None when no severity attribute is present.
    """
    severities: list[int] = []
    for el in root.iter():
        if strip_namespace(el.tag) not in ("AlarmDigitalParameters", "AlarmAnalogParameters"):
            continue
        for key, value in el.attrib.items():
            if strip_namespace(key).endswith("Severity"):
                try:
                    severities.append(int(value))
                except (TypeError, ValueError):
                    continue
    return max(severities) if severities else None


def fault_row(root: ET.Element, resolve_desc=None, scope: str = "") -> dict | None:
    """Return a fault dict for an alarm Tag root, or None if not an alarm tag.

    Pulls the tag Name + DataType from the root, AlarmClass and the first
    Message text from the AlarmConfig block. Tags without an AlarmConfig
    (e.g. STRING/INT helpers that merely have "fault" in their name) are
    skipped by returning None.

    The returned dict also carries a "Severity" key (the alarm severity code)
    used to classify the fault; it is not part of FAULT_FIELDS so it is dropped
    from the exported table columns.

    When resolve_desc is given, FactoryTalk %TagN placeholders in the message
    are expanded with the referenced tag's description for readability.
    """
    if strip_namespace(root.tag) != "Tag":
        return None
    if _first_descendant(root, "AlarmConfig") is None:
        return None

    message = ""
    message_el = _first_descendant(root, "Message")
    if message_el is not None:
        text_el = _first_descendant(message_el, "Text")
        if text_el is not None and text_el.text:
            message = text_el.text.strip()

    message = _resolve_message(message, _assoc_tags(root), resolve_desc)

    alarm_class_el = _first_descendant(root, "AlarmClass")
    alarm_class = (alarm_class_el.text or "").strip() if alarm_class_el is not None else ""

    return {
        "Fault": root.attrib.get("Name", ""),
        "Scope": scope,
        "DataType": root.attrib.get("DataType", ""),
        "Alarm Class": alarm_class,
        "Message": message,
        "Severity": fault_severity(root),
    }


ALARM_FIELDS = ["Parameter", "Description"]


def alarm_rows(root: ET.Element):
    """Yield one row per Comment in the Alarms tag.

    Operand "[n].m" becomes Parameter "Alarm[n].m"; the CDATA text is the
    Description.
    """
    for comment in root.iter():
        if strip_namespace(comment.tag) != "Comment":
            continue
        operand = comment.attrib.get("Operand", "").strip()
        if not operand:
            continue
        yield {
            "Parameter": f"Alarm{operand}",
            "Description": (comment.text or "").strip(),
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