"""Expand reusable encounter data into the ordinary level event and query contract."""


def expand_encounter(source, error):
    encounter = source.pop("encounter")
    entities = source["entities"]
    events = source["events"]
    queries = source["queries"]
    sections = source.setdefault("sections", {})
    origin = {}
    births = {}
    projectiles = set()
    hz = source["tick_hz"]
    deadline = source["duration_ms"] * hz // 1000

    def tick(ms):
        return (ms * hz + 999) // 1000

    def insert(table, key, value, pointer):
        if key in table:
            raise error(f"{pointer}: generated ID already exists: {key}")
        table[key] = value

    def add_event(event_id, pointer, trigger, actions, guards=(), limit=1):
        names = [f"a{i}" for i in range(len(actions))]
        insert(events, event_id, {
            "trigger": trigger, "actions": dict(zip(names, actions)), "order": names,
            "guards": list(guards), "max_firings": limit, "priority": 0,
        }, pointer)
        origin[event_id] = pointer

    def active(entity):
        return {"entity": entity, "field": "active", "compare": "eq", "value": True}

    def age_query(entity, pointer):
        name = entity + ".age"
        insert(queries, name, {
            "op": "entity_age_ms", "entity": entity, "space": "scalar",
            "algorithm": "entity-clock60-v1",
        }, pointer)
        return name

    def at_age(query, ms):
        return {"query": query, "compare": "gte", "value": ms}

    def vfx(effect, entity):
        return {"op": "vfx", "effect": effect, "entity": entity}

    def add_phase(entity, name, begin, end, style, pointer):
        phases = entities[entity].setdefault("phases", [])
        if any(p["id"] == name or (begin < p["end_ms"] and p["start_ms"] < end) for p in phases):
            raise error(f"{pointer}: overlaps an authored phase on {entity}")
        phases.append({
            "id": name, "start_ms": begin, "end_ms": end,
            **{key: style[key] for key in ("color", "label") if key in style},
        })

    # Keep generated lifetimes single-owner so local attack events fire once per actor.
    action_lists = [event["actions"].values() for event in events.values()]
    action_lists.extend(attack.get("projectile", {}).get("on_intercept", [])
                        for attack in encounter.get("attacks", {}).values())
    manually_spawned = {
        action["entity"]
        for actions in action_lists for action in actions
        if action["op"] in ("spawn", "launch")
        or (action["op"] == "set" and action["field"] == "active" and action["value"])
    }

    def require_inactive(entity, template, pointer):
        definition = entities.get(entity)
        if definition is None or definition["template"] != template:
            raise error(f"{pointer}: expected a {template} entity: {entity}")
        if definition.get("properties", {}).get("active") or entity in manually_spawned:
            raise error(f"{pointer}: entity must start inactive and have a single spawn owner: {entity}")

    indices = {section["index"] for section in sections.values()}
    if not encounter["waves"]:
        raise error("/encounter/waves: at least one wave is required")
    for wave_id, wave in encounter["waves"].items():
        pointer = f"/encounter/waves/{wave_id}"
        if wave["index"] in indices:
            raise error(f"{pointer}: duplicate wave index")
        indices.add(wave["index"])
        spawns = sorted(wave["spawns"], key=lambda name: (wave["spawns"][name], name))
        if not spawns:
            raise error(f"{pointer}: wave must spawn at least one target")
        section = {"index": wave["index"], "title": wave["title"], "targets": spawns}
        if "hint" in wave:
            section["hint"] = wave["hint"]
        insert(sections, wave_id, section, pointer)
        add_event(wave_id + ".begin", pointer + "/at_ms", {"at_ms": wave["at_ms"]},
                  [{"op": "section", "section": wave_id}])
        for actor in spawns:
            spawn_pointer = f"{pointer}/spawns/{actor}"
            require_inactive(actor, "target", spawn_pointer)
            if actor in births:
                raise error(f"{spawn_pointer}: target already belongs to a wave")
            births[actor] = wave["at_ms"] + wave["spawns"][actor]
            if tick(births[actor]) >= deadline:
                raise error(f"{spawn_pointer}: target has no active time before the level deadline")
            add_event(actor + ".spawn", spawn_pointer, {"at_ms": births[actor]},
                      [{"op": "spawn", "entity": actor}])

    for actor, attack in encounter.get("attacks", {}).items():
        pointer = f"/encounter/attacks/{actor}"
        if actor not in births:
            raise error(f"{pointer}: attacker must belong to a wave")
        windup = attack["windup"]
        release = attack["release_ms"]
        retire = attack["retire_ms"]
        projectile = attack.get("projectile")
        contact = attack.get("contact_ms")
        if projectile and contact is not None:
            raise error(f"{pointer}: projectile attacks use flight_ms instead of contact_ms")
        if not projectile and (contact is None or tick(contact) <= tick(release)):
            raise error(f"{pointer}: melee contact must follow release by at least one tick")
        impact = release if projectile else contact
        if tick(windup["at_ms"]) >= tick(release) or tick(impact) >= tick(retire):
            raise error(f"{pointer}: windup, release and retirement need ordered tick windows")
        last_tick = tick(births[actor]) + max(
            tick(retire), tick(release) + tick(projectile["flight_ms"]) if projectile else 0,
        )
        if last_tick >= deadline:
            raise error(f"{pointer}: unstunned attack must finish before the level deadline")

        anchors = {"windup": windup["at_ms"], "release": release, "retire": retire}
        if not projectile:
            anchors["contact"] = contact
        for frame in entities[actor].get("motion", {}).get("frames", []):
            if "attack_time" not in frame:
                continue
            marker = frame.pop("attack_time")
            if marker not in anchors:
                raise error(f"{pointer}: motion refers to an unavailable attack time: {marker}")
            frame["at_ms"] = anchors[marker] + frame.pop("offset_ms", 0)

        actor_age = age_query(actor, pointer)
        add_phase(actor, "windup", windup["at_ms"], impact, windup, pointer)
        add_event(actor + ".warning", pointer + "/windup", at_age(actor_age, windup["at_ms"]),
                  [{"op": "emit", "event": "attack.warning"}], [active(actor)])
        damage = attack["damage"]
        damage_actions = [{"op": "resource_add", "resource": damage["resource"], "amount": -damage["amount"]}]
        if "effect" in damage:
            damage_actions.append(vfx(damage["effect"], actor))
        damage_actions.append({"op": "emit", "event": damage["topic"]})
        release_actions = []
        if "release_effect" in attack:
            release_actions.append(vfx(attack["release_effect"], actor))

        if projectile:
            bolt = projectile["entity"]
            require_inactive(bolt, "projectile", pointer + "/projectile")
            if bolt in projectiles:
                raise error(f"{pointer}/projectile: projectile already belongs to an attack")
            projectiles.add(bolt)
            flight = projectile["flight_ms"]
            if "color" in projectile or "label" in projectile:
                add_phase(bolt, "in_flight", 0, flight, projectile, pointer + "/projectile")
            release_actions.append({
                "op": "launch", "entity": bolt, "source": actor, "x": projectile["x"],
                "y": projectile["y"], "duration_ms": flight,
            })
            add_event(actor + ".attack", pointer + "/release_ms", at_age(actor_age, release),
                      release_actions, [active(actor)])
            bolt_age = age_query(bolt, pointer + "/projectile")
            add_event(bolt + ".impact", pointer + "/projectile/flight_ms", at_age(bolt_age, flight),
                      damage_actions + [{"op": "remove", "entity": bolt}], [active(bolt)])
            if "on_intercept" in projectile:
                add_event(bolt + ".intercept", pointer + "/projectile/on_intercept",
                          {"on": "target.neutralized:" + bolt}, projectile["on_intercept"])
        else:
            release_actions.append({"op": "emit", "event": "attack.launched"})
            add_event(actor + ".release", pointer + "/release_ms", at_age(actor_age, release),
                      release_actions, [active(actor)])
            add_event(actor + ".attack", pointer + "/contact_ms", at_age(actor_age, contact),
                      damage_actions, [active(actor)])
        add_event(actor + ".leave", pointer + "/retire_ms", at_age(actor_age, retire),
                  [{"op": "remove", "entity": actor}], [active(actor)])

    for support_id, support in encounter.get("supports", {}).items():
        pointer = f"/encounter/supports/{support_id}"
        emitter = support["source"]
        if entities.get(emitter, {}).get("template") != "activation_source":
            raise error(f"{pointer}: expected an activation source: {emitter}")
        if "region" in support and min(support["region"][2:]) <= 0:
            raise error(f"{pointer}: support region must have positive dimensions")
        for target in support["targets"]:
            if target not in births:
                raise error(f"{pointer}: support target must belong to a wave: {target}")
            event_id = f"{target}.{support_id}"
            distance = event_id + "_range"
            insert(queries, distance, {
                "op": "distance", "entity": target, "other": emitter,
                "space": "content_px", "algorithm": "cpu-nearest-v1",
            }, pointer)
            guards = [active(target), {"query": distance, "compare": "lte", "value": support["range_px"]}]
            if "region" in support:
                region = event_id + "_region"
                insert(queries, region, {
                    "op": "region_contains", "entity": target, "region": support["region"],
                    "space": "content_px", "algorithm": "cpu-nearest-v1",
                }, pointer)
                guards.append({"query": region, "compare": "gte", "value": 1})
            actions = [{"op": "stun", "entity": target, "duration_ms": support["duration_ms"]}]
            if "effect" in support:
                actions.append({**vfx(support["effect"], target), "source": emitter})
            add_event(event_id, pointer, {"on": "interaction.activated:" + emitter},
                      actions, guards, support["max_firings"])
    return origin
