#!/usr/bin/env python3
"""
RestedXP to TurtleGuide Converter

Converts RestedXP guide format to TurtleGuide format.
Usage: python3 convert_rxp.py input.lua [output_dir]
"""

import re
import sys
import os
from pathlib import Path


def strip_formatting(text):
    """Remove RXP color codes and texture tags"""
    if not text:
        return ""
    # Remove texture tags |Tpath:size|t
    text = re.sub(r'\|T[^|]+\|t', '', text)
    # Remove nested color codes iteratively until none remain
    for _ in range(6):
        new = re.sub(r'\|[cC]RXP_\w+_([^|]*)\|r', r'\1', text)
        new = re.sub(r'\|[cC][0-9a-fA-F]{8}([^|]*)\|r', r'\1', new)
        if new == text:
            break
        text = new
    # Strip unmatched openers/closers and malformed color codes
    text = re.sub(r'\|[cC]RXP_\w+_', '', text)
    text = re.sub(r'\|[cC]RXP\w*', '', text)  # malformed like |cRXPTyrant (missing underscore)
    text = re.sub(r'\|[cC][0-9a-fA-F]{8}', '', text)
    text = re.sub(r'\|[rR]', '', text)
    # Clean up whitespace
    text = text.strip()
    return text


# Vanilla-era zone ID -> name mapping (client map IDs used in RXP .goto)
ZONE_ID_TO_NAME = {
    1: "Dun Morogh",
    3: "Badlands",
    4: "Blasted Lands",
    8: "Swamp of Sorrows",
    10: "Duskwood",
    11: "Wetlands",
    12: "Elwynn Forest",
    14: "Durotar",
    15: "Dustwallow Marsh",
    16: "Azshara",
    17: "The Barrens",
    28: "Western Plaguelands",
    33: "Stranglethorn Vale",
    36: "Alterac Mountains",
    38: "Loch Modan",
    40: "Westfall",
    41: "Deadwind Pass",
    44: "Redridge Mountains",
    45: "Arathi Highlands",
    46: "Burning Steppes",
    47: "The Hinterlands",
    51: "Searing Gorge",
    85: "Tirisfal Glades",
    130: "Silverpine Forest",
    139: "Eastern Plaguelands",
    141: "Teldrassil",
    148: "Darkshore",
    215: "Mulgore",
    267: "Hillsbrad Foothills",
    331: "Ashenvale",
    357: "Feralas",
    361: "Felwood",
    400: "Thousand Needles",
    405: "Desolace",
    406: "Stonetalon Mountains",
    440: "Tanaris",
    490: "Un'Goro Crater",
    493: "Moonglade",
    618: "Winterspring",
    1377: "Silithus",
    1417: "Teldrassil",
    1429: "Elwynn Forest",
    1436: "Westfall",
    1437: "Loch Modan",
    1438: "Badlands",
    1441: "Azshara",
    1443: "Blasted Lands",
    1446: "Burning Steppes",
    1447: "Deadwind Pass",
    1448: "Duskwood",
    1449: "Redridge Mountains",
    1450: "Swamp of Sorrows",
    1451: "Tirisfal Glades",
    1453: "Silverpine Forest",
    1454: "Hillsbrad Foothills",
    1455: "Alterac Mountains",
    1456: "The Hinterlands",
    1457: "Western Plaguelands",
    1458: "Stranglethorn Vale",
    1459: "Arathi Highlands",
    1460: "Wetlands",
    1464: "Eastern Plaguelands",
    1474: "Dun Morogh",
    1476: "Searing Gorge",
    1477: "The Hinterlands",
    1478: "Stranglethorn Vale",
    1497: "Undercity",
    1519: "Stormwind City",
    1537: "Ironforge",
    1581: "The Deadmines",
    1637: "Orgrimmar",
    1638: "Thunder Bluff",
    1657: "Darnassus",
    1941: "Darkshore",
    1942: "Stonetalon Mountains",
    1943: "Desolace",
    1944: "Ashenvale",
    1945: "Thousand Needles",
    1946: "Feralas",
    1947: "Tanaris",
    1948: "Un'Goro Crater",
    1949: "Silithus",
    1951: "Azshara",
    1952: "Felwood",
    1953: "Winterspring",
    1955: "Dustwallow Marsh",
    1956: "Durotar",
    1957: "Mulgore",
    1958: "The Barrens",
    3524: "Teldrassil",
    3525: "Azuremyst Isle",
    3557: "The Exodar",
    3430: "Eversong Woods",
    3433: "Ghostlands",
}


CLASSES = {'Warrior', 'Paladin', 'Hunter', 'Rogue', 'Priest', 'Shaman', 'Mage', 'Warlock', 'Druid', 'Deathknight'}
RACES = {'Human', 'Dwarf', 'Gnome', 'NightElf', 'Orc', 'Troll', 'Tauren', 'Undead', 'BloodElf', 'Draenei', 'HighElf', 'Goblin'}
FACTIONS = {'Alliance', 'Horde'}
# Expansion tokens that mean a line is non-vanilla
NONCLASSIC_TAGS = {'tbc', 'wotlk', 'cata', 'mop', 'wod', 'legion', 'bfa', 'shadowlands', 'retail', 'dragonflight', 'tww', 'sod'}
# Classic-era tokens we can safely drop from filters without skipping
KEEP_TOKENS = {'classic', 'era', 'hc', 'hardcore', 'softcore'}


def filter_tokens(filter_str):
    """Parse a `<<` filter string into a list of (negated, token) tuples."""
    if not filter_str:
        return []
    tokens = []
    for raw in filter_str.split():
        raw = raw.strip()
        if not raw:
            continue
        negated = raw.startswith('!')
        if negated:
            raw = raw[1:]
        if not raw:
            continue
        tokens.append((negated, raw))
    return tokens


def filter_is_nonclassic(filter_str):
    """Return True if a filter string gates this content to a non-vanilla expansion/season.
    RXP convention: season 0 = classic era. Any season list that lacks 0 is SoD-only."""
    if not filter_str:
        return False
    low = filter_str.lower()
    m = re.search(r'\bseason\s+([0-9,\s]+)', low)
    if m:
        seasons = [int(x) for x in re.findall(r'\d+', m.group(1))]
        if seasons and 0 not in seasons:
            return True
    for neg, tok in filter_tokens(filter_str):
        if neg:
            continue
        if tok.lower() in NONCLASSIC_TAGS:
            return True
    return False


def filter_classes_races(filter_str):
    """Extract classes/races from a filter string as two strings suitable for |C| / |R| tags."""
    classes_inc, classes_exc = [], []
    races_inc, races_exc = [], []
    for neg, tok in filter_tokens(filter_str or ''):
        # Handle slash-combined like Orc/Troll
        parts = tok.split('/')
        for p in parts:
            if p in CLASSES:
                (classes_exc if neg else classes_inc).append(p)
            elif p in RACES:
                (races_exc if neg else races_inc).append(p)
    cls = None
    if classes_inc:
        cls = '/'.join(classes_inc)
    elif classes_exc:
        cls = '/'.join('!' + c for c in classes_exc)
    race = None
    if races_inc:
        race = '/'.join(races_inc)
    elif races_exc:
        race = '/'.join('!' + r for r in races_exc)
    return cls, race


def split_line_filter(line):
    """Split a line on trailing `<<` filter. Returns (body, filter_str_or_None)."""
    m = re.search(r'<<\s*(.+?)\s*$', line)
    if m:
        return line[:m.start()].rstrip(), m.group(1).strip()
    return line.rstrip(), None


def parse_coords(line):
    """Parse coordinates from .goto Zone,x,y format. Translates numeric zone IDs."""
    match = re.search(r'\.goto\s+([^,]+),\s*([-0-9.]+)\s*,\s*([-0-9.]+)', line)
    if not match:
        return None, None, None
    zone_raw = match.group(1).strip()
    try:
        x = float(match.group(2))
        y = float(match.group(3))
    except ValueError:
        return None, None, None
    if zone_raw.isdigit():
        zone = ZONE_ID_TO_NAME.get(int(zone_raw))
        if not zone:
            return None, None, None
    else:
        zone = zone_raw
    return zone, x, y


def parse_quest_action(line):
    """Parse quest ID and name from .accept/.turnin lines"""
    match = re.search(r'\.(accept|turnin)\s+(\d+)[^>]*>>\s*(.+)', line)
    if match:
        action_type = match.group(1)
        qid = int(match.group(2))
        quest_name = match.group(3)
        # Clean up quest name
        quest_name = re.sub(r'^(Accept|Turn in)\s+', '', quest_name, flags=re.IGNORECASE)
        quest_name = strip_formatting(quest_name)
        return action_type, qid, quest_name
    return None, None, None


def parse_complete(line):
    """Parse .complete lines"""
    match = re.search(r'\.complete\s+(\d+),(\d+)\s*(?:--(.+))?', line)
    if match:
        qid = int(match.group(1))
        obj_idx = int(match.group(2))
        comment = strip_formatting(match.group(3)) if match.group(3) else None
        return qid, obj_idx, comment
    return None, None, None


def parse_step(step_lines, step_filter, current_zone):
    """Parse a single step block. step_filter is the `<<` filter from the `step` line (or None)."""
    # If step filter itself is non-classic, skip entire step
    if filter_is_nonclassic(step_filter):
        return None

    # Scan for a step-level #season directive. In RXP conventions, season 0 is
    # classic era. Any season directive that omits 0 is SoD-phase-specific.
    for raw in step_lines:
        s = raw.strip()
        m = re.match(r'#season\s+([0-9,\s]+)', s)
        if m:
            seasons = [int(x) for x in re.findall(r'\d+', m.group(1))]
            if seasons and 0 not in seasons:
                return None
            break
        # Also respect era directives per-step
        if s.startswith('#tbc') or s.startswith('#wotlk') or s.startswith('#cata') \
                or s.startswith('#mop') or s.startswith('#retail') or s.startswith('#sod'):
            return None

    step_cls, step_race = filter_classes_races(step_filter)

    # Detect mode directives (#hardcore / #softcore and their *server variants)
    step_mode = None
    for raw in step_lines:
        s = raw.strip()
        if s == '#hardcore' or s == '#hardcoreserver':
            step_mode = 'hardcore'
            break
        if s == '#softcore' or s == '#softcoreserver':
            step_mode = 'speedrun'
            break

    result = {
        'action': None,
        'quest': None,
        'qid': None,
        'note': None,
        'coords': [],
        'zone': current_zone,
        'class': step_cls,
        'race': step_race,
        'mode': step_mode,
        'optional': False,
    }

    notes = []
    target_npc = None
    mob_name = None
    use_item = None

    def line_filter_conflicts_with_step(line_filter):
        """True if a per-line class/race filter gates content more specifically than the step's filter.
        When true, the line belongs to a class/race subset and shouldn't be merged into a step-wide note."""
        if not line_filter:
            return False
        line_cls, line_race = filter_classes_races(line_filter)
        if line_cls and line_cls != step_cls:
            return True
        if line_race and line_race != step_race:
            return True
        return False

    for raw_line in step_lines:
        line = raw_line.strip()
        if not line or line.startswith('--'):
            continue

        # Handle per-line trailing `<< filter`
        body, line_filter = split_line_filter(line)
        if filter_is_nonclassic(line_filter):
            continue
        # Drop lines gated to a class/race subset of the step — they'd corrupt the merged note
        if line_filter_conflicts_with_step(line_filter):
            continue

        # Directives
        if body.startswith('#completewith') or body.startswith('#optional'):
            result['optional'] = True
            continue
        if body.startswith('#'):
            # Skip other directives (#label, #requires, #sticky, #loop, #season, #name, etc.)
            continue

        # Parse commands
        if body.startswith('.goto'):
            zone, x, y = parse_coords(body)
            if zone and x is not None and y is not None:
                result['zone'] = zone
                result['coords'].append(f"{x:.1f}, {y:.1f}")

        elif body.startswith('.accept'):
            result['action'] = 'A'
            _, qid, quest = parse_quest_action(body)
            result['qid'] = qid
            result['quest'] = quest

        elif body.startswith('.turnin'):
            result['action'] = 'T'
            _, qid, quest = parse_quest_action(body)
            result['qid'] = qid
            result['quest'] = quest

        elif body.startswith('.complete'):
            result['action'] = 'C'
            qid, obj_idx, comment = parse_complete(body)
            result['qid'] = qid
            if comment:
                notes.append(comment)

        elif body.startswith('.train') or body.startswith('.trainer'):
            result['action'] = 't'
            match = re.search(r'>>\s*(.+)', body)
            if match:
                result['quest'] = strip_formatting(match.group(1))

        elif body.startswith('.vendor'):
            match = re.search(r'>>(.+)', body)
            if match:
                notes.append(strip_formatting(match.group(1)))

        elif body.startswith('.target'):
            match = re.search(r'\.target\s+\+?(.+)', body)
            if match:
                target_npc = strip_formatting(match.group(1))

        elif body.startswith('.mob'):
            match = re.search(r'\.mob\s+(.+)', body)
            if match:
                mob_name = strip_formatting(match.group(1))

        elif body.startswith('.home'):
            result['action'] = 'h'
            result['quest'] = result['zone'] or 'Inn'

        elif body.startswith('.hs'):
            result['action'] = 'H'
            result['quest'] = 'Hearthstone'

        elif body.startswith('.fp'):
            result['action'] = 'f'
            match = re.search(r'\.fp\s+(.+)', body)
            if match:
                result['quest'] = strip_formatting(match.group(1))

        elif body.startswith('.fly'):
            result['action'] = 'F'
            match = re.search(r'\.fly\s+(.+)', body)
            if match:
                result['quest'] = strip_formatting(match.group(1))

        elif body.startswith('.zone'):
            result['action'] = 'R'
            match = re.search(r'>>(.+)', body)
            if match:
                result['quest'] = strip_formatting(match.group(1))

        elif body.startswith('.xp'):
            match = re.search(r'\.xp\s+(\d+)', body)
            xp_note = re.search(r'>>(.+)', body)
            if match:
                result['action'] = 'G'
                if xp_note:
                    result['quest'] = strip_formatting(xp_note.group(1))
                else:
                    result['quest'] = f"Grind to level {match.group(1)}"

        elif body.startswith('.deathskip'):
            result['action'] = 'D'
            result['quest'] = 'Die and respawn'

        elif body.startswith('.use'):
            result['action'] = 'U'
            match = re.search(r'>>(.+)', body)
            if match:
                result['quest'] = strip_formatting(match.group(1))
            item_match = re.search(r'\.use\s+(\d+)', body)
            if item_match:
                use_item = item_match.group(1)

        elif body.startswith('.equip'):
            # .equip <slot>,<itemId>  → Use/equip action
            m = re.match(r'\.equip\s+\d+\s*,\s*(\d+)(?:\s*>>\s*(.+))?', body)
            if m:
                result['action'] = 'U'
                result['quest'] = strip_formatting(m.group(2)) if m.group(2) else 'Equip item'
                use_item = m.group(1)

        elif body.startswith('.collect'):
            # .collect <itemId>,<count>  --optional comment
            m = re.match(r'\.collect\s+(\d+)\s*,\s*(\d+)(?:[^-]*--(.+))?', body)
            if m:
                if m.group(3):
                    notes.append(strip_formatting(m.group(3)))
                else:
                    notes.append(f"Collect item {m.group(1)} (x{m.group(2)})")
                # .collect often accompanies a quest (.complete); do not override action

        elif body.startswith('.cast'):
            m = re.search(r'>>\s*(.+)', body)
            if m:
                notes.append('Cast ' + strip_formatting(m.group(1)))

        elif body.startswith('.link') or body.startswith('.itemcount') or body.startswith('.itemStat') \
                or body.startswith('.destroy') or body.startswith('.engrave') or body.startswith('.abandon'):
            # Unsupported / no TurtleGuide equivalent
            pass

        elif body.startswith('>>'):
            note = strip_formatting(body[2:])
            if note:
                notes.append(note)

        elif body.startswith('+'):
            note = strip_formatting(body[1:])
            if note:
                notes.append(note)

    # Build note
    note_parts = []
    if target_npc:
        note_parts.append(f"Talk to {target_npc}")
    if mob_name and result['action'] != 'C':
        note_parts.append(f"Kill {mob_name}")
    note_parts.extend(notes)
    if result['coords']:
        note_parts.append(f"({result['coords'][0]})")

    if note_parts:
        result['note'] = ' - '.join(note_parts)

    if use_item:
        result['use_item'] = use_item

    return result


def step_to_turtleguide(step):
    """Convert a parsed step to TurtleGuide format"""
    if not step['action'] or not step['quest']:
        # If we have notes but no action, make it a NOTE
        if step.get('note') and len(step['note']) > 0:
            step['action'] = 'N'
            step['quest'] = step['note']
            step['note'] = None
        else:
            return None

    parts = [step['action'], ' ', step['quest']]

    if step.get('qid'):
        parts.append(f" |QID|{step['qid']}|")

    if step.get('note'):
        parts.append(f" |N|{step['note']}|")

    if step.get('use_item'):
        parts.append(f" |U|{step['use_item']}|")

    if step.get('optional'):
        parts.append(" |O|")

    if step.get('class'):
        parts.append(f" |C|{step['class']}|")

    if step.get('race'):
        parts.append(f" |R|{step['race']}|")

    if step.get('mode'):
        parts.append(f" |M|{step['mode']}|")

    return ''.join(parts)


def convert_rxp_guide(content, namespace="RXP"):
    """Convert RXP guide content to TurtleGuide format. Returns None if the guide is not classic-compatible."""
    lines = content.split('\n')

    # Parse metadata
    guide_name = "Converted Guide"
    next_guide = ""
    faction = "Both"
    levels = None
    guide_has_classic_tag = False
    has_any_era_tag = False
    guide_seasons = None

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        if line.startswith('#displayname'):
            dn = line[len('#displayname'):].strip()
            # Split off `<<` filter and skip if non-vanilla
            dn_body, dn_filter = split_line_filter(dn)
            if filter_is_nonclassic(dn_filter):
                pass
            else:
                # If filter explicitly gates to SoD (`<< sod` / `<< season 2+`), skip;
                # `<< !sod` means "not SoD" → use it in vanilla
                if dn_filter and re.search(r'(?<!!)\bsod\b', dn_filter):
                    pass
                else:
                    dn_body = strip_formatting(dn_body)
                    if dn_body:
                        guide_name = dn_body
                        m = re.search(r'\b(\d{1,2})-(\d{1,2})\b', dn_body)
                        if m:
                            levels = (int(m.group(1)), int(m.group(2)))
        elif line.startswith('#name'):
            candidate = strip_formatting(line[5:].strip())
            # Only use #name if we haven't set a display name yet
            if guide_name == "Converted Guide":
                guide_name = candidate
            # Find a sensible level range (two 1-2 digit numbers within 1..60)
            for m in re.finditer(r'\b(\d{1,2})-(\d{1,2})\b', candidate):
                a, b = int(m.group(1)), int(m.group(2))
                if 1 <= a <= 60 and 1 <= b <= 60 and a <= b:
                    levels = (a, b)
                    break
        elif line.startswith('#next'):
            nxt = strip_formatting(line[5:].strip())
            if ';' in nxt:
                nxt = nxt.split(';')[0].strip()
            next_guide = nxt
        elif line.startswith('#classic') or line.startswith('#era'):
            guide_has_classic_tag = True
            has_any_era_tag = True
        elif re.match(r'^#(tbc|wotlk|cata|mop|wod|legion|bfa|shadowlands|retail|dragonflight|tww)\b', line):
            has_any_era_tag = True
        elif line.startswith('#season'):
            m = re.match(r'#season\s+([0-9,\s]+)', line)
            if m:
                guide_seasons = [int(x) for x in re.findall(r'\d+', m.group(1))]
        elif line.startswith('<<'):
            # Extract any faction/race tokens
            for tok in re.findall(r'!?\w+', line[2:]):
                raw = tok.lstrip('!')
                if raw in FACTIONS:
                    faction = raw
                    break
                elif raw in {'Human', 'Dwarf', 'Gnome', 'NightElf', 'HighElf', 'Draenei'}:
                    faction = 'Alliance'
                    break
                elif raw in {'Orc', 'Troll', 'Tauren', 'Undead', 'BloodElf', 'Goblin'}:
                    faction = 'Horde'
                    break
        elif line.startswith('step'):
            break
        i += 1

    # If any era tag was declared but not #classic, this guide is not for vanilla
    if has_any_era_tag and not guide_has_classic_tag:
        return None
    # If a guide-level #season directive excludes 0 (classic), skip the whole guide
    if guide_seasons and 0 not in guide_seasons:
        return None
    # Skip guides with SoD in their name (Season of Discovery content)
    if re.search(r'\bSoD\b', guide_name):
        return None

    # Parse steps. Each step starts at a line beginning with `step` (optionally `step << filter`).
    steps = []
    current_step_lines = []
    current_step_filter = None
    current_zone = None

    def flush():
        nonlocal current_zone
        if not current_step_lines and current_step_filter is None:
            return
        parsed = parse_step(current_step_lines, current_step_filter, current_zone)
        if parsed is None:
            return
        if parsed.get('zone'):
            current_zone = parsed['zone']
        tg_line = step_to_turtleguide(parsed)
        if tg_line:
            steps.append(tg_line)

    seen_first_step = False
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if re.match(r'^step\b', stripped):
            if seen_first_step:
                flush()
            seen_first_step = True
            current_step_lines = []
            # Capture step-level filter
            m = re.match(r'^step\s*<<\s*(.+?)\s*$', stripped)
            current_step_filter = m.group(1).strip() if m else None
        else:
            current_step_lines.append(line)
        i += 1

    if seen_first_step:
        flush()

    # Create safe filename from guide name
    safe_name = re.sub(r'[^\w\s-]', '', guide_name)
    safe_name = re.sub(r'\s+', '_', safe_name)

    # Clean up guide names (remove double spaces, etc.)
    guide_name = re.sub(r'\s+', ' ', guide_name).strip()
    if next_guide:
        # Strip trailing `<< filter` (class/race/era tags on the #next directive)
        if '<<' in next_guide:
            next_guide = next_guide.split('<<', 1)[0].strip()
        # Strip RXP subgroup prefix like "RestedXP Horde 30-40\30-33 Hillsbrad/Arathi" → "30-33 Hillsbrad/Arathi"
        if '\\' in next_guide:
            next_guide = next_guide.rsplit('\\', 1)[-1].strip()
        next_guide = re.sub(r'\s+', ' ', next_guide).strip()
        # Prefix our namespace only if the value doesn't already look prefixed
        if next_guide and not re.match(r'^[A-Za-z][A-Za-z0-9 ]*/', next_guide):
            next_guide = f"{namespace}/{next_guide}"

    # Build output
    output = []
    output.append("-- Converted from RestedXP format")
    output.append(f"-- Original guide: {guide_name}")
    output.append("")

    level_range = ""
    if levels:
        level_range = f" ({levels[0]}-{levels[1]})"

    def lua_str(s):
        return s.replace('\\', '\\\\').replace('"', '\\"')

    output.append(f'TurtleGuide:RegisterGuide("{lua_str(namespace + "/" + guide_name)}", "{lua_str(next_guide or "")}", "{faction}", function()')
    output.append("")
    output.append("return [[")
    output.append("")
    output.append(f"N {guide_name} |N|Converted from RestedXP guide|")
    output.append("")

    for step in steps:
        output.append(step)

    output.append("")
    output.append("]]")
    output.append("end)")

    return '\n'.join(output), safe_name, faction, levels


def extract_guides_from_file(content):
    """Extract individual guides from a file with multiple RegisterGuide calls"""
    guides = []

    # Try format: RXPGuides.RegisterGuide("name", [[...]])
    pattern1 = r'RXPGuides\.RegisterGuide\s*\(\s*"([^"]+)"\s*,\s*\[\[(.*?)\]\]\s*\)'
    matches = re.findall(pattern1, content, re.DOTALL)

    for name, guide_content in matches:
        guides.append((name, guide_content))

    # Try format: RXPGuides.RegisterGuide([[...]])
    if not matches:
        pattern2 = r'RXPGuides\.RegisterGuide\s*\(\s*\[\[(.*?)\]\]\s*\)'
        matches = re.findall(pattern2, content, re.DOTALL)
        for guide_content in matches:
            # Extract name from #name directive
            name_match = re.search(r'#name\s+(.+)', guide_content)
            name = name_match.group(1).strip() if name_match else "Unknown"
            guides.append((name, guide_content))

    # Fallback: treat whole file as one guide
    if not guides:
        guides.append(("Main", content))

    return guides


def convert_file(input_file, output_dir, namespace="RXP"):
    """Convert a single RXP source file; return list of (guide_name, output_path, faction, levels)."""
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    guides = extract_guides_from_file(content)
    results = []
    for guide_name, guide_content in guides:
        try:
            converted = convert_rxp_guide(guide_content, namespace=namespace)
            if converted is None:
                print(f"  Skipped (not classic): {guide_name}")
                continue
            text, safe_name, faction, levels = converted
            subfolder = os.path.join(output_dir, faction if faction != "Both" else "Both")
            os.makedirs(subfolder, exist_ok=True)
            if levels:
                filename = f"{levels[0]:02d}_{levels[1]:02d}_{safe_name}.lua"
            else:
                filename = f"{safe_name}.lua"
            output_path = os.path.join(subfolder, filename)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(text)
            results.append((guide_name, output_path, faction, levels))
            print(f"  Converted: {guide_name} -> {output_path}")
        except Exception as e:
            print(f"  Error converting {guide_name}: {e}")
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Convert RestedXP guides to TurtleGuide format")
    parser.add_argument("input", help="Input RestedXP guide file, or a directory (use --glob)")
    parser.add_argument("output_dir", nargs="?", default="./Guides/RXP/", help="Output directory (default: ./Guides/RXP/)")
    parser.add_argument("--namespace", default="RXP", help="Guide name prefix (default: RXP)")
    parser.add_argument("--glob", action="store_true", help="Treat input as a directory and convert *.lua inside it")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    all_results = []

    if args.glob:
        import glob as _glob
        pattern = os.path.join(args.input, "*.lua")
        files = sorted(_glob.glob(pattern))
        for fp in files:
            print(f"Processing {fp}")
            all_results.extend(convert_file(fp, args.output_dir, args.namespace))
    else:
        all_results.extend(convert_file(args.input, args.output_dir, args.namespace))

    print(f"\nConversion complete! {len(all_results)} guide(s) written to {args.output_dir}")


if __name__ == "__main__":
    main()
