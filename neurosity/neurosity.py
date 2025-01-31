import pyrebase
import atexit
from config import PyRebase

class neurosity_sdk:
    def __init__(self, options):
        if ("device_id" not in options):
            raise ValueError("Neurosity SDK: A device ID is required to use the SDK")

        options.setdefault("environment", "production")
        self.options = options
        pyrebase_config = PyRebase.STAGING if options["environment"] == "staging" else PyRebase.PRODUCTION
        self.firebase = pyrebase.initialize_app(pyrebase_config)
        self.auth = self.firebase.auth()
        self.db = self.firebase.database()
        self.subscription_ids = []
        atexit.register(self.exit_handler)

    def exit_handler(self):
        self.remove_client()
        self.remove_all_subscriptions()

    def get_server_timestamp(self):
        return {".sv": "timestamp"}

    def login(self, credentials):
        if (hasattr(self, "user") and hasattr(self, "token")):
            print("Neurosity SDK: The SDK is already authenticated.")
            return

        self.user = self.auth.sign_in_with_email_and_password(
            credentials["email"], credentials["password"])
        self.token = self.user['idToken']

        if (not hasattr(self, "client_id")):
            self.add_client()

    def add_client(self):
        device_id = self.options["device_id"]
        clients_path = f"devices/{device_id}/clients"
        timestamp = self.get_server_timestamp()
        push_result = self.db.child(clients_path).push(timestamp, self.token)
        self.client_id = push_result["name"]

    def remove_client(self):
        client_id = self.client_id
        if(client_id):
            device_id = self.options["device_id"]
            client_path = f"devices/{device_id}/clients/{client_id}"
            self.db.child(client_path).remove(self.token)

    # @TODO: handle resnponse
    def add_action(self, action, callback=None):
        if ("command" not in action):
            raise ValueError("A command is required for actions")

        if ("action" not in action):
            raise ValueError("An action is required for actions")

        if ("message" not in action):
            action.setDefault("message", None)


        device_id = self.options["device_id"]
        actions_path = f"devices/{device_id}/actions"

        push_result = self.db.child(actions_path).push(action, self.token)

        if "responseRequired" in action:
            if action["responseRequired"]:
                response_timeout = action["responseTimeout"] or 600000
                path = actions_path + "/" + push_result["name"] + "/response"

                print("path: " + str(path))
                response = self.get_from_path(path)
                print("response: " + str(response))
            return response

        return ""

    def add_subscription(self, metric, label, atomic):
        client_id = self.client_id
        device_id = self.options["device_id"]
        subscription_id = self.db.generate_key()
        subscription_path = f"devices/{device_id}/subscriptions/{subscription_id}"

        subscription_payload = {
            "atomic": atomic,
            "clientId": client_id,
            "id": subscription_id,
            "labels": [label],
            "metric": metric,
            "serverType": "firebase",
        }

        self.db.child(subscription_path).set(
            subscription_payload, self.token)

        # caching subscription ids locally for unsubscribe teardown on exit
        self.subscription_ids.append(subscription_id)

        return subscription_id

    def remove_subscription(self, subscription_id):
        device_id = self.options["device_id"]
        subscription_path = f"devices/{device_id}/subscriptions/{subscription_id}"
        self.db.child(subscription_path).remove(self.token)

    def remove_all_subscriptions(self):
        device_id = self.options["device_id"]
        subscriptions_path = f"devices/{device_id}/subscriptions"
        data = {}

        for subscription_id in self.subscription_ids:
            data[subscription_id] = None

        self.db.child(subscriptions_path).update(data, self.token)

    def stream_metric(self, callback, metric, label, atomic):
        subscription_id = self.add_subscription(metric, label, atomic)

        if (atomic):
            metric_path = f"metrics/{metric}"
        else:
            metric_path = f"metrics/{metric}/{label}"

        def teardown(subscription_id):
            self.remove_subscription(subscription_id)
            self.subscription_ids.remove(subscription_id)

        return self.stream_from_path(callback, metric_path, teardown, subscription_id)

    def stream_from_path(self, callback, path_name, teardown=None, subscription_id=None):
        device_id = self.options["device_id"]

        path = f"devices/{device_id}/{path_name}"
        stream_id = subscription_id or self.db.generate_key()

        initial_message = {}

        def stream_handler(message):
            if (message["path"] == "/"):
                initial_message[message["stream_id"]] = message
                full_payload = message["data"]
            else:
                child = message["path"][1:]
                full_payload = initial_message[message["stream_id"]]["data"]
                if (message["data"] == None):
                    # delete key is value is `None`
                    full_payload.pop(child, None)
                else:
                    full_payload[child] = message["data"]

            callback(full_payload)

        stream = self.db.child(path).stream(
            stream_handler, self.token, stream_id=stream_id)

        def unsubscribe():
            if (teardown):
                teardown(stream_id)
            stream.close()

        return unsubscribe

    def get_from_path(self, path_name):
        device_id = self.options["device_id"]
        path = f"devices/{device_id}/{path_name}"
        snapshot = self.db.child(path).get(self.token)
        return snapshot.val()

    def add_marker(self, label):
        if (not label):
            raise ValueError("A label is required for markers")

        return self.add_action({
            "command": "marker",
            "action": "add",
            "message": {
                "label": label,
                "timestamp": self.get_server_timestamp()
            }
        })

    def get_timesync(self):

        def callback(data):
            print("callback data: " + str(data))

        return self.add_action({
            "command": "timesync",
            "action": "get",
            "responseRequired": True,
            "responseTimeout": 250,
            "message": {}
        }, callback=callback)


    def brainwaves_raw(self, callback):
        return self.stream_metric(callback, "brainwaves", "raw", False)

    def brainwaves_raw_unfiltered(self, callback):
        return self.stream_metric(callback, "brainwaves", "rawUnfiltered", False)

    def brainwaves_psd(self, callback):
        return self.stream_metric(callback, "brainwaves", "psd", False)

    def brainwaves_power_by_band(self, callback):
        return self.stream_metric(callback, "brainwaves", "powerByBand", False)

    def signal_quality(self, callback):
        return self.stream_metric(callback, "signalQuality", None, True)

    def accelerometer(self, callback):
        return self.stream_metric(callback, "accelerometer", None, True)

    def calm(self, callback):
        return self.stream_metric(callback, "awareness", "calm", False)

    def focus(self, callback):
        return self.stream_metric(callback, "awareness", "focus", False)

    def kinesis(self, label, callback):
        return self.stream_metric(callback, "kinesis", label, False)

    def kinesis_predictions(self, label, callback):
        return self.stream_metric(callback, "predictions", label, False)

    def status(self, callback):
        return self.stream_from_path(callback, "status")

    def settings(self, callback):
        return self.stream_from_path(callback, "settings")

    def status_once(self):
        return self.get_from_path("status")

    def settings_once(self):
        return self.get_from_path("settings")

    def get_info(self):
        return self.get_from_path("info")
