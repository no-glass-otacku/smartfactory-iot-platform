import pandas as pd
import json
import time
import os
import random
from azure.iot.device import IoTHubDeviceClient, Message
from dotenv import load_dotenv

load_dotenv()

CONNECTION_STRING = os.getenv("CONNECTION_STRING")
CSV_PATH = os.getenv("CSV_PATH")
SPEED_FACTOR = int(os.getenv("SPEED_FACTOR", 15))
NOISE_SEED = int(os.getenv("NOISE_SEED", 42))

random.seed(NOISE_SEED)

NOISE_FIELDS = {
    "temperature": (-999, 9999),
    "vibration": (-999, 9999),
    "humidity": (-999, 9999),
    "pressure": (-999, 9999),
    "energy_consumption": (-999, 9999),
    "machine_id": None,
    "timestamp": None,
}

def inject_noise(payload):
    if random.random() < 0.05:
        field = random.choice(list(NOISE_FIELDS.keys()))
        if NOISE_FIELDS[field] is None:
            payload[field] = None
        else:
            payload[field] = random.choice(NOISE_FIELDS[field])
        print(f"  [오염값 주입] {field} = {payload[field]}")
    return payload

def main():
    df = pd.read_csv(CSV_PATH)
    df = df.sort_values('timestamp').reset_index(drop=True)
    df = df.head(40)  # 가장 최근 40건만
    df = df.reset_index(drop=True)

    client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING)
    client.connect()
    print(f"IoT Hub 연결 성공! 전송 시작: 총 {len(df)}건")

    try:
        for i, row in df.iterrows():
            payload = {
                "machine_id": int(row['machine_id']),
                "timestamp": str(row['timestamp']),
                "temperature": float(row['temperature']),
                "vibration": float(row['vibration']),
                "humidity": float(row['humidity']),
                "pressure": float(row['pressure']),
                "energy_consumption": float(row['energy_consumption']),
                "machine_status": int(row['machine_status']),
                "predicted_remaining_life": float(row['predicted_remaining_life']),
                "failure_type": str(row['failure_type'])
            }

            payload = inject_noise(payload)

            message = Message(json.dumps(payload))
            message.content_encoding = "utf-8"
            message.content_type = "application/json"

            client.send_message(message)
            print(f"[{i+1}/{len(df)}] ✅ machine_id={payload['machine_id']} timestamp={payload['timestamp']}")

            time.sleep(60 / SPEED_FACTOR)

    except KeyboardInterrupt:
        print("\n전송 중단됨")
    finally:
        client.disconnect()
        print("IoT Hub 연결 종료")

if __name__ == "__main__":
    main()