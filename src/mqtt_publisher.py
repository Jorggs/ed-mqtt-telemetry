"""
Thin wrapper around paho-mqtt that reproduces the connection behaviour of
EDMC-Telemetry: a retained Last-Will-and-Testament on <root>/FeedActive that
publishes "False" on any unclean disconnect, and "True" (retained) once
connected.
"""

import json
import ssl
import threading

import paho.mqtt.client as mqtt


class MQTTPublisher:
    def __init__(self, settings, on_status=None, on_log=None):
        self.settings = settings
        self.on_status = on_status or (lambda connected: None)
        self.on_log = on_log or (lambda msg: None)
        self.client = None
        self.connected = False
        self._lock = threading.Lock()

    # ---- topic helpers -------------------------------------------------

    def _maybe_lower(self, topic):
        return topic.lower() if self.settings.get("lowercase_topics") else topic

    def topic_for(self, *parts):
        """Build a topic string: root + given path segments."""
        root = self.settings["topics"]["root"]
        topic = "/".join([root] + [p for p in parts if p is not None])
        return self._maybe_lower(topic)

    def feedactive_topic(self):
        return self.topic_for(self.settings["topics"]["feedactive"])

    # ---- lifecycle -------------------------------------------------------

    def start(self):
        s = self.settings
        client_id = s.get("client_id") or "EDMCTelemetryPlugin"
        try:
            # paho-mqtt >= 2.0 requires an explicit callback API version
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION1, client_id=client_id, clean_session=True
            )
        except AttributeError:
            # paho-mqtt < 2.0
            self.client = mqtt.Client(client_id=client_id, clean_session=True)

        if s.get("username"):
            self.client.username_pw_set(s.get("username"), s.get("password") or None)

        if s.get("encryption"):
            ca = s.get("ca_certs") or None
            cert = s.get("certfile") or None
            key = s.get("keyfile") or None
            self.client.tls_set(
                ca_certs=ca,
                certfile=cert,
                keyfile=key,
                cert_reqs=ssl.CERT_NONE if s.get("tls_insecure") else ssl.CERT_REQUIRED,
            )
            if s.get("tls_insecure"):
                self.client.tls_insecure_set(True)

        self.client.will_set(
            self.feedactive_topic(), payload="False", qos=s.get("qos", 0), retain=True
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        self.on_log(f"Connecting to {s.get('broker')}:{s.get('port')} ...")
        self.client.connect_async(
            s.get("broker", "127.0.0.1"), int(s.get("port", 1883)), int(s.get("keepalive", 60))
        )
        self.client.loop_start()

    def stop(self):
        if self.client:
            try:
                self.publish_raw(self.feedactive_topic(), "False", retain=True)
            except Exception:
                pass
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
        self.connected = False

    def _on_connect(self, client, userdata, flags, rc, *args):
        self.connected = rc == 0
        if self.connected:
            self.on_log("Connected to MQTT broker.")
            self.publish_raw(self.feedactive_topic(), "True", retain=True)
        else:
            self.on_log(f"MQTT connection failed (rc={rc}).")
        self.on_status(self.connected)

    def _on_disconnect(self, client, userdata, rc, *args):
        self.connected = False
        self.on_log("Disconnected from MQTT broker.")
        self.on_status(False)

    # ---- publishing ------------------------------------------------------

    def publish_raw(self, topic, payload, retain=False, qos=None):
        if not self.client:
            return
        q = self.settings.get("qos", 0) if qos is None else qos
        try:
            self.client.publish(topic, payload=payload, qos=q, retain=retain)
        except Exception as e:
            self.on_log(f"Publish error on {topic}: {e}")

    def publish(self, parts, value, retain=False):
        """Publish a value under root + parts. dict/list values are JSON-encoded,
        everything else is stringified (matching the plugin's plain-text style
        for scalar dashboard values)."""
        topic = self.topic_for(*parts)
        if isinstance(value, (dict, list)):
            payload = json.dumps(value)
        elif isinstance(value, bool):
            payload = "True" if value else "False"
        else:
            payload = str(value)
        self.publish_raw(topic, payload, retain=retain)
