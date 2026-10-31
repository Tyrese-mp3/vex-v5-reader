#!/usr/bin/env python3
"""Turn VEX V5 robot code into plain text. Read-only: input files are never changed.

Usage:
  vex_read.py FILE [FILE ...]   Decode .v5cpp, .v5blocks or .v5python project files.
  vex_read.py FOLDER            Summarize a PROS or VS Code VEX project.
  vex_read.py FILE --summary    Show only the project info, devices and checks.
  vex_read.py FILE --full       Always show the generated robot-config code.
  vex_read.py OLD --diff NEW    Show what changed between two versions of a project.
"""

import argparse
import collections
import difflib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

CARTRIDGES = {
    "ratio36_1": "red 36:1, 100 rpm",
    "ratio18_1": "green 18:1, 200 rpm",
    "ratio6_1": "blue 6:1, 600 rpm",
}
THREE_WIRE = {
    "accelerometer", "analog_in", "bumper", "digital_in", "digital_out", "encoder",
    "led", "light", "limit", "line", "motor29", "motor_victor", "pneumatics", "pot",
    "potV2", "pwm_out", "servo", "sonar",
}
SMART = {
    "aivision", "controller", "distance", "drivetrain", "electromagnet", "gps", "inertial",
    "motor", "motor_group", "optical", "rotation", "smartdrive", "triport", "vision",
}
BRAIN_TRIPORT = 22  # The "port" VEXcode records for the brain's own A-H ports.

COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
GENERATED_END = re.compile(r"#\s*(?:pragma\s+)?endregion\s+VEXcode Generated Robot Configuration")
READS_CONTROLLER = re.compile(r"Controller\d\.(?:Axis|Button)|controller_\d\.(?:axis|button)")
VEX_DEVICE = re.compile(
    r"^[ \t]*(?:vex::)?(%s)[ \t]+(\w+)[ \t]*(?:=[ \t]*(?:vex::)?\w+[ \t]*)?\(([^;{]*)\)[ \t]*;"
    % "|".join(sorted(THREE_WIRE | SMART, key=len, reverse=True)),
    re.M,
)
PROS_DEVICE = re.compile(
    r"^[ \t]*(?:(?:inline|static|const|extern)[ \t]+)*"
    r"((?:pros::)?(?:v5::)?(?:adi::)?(?:MotorGroup|Motor_Group|Motor|Controller|Imu|IMU|Rotation|"
    r"Distance|Optical|Vision|Gps|GPS|AIVision|ADI\w+|DigitalOut|DigitalIn|AnalogIn|AnalogOut|"
    r"Encoder|Ultrasonic|Led|Pneumatics))"
    r"[ \t]+(\w+)[ \t]*(?:=[ \t]*[\w:]+[ \t]*)?[({]([^;]*?)[)}][ \t]*;",
    re.M,
)
VEX_ENTRY = re.compile(r"(\w+\.(?:autonomous|drivercontrol)[ \t]*\([ \t]*\w+[ \t]*\)|\bint[ \t]+main[ \t]*\()")
PROS_ENTRY = re.compile(
    r"^[ \t]*void[ \t]+(initialize|disabled|competition_initialize|autonomous|opcontrol)[ \t]*\([^)]*\)\s*\{",
    re.M,
)
BLOCK_HAT = re.compile(r"(?:^|_)when(?:_|$)|^procedures_definition$")

SOURCE_EXTENSIONS = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp")
PROS_VENDOR_DIRS = ("include/pros/", "include/liblvgl/", "include/okapi/", "include/display/")
SKIP_WHEN_SEARCHING = {".git", ".d", "bin", "build", "firmware", "node_modules", "include", "src"}


class ReadError(Exception):
    """A problem worth showing the reader as a plain message, not a traceback."""


def read_text(path):
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        return fh.read()


def load_project(path):
    raw = read_text(path)
    try:
        data = json.loads(raw)
    except ValueError:
        raise ReadError(f"{path} is not a VEXcode project file: expected JSON, found {raw[:40]!r}")
    if not isinstance(data, dict) or not ("textContent" in data or "workspace" in data):
        keys = ", ".join(sorted(data)) if isinstance(data, dict) else type(data).__name__
        raise ReadError(f"{path} is JSON but has no code in a known place. Top-level keys: {keys}")
    return data


def print_table(headers, rows):
    rows = [[str(cell) for cell in row] for row in rows]
    widths = [max(len(row[i]) for row in [headers] + rows) for i in range(len(headers))]
    for row in [headers] + rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())


def print_checks(checks):
    print("\n## Checks")
    for check in checks or ["No port conflicts found."]:
        print(f"- {check}")


def blank_comments(code):
    """Remove comments but keep every newline, so line numbers still match the original."""
    return COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), code)


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def device_row(dev):
    return [dev["name"], dev["kind"], ", ".join(dev["where"]) or "-", dev["notes"]]


def print_devices(title, devices):
    print(f"\n## {title}")
    if not devices:
        print("None found.")
        return
    has_lines = "line" in devices[0]
    headers = ["name", "type", "port", "notes"] + (["line"] if has_lines else [])
    print_table(headers, [device_row(d) + ([d["line"]] if has_lines else []) for d in devices])


def port_conflicts(devices):
    users = collections.defaultdict(list)
    for dev in devices:
        for port in dev["where"]:
            users[port].append(dev["name"])
    return [
        f"{port} is used by more than one device: {', '.join(names)}"
        for port, names in sorted(users.items())
        if len(set(names)) > 1
    ]


def config_devices(data):
    """Read the device list VEXcode shows in its Devices panel."""
    devices = []
    for dev in data.get("robotConfig") or data.get("rconfig") or []:
        kind = dev.get("deviceClass", "?")
        ports = dev.get("port") or []
        if kind in THREE_WIRE:
            source = dev.get("triportSourcePort")
            suffix = "" if source in (None, BRAIN_TRIPORT) else f" (expander on PORT{source})"
            where = [f"3-wire {chr(ord('A') + int(p) - 1)}{suffix}" for p in ports]
        else:
            where = [f"PORT{p}" for p in ports]
        devices.append({"name": dev.get("name", "?"), "kind": kind, "where": where, "notes": config_notes(kind, dev)})
    return devices


def config_notes(kind, dev):
    setting = dev.get("setting") or {}
    notes = []
    if setting.get("gear"):
        notes.append(CARTRIDGES.get(setting["gear"], setting["gear"]))
    if setting.get("reversed") == "true":
        notes.append("reversed")
    flipped = [m.group(1) for m in (re.fullmatch(r"motor_([a-z])_reversed", k) for k in setting)
               if m and setting[m.group(0)] == "true"]
    if flipped:
        notes.append("reversed motor " + ", ".join(flipped))
    if kind in ("smartdrive", "drivetrain"):
        notes += [setting[key] for key in ("type", "wheelSize") if setting.get(key)]
        if setting.get("gearRatio"):
            notes.append(f"gear ratio {setting['gearRatio']}")
        if setting.get("gyroType"):
            notes.append(f"gyro: {setting['gyroType']}")
    return ", ".join(notes)


def parse_vex_devices(clean_code):
    """Find VEX C++ device declarations. Expects comments to be blanked already."""
    devices = []
    for match in VEX_DEVICE.finditer(clean_code):
        kind, name, args = match.group(1), match.group(2), " ".join(match.group(3).split())
        where = [f"PORT{n}" for n in re.findall(r"\bPORT(\d+)\b", args)]
        for source, letter in re.findall(r"\b(\w+)(?:\.ThreeWirePort)?\.([A-H])\b", args):
            where.append(f"3-wire {letter}" if source == "Brain" else f"3-wire {letter} (expander {source})")
        notes = [CARTRIDGES[g] for g in re.findall(r"ratio\d+_1", args) if g in CARTRIDGES]
        if kind == "motor" and re.search(r"\btrue\s*$", args):
            notes.append("reversed")
        if kind in ("motor_group", "smartdrive", "drivetrain"):
            notes.append(args)
        devices.append({"name": name, "kind": kind, "where": where, "notes": ", ".join(notes),
                        "line": line_of(clean_code, match.start())})
    return devices


def parse_pros_devices(clean_code):
    """Find PROS device declarations. A negative smart port means the motor is reversed."""
    devices = []
    for match in PROS_DEVICE.finditer(clean_code):
        kind, name, args = match.group(1), match.group(2), " ".join(match.group(3).split())
        letters = re.findall(r"'([A-Ha-h])'", args)
        listed = re.search(r"\{([^{}]*)\}", args)
        numbers = re.findall(r"-?\b\d+\b", listed.group(1) if listed else args.split(",")[0])
        where, notes = [f"3-wire {letter.upper()}" for letter in letters], []
        if not letters and "Controller" not in kind:
            where = [f"PORT{abs(int(n))}" for n in numbers]
            reversed_ports = [f"PORT{abs(int(n))}" for n in numbers if int(n) < 0]
            if reversed_ports:
                notes.append("reversed: " + ", ".join(reversed_ports))
        devices.append({"name": name, "kind": kind, "where": where, "notes": ", ".join(notes),
                        "line": line_of(clean_code, match.start())})
    return devices


def config_mismatches(code_devices, config):
    """Compare the ports in the code with the ports in VEXcode's Devices panel."""
    wanted = lambda devices: {p for d in devices for p in d["where"] if "expander" not in p}
    in_code, in_config = wanted(code_devices), wanted(config)
    checks = []
    if in_code - in_config:
        checks.append("In the code but not in VEXcode's Devices panel: " + ", ".join(sorted(in_code - in_config)))
    if in_config - in_code:
        checks.append("In VEXcode's Devices panel but not in the code: " + ", ".join(sorted(in_config - in_code)))
    return checks


def kids(element, tag):
    """Direct children by tag name. Blockly files use more than one XML namespace."""
    return [child for child in element if child.tag.rsplit("}", 1)[-1] == tag]


def first(element, tag):
    found = kids(element, tag)
    return found[0] if found else None


def json_list(text):
    try:
        value = json.loads(text or "[]")
    except ValueError:
        return []
    return value if isinstance(value, list) else []


def fill_proccode(code, args):
    """Turn a My Block signature like 'Drive %n fast' into 'Drive 24 fast'."""
    remaining = iter(args)
    return re.sub(r"%[a-z]", lambda m: str(next(remaining, "?")), code)


def call_text(block):
    mutation = first(block, "mutation")
    if mutation is None:
        return block.get("type", "?")
    values = {v.get("name"): render_input(v) for v in kids(block, "value")}
    args = [values.get(arg_id, "?") for arg_id in json_list(mutation.get("argumentids"))]
    return fill_proccode(mutation.get("proccode", "?"), args)


def definition_text(block):
    prototype = first(block, "statement")
    mutations = [] if prototype is None else [n for n in prototype.iter() if n.get("proccode")]
    if not mutations:
        return "?"
    names = [f"[{name}]" for name in json_list(mutations[0].get("argumentnames"))]
    return fill_proccode(mutations[0].get("proccode", "?"), names)


def render_input(value):
    # A value keeps its default shadow even when a real block is plugged in over it.
    inner = first(value, "block")
    if inner is None:
        inner = first(value, "shadow")
    return "(empty)" if inner is None else render_expression(inner)


def render_expression(block):
    kind = block.get("type", "?")
    fields, values = kids(block, "field"), kids(block, "value")
    if len(fields) == 1 and not values:
        text = fields[0].text or ""
        return f'"{text}"' if kind == "text" else text
    if kind == "procedures_call":
        return call_text(block)
    return f"{kind}({', '.join(block_args(block))})"


def block_args(block):
    args = [f"{field.get('name')}={field.text or ''}" for field in kids(block, "field")]
    return args + [f"{value.get('name')}={render_input(value)}" for value in kids(block, "value")]


def block_line(block):
    kind = block.get("type", "?")
    if kind == "procedures_definition":
        return f"define {definition_text(block)}"
    if kind == "procedures_call":
        return f"call {call_text(block)}"
    if kind.endswith("_comment") and first(block, "value") is not None:
        return f"# {render_input(first(block, 'value'))}"
    return " ".join([kind] + block_args(block))


def render_stack(block, depth, lines):
    pad = "  " * depth
    while block is not None:
        disabled = " [DISABLED]" if block.get("disabled") == "true" else ""
        lines.append(f"{pad}{block_line(block)}{disabled}")
        note = first(block, "comment")
        if note is not None and note.text:
            lines.append(f"{pad}  # {note.text}")
        # A My Block's only statement holds its signature, which block_line already printed.
        statements = [] if block.get("type") == "procedures_definition" else kids(block, "statement")
        labeled = len(statements) > 1
        for statement in statements:
            if labeled:
                lines.append(f"{pad}  [{statement.get('name')}]")
            inner = first(statement, "block")
            if inner is not None:
                render_stack(inner, depth + (2 if labeled else 1), lines)
        after = first(block, "next")
        block = None if after is None else first(after, "block")


def render_workspace(xml_text):
    """Return (variable names, program lines). Positions and ids are left out on purpose."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ReadError(f"the blocks in this project could not be parsed: {exc}")
    holder = first(root, "variables")
    variables = [] if holder is None else [v.text or "?" for v in kids(holder, "variable")]
    lines = []
    for number, top in enumerate(kids(root, "block"), 1):
        attached = BLOCK_HAT.search(top.get("type", ""))
        lines.append(f"Stack {number}" if attached else
                     f"Stack {number} (no event block on top, so it will not run)")
        render_stack(top, 1, lines)
        lines.append("")
    for note in kids(root, "comment"):
        lines.append(f"# {note.text or ''}")
    return variables, lines


def project_header(path, data):
    print(f"# {os.path.basename(path)}")
    kind = "Blocks" if data.get("workspace") else f"Text ({data.get('textLanguage', '?')})"
    facts = [f"Type: {kind}", f"Platform: {data.get('platform', '?')}"]
    if isinstance(data.get("slot"), int):
        # Stored counting from 0, but VEXcode shows slots 1-8.
        facts.append(f"Slot: {data['slot'] + 1}")
    facts += [f"VEXcode {data.get('appVersion', '?')}", f"SDK {data.get('sdkVersion', '?')}",
              f"File format {data.get('fileFormat', '?')}"]
    print(" | ".join(facts))


def show_blocks(data, summary):
    devices = config_devices(data)
    print_devices("Devices", devices)
    print_checks(port_conflicts(devices))
    variables, lines = render_workspace(data["workspace"])
    if summary:
        return
    print("\n## Variables and broadcasts")
    print(", ".join(variables) or "None")
    print("\n## Program\n")
    print("\n".join(lines).rstrip())


def show_text(data, show_generated, summary):
    code = data.get("textContent") or ""
    lines = code.split("\n")
    end = next((i + 1 for i, line in enumerate(lines) if GENERATED_END.search(line)), 0)
    has_controls = bool(READS_CONTROLLER.search(blank_comments("\n".join(lines[:end]))))

    config = config_devices(data)
    code_devices = parse_vex_devices(blank_comments(code))
    print_devices("Devices (from the code)" if code_devices else "Devices", code_devices or config)

    checks = port_conflicts(code_devices or config)
    if code_devices:
        checks += config_mismatches(code_devices, config)
    if has_controls:
        checks.append(f"The generated section (lines 1-{end}) contains real driver controls, "
                      "so it is shown below instead of hidden.")
    print_checks(checks)
    if summary:
        return

    start = 0 if show_generated or has_controls else end
    print("\n## Code (line numbers match VEXcode)")
    if start:
        print(f"Lines 1-{start} are generated setup with no driver controls. Add --full to see them.")
    print()
    width = len(str(len(lines)))
    for number, line in enumerate(lines[start:], start + 1):
        print(f"{number:>{width}} | {line}")


def show_project(path, show_generated, summary):
    data = load_project(path)
    project_header(path, data)
    if data.get("workspace"):
        show_blocks(data, summary)
    if data.get("textContent") or not data.get("workspace"):
        show_text(data, show_generated, summary)


def comparable_lines(path):
    data = load_project(path)
    lines = [f"device: {' | '.join(device_row(d))}" for d in config_devices(data)]
    if data.get("workspace"):
        lines += render_workspace(data["workspace"])[1]
    return lines + (data.get("textContent") or "").split("\n")


def show_diff(old, new):
    diff = list(difflib.unified_diff(comparable_lines(old), comparable_lines(new),
                                     os.path.basename(old), os.path.basename(new), lineterm=""))
    print("\n".join(diff) if diff else "No differences in the code, blocks or devices.")


def source_files(root, skip=frozenset(), vendor_dirs=()):
    """List code under src/ and include/, leaving out library files."""
    found, other = [], []
    for top in ("src", "include"):
        for folder, _, names in os.walk(os.path.join(root, top)):
            for name in sorted(names):
                relative = os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/")
                if relative in skip or relative.startswith(vendor_dirs):
                    continue
                (found if name.lower().endswith(SOURCE_EXTENSIONS) else other).append(relative)
    return found, other


def summarize_sources(root, files, other, parse_devices, entry_pattern):
    print("\n## Your source files")
    if not files:
        print("None found. This project has no code in src/ or include/.")
    sizes, devices, entries = [], [], []
    for relative in files:
        text = read_text(os.path.join(root, relative))
        sizes.append([relative, text.count("\n") + 1])
        clean = blank_comments(text)
        for dev in parse_devices(clean):
            dev["line"] = f"{relative}:{dev['line']}"
            devices.append(dev)
        for match in entry_pattern.finditer(clean):
            entries.append([match.group(1), f"{relative}:{line_of(clean, match.start())}"])
    if sizes:
        print_table(["file", "lines"], sizes)
    if other:
        print("Other files here are not compiled: " + ", ".join(other))
    print_devices("Devices (from the code)", devices)
    print("\n## Where the program starts")
    if entries:
        print_table(["entry point", "location"], entries)
    else:
        print("None found.")
    print_checks(port_conflicts(devices))


def show_pros(root):
    project = json.loads(read_text(os.path.join(root, "project.pros")))
    state = project.get("py/state", project)
    templates = state.get("templates") or {}
    system_files = set()
    for template in templates.values():
        system_files.update(template.get("system_files") or [])
    print(f"# {state.get('project_name') or os.path.basename(root)}")
    libraries = ", ".join(f"{name} {t.get('version', '?')}" for name, t in templates.items())
    print(f"Type: PROS project | Target: {state.get('target', '?')} | Libraries: {libraries or 'none'}")
    files, other = source_files(root, system_files, PROS_VENDOR_DIRS)
    summarize_sources(root, files, other, parse_pros_devices, PROS_ENTRY)


def show_vscode(root, settings_path):
    project = json.loads(read_text(settings_path)).get("project", {})
    print(f"# {project.get('name') or os.path.basename(root)}")
    print(f"Type: VS Code VEX project | Platform: {project.get('platform', '?')} | "
          f"Language: {project.get('language', '?')} | Slot: {project.get('slot', '?')} | "
          f"SDK {project.get('sdkVersion', '?')}")
    files, other = source_files(root)
    summarize_sources(root, files, other, parse_vex_devices, VEX_ENTRY)


def find_projects(root, max_depth=4):
    found = []
    for folder, dirs, names in os.walk(root):
        depth = os.path.relpath(folder, root).count(os.sep)
        dirs[:] = [] if depth >= max_depth else [d for d in dirs if d not in SKIP_WHEN_SEARCHING]
        if "project.pros" in names or os.path.isfile(os.path.join(folder, ".vscode", "vex_project_settings.json")):
            found.append(folder)
    return found


def show_folder(root):
    settings = os.path.join(root, ".vscode", "vex_project_settings.json")
    if os.path.isfile(os.path.join(root, "project.pros")):
        show_pros(root)
    elif os.path.isfile(settings):
        show_vscode(root, settings)
    else:
        nested = find_projects(root)
        hint = "Projects inside it: " + "; ".join(nested) if nested else "Pass a project file instead."
        raise ReadError(f"{root} is not a PROS or VS Code VEX project. {hint}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="project files or a project folder")
    parser.add_argument("--summary", action="store_true", help="show project info, devices and checks only")
    parser.add_argument("--full", action="store_true", help="always show the generated robot-config code")
    parser.add_argument("--diff", metavar="NEW", help="compare the one given file against this newer version")
    args = parser.parse_args()
    if args.diff and len(args.paths) != 1:
        parser.error("--diff compares exactly two files: vex_read.py OLD --diff NEW")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    status = 0
    for index, path in enumerate(args.paths):
        if index:
            print("\n" + "=" * 72 + "\n")
        try:
            if args.diff:
                show_diff(path, args.diff)
            elif os.path.isdir(path):
                show_folder(path)
            else:
                show_project(path, args.full, args.summary)
        except (ReadError, OSError) as exc:
            print(f"ERROR: {exc}")
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
