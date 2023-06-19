import glob
import json
import os
from typing import Optional, Tuple

from dotty_dict import dotty

from tracardi.domain.event import Event, Tags
from tracardi.domain.profile import Profile
from tracardi.service.module_loader import load_callable, import_package
from tracardi.service.storage.driver.storage.driver import event as event_db
from tracardi.service.string_manager import capitalize_event_type_id

_local_dir = os.path.dirname(__file__)
_predefined_event_types = {}


def cache_predefined_event_types():
    path = os.path.join(f"{_local_dir}/setup/events/*.json")
    for file_path in glob.glob(path):
        with open(file_path, "r") as file:
            try:
                content = json.load(file)
                for item in content:
                    _predefined_event_types[item['id']] = item
            except Exception as e:
                raise ValueError(f"Could not decode JSON for file {file_path}. Error: {repr(e)}")


def get_event_type_names():
    if not _predefined_event_types:
        cache_predefined_event_types()

    for _, event_def in _predefined_event_types.items():
        yield event_def['id'], event_def['name']


async def get_event_types(query: str = None, limit: int = 1000):
    pre_defined = list(get_event_type_names())
    pre_defined_ids = [item[0] for item in pre_defined]
    result = await event_db.unique_field_value(query, limit)
    for item in result:
        if item not in pre_defined_ids:
            pre_defined.append((item, capitalize_event_type_id(item)))

    events_types = [{"id": item[0], "name": item[1]} for item in sorted(pre_defined)]
    return {
        "total": len(events_types),
        "result": events_types
    }


def get_default_event_type_mapping(event_type, type) -> Optional[dict]:
    if event_type not in _predefined_event_types:
        cache_predefined_event_types()

    schema = _predefined_event_types.get(event_type, None)
    if schema and type in schema:
        return schema[type]
    return None


def get_default_event_type_schema(event_type) -> Optional[dict]:
    if event_type not in _predefined_event_types:
        cache_predefined_event_types()

    schema = _predefined_event_types.get(event_type, None)
    return schema


def copy_default_event_to_profile(copy_schema, flat_profile: dotty, flat_event: dotty) -> Tuple[dotty, bool]:
    profile_updated_flag = False

    if copy_schema is not None:

        for profile_path, (event_path, operation) in copy_schema.items():  # type: str, tuple(str, str)

            # Skip none existing event properties.
            if event_path in flat_event:
                profile_updated_flag = True
                if operation == 'append':
                    if profile_path not in flat_profile:
                        flat_profile[profile_path] = [flat_event[event_path]]
                    elif isinstance(flat_profile[profile_path], list):
                        flat_profile[profile_path].append(flat_event[event_path])
                    elif not isinstance(flat_profile[profile_path], dict):
                        # data in profile exists but is not dict, list. It can be a string ot int.
                        flat_profile[profile_path] = [flat_profile[profile_path]]
                        flat_profile[profile_path].append(flat_event[event_path])
                    else:
                        raise KeyError(
                            f"Can not append data {flat_event[event_path]} to {flat_profile[profile_path]} at profile@{profile_path}")

                elif operation == 'equals_if_not_exists':
                    if profile_path not in flat_profile:
                        flat_profile[profile_path] = flat_event[event_path]
                elif operation == 'delete':
                    if profile_path in flat_profile:
                        flat_profile[profile_path] = None
                else:
                    flat_profile[profile_path] = flat_event[event_path]

    return flat_profile, profile_updated_flag


def remove_empty_dicts(dictionary):
    keys_to_remove = []
    for key, value in dictionary.items():
        if isinstance(value, dict):
            remove_empty_dicts(value)  # Recursively check nested dictionaries
            if not value:  # Empty dictionary after recursive check
                keys_to_remove.append(key)
    for key in keys_to_remove:
        del dictionary[key]


def auto_index_default_event_type(event: Event, profile: Profile) -> Event:
    index_schema = get_default_event_type_mapping(event.type, 'copy')

    if index_schema is not None:

        dot_event = dotty(event.dict())

        for destination, source in index_schema.items():  # type: str, str
            try:
                # Skip none existing event properties.
                if source in dot_event:
                    dot_event[destination] = dot_event[source]
                    del dot_event[source]
            except KeyError:
                pass

        event_dict = dot_event.to_dict()
        remove_empty_dicts(event_dict)
        event = Event(**event_dict)

        state = get_default_event_type_mapping(event.type, 'state')

        if state:
            if isinstance(state, str):
                if state.startswith("call:"):
                    state = state[5:]
                    module, function = state.split(',')
                    module = import_package(module)
                    state_function = load_callable(module, function)

                    event.journey.state = state_function(event, profile)
                else:
                    event.journey.state = state


        tags = get_default_event_type_mapping(event.type, 'tags')
        if tags:
            event.tags = Tags(values=tuple(tags), count=len(tags))

    return event
