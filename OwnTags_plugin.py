# This script takes OpenHaystack location reports and publishes them over MQTT 
# as OwnTracks location reports.
# TODO: implement checks so that messages are published to topics as described in `secrets.py`

import json
import time
import datetime
import paho.mqtt.publish as publish
from output.mysecrets import owntag_options
from output.mysecrets import mqtt_secrets


def owntags(ordered, time_window, found_keys):
    """This function processess the location reports from request_reports.py
    and outputs them as OwnTracks MQTT reports.
    """

    check_time = datetime.datetime.now().replace(microsecond=0).isoformat()
    # Pull settings from secrets.py
    # MQTT Options
    broker_address = mqtt_secrets["mqtt_broker"]
    broker_port = mqtt_secrets["mqtt_port"]
    broker_user = mqtt_secrets["mqtt_user"]
    broker_pass = mqtt_secrets["mqtt_pass"]
    broker_tls = mqtt_secrets["mqtt_tls"]

    # OwnTag Options
    print_history = owntag_options["print_history"]
    owntracks_device = owntag_options["owntracks_device"]
    haystack_base = owntag_options["owntags_base"]
    status_msg = owntag_options["status_msg"]
    status_base = owntag_options["status_base"]
    if not status_msg:
        status_base = "Status messages turned off"

    # Catching errors. What to do if no reports are found.
    if len(ordered) == 0:
        ordered = "No reports."
        if status_msg:
            no_reports = {"reports": 0, "check_time": check_time}
            publish.single(
                status_base,
                payload=f"{json.dumps(no_reports, separators=(',', ':'))}",
                qos=0, retain=True, hostname=broker_address,
                port=broker_port, client_id="the_script", keepalive=60, will=None,
                auth={'username': broker_user, 'password': broker_pass}, tls=broker_tls,
                transport="tcp")
        return ordered

    """Main script"""
    output_message = []
    report_update = []
    for key in found_keys:
        # setup MQTT topics
        waypoint_topic = f"{owntracks_device}/cmd"
        location_topic = f"{haystack_base}/{key}"
        status_topic = f"{status_base}/{key}"
        if not status_msg:
            status_topic = status_base

        # sort reports
        key_list = []
        for item in range(len(ordered)):
            if ordered[item]["key"] == key:
                key_list.append(ordered[item])

        # identify most recent report
        last_report_num = len(key_list) - 1

        # convenience variables
        latitude = key_list[last_report_num]["lat"]
        longitude = key_list[last_report_num]["lon"]
        confidence = key_list[last_report_num]["conf"]  # is this feet, signal strength or something else?
        meters = round(confidence * .3048)  # feet to meters seems reasonable
        timestamp = key_list[last_report_num]["timestamp"]
        prefix = key_list[last_report_num]["key"]

        # TODO waypoint timestamps
        try:
            creation_stamp = owntag_options[prefix]["tst"]
        except KeyError as e:
            unknown_key = f'Used 1000000000 as creation_stamp for {prefix}\n{e}'
            print(unknown_key)
            creation_stamp = 1000000000
        # print(f"Creation Stamp: {creation_stamp}")

        if owntag_options[prefix]["location"]:
            location_msg = {
                # object that updates device location
                # construct MQTT message
                "_type": "location",
                "lat": latitude,
                "lon": longitude,
                "tst": timestamp,
                "acc": confidence,
            }
            # print(json.dumps(location_msg, separators=(',', ':')))

            location_payload = {
                # object that re-publishes (updates) a waypoint location
                # construct MQTT payload
                "topic": location_topic,
                "payload": f"{json.dumps(location_msg, separators=(',', ':'))}",
                "qos": 0, "retain": True
            }
            report_update.append(location_payload)

        if owntag_options[prefix]["waypoint"]:
            waypoint_msg = {
                # object that re-publishes (updates) a waypoint location
                # construct MQTT message
                "_type": "cmd",
                "action": "setWaypoints",
                "waypoints": {
                    "_type": "waypoints",
                    "waypoints": [{
                        "_type": "waypoint",
                        "desc": prefix,
                        "tst": creation_stamp,  # this is where
                        "lat": latitude,
                        "lon": longitude,
                        "rad": meters,
                    }]
                }
            }

            waypoint_payload = {
                # construct MQTT payload
                "topic": waypoint_topic,
                "payload": f"{json.dumps(waypoint_msg, separators=(',', ':'))}",
                "qos": 0, "retain": True
            }
            report_update.append(waypoint_payload)

        latest_report_metadata = {
            # optional metadaa object for debugging/verification
            # construct MQTT payload
            "key": key,
            "creation_stamp": creation_stamp,
            "status_topic": status_topic,
            "check_time": check_time,
            "report_minutes": round(time_window/60,2),
            "reports_count": len(key_list),
            "last_report": key_list  # (this is actually the list of locations)
        }

        if status_msg:  # TODO or if owntag_options[key]["status"]
            last_report_payload = {
                # construct MQTT message
                "topic": status_topic,
                "payload": f'{json.dumps(latest_report_metadata, separators=(",", ":"))}',
                "qos": 0, "retain": True
            }
            report_update.append(last_report_payload)

        # TODO: if status_msg:  # a KPI message sent to the status_topic base
        # meta_report = {
        #     "check_time": check_time,
        #     "report_minutes": time_window,
        #     "reports_count": len(ordered),
        #     "all_tags" = prefixes,
        #     "found_tags" = found,
        #     "missing_tags" = missing,
        # }
        # meta_payload = {
        #     # construct MQTT payload
        #     "topic": waypoint_topic,
        #     "payload": f"{json.dumps(meta_report, separators=(',', ':'))}",
        #     "qos": 0, "retain": True
        #  }
        # report_update.append(meta_payload)

        # Trim report list to print_history number before creating output_message
        # print_history = owntag_options["print_history"]
        if print_history > last_report_num+1 or print_history < 0:
            print_history = last_report_num+1
        reports_num = (last_report_num+1) - print_history

        del latest_report_metadata["last_report"][0:reports_num]
        output_message.append(latest_report_metadata)
    
    publish.multiple(
        # Publish messages to MQTT broker
        report_update, hostname=broker_address,
        port=broker_port, client_id="the_script", keepalive=60,
        auth={'username': broker_user, 'password': broker_pass}, tls=broker_tls,
    )
    
    update_send = {"update_send": time.monotonic()}
    print(f"{len(report_update)} messages sent!\n\
        update send: {update_send}")
    output_message.append(update_send)

    if print_history == 0:
        output_message = None

    return output_message
